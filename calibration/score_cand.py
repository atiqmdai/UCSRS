"""Scoring workers. Every patient goes through ucsrs_engine.patient_from_row(), i.e.
the same code path an enrolled ATLAS patient takes.

NO OUTCOME IS SIMULATED ANYWHERE IN THIS FILE.
"""
import sys
import numpy as np

sys.path.insert(0, "/home/claude/UCSRS")
sys.path.insert(0, "/home/claude/registries")

import candidate_engine as E
from cohort import Cohort, rows

# EuroSCORE II histogram used to recover quartile boundaries without holding 30M values.
BIN_W = 0.05          # percentage points
NBINS = 2000          # 0 .. 100 %


def _set_shift(v):
    E.BASELINE_A2["calibration_shift"] = v


def _score_row(r, shift):
    """Full engine path for one row at one calibration shift. Returns (ucsrs, esii)."""
    p = E.patient_from_row(r)
    _set_shift(shift)
    baseline = E.physiology_baseline(p)
    euro = E.euroscore2(p)

    cog_raw = r.get("cog_impaired")
    cog = None if cog_raw in (None, "") else str(cog_raw) not in ("0", "no", "n", "false")
    eft = E.eft_score(r.get("chair_rise"), cog, r["hgb_g_dl"], r["albumin_g_dl"], p["female"])

    meld = None
    if "bilirubin_mg_dl" in r:
        meld = E.meld_from_labs(r["bilirubin_mg_dl"], r["inr"], p["creatinine"])

    tier = 2 if "rhc_map_mmhg" in r else 0
    res = E.ucsrs(baseline, eft["points"], meld,
                  lvesvi=r.get("lvesvi_ml_m2"), lvedd=r.get("lvedd_mm"),
                  syntax=r.get("syntax_score"), tier=tier,
                  map_mmhg=r.get("rhc_map_mmhg"), co=r.get("rhc_co_l_min"),
                  pvr=r.get("rhc_pvr_wu"))
    return res["final"], euro, baseline


def esii_mean(args):
    """Dial solving only needs the comparator. args = (seed, dial, n)."""
    seed, dial, n = args
    d = Cohort(seed).draw(n, dial)
    tot = 0.0
    for r in rows(d):
        tot += E.euroscore2(E.patient_from_row(r))
    return tot, n


def run_block(args):
    """Score one block at one or two calibration shifts.

    args = (seed, dial, n, shifts) where shifts is a tuple of calibration_shift values.
    Returns a dict of accumulators; nothing per-patient is retained.
    """
    seed, dial, n, shifts = args
    d = Cohort(seed).draw(n, dial)

    k = len(shifts)
    sum_u = np.zeros(k)
    sum_log_u = np.zeros(k)
    cap_hits = np.zeros(k, dtype=np.int64)
    br_clamp = np.zeros(k, dtype=np.int64)
    sum_e = 0.0
    hist_n = np.zeros(NBINS, dtype=np.int64)
    hist_u = np.zeros((k, NBINS))
    hist_e = np.zeros(NBINS)

    for r in rows(d):
        p = E.patient_from_row(r)
        euro = E.euroscore2(p)

        cog_raw = r.get("cog_impaired")
        cog = None if cog_raw in (None, "") else str(cog_raw) not in ("0", "no", "n", "false")
        eft = E.eft_score(r.get("chair_rise"), cog, r["hgb_g_dl"], r["albumin_g_dl"],
                          p["female"])
        meld = None
        if "bilirubin_mg_dl" in r:
            meld = E.meld_from_labs(r["bilirubin_mg_dl"], r["inr"], p["creatinine"])
        tier = 2 if "rhc_map_mmhg" in r else 0

        b = min(int(euro / BIN_W), NBINS - 1)
        hist_n[b] += 1
        hist_e[b] += euro
        sum_e += euro

        for j, sh in enumerate(shifts):
            _set_shift(sh)
            baseline = E.physiology_baseline(p)
            res = E.ucsrs(baseline, eft["points"], meld,
                          lvesvi=r.get("lvesvi_ml_m2"), lvedd=r.get("lvedd_mm"),
                          syntax=r.get("syntax_score"), tier=tier,
                          map_mmhg=r.get("rhc_map_mmhg"), co=r.get("rhc_co_l_min"),
                          pvr=r.get("rhc_pvr_wu"))
            u = res["final"]
            sum_u[j] += u
            sum_log_u[j] += np.log(u)
            hist_u[j, b] += u
            if u >= 69.999:
                cap_hits[j] += 1
            if baseline >= 49.999:
                br_clamp[j] += 1

    return {"n": n, "sum_e": sum_e, "sum_u": sum_u, "sum_log_u": sum_log_u,
            "cap_hits": cap_hits, "br_clamp": br_clamp,
            "hist_n": hist_n, "hist_u": hist_u, "hist_e": hist_e}


def merge(acc, b):
    if acc is None:
        return {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in b.items()}
    acc["n"] += b["n"]
    acc["sum_e"] += b["sum_e"]
    for k in ("sum_u", "sum_log_u", "cap_hits", "br_clamp", "hist_n", "hist_u", "hist_e"):
        acc[k] = acc[k] + b[k]
    return acc
