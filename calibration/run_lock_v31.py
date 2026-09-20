"""UCSRS v3.1 LOCKING CALIBRATION RUN — 30,000,000 patients.

Investigator instruction, 20 September 2026: this is the LAST calibration run until the
ATLAS trial reaches 5,000 enrolled patients. Nothing here is tuned to a result; the run
is a confirmation that the engine as it now stands still holds its registry anchoring
after this session's changes.

What changed since the 20 September confirmatory run, and why this run exists
-----------------------------------------------------------------------------
Nothing numeric, by construction: the intervening commits deleted dead code, removed the
unused euro_pct parameter, and corrected stale comments, and a 3,000-patient before/after
fingerprint over ten quantities was identical. But "proven behaviour-neutral on 3,000
patients through one entry point" is not the same claim as "holds across thirteen
registry case mixes at 30,000,000 patients", and the euro_pct removal in particular
touched a POSITIONAL signature at five call sites, which is the defect class that voided
two earlier runs. So the run is repeated in full.

STAGES
  gate  engine byte-identity, version, constants, and wrapper == score_row()
  A     SKIPPED. The thirteen severity dials are solved against EuroSCORE II alone and
        EuroSCORE II has not changed since v3.0 -- the parity suite confirms the
        coefficient tables agree between the engines. out/dials.json is reused verbatim.
  B     RE-SOLVE the calibration shift from scratch, by root-finding, WITHOUT reference
        to the shipped value. If the engine still holds its anchoring, the solve must
        land back on 0.433039. This is the independent half of the confirmation.
  C     30,000,000-patient definitive run, scored at BOTH the freshly solved shift and
        the shipped 0.433039, plus quartile drift against EuroSCORE II.
  D     two hold-out realisations on seeds that took no part in the solve.

NO SIMULATED PATIENT IS ASSIGNED AN OUTCOME AT ANY STAGE. No outcome model is used.
No performance claim follows from this run.
"""
import sys, json, time, os, hashlib
import numpy as np
from multiprocessing import Pool
from scipy.optimize import brentq

sys.path.insert(0, "/home/claude/UCSRS")
sys.path.insert(0, "/home/claude/registries")

import candidate_engine as E
from anchors import table
from score_cand import run_block, merge, _score_row, NBINS

OUT = "/home/claude/registries/out_lock"
os.makedirs(OUT, exist_ok=True)

WORKERS = 2
CHUNK = 60_000
SHIPPED_SHIFT = 0.433039
TOTAL_N = 30_000_000
HOLDOUT_N = 2_600_000

REG = table()


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


def gate():
    shipped = "/home/claude/UCSRS/ucsrs_engine.py"
    worker = "/home/claude/registries/candidate_engine.py"
    a, b = _sha(shipped), _sha(worker)
    log(f"GATE 1  engine sha  shipped {a}  worker {b}")
    assert a == b, "worker engine is not byte-identical to the shipped engine"

    assert E.SPEC_VERSION == "3.1.0"
    assert abs(E.BASELINE_A2["calibration_shift"] - SHIPPED_SHIFT) < 1e-9
    L = E.L1
    assert L["renal_k"] == 1.30
    assert (L["age_65_69"], L["age_70_74"], L["age_75_79"]) == (0.05, 0.30, 0.55)
    assert (L["age_80_84"], L["age_85_89"], L["age_ge_90"]) == (0.85, 1.10, 1.40)
    assert (L["lung_chronic_o2"], L["lung_acute"], L["lung_acute_vent"]) == (0.60, 0.50, 1.10)
    assert (L["ef_30_40"], L["ef_20_30"], L["ef_lt_20"]) == (0.40, 0.80, 1.20)
    S = E.SPEC["layer2b_eft"]
    assert (S["alb_lo"], S["alb_crit"], S["hgb_crit"]) == (3.5, 3.0, 8.0)
    assert not hasattr(E, "meld_hepatic"), "the deleted MELD variant is back"
    log(f"GATE 2  SPEC_VERSION {E.SPEC_VERSION}, shift {E.BASELINE_A2['calibration_shift']}, "
        "all v3.1 coefficients as committed")

    from cohort import Cohort, rows
    bad = 0
    for r in rows(Cohort(4242).draw(400, 0.0)):
        u, e, _ = _score_row(r, SHIPPED_SHIFT)
        ref = E.score_row(r)
        if abs(u - ref["ucsrs"]) > 1e-9 or abs(e - ref["euroscore2_computed_pct"]) > 1e-9:
            bad += 1
    assert bad == 0, f"{bad}/400 rows disagree with score_row()"
    log("GATE 3  wrapper path == engine score_row() on 400/400 rows")
    return a


def _chunks(n, size):
    out = []
    while n > 0:
        c = min(size, n)
        out.append(c)
        n -= c
    return out


def score_cohort(pool, seed, dial, n, shifts):
    jobs = [(seed + 1_000 * i, dial, c, tuple(shifts)) for i, c in enumerate(_chunks(n, CHUNK))]
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
        mu = acc["sum_u"][j] / n
        out["shifts"][f"{sh:.6f}"] = {
            "mean_ucsrs": mu, "oe_ucsrs": obs / mu,
            "geo_mean_ucsrs": float(np.exp(acc["sum_log_u"][j] / n)),
            "cap_hit_pct": 100.0 * acc["cap_hits"][j] / n,
            "baseline_clamp_pct": 100.0 * acc["br_clamp"][j] / n,
        }
    return out


def metrics(rows_, key):
    oes = np.array([x["shifts"][key]["oe_ucsrs"] for x in rows_])
    means = np.array([x["shifts"][key]["mean_ucsrs"] for x in rows_])
    return {"median_oe": float(np.median(oes)),
            "mean_abs_log_oe": float(np.mean(np.abs(np.log(oes)))),
            "in_band_0p80_1p25": int(((oes >= 0.80) & (oes <= 1.25)).sum()),
            "min_oe": float(oes.min()), "max_oe": float(oes.max()),
            "dynamic_range": float(means.max() / means.min())}


def quartile_drift(acc, j):
    cn = acc["hist_n"].cumsum()
    total = cn[-1]
    edges = [np.searchsorted(cn, total * q) for q in (0.25, 0.5, 0.75)]
    bounds = [0] + [int(e) + 1 for e in edges] + [NBINS]
    res = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        nc = acc["hist_n"][a:b].sum()
        if nc == 0:
            res.append(None); continue
        mu = acc["hist_u"][j, a:b].sum() / nc
        me = acc["hist_e"][a:b].sum() / nc
        res.append({"n": int(nc), "mean_ucsrs": float(mu), "mean_esii": float(me),
                    "ratio": float(mu / me) if me else None})
    return res


def stage_b(pool, dials, n_pilot=150_000):
    log(f"STAGE B - RE-SOLVING the calibration shift from scratch, {n_pilot:,} per registry")
    log("          (the shipped value is NOT used as a starting point)")

    def median_oe(shift):
        rows_ = [summarize(score_cohort(pool, 2_000_000 + 7919 * i, d["dial"], n_pilot, (shift,)),
                           r, (shift,))
                 for i, (r, d) in enumerate(zip(REG, dials))]
        m = metrics(rows_, f"{shift:.6f}")
        log(f"  shift {shift:+.4f} -> median O/E {m['median_oe']:.4f}  "
            f"in-band {m['in_band_0p80_1p25']}/13")
        return m["median_oe"]

    t0 = time.time()
    shift = brentq(lambda s: median_oe(s) - 1.0, -1.0, 3.0, xtol=1e-3, rtol=1e-8)
    drift = shift - SHIPPED_SHIFT
    log(f"  SOLVED calibration_shift = {shift:.6f}  ({time.time()-t0:.0f}s)")
    log(f"  shipped value            = {SHIPPED_SHIFT:.6f}   difference {drift:+.6f} log-odds")
    json.dump({"solved_shift": shift, "shipped_shift": SHIPPED_SHIFT,
               "difference_log_odds": drift, "pilot_n_per_registry": n_pilot},
              open(f"{OUT}/shift.json", "w"), indent=1)
    return shift


def stage_c(pool, dials, shifts, total, seed0, tag):
    per = total // len(REG)
    extra = total - per * len(REG)
    log(f"{tag} - {total:,} patients, {per:,} per registry, shifts {['%.6f' % s for s in shifts]}")
    rows_, drift = [], {}
    for i, (r, d) in enumerate(zip(REG, dials)):
        n = per + (extra if i == 0 else 0)
        t0 = time.time()
        acc = score_cohort(pool, seed0 + 7919 * i, d["dial"], n, shifts)
        s = summarize(acc, r, shifts)
        rows_.append(s)
        drift[r["name"]] = {f"{sh:.6f}": quartile_drift(acc, j) for j, sh in enumerate(shifts)}
        sk = f"{shifts[-1]:.6f}"
        log(f"  {r['name']:<17} n {n:>9,}  ESII {s['mean_esii']:6.3f}% "
            f"(O/E {s['oe_esii_realised']:.2f} vs pub {s['oe_esii_published']:.2f})  "
            f"UCSRS {s['shifts'][sk]['mean_ucsrs']:6.3f}%  O/E {s['shifts'][sk]['oe_ucsrs']:.3f}  "
            f"({time.time()-t0:.0f}s)")
    res = {"tag": tag, "total_n": total, "per_registry": per,
           "shifts": [f"{s:.6f}" for s in shifts], "registries": rows_,
           "metrics": {f"{s:.6f}": metrics(rows_, f"{s:.6f}") for s in shifts},
           "quartile_drift": drift}
    json.dump(res, open(f"{OUT}/{tag}.json", "w"), indent=1, default=float)
    for s in shifts:
        m = res["metrics"][f"{s:.6f}"]
        log(f"  >> {s:.6f}: median O/E {m['median_oe']:.4f}  mean|log O/E| "
            f"{m['mean_abs_log_oe']:.4f}  in band {m['in_band_0p80_1p25']}/13  "
            f"range {m['min_oe']:.3f}-{m['max_oe']:.3f}")
    return res


def main():
    t0 = time.time()
    sha = gate()
    dials = json.load(open("/home/claude/registries/out/dials.json"))
    assert [d["name"] for d in dials] == [r["name"] for r in REG]
    log("STAGE A skipped - dials anchor on EuroSCORE II, unchanged v3.0 -> v3.1")
    json.dump(dials, open(f"{OUT}/dials.json", "w"), indent=1)

    with Pool(WORKERS) as pool:
        solved = stage_b(pool, dials)
        shifts = sorted({round(solved, 6), SHIPPED_SHIFT})
        stage_c(pool, dials, shifts, TOTAL_N, 5_000_000, "definitive")
        stage_c(pool, dials, shifts, HOLDOUT_N, 9_000_000, "holdout_1")
        stage_c(pool, dials, shifts, HOLDOUT_N, 11_000_000, "holdout_2")

    json.dump({"engine_sha256_16": sha, "spec_version": E.SPEC_VERSION,
               "shipped_shift": SHIPPED_SHIFT, "total_n": TOTAL_N,
               "finished": time.strftime("%Y-%m-%d %H:%M:%S")},
              open(f"{OUT}/provenance.json", "w"), indent=1)
    log(f"DONE in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
