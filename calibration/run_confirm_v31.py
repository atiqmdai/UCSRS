"""UCSRS v3.1 CONFIRMATORY registry run.

Why this run exists
-------------------
The 30,000,000-patient run of 19 September (run_final.log, out_final/) solved and
validated calibration_shift = 0.438507 against a Layer 1 floor of 0.30%. The floor was
then raised to 0.40% by investigator ruling, and the shift was re-solved to 0.433039 at
PILOT scale only. The shipped v3.1 configuration had therefore never itself been run at
registry scale. This run closes that gap: it scores the engine exactly as shipped.

Stage A is not repeated. The thirteen severity dials are solved against EuroSCORE II
alone, and EuroSCORE II did not change between v3.0 and v3.1, so out/dials.json is
carried forward unchanged and is reused verbatim.

A parity gate runs before any scoring: the worker engine must be byte-identical to the
shipped /home/claude/UCSRS/ucsrs_engine.py, and the wrapper's scoring path must agree
with the engine's own score_row() on a sample of rows. This gate exists because the
19 September candidate wrapper was built by swapping an import line and silently kept
calling a superseded MELD function, which voided two runs.

NO SIMULATED PATIENT IS ASSIGNED AN OUTCOME AT ANY STAGE.
"""
import sys, json, time, os, hashlib
import numpy as np
from multiprocessing import Pool

sys.path.insert(0, "/home/claude/UCSRS")
sys.path.insert(0, "/home/claude/registries")

import candidate_engine as E
from anchors import table
from score_cand import run_block, merge, _score_row, NBINS

OUT = "/home/claude/registries/out_v31"
os.makedirs(OUT, exist_ok=True)

WORKERS = 2
CHUNK = 60_000
SHIPPED_SHIFT = 0.433039
PRIOR_SHIFT = 0.438507      # the floor-0.30 solve, carried for comparison only
TOTAL_N = 30_000_000
HOLDOUT_N = 2_600_000

REG = table()


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


# ------------------------------------------------------------------ parity gate
def parity_gate():
    shipped = "/home/claude/UCSRS/ucsrs_engine.py"
    worker = "/home/claude/registries/candidate_engine.py"
    a, b = _sha(shipped), _sha(worker)
    log(f"GATE 1  engine sha  shipped {a}  worker {b}")
    assert a == b, "worker engine is not byte-identical to the shipped engine"

    assert E.SPEC_VERSION == "3.1.0", E.SPEC_VERSION
    assert abs(E.BASELINE_A2["calibration_shift"] - SHIPPED_SHIFT) < 1e-9
    log(f"GATE 2  SPEC_VERSION {E.SPEC_VERSION}  shift {E.BASELINE_A2['calibration_shift']}")

    # GATE 3 -- the wrapper's path must agree with the engine's own score_row().
    from cohort import Cohort, rows
    bad = 0
    for i, r in enumerate(rows(Cohort(4242).draw(400, 0.0))):
        u, e, base = _score_row(r, SHIPPED_SHIFT)
        ref = E.score_row(r)
        if abs(u - ref["ucsrs"]) > 1e-9 or abs(e - ref["euroscore2_computed_pct"]) > 1e-9:
            bad += 1
            if bad <= 3:
                log(f"   MISMATCH row {i}: wrapper {u:.6f}/{e:.6f} vs score_row "
                    f"{ref['ucsrs']:.6f}/{ref['euroscore2_computed_pct']:.6f}")
    assert bad == 0, f"{bad}/400 rows disagree with score_row()"
    log("GATE 3  wrapper path == engine score_row() on 400/400 rows")


# ------------------------------------------------------------------ scoring
def _chunks(n, size):
    out = []
    while n > 0:
        c = min(size, n)
        out.append(c)
        n -= c
    return out


def score_cohort(pool, seed, dial, n, shifts):
    jobs = [(seed + 1_000 * i, dial, c, shifts) for i, c in enumerate(_chunks(n, CHUNK))]
    acc = None
    for b in pool.imap_unordered(run_block, jobs):
        acc = merge(acc, b)
    return acc


def summarize(acc, r, shifts):
    n = acc["n"]
    mean_e = acc["sum_e"] / n
    obs = r["observed_mortality_pct"]
    out = {"name": r["name"], "n": n, "mean_esii": mean_e,
           "oe_esii_realised": obs / mean_e,
           "oe_esii_published": r["oe_esii_published"],
           "target_mean_esii": r["target_mean_esii_pct"], "shifts": {}}
    for j, sh in enumerate(shifts):
        mean_u = acc["sum_u"][j] / n
        out["shifts"][f"{sh:.6f}"] = {
            "mean_ucsrs": mean_u,
            "oe_ucsrs": obs / mean_u,
            "geo_mean_ucsrs": float(np.exp(acc["sum_log_u"][j] / n)),
            "cap_hit_pct": 100.0 * acc["cap_hits"][j] / n,
            "baseline_clamp_pct": 100.0 * acc["br_clamp"][j] / n,
        }
    return out


def metrics(rows_, key):
    oes = np.array([x["shifts"][key]["oe_ucsrs"] for x in rows_])
    return {"median_oe": float(np.median(oes)),
            "mean_abs_log_oe": float(np.mean(np.abs(np.log(oes)))),
            "in_band_0p80_1p25": int(((oes >= 0.80) & (oes <= 1.25)).sum()),
            "n_registries": len(oes)}


def stage(pool, tag, total_n, dials, seed_off, shifts):
    per = total_n // len(REG)
    log(f"{tag} - {total_n:,} patients, {per:,} per registry, shifts {shifts}")
    res = []
    for i, (r, d) in enumerate(zip(REG, dials)):
        t0 = time.time()
        acc = score_cohort(pool, seed_off + 7919 * i, d["dial"], per, shifts)
        s = summarize(acc, r, shifts)
        res.append(s)
        k = f"{shifts[0]:.6f}"
        log(f"  {r['name']:<17} n {s['n']:>9,}  ESII {s['mean_esii']:6.3f}% "
            f"(O/E {s['oe_esii_realised']:.2f} vs published {s['oe_esii_published']:.2f})  "
            f"UCSRS {s['shifts'][k]['mean_ucsrs']:6.3f}%  O/E {s['shifts'][k]['oe_ucsrs']:.3f}  "
            f"({time.time()-t0:.0f}s)")
    doc = {"tag": tag, "total_n": total_n, "per_registry": per,
           "shifts": [f"{s:.6f}" for s in shifts], "registries": res,
           "metrics": {f"{s:.6f}": metrics(res, f"{s:.6f}") for s in shifts}}
    json.dump(doc, open(f"{OUT}/{tag}.json", "w"), indent=1)
    for s in shifts:
        m = doc["metrics"][f"{s:.6f}"]
        log(f"  >> shift {s:.6f}: median O/E {m['median_oe']:.3f}  "
            f"mean|log O/E| {m['mean_abs_log_oe']:.3f}  "
            f"in band {m['in_band_0p80_1p25']}/{m['n_registries']}")
    return doc


def main():
    t0 = time.time()
    parity_gate()
    dials = json.load(open("/home/claude/registries/out/dials.json"))
    assert [d["name"] for d in dials] == [r["name"] for r in REG]
    log("dials carried forward from out/dials.json (EuroSCORE II unchanged v3.0 -> v3.1)")
    json.dump(dials, open(f"{OUT}/dials.json", "w"), indent=1)

    shifts = [SHIPPED_SHIFT, PRIOR_SHIFT]
    with Pool(WORKERS) as pool:
        stage(pool, "definitive", TOTAL_N, dials, 1_000_000, shifts)
        stage(pool, "holdout_1", HOLDOUT_N, dials, 50_000_000, shifts)
        stage(pool, "holdout_2", HOLDOUT_N, dials, 90_000_000, shifts)
    log(f"DONE in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
