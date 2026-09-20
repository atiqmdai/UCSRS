"""CONTROLLED floor comparison, 0.30 vs 0.40, on TODAY'S engine.

The archived 19 September 30M run used floor 0.30, but the engine file it ran against
was edited later the same evening and its exact state at 18:52 cannot now be verified
beyond the floor value and the shift. So rather than rely on that comparison, this runs
both floors against the engine as it stands, changing ONE constant and nothing else.

Each arm re-solves its own calibration shift, because raising the floor lifts the
population mean and the anchoring takes it straight back out; only the change in shape
survives. Profiles are cut on EuroSCORE II (comparable with the archived run) and on the
rank mean of both scores (symmetric, unbiased).

Absolute mean predicted risk per quartile is reported alongside the ratios, because the
pooled-mean-of-ratios and the ratio-of-pooled-means are not the same number and the
archived run reported only the first.

DIAGNOSTIC ONLY -- the engine file is not modified; the clamp is patched in memory.
NO OUTCOME IS SIMULATED.
"""
import sys, json, math
import numpy as np
from scipy.optimize import brentq

sys.path.insert(0, "/home/claude/UCSRS")
sys.path.insert(0, "/home/claude/registries")

import candidate_engine as E
import cohort_cfg as C
from anchors import table

REG = table()
DIALS = {d["name"]: d["dial"] for d in json.load(open("/home/claude/registries/out/dials.json"))}
N_SOLVE = 30_000
N_EVAL = 165_000

_orig_baseline = E.physiology_baseline


def set_floor(f):
    """Re-wrap physiology_baseline with a different lower clamp. One constant, nothing else."""
    def patched(p):
        v = _orig_baseline(p)
        if v <= 0.40 + 1e-12:          # was on the shipped floor -> recompute at the new one
            return max(v * 0.0 + _recompute(p), f) if False else max(_recompute(p), f)
        return v
    def _recompute(p):
        # reproduce the unclamped value by inverting the shipped clamp is not possible,
        # so call the engine's own z-builder via a temporary clamp override instead.
        raise RuntimeError
    return patched


# Simpler and exact: patch the module-level clamp constants the function closes over by
# rebuilding the function from source with the literal replaced.
import re, types, textwrap, inspect
_SRC = inspect.getsource(_orig_baseline)


def make_baseline(floor):
    src = _SRC.replace("min(max(100.0 / (1.0 + math.exp(-z)), 0.40), 50.0)",
                       f"min(max(100.0 / (1.0 + math.exp(-z)), {floor}), 50.0)")
    assert f", {floor})" in src, "clamp literal not found -- refusing to run"
    ns = dict(E.__dict__)
    exec(compile(textwrap.dedent(src), "<floor>", "exec"), ns)
    return ns["physiology_baseline"]


def score_block(seed, dial, n, shift):
    E.BASELINE_A2["calibration_shift"] = shift
    u = np.empty(n); e = np.empty(n)
    for i, r in enumerate(C.rows(C.Cohort(seed).draw(n, dial))):
        o = E.score_row(r)
        u[i] = o["ucsrs"]; e[i] = o["euroscore2_computed_pct"]
    return u, e


def median_oe(shift):
    return float(np.median([r["observed_mortality_pct"] /
                            score_block(3_100_000 + 7919 * i, DIALS[r["name"]], N_SOLVE, shift)[0].mean()
                            for i, r in enumerate(REG)]))


def run(floor):
    E.physiology_baseline = make_baseline(floor)
    try:
        sh = brentq(lambda s: median_oe(s) - 1.0, -1.0, 3.0, xtol=1.5e-3, rtol=1e-8)
        U, Ee = [], []
        for i, r in enumerate(REG):
            u, e = score_block(6_200_000 + 7919 * i, DIALS[r["name"]], N_EVAL, sh)
            U.append(u); Ee.append(e)
        U = np.concatenate(U); Ee = np.concatenate(Ee)
        on_floor = float((U <= floor + 1e-9).mean() * 100)
        rank = lambda x: np.argsort(np.argsort(x)) / len(x)
        out = {"floor": floor, "shift": sh, "n": int(len(U)),
               "mean_ucsrs": float(U.mean()), "mean_esii": float(Ee.mean()),
               "pct_at_floor": on_floor}
        for lbl, key in (("esii", Ee), ("rankmean", (rank(U) + rank(Ee)) / 2)):
            q = np.quantile(key, [0.25, 0.5, 0.75])
            bands = [key <= q[0], (key > q[0]) & (key <= q[1]),
                     (key > q[1]) & (key <= q[2]), key > q[2]]
            out[lbl] = [{"ucsrs": float(U[b].mean()), "esii": float(Ee[b].mean()),
                         "ratio": float(U[b].mean() / Ee[b].mean())} for b in bands]
        return out
    finally:
        E.physiology_baseline = _orig_baseline
        E.BASELINE_A2["calibration_shift"] = 0.433039


if __name__ == "__main__":
    res = [run(0.30), run(0.40)]
    for r in res:
        print(f"\n{'='*86}\nFLOOR {r['floor']:.2f}   re-solved shift {r['shift']:.6f}   "
              f"n={r['n']:,}   {r['pct_at_floor']:.1f}% of patients sit on the floor")
        print(f"  mean UCSRS {r['mean_ucsrs']:.3f}%   mean EuroSCORE II {r['mean_esii']:.3f}%")
        for lbl, nice in (("esii", "cut on EuroSCORE II"), ("rankmean", "cut on RANK MEAN")):
            print(f"  {nice}")
            for i, b in enumerate(r[lbl]):
                print(f"    Q{i+1}   UCSRS {b['ucsrs']:7.3f}%   ESII {b['esii']:7.3f}%   "
                      f"ratio {b['ratio']:.3f}")
    a, b = res
    print(f"\n{'='*86}\nWHAT THE FLOOR DID (ratio, floor 0.30 -> floor 0.40)")
    for lbl, nice in (("esii", "cut on EuroSCORE II"), ("rankmean", "cut on RANK MEAN")):
        print(f"  {nice:<22}" + "   ".join(
            f"Q{i+1} {a[lbl][i]['ratio']:.3f}->{b[lbl][i]['ratio']:.3f} ({b[lbl][i]['ratio']-a[lbl][i]['ratio']:+.3f})"
            for i in range(4)))
    json.dump(res, open("/home/claude/registries/out_lock/floor_experiment.json", "w"),
              indent=1, default=float)
    print("\nwritten out_lock/floor_experiment.json")
