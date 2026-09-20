"""EXPERIMENT — what actually moves the Q3/Q4 reading against EuroSCORE II?

Investigator questions, 20 September 2026:
  1. does the 0.40 floor have anything to do with the Q3/Q4 ratio?
  2. what happens with the generator configured so mEFT and MELD data are COMPLETE?
  3. would raising Layer 1 (the weights are heuristic) lift Q3 and Q4?
  4. would an unclamped mEFT, with albumin not limited by the 6-point ceiling, lift them?

DIAGNOSTIC ONLY. Nothing here writes to the engine or to cohort.py. The generator used is
cohort_cfg.py, a copy of cohort.py whose three optional-domain availability rates are
module constants; with the knobs off it reproduces cohort.py row for row (verified).

EVERY ARM RE-SOLVES THE CALIBRATION SHIFT on its own cohort before its profile is read.
This is the whole point. Completing MELD, or raising Layer 1, lifts every patient; the
registry anchoring then pulls the intercept straight back down. Only the change in SHAPE
survives, and a profile read without re-anchoring would show an improvement the
calibration immediately removes.

Each profile is cut three ways:
  - on EuroSCORE II  (as in the locking run; biased DOWN at the top by selection)
  - on UCSRS         (the mirror; biased UP at the top by the same effect)
  - on the RANK MEAN of the two -- symmetric, neither score picks its own bins.
Read the rank-mean row. Averaging the first two is not equivalent: they are biased in
opposite directions but not by the same amount.

NO OUTCOME IS SIMULATED ANYWHERE.
"""
import sys, json
import numpy as np
from scipy.optimize import brentq

sys.path.insert(0, "/home/claude/UCSRS")
sys.path.insert(0, "/home/claude/registries")

import candidate_engine as E
import cohort_cfg as C
from anchors import table

REG = table()
DIALS = {d["name"]: d["dial"] for d in json.load(open("/home/claude/registries/out/dials.json"))}
SHIPPED = 0.433039
N_SOLVE = 30_000     # 390,000 patients per shift evaluation
N_EVAL = 165_000     # 2,145,000 patients per arm


def score_block(seed, dial, n, shift):
    E.BASELINE_A2["calibration_shift"] = shift
    u = np.empty(n); e = np.empty(n)
    for i, r in enumerate(C.rows(C.Cohort(seed).draw(n, dial))):
        o = E.score_row(r)
        u[i] = o["ucsrs"]; e[i] = o["euroscore2_computed_pct"]
    return u, e


def median_oe(shift, n_per):
    oes = [r["observed_mortality_pct"] / score_block(3_100_000 + 7919 * i,
                                                     DIALS[r["name"]], n_per, shift)[0].mean()
           for i, r in enumerate(REG)]
    return float(np.median(oes))


def profile(shift, n_per=N_EVAL):
    U, Ee = [], []
    for i, r in enumerate(REG):
        u, e = score_block(6_200_000 + 7919 * i, DIALS[r["name"]], n_per, shift)
        U.append(u); Ee.append(e)
    U = np.concatenate(U); Ee = np.concatenate(Ee)
    rank = lambda x: np.argsort(np.argsort(x)) / len(x)
    out = {"n": int(len(U)), "mean_ucsrs": float(U.mean()), "mean_esii": float(Ee.mean())}
    for label, key in (("esii", Ee), ("ucsrs", U), ("rankmean", (rank(U) + rank(Ee)) / 2)):
        q = np.quantile(key, [0.25, 0.5, 0.75])
        bands = [key <= q[0], (key > q[0]) & (key <= q[1]),
                 (key > q[1]) & (key <= q[2]), key > q[2]]
        out[label] = [float(U[b].mean() / Ee[b].mean()) for b in bands]
    return out


def run_arm(name, setup, teardown):
    print(f"\n{'='*94}\nARM {name}\n{'='*94}", flush=True)
    setup()
    try:
        sh = brentq(lambda s: median_oe(s, N_SOLVE) - 1.0, -1.0, 3.0, xtol=1.5e-3, rtol=1e-8)
        p = profile(sh)
        print(f"  re-solved calibration_shift {sh:.6f}   (shipped {SHIPPED}, "
              f"difference {sh - SHIPPED:+.4f})")
        print(f"  mean UCSRS {p['mean_ucsrs']:.3f}%   mean EuroSCORE II {p['mean_esii']:.3f}%   "
              f"n = {p['n']:,}")
        for lbl, nice in (("esii", "cut on EuroSCORE II"), ("ucsrs", "cut on UCSRS"),
                          ("rankmean", "cut on RANK MEAN   <-- read this")):
            q = p[lbl]
            print(f"    {nice:<32} Q1 {q[0]:.3f}   Q2 {q[1]:.3f}   Q3 {q[2]:.3f}   Q4 {q[3]:.3f}")
        return {"arm": name, "shift": sh, **p}
    finally:
        teardown()
        C.EFT_COMPLETE = False; C.MELD_COMPLETE = False; C.RHC_RATE = None
        E.BASELINE_A2["calibration_shift"] = SHIPPED


def complete_data():
    C.EFT_COMPLETE = True; C.MELD_COMPLETE = True


if __name__ == "__main__":
    res = []
    noop = lambda: None

    res.append(run_arm("A — AS SHIPPED, current data-availability rates", noop, noop))

    res.append(run_arm("B — COMPLETE mEFT + COMPLETE MELD data (the investigator's request)",
                       complete_data, noop))

    # C. does an intercept change the shape? It cannot, and this measures that it cannot.
    def c_up():
        complete_data()
        E.BASELINE_A2["intercept"] += 0.30
    def c_down():
        E.BASELINE_A2["intercept"] -= 0.30
    res.append(run_arm("C — Layer 1 intercept +0.30, complete data "
                       "(does raising Layer 1 uniformly change the SHAPE?)", c_up, c_down))

    # D. slope instead of intercept: steepen the severity-carrying Layer 1 terms.
    L1 = E.L1
    saved = {k: L1[k] for k in ("renal_k", "ef_30_40", "ef_20_30", "ef_lt_20",
                                "age_75_79", "age_80_84", "age_85_89", "age_ge_90")}
    def d_up():
        complete_data()
        L1["renal_k"] = 1.60
        L1["ef_30_40"], L1["ef_20_30"], L1["ef_lt_20"] = 0.55, 1.10, 1.60
        L1["age_75_79"], L1["age_80_84"] = 0.70, 1.05
        L1["age_85_89"], L1["age_ge_90"] = 1.35, 1.70
    def d_down():
        L1.update(saved)
    res.append(run_arm("D — Layer 1 SLOPES steepened (renal 1.30->1.60, EF and age up), "
                       "complete data", d_up, d_down))

    # E. mEFT ladder extended to a 7th rung so graded albumin is not absorbed by the clamp.
    S = E.SPEC["layer2b_eft"]
    orig_mult = dict(S["mult"])
    import candidate_engine as _E
    orig_eft = _E.eft_score
    def e_up():
        complete_data()
        S["mult"] = dict(orig_mult); S["mult"][7] = 5.00
        def unclamped(chair, cog, hgb, albumin, female):
            r = orig_eft(chair, cog, hgb, albumin, female)
            # recompute without the min(pts,6) ceiling
            pts = 0
            if chair == "unable": pts += 2
            elif chair == "slow": pts += 1
            if cog: pts += 1
            h = hgb
            if h is not None:
                lo = S["hgb_lo_f"] if female else S["hgb_lo_m"]
                if h < S["hgb_crit"]: pts += 2
                elif h < lo: pts += 1
            a = albumin
            if a is not None:
                if a < S["alb_crit"]: pts += 2
                elif a < S["alb_lo"]: pts += 1
            return {**r, "points": min(pts, 7)}
        _E.eft_score = unclamped
    def e_down():
        _E.eft_score = orig_eft
        S["mult"] = dict(orig_mult)
    res.append(run_arm("E — mEFT ladder extended to 7 rungs (x5.00), albumin not absorbed "
                       "by the 6-point clamp, complete data", e_up, e_down))

    json.dump(res, open("/home/claude/registries/out_lock/quartile_experiment.json", "w"),
              indent=1, default=float)
    print("\n" + "=" * 94)
    print(f"{'ARM':<58}{'Q1':>8}{'Q2':>8}{'Q3':>8}{'Q4':>8}   (rank-mean cut)")
    print("=" * 94)
    for r in res:
        q = r["rankmean"]
        print(f"{r['arm'][:57]:<58}{q[0]:>8.3f}{q[1]:>8.3f}{q[2]:>8.3f}{q[3]:>8.3f}")
    print("\nwritten out_lock/quartile_experiment.json")
