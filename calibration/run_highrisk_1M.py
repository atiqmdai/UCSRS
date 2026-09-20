"""UCSRS v3.1 — HIGH-RISK VALIDATION, 1,000,000 patients, complete mEFT and complete MELD.

Investigator instruction, 20 September 2026. The registry calibration anchors the whole
population; this run interrogates the population the score is actually FOR -- the patient
a heart team is deciding whether to operate on. Its purpose is to establish whether the
two layers that distinguish UCSRS from its comparators, the modified Essential Frailty
Toolset and MELD, produce a materially different reading from EuroSCORE II in patients
where they all fire at once.

Profile, per the investigator's specification: age 70 and 80, ejection fraction normal,
no pulmonary disease, haemoglobin 9 g/dL, haematocrit 27%, platelets 150,000/uL,
creatinine 2.0 and 4.0 mg/dL, albumin 3.0 g/dL, INR 2.0, bilirubin 2.5 mg/dL, chair rise
greater than 15 seconds, cognition poor. Elective first-time isolated CABG. Clinically
plausible spread is applied around each value so the run describes a population rather
than eight points; the eight exact cells are also reported.

EuroSCORE II is computed by the engine. STS-PROM is NOT computed here -- the general STS
ACSD calculator is a live web application and cannot be run a million times; the eight
exact cells were taken to it separately.

NO OUTCOME IS SIMULATED. No outcome model is used. No performance claim follows.
"""
import sys, json, time
import numpy as np

sys.path.insert(0, "/home/claude/UCSRS")
sys.path.insert(0, "/home/claude/registries")

import candidate_engine as E

N = 1_000_000
SEED = 20260920
OUT = "/home/claude/registries/out_lock"


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def gate():
    import hashlib
    a = hashlib.sha256(open("/home/claude/UCSRS/ucsrs_engine.py", "rb").read()).hexdigest()[:16]
    b = hashlib.sha256(open("/home/claude/registries/candidate_engine.py", "rb").read()).hexdigest()[:16]
    log(f"GATE  engine sha shipped {a}  worker {b}")
    assert a == b, "worker engine is not byte-identical to the shipped engine"
    assert E.SPEC_VERSION == "3.1.0"
    assert abs(E.BASELINE_A2["calibration_shift"] - 0.433039) < 1e-9
    log(f"GATE  SPEC_VERSION {E.SPEC_VERSION}, calibration_shift "
        f"{E.BASELINE_A2['calibration_shift']} (locked)")
    return a


BASE = dict(height_cm=175, weight_kg=80, lvef_pct=55, pulm_status="none",
            renal_status="none", procedure_code="cabg_isolated", urgency="elective",
            operation_number="1", hgb_g_dl=9.0, albumin_g_dl=3.0, inr=2.0,
            bilirubin_mg_dl=2.5, chair_rise="slow", cog_impaired="1")


def exact_cells():
    log("EXACT CELLS — the investigator's specification, no spread")
    log(f"  {'age':>4} {'sex':>4} {'Cr':>5} {'MELD':>5} {'mEFT':>5} {'xEFT':>6} "
        f"{'Layer1':>8} {'UCSRS':>8} {'ESII':>7} {'ratio':>7}")
    rows = []
    for age in (70, 80):
        for sex in ("M", "F"):
            for cr in (2.0, 4.0):
                r = dict(BASE, age_years=age, sex=sex, creatinine_mg_dl=cr)
                o = E.score_row(r)
                rows.append({"age": age, "sex": sex, "creatinine": cr, "meld": o["meld"],
                             "eft": o["eft"], "eft_multiplier": o["eft_multiplier"],
                             "layer1_pct": o["baseline_pct"], "ucsrs_pct": o["ucsrs"],
                             "euroscore2_pct": o["euroscore2_computed_pct"],
                             "at_cap": o["ucsrs"] >= 69.99})
                log(f"  {age:>4} {sex:>4} {cr:>5.1f} {o['meld']:>5} {o['eft']:>5} "
                    f"{o['eft_multiplier']:>6.2f} {o['baseline_pct']:>8.2f} "
                    f"{o['ucsrs']:>8.2f} {o['euroscore2_computed_pct']:>7.2f} "
                    f"{o['ucsrs']/o['euroscore2_computed_pct']:>7.1f}x")
    return rows


def population():
    rng = np.random.default_rng(SEED)
    age = rng.choice([70, 80], N) + rng.normal(0, 3, N)
    female = rng.random(N) < 0.35
    cr = np.exp(rng.normal(np.log(2.6), 0.35, N)).clip(1.2, 6.0)
    alb = rng.normal(3.0, 0.35, N).clip(1.8, 4.2)
    inr = rng.normal(2.0, 0.35, N).clip(1.0, 4.5)
    bili = np.exp(rng.normal(np.log(2.5), 0.5, N)).clip(0.4, 20)
    hgb = rng.normal(9.0, 1.1, N).clip(6.0, 13.5)
    ef = rng.normal(55, 5, N).clip(40, 70)
    chair = rng.choice(["slow", "unable"], N, p=[0.7, 0.3])
    cog = rng.random(N) < 0.8

    U = np.empty(N); Ee = np.empty(N); ML = np.empty(N); FT = np.empty(N); L1 = np.empty(N)
    t0 = time.time()
    for i in range(N):
        r = dict(BASE, age_years=float(age[i]), sex="F" if female[i] else "M",
                 height_cm=170.0, weight_kg=78.0, creatinine_mg_dl=float(cr[i]),
                 lvef_pct=float(ef[i]), hgb_g_dl=float(hgb[i]), albumin_g_dl=float(alb[i]),
                 inr=float(inr[i]), bilirubin_mg_dl=float(bili[i]),
                 chair_rise=str(chair[i]), cog_impaired="1" if cog[i] else "0")
        o = E.score_row(r)
        U[i] = o["ucsrs"]; Ee[i] = o["euroscore2_computed_pct"]
        ML[i] = o["meld"]; FT[i] = o["eft"]; L1[i] = o["baseline_pct"]
        if (i + 1) % 200_000 == 0:
            log(f"  scored {i+1:,} / {N:,}  ({time.time()-t0:.0f}s)")

    capped = U >= 69.99
    res = {
        "n": N, "seed": SEED,
        "meld_mean": float(ML.mean()), "meld_median": float(np.median(ML)),
        "meld_ge20_pct": float((ML >= 20).mean() * 100),
        "eft_mean": float(FT.mean()), "eft_ge4_pct": float((FT >= 4).mean() * 100),
        "esii": {"mean": float(Ee.mean()), "p10": float(np.percentile(Ee, 10)),
                 "p50": float(np.median(Ee)), "p90": float(np.percentile(Ee, 90))},
        "ucsrs": {"mean": float(U.mean()), "p10": float(np.percentile(U, 10)),
                  "p50": float(np.median(U)), "p90": float(np.percentile(U, 90))},
        "layer1_mean": float(L1.mean()),
        "ratio_of_means": float(U.mean() / Ee.mean()),
        "median_ratio": float(np.median(U / Ee)),
        "at_cap_pct": float(capped.mean() * 100),
        "ge50_pct": float((U >= 50).mean() * 100),
        "ge30_pct": float((U >= 30).mean() * 100),
        "uncapped": {"n": int((~capped).sum()),
                     "p10": float(np.percentile(U[~capped], 10)),
                     "p50": float(np.median(U[~capped])),
                     "p90": float(np.percentile(U[~capped], 90))},
    }
    log("")
    log(f"POPULATION RESULT, n = {N:,}")
    log(f"  MELD mean {res['meld_mean']:.1f}, median {res['meld_median']:.0f}, "
        f">=20 in {res['meld_ge20_pct']:.1f}%")
    log(f"  mEFT mean {res['eft_mean']:.2f} points, >=4 points in {res['eft_ge4_pct']:.1f}%")
    log(f"  EuroSCORE II  mean {res['esii']['mean']:6.2f}%  p10 {res['esii']['p10']:6.2f}  "
        f"p50 {res['esii']['p50']:6.2f}  p90 {res['esii']['p90']:6.2f}   "
        f"spread {res['esii']['p90']/res['esii']['p10']:.1f}x")
    log(f"  UCSRS         mean {res['ucsrs']['mean']:6.2f}%  p10 {res['ucsrs']['p10']:6.2f}  "
        f"p50 {res['ucsrs']['p50']:6.2f}  p90 {res['ucsrs']['p90']:6.2f}   "
        f"spread {res['ucsrs']['p90']/res['ucsrs']['p10']:.1f}x")
    log(f"  UCSRS / EuroSCORE II: ratio of means {res['ratio_of_means']:.1f}x, "
        f"median ratio {res['median_ratio']:.1f}x")
    log(f"  AT THE 70% CAP: {res['at_cap_pct']:.1f}%   >=50%: {res['ge50_pct']:.1f}%   "
        f">=30%: {res['ge30_pct']:.1f}%")
    log(f"  excluding capped (n={res['uncapped']['n']:,}): p10 {res['uncapped']['p10']:.2f}%  "
        f"p50 {res['uncapped']['p50']:.2f}%  p90 {res['uncapped']['p90']:.2f}%")
    return res


if __name__ == "__main__":
    t0 = time.time()
    sha = gate()
    cells = exact_cells()
    log("")
    log(f"POPULATION RUN — {N:,} patients around the specified profile")
    res = population()
    json.dump({"engine_sha256_16": sha, "spec_version": E.SPEC_VERSION,
               "calibration_shift": E.BASELINE_A2["calibration_shift"],
               "exact_cells": cells, "population": res,
               "finished": time.strftime("%Y-%m-%d %H:%M:%S")},
              open(f"{OUT}/highrisk_1M.json", "w"), indent=1, default=float)
    log(f"DONE in {(time.time()-t0)/60:.1f} min — out_lock/highrisk_1M.json")
