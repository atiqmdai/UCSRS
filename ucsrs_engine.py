#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UCSRS v3.0 — reference implementation in Python.

This is a line-for-line port of the engine block in UCSRS_Calculator.index.html
(between the ENGINE START and ENGINE END markers). The JavaScript file remains the
normative source; test_engine_parity.py runs random patients through both and
fails if they disagree by more than 0.005 percentage points on any endpoint.

Why this file exists
--------------------
Up to v1.1 the trial's analysis script computed UCSRS from the site's own entered
STS-PROM and EuroSCORE II. From v2.0 UCSRS is an independent score: it computes
its own baseline from the patient's clinical variables and does not read the
comparator scores at all. The analysis therefore needs the engine itself, not two
percentages, which is what this module provides.

Nothing here is site-configurable. Every derived quantity — MELD, creatinine
clearance, body surface area, the volume index, the frailty total — is computed
here, identically for every center.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

SPEC_VERSION = "3.0.0"

SPEC: Dict[str, Any] = {
    # v3.0: Layer 1 is the physiology-derived baseline alone.
    "layer1": {"cap_br": 60},
    # v3.0: MELD in log-odds. per_point = ln(1.09), the ADJUSTED OR per MELD point
    # (95% CI 1.07-1.10) in a 10,882-patient cardiac surgical cohort. Adjusted is the
    # correct estimate: MELD contains creatinine and Layer 1 carries a renal term.
    "layer2a_meld": {"cap_pre_cfs": 65, "threshold": 9, "meld_max": 40,
                     # TWO-SEGMENT (investigator, 15 Sep): the published cardiac
                     # gradient is steep to MELD 20 and flattens above it. A single
                     # slope fits neither end.
                     "per_point": 0.18,          # MELD 9 -> 20
                     "per_point_hi": 0.08,       # above MELD 20
                     "breakpoint": 20},
    # v3.0 final: slope raised 0.0862 -> 0.18 per MELD point, extrapolated from a
    # 10,882-patient cardiac-surgery series on CPB (MELD <10 4.6%, 10-19 17.5%,
    # >=20 31.2%), which implies 0.198 log-odds/point below MELD ~15 flattening to
    # 0.080 above 20. 0.18 is a single-segment compromise set by the investigator.
    # The published gradient is UNADJUSTED: creatinine is 24-43% of a sick patient's
    # MELD and is scored separately, and albumin/haemoglobin in the mEFT track the
    # same hepatic synthetic failure as INR. That overlap is DECLARED, not removed -
    # ATLAS resolves it by joint estimation. See UCSRS_v3.0_Calibration_Protocol.md.
    # v2.0: the excess above 1.00 is reduced by 25% from the published ladder
    # (1.15/1.35/1.60/1.90/2.30). A deliberate departure, not a correction.
    "layer2b_eft": {
        "mult": {0: 1.00, 1: 1.25, 2: 1.60, 3: 2.10, 4: 2.60, 5: 3.10, 6: 4.00},
        "cap": 70, "hgb_lo_m": 13.0, "hgb_lo_f": 12.0, "alb_lo": 3.5,
        # v3.0: a SECOND haemoglobin point below 8.0 g/dL. The published EFT scores
        # haemoglobin as one binary point at the WHO anaemia thresholds and is blind
        # to depth; chair rise is already graded 1/2 in the same instrument, so this
        # follows its own internal logic. This makes the instrument a MODIFIED EFT
        # and it must be described as such.
        "hgb_crit": 8.0,
    },
    # v3.0 final: Layer 2c converted from PERCENTAGE POINTS to LOG-ODDS, so the whole
    # score is on one scale (Layer 1 converted at v2.1, Layer 2a in this build).
    # Values raised per investigator, 15 Sep: LV geometry and SYNTAX were inert at
    # cohort scale (LVEDD moved the score 1.1pp, SYNTAX 3.2pp, across their full range).
    "layer2c": {
        "lvesvi": [("lte", 60, 0.00), ("lte", 100, 0.25), ("gt", 100, 0.60)],
        "lvedd": [("lte", 55, 0.00), ("lte", 65, 0.20), ("gt", 65, 0.45)],
        # SYNTAX is OPTIONAL and frequently unmeasured outside trial centres. Absent
        # scores 0.00 and the patient is flagged; it may not enter a primary analysis.
        # Coefficients are investigator judgment, NOT published: SYNTAX was validated
        # for PCI-vs-CABG allocation, not operative mortality after CABG.
        "syntax": [("lte", 32, 0.00), ("lte", 40, 0.35), ("gt", 40, 0.70)],
    },
    "layer3": {
        "cpo_div": 451,
        "cpo": [("lt", 0.6, 2.5), ("lt", 0.9, 0.8)],
        "pvr": [("gt", 5, 2.8), ("gt", 3, 1.2)],
        "ci": [("lt", 2.0, 1.5)],
        "tapse_pasp": [("lt", 0.406, 1.8)],
        "cap_final": 70,
    },
    "outcomes": {
        "anchor_mort": 2.5,
        "slopes": {"vent": 0.60, "renal": 0.65, "stroke": 0.55, "reop": 0.45},
        "anchors": {"vent": 9.5, "renal": 2.8, "stroke": 1.3, "reop": 5.5},
        "modifiers": {
            "vent": {"lvef_lt30": 0.30, "lvef_30_50": 0.12, "copd": 0.35, "smoker": 0.20,
                     "nyha4": 0.15, "critical": 0.30, "urgent": 0.12, "emergency": 0.35,
                     "salvage": 0.55},
            "renal": {"cc_lt30": 0.50, "cc_30_60": 0.25, "iddm": 0.15, "age_gt75": 0.15,
                      "critical": 0.20, "emergency": 0.20, "salvage": 0.35},
            "stroke": {"arteriopathy": 0.30, "aortic_atheroma": 0.25, "neuro": 0.25,
                       "afib": 0.20, "age_gt75": 0.18, "aorta": 0.25, "endocarditis": 0.20,
                       "emergency": 0.15, "radiation": 0.20},
            # anticoagulant: an oral antiplatelet or anticoagulant still inside its own
            # guideline hold window at operation. Heuristic, same magnitude and the
            # same kind of term as immuno; carries NO mortality weight. Added in
            # v2.2.0 and superseded at the ~5,000-patient re-estimation.
            "reop": {"prev_cardiac": 0.20, "radiation": 0.20, "immuno": 0.15,
                     "anticoagulant": 0.15,
                     "critical": 0.20, "emergency": 0.20, "salvage": 0.35, "aorta": 0.15,
                     "endocarditis": 0.20},
        },
    },
    "valve_severity": {"untreated_severe": {"aortic_s": 0.4, "mitral_r": 0.4}},
    "euroscore2": {
        "constant": -5.324537, "age": 0.0285181, "female": 0.2196434,
        "cc_51_85": 0.303553, "cc_le50": 0.8592256, "dialysis": 0.6421508,
        "arteriopathy": 0.5360268, "mobility": 0.2407181, "prev_cardiac": 1.118599,
        "pulmonary": 0.1886564, "endocarditis": 0.6194522, "critical": 1.086517,
        "iddm": 0.3542749, "nyha2": 0.1070545, "nyha3": 0.2958358, "nyha4": 0.5597929,
        "ccs4": 0.2226147, "lv_moderate": 0.3150652, "lv_poor": 0.8084096,
        "lv_verypoor": 0.9346919, "recent_mi": 0.1528943, "pasp_31_55": 0.1788899,
        "pasp_gt55": 0.3491475, "urgent": 0.3174673, "emergency": 0.7039121,
        "salvage": 1.362947, "single_non_cabg": 0.0062118, "two_procedures": 0.5521478,
        "three_plus": 0.9724533, "thoracic_aorta": 0.6527205,
    },
}

# Which valves each procedure addresses, and how EuroSCORE II counts it.
PROC_VALVES = {
    "avr": ["aortic"], "avr_are": ["aortic"], "tavr_explant": ["aortic"],
    "av_repair": ["aortic"], "mvr": ["mitral"], "mv_repair": ["mitral"],
    "tv_repair": ["tricuspid"], "tvr": ["tricuspid"],
    "avr_mvr": ["aortic", "mitral"],
    "avr_mvr_tvr": ["aortic", "mitral", "tricuspid"],
    "avr_mv_repair_tv_repair": ["aortic", "mitral", "tricuspid"],
    "cabg_avr": ["aortic"], "cabg_avr_mv_repair": ["aortic", "mitral"],
    "cabg_avr_mv_repair_tv_repair": ["aortic", "mitral", "tricuspid"],
    "cabg_avr_mvr_tv_repair": ["aortic", "mitral", "tricuspid"],
    "cabg_mvr": ["mitral"], "cabg_mv_repair": ["mitral"],
    "cabg_tv_repair": ["tricuspid"],
    "avr_asc_aorta": ["aortic"], "avr_root_asc_aorta": ["aortic"],
}

PROC_WEIGHT = {
    "cabg": "cabg", "cabg_tv_repair": "cabg",
    "avr": "single", "avr_are": "single", "tavr_explant": "single", "av_repair": "single",
    "mvr": "single", "mv_repair": "single", "tv_repair": "single", "tvr": "single",
    "asc_aorta": "single", "other": "single",
    "cabg_asc_aorta": "two", "avr_mvr": "two", "avr_mv_repair_tv_repair": "two",
    "cabg_avr": "two", "cabg_mvr": "two", "cabg_mv_repair": "two",
    "avr_asc_aorta": "two", "avr_root_asc_aorta": "two",
    "avr_mvr_tvr": "three", "cabg_avr_mv_repair": "three",
    "cabg_avr_mv_repair_tv_repair": "three", "cabg_avr_mvr_tv_repair": "three",
}

AORTA_PROCS = {"asc_aorta", "cabg_asc_aorta", "avr_asc_aorta", "avr_root_asc_aorta"}

PROC_INCREMENT = {
    "cabg": 0.0, "avr": 0.0, "avr_are": 0.3, "tavr_explant": 5.0, "av_repair": -0.2,
    "mvr": 1.5, "mv_repair": -0.5, "tv_repair": 2.0, "tvr": 3.0,
    "avr_mvr": 2.5, "avr_mvr_tvr": 4.0, "avr_mv_repair_tv_repair": 1.5,
    "cabg_avr": 1.2, "cabg_avr_mv_repair": 2.0, "cabg_avr_mv_repair_tv_repair": 2.0,
    "cabg_avr_mvr_tv_repair": 3.0, "cabg_mvr": 2.0, "cabg_mv_repair": 1.0,
    "cabg_tv_repair": 0.0, "asc_aorta": 2.5, "cabg_asc_aorta": 3.0,
    "avr_asc_aorta": 3.2, "avr_root_asc_aorta": 4.2, "other": 1.5,
}


# ---------------------------------------------------------------- helpers
def _num(v) -> Optional[float]:
    """None for anything that is not a finite number — blank, NaN, empty string."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def band(v: float, rules) -> float:
    for op, threshold, coefficient in rules:
        if op == "lte" and v <= threshold:
            return coefficient
        if op == "lt" and v < threshold:
            return coefficient
        if op == "gt" and v > threshold:
            return coefficient
    return 0.0


def meld_from_labs(bili_mgdl: float, inr: float, cr_mgdl: float) -> int:
    """Three inputs only. The creatinine entered is the creatinine used, capped at
    4.0; no dialysis substitution — dialysis is already carried in Layer 1."""
    cr = min(cr_mgdl, 4.0)
    b, i, c = max(bili_mgdl, 1.0), max(inr, 1.0), max(cr, 1.0)
    raw = 3.78 * math.log(b) + 11.2 * math.log(i) + 9.57 * math.log(c) + 6.43
    return int(max(6, min(40, _js_round(raw))))


def _js_round(x: float) -> float:
    """JavaScript Math.round: half away from zero for positives, half up overall.
    Python's round() is banker's rounding and would disagree on exact .5 values."""
    return math.floor(x + 0.5)


def meld_correction(m: Optional[float]) -> float:
    """v3.0: returns a LOG-ODDS increment, not percentage points. Layer 1 is log-odds;
    points add and risk multiplies, so an additive point correction was
    disproportionate for a low-risk patient and too small for a high-risk one."""
    S = SPEC["layer2a_meld"]
    if m is None or m < S["threshold"]:
        return 0.0
    m = min(m, S["meld_max"])
    bp = S["breakpoint"]
    lo = S["per_point"] * (min(m, bp) - S["threshold"])
    hi = S["per_point_hi"] * (m - bp) if m > bp else 0.0
    return lo + hi


def shift_log_odds(pct: float, d: float) -> float:
    """Apply a log-odds increment to a percentage."""
    if d == 0:
        return pct
    p = min(max(pct, 1e-9), 100 - 1e-9) / 100.0
    return 100.0 / (1.0 + math.exp(-(math.log(p / (1 - p)) + d)))


def bsa_mosteller(height_cm, weight_kg) -> Optional[float]:
    h, w = _num(height_cm), _num(weight_kg)
    if h is None or w is None:
        return None
    return math.sqrt((h * w) / 3600.0)



def creatinine_clearance(age, weight_kg, cr_mgdl, female: bool) -> Optional[float]:
    a, w, c = _num(age), _num(weight_kg), _num(cr_mgdl)
    if not a or not w or not c:          # matches the JS falsy test, so 0 is "missing"
        return None
    cc = ((140 - a) * w) / (72 * c)
    return cc * 0.85 if female else cc



# Cockcroft-Gault was derived and validated on actual body weight in populations
# that were not morbidly obese. Above roughly 120% of ideal body weight the added
# mass is overwhelmingly adipose, not the lean/muscle mass that generates creatinine,
# so feeding raw weight in continues to inflate the estimate the heavier a patient
# gets -- a real patient at 200 kg with Cr 2.5 does not have materially better renal
# function than the same patient at 124 kg. Devine ideal-body-weight + the standard
# 0.4 adjustment factor (ASHP/kidney-dosing convention) caps that inflation. Applied
# ONLY to UCSRS's own native renal term below -- the EuroSCORE II sub-computation
# keeps raw actual weight, unmodified, since it must stay faithful to Nashef et al.
# 2012's published methodology for the head-to-head comparator to remain valid.
def ideal_body_weight(height_cm, female: bool) -> Optional[float]:
    h = _num(height_cm)
    if h is None:
        return None
    height_in = h / 2.54
    base = 45.5 if female else 50.0
    return base + 2.3 * max(0.0, height_in - 60.0)


def renal_weight(height_cm, weight_kg, female: bool) -> Optional[float]:
    """Actual body weight, unless it exceeds 120% of ideal body weight -- then the
    Devine adjusted body weight (IBW + 0.4 * (actual - IBW)) is used instead, so the
    renal term stops treating excess adipose mass as if it were excess lean mass."""
    w = _num(weight_kg)
    if w is None:
        return None
    ibw = ideal_body_weight(height_cm, female)
    if ibw is None or ibw <= 0:
        return w
    if w <= 1.20 * ibw:
        return w
    return ibw + 0.4 * (w - ibw)


# ---------------------------------------------------------------- EuroSCORE II
def euroscore2(p: Dict[str, Any]) -> float:
    E = SPEC["euroscore2"]
    lp = E["constant"]
    age = p["age"]
    lp += E["age"] * max(1, 1 if age <= 60 else age - 59)
    if p.get("female"):
        lp += E["female"]

    if p.get("dialysis"):
        lp += E["dialysis"]
    else:
        cc = creatinine_clearance(age, p.get("weight"), p.get("creatinine"), p.get("female", False))
        if cc is not None:
            if cc <= 50:
                lp += E["cc_le50"]
            elif cc <= 85:
                lp += E["cc_51_85"]

    for flag, key in (("arteriopathy", "arteriopathy"), ("mobility", "mobility"),
                      ("prevCardiac", "prev_cardiac"), ("pulmonary", "pulmonary"),
                      ("endocarditis", "endocarditis"), ("critical", "critical"),
                      ("iddm", "iddm")):
        if p.get(flag):
            lp += E[key]

    nyha = p.get("nyha")
    if nyha == 2:
        lp += E["nyha2"]
    elif nyha == 3:
        lp += E["nyha3"]
    elif nyha == 4:
        lp += E["nyha4"]
    if p.get("ccs4"):
        lp += E["ccs4"]

    lvef = _num(p.get("lvef"))
    if lvef is not None:
        if lvef <= 20:
            lp += E["lv_verypoor"]
        elif lvef <= 30:
            lp += E["lv_poor"]
        elif lvef <= 50:
            lp += E["lv_moderate"]
    if p.get("recentMI"):
        lp += E["recent_mi"]

    pasp = _num(p.get("pasp"))
    if pasp is not None and pasp > 0:
        if pasp > 55:
            lp += E["pasp_gt55"]
        elif pasp >= 31:
            lp += E["pasp_31_55"]

    urgency = p.get("urgency")
    if urgency == "urgent":
        lp += E["urgent"]
    elif urgency == "emergency":
        lp += E["emergency"]
    elif urgency == "salvage":
        lp += E["salvage"]

    iw = p.get("interventionWeight")
    if iw == "single":
        lp += E["single_non_cabg"]
    elif iw == "two":
        lp += E["two_procedures"]
    elif iw == "three":
        lp += E["three_plus"]

    if p.get("thoracicAorta"):
        lp += E["thoracic_aorta"]

    return (math.exp(lp) / (1 + math.exp(lp))) * 100


# ---------------------------------------------------------------- frailty
def eft_score(chair: Optional[str], cog_impaired: Optional[bool],
              hgb, albumin, female: bool) -> Dict[str, Any]:
    """Essential Frailty Toolset, 0-6 points (modified: graded haemoglobin). Missing chair rise or cognition gives a
    partial EFT computed from the laboratory components."""
    S = SPEC["layer2b_eft"]
    pts, missing, any_component = 0, [], False

    if chair == "unable":
        pts += 2
        any_component = True
    elif chair == "slow":
        pts += 1
        any_component = True
    elif chair == "fast":
        any_component = True
    else:
        missing.append("chair rise")

    if cog_impaired is True:
        pts += 1
        any_component = True
    elif cog_impaired is False:
        any_component = True
    else:
        missing.append("cognition")

    h = _num(hgb)
    if h is not None:
        if h < S["hgb_crit"]:
            pts += 2
        elif h < (S["hgb_lo_f"] if female else S["hgb_lo_m"]):
            pts += 1
        any_component = True
    else:
        missing.append("hemoglobin")

    a = _num(albumin)
    if a is not None:
        if a < S["alb_lo"]:
            pts += 1
        any_component = True
    else:
        missing.append("albumin")

    return {"points": pts, "missing": missing,
            "partial": len(missing) > 0, "none": not any_component}


# ---------------------------------------------------------------- valves
def valve_burden(valves: Optional[Dict[str, Dict[str, Any]]]) -> float:
    """Only a severe lesion the operation leaves alone can add, and only two of those
    have a defensible effect on 30-day mortality."""
    if not valves:
        return 0.0
    W = SPEC["valve_severity"]["untreated_severe"]
    total = 0.0
    for position in ("aortic", "mitral", "tricuspid"):
        x = valves.get(position)
        if not x or x.get("treated") or x.get("severity") != "severe":
            continue
        if position == "aortic" and x.get("lesion") == "s":
            total += W["aortic_s"]
        if position == "mitral" and x.get("lesion") == "r":
            total += W["mitral_r"]
    return total


# ---------------------------------------------------------------- baseline (v2.1)
# 28 Aug 2026. Three changes from v2.0, all inside the published 50/50:
#
#   1. LOG-ODDS FORM. Increments move from percentage points to log-odds at a 3%
#      reference risk. Odds multiply, so risk fans out; the additive-percentage form
#      compressed the range to about 5x against EuroSCORE II's 9.1x. Relative ordering of
#      every weight is preserved.
#   2. UNIQUE TERMS DOUBLED. Anaemia, atrial fibrillation, ascending/arch atheroma and
#      the untreated-severe-valve burden are multiplied by two, so that after the 0.5
#      blend they land at full strength rather than half. 85.6% of the old baseline sat
#      on variables EuroSCORE II already scores, which the blend then counted ~1.5x
#      while counting the distinctive terms at 0.5x.
#   3. SHARED TERMS SCALED, AND THREE READ CONTINUOUSLY. One factor k shrinks the
#      duplicated terms; age, creatinine clearance and ejection fraction are read as
#      continuous values instead of bands, which is what restores the dynamic range.
#
# k and the intercept were solved together against PUBLISHED OBSERVED MORTALITY across
# the 13 anchorable registries, targeting median O/E = 1.00. Not against EuroSCORE II.
#
# HYPERTENSION REMOVED: neither parent model weights it, it is a weak independent
# predictor of operative mortality, and at 70% prevalence it was adding risk to two
# patients in three for no measurable gain.

BASELINE_A2 = {
    # v3.0 final. Solved so a normal-risk 70-year-old man having an isolated elective
    # first-time CABG reads 1.15x EuroSCORE II. See UCSRS_v3.0_Calibration_Protocol.md.
    "reference_risk": 0.03,
    "intercept": -6.0777,
    "calibration_shift": 1.451532,
    "sternotomy_scale": 1.118599,
}

_REF = BASELINE_A2["reference_risk"]


def _pp_to_logodds(pp):
    """Convert a percentage-point increment to a log-odds increment at the reference."""
    p2 = min(0.60, _REF + pp / 100.0)
    return math.log(p2 / (1 - p2)) - math.log(_REF / (1 - _REF))


# v3.0 Layer 1: one coefficient per variable, log-odds, set from clinical and
# literature judgment. No shared/unique tagging and no k_shared — with the whole layer
# under our control there is no external formula to compensate for. EuroSCORE II is no
# longer a component; it is computed separately as an external comparator only.
# Anaemia, albumin and mobility carry NO Layer 1 weight: each is counted once, in the
# Essential Frailty Toolset at Layer 2b.
L1 = {
    # v3.0 final: age is BANDED (creatinine carries no age signal, so the age term is
    # complete). Each band is EuroSCORE II's own log-odds delta at the band midpoint,
    # plus a deliberate acceleration above 80.
    "age_lt_60": -0.59, "age_60_64": -0.53, "age_65_69": -0.09, "age_70_74": 0.06,
    "age_75_79": 0.20, "age_80_84": 0.44, "age_85_89": 0.60, "age_ge_90": 0.83,
    "female": 0.20,
    # Renal: serum creatinine only. Cockcroft-Gault is DELETED from the scored path
    # (it survives inside euroscore2(), which needs it by published method).
    "renal_k": 1.10,
    "dialysis_cr_equiv": 4.0,   # dialysis scores AS IF creatinine 4.0, replacing the term
    "anuria": 0.00,             # calculated from creatinine; no separate weight
    "lung_chronic": 0.25, "lung_chronic_o2": 0.50,
    "lung_acute": 0.40, "lung_acute_vent": 0.95,
    "ef_30_40": 0.40, "ef_20_30": 0.80, "ef_lt_20": 1.20,
    "nyha3": 0.25, "nyha4": 0.80, "acute_decomp": 0.25,
    "mi_7": 0.45, "mi_30": 0.30, "mi_90": 0.18, "afib": 0.25,
    "pasp_50_70": 0.40, "pasp_gt_70": 0.80,
    "inotropes": 0.40, "vtvf": 0.60, "iabp": 0.50, "impella": 0.62, "ecmo": 0.95,
    "sternotomy2": 1.00, "sternotomy3": 1.50,
    "urgent": 0.35, "emergency": 0.90, "salvage": 2.00,
    "asc_aorta": 0.20,
    # Arch: 1.012, set to the investigator's <10% target for a normal-risk elective
    # 70-year-old (Bentall + arch = 9.80%). NO PUBLISHED ANCHOR EXISTS: EuroSCORE II
    # carries one binary thoracic-aorta flag (0.6527205) that does not distinguish
    # ascending from arch, and the STS ACSD models exclude aortic surgery entirely -
    # the April 2025 STS aortic calculator covers root and ascending only, not arch.
    # This is investigator judgment and must be labelled as such in the spec.
    "aortic_arch": 1.012,
    "bmi_30_40": 0.30, "bmi_40_50": 0.80, "bmi_gt_50": 1.20,
    "iddm": 0.25, "endocarditis": 0.58, "arteriopathy": 0.35,
    "aortic_atheroma": 0.30, "neuro": 0.28, "valve_burden_per_04": 0.25,
    "immuno": 0.40, "radiation": 0.40,
}

# Procedure categories that already price aortic work. The graded asc/arch term is
# suppressed for these so one operation is never charged for the aorta twice.
AORTA_PRICED = {"asc_aorta", "cabg_asc_aorta", "avr_asc_aorta", "avr_root_asc_aorta"}

# v3.0: the procedure table is re-expressed in log-odds with no k scaling.
# v3.0 final: procedure increments REPLACED, not scaled. Each takes EuroSCORE II's
# own intervention-class baseline plus half of UCSRS's within-class deviation;
# aortic codes take EuroSCORE II's value directly (it models them via its aorta flag).
# v3.0 final: each procedure takes EuroSCORE II's intervention-class baseline plus
# HALF its deviation from that class's REFERENCE operation (cabg / avr / cabg_avr /
# cabg_avr_mv_repair) - not from the class mean. The root increment over plain
# ascending replacement is 0.130 (investigator, 15 Sep), giving a normal-risk
# elective Bentall 3.80% against EuroSCORE II's 2.92%. Averaging over the "single" class
# dragged isolated AVR below isolated CABG, because that class also contains TAVR
# explant, TVR and the aortic codes. Aortic codes take EuroSCORE II's value directly.
_PROC_W = {
    "asc_aorta": 0.658932,
    "av_repair": -0.029315,
    "avr": 0.006212,
    "avr_are": 0.055416,
    "avr_asc_aorta": 1.204868,
    "avr_mv_repair_tv_repair": 0.588212,
    "avr_mvr": 0.693811,
    "avr_mvr_tvr": 1.151328,
    "avr_root_asc_aorta": 1.334868,
    "cabg": 0.0,
    "cabg_asc_aorta": 1.204868,
    "cabg_avr": 0.552148,
    "cabg_avr_mv_repair": 0.972453,
    "cabg_avr_mv_repair_tv_repair": 0.972453,
    "cabg_avr_mvr_tv_repair": 1.068905,
    "cabg_mv_repair": 0.52671,
    "cabg_mvr": 0.643517,
    "cabg_tv_repair": 0.0,
    "mv_repair": -0.08752,
    "mvr": 0.216737,
    "other": 0.006212,
    "tavr_explant": 0.523088,
    "tv_repair": 0.272042,
    "tvr": 0.368493
}



def age_band(age):
    """v3.0 final: banded age. Bands are EuroSCORE II's own log-odds delta at the band
    midpoint, plus a deliberate acceleration above 80 (investigator, 15 Sep 2026)."""
    a = _num(age) or 0.0
    if a < 60:  return L1["age_lt_60"]
    if a < 65:  return L1["age_60_64"]
    if a < 70:  return L1["age_65_69"]
    if a < 75:  return L1["age_70_74"]
    if a < 80:  return L1["age_75_79"]
    if a < 85:  return L1["age_80_84"]
    if a < 90:  return L1["age_85_89"]
    return L1["age_ge_90"]


def physiology_baseline(p):
    z = BASELINE_A2["intercept"]
    age = p["age"]

    z += BASELINE_A2["calibration_shift"]

    # Age: banded. Creatinine carries no age signal, so this term is complete.
    z += age_band(age)
    if p.get("female"):
        z += L1["female"]

    # Renal: serum creatinine only. Dialysis REPLACES the term at a fixed creatinine
    # equivalent of 4.0, so the score cannot depend on hours since the last session.
    # Anuria carries no separate weight - it is read off the creatinine (investigator,
    # 15 Sep), which also removes the additive double-count.
    if p.get("dialysis"):
        z += L1["renal_k"] * math.log(L1["dialysis_cr_equiv"])
    else:
        cr = _num(p.get("creatinine"))
        if cr:
            z += L1["renal_k"] * max(0.0, math.log(cr))

    pulm = p.get("pulmStatus")
    if pulm == "acute_vent":
        z += L1["lung_acute_vent"]
    elif pulm == "acute":
        z += L1["lung_acute"]
    elif pulm == "chronic_o2":
        z += L1["lung_chronic_o2"]
    elif pulm == "chronic":
        z += L1["lung_chronic"]

    # v3.0 final: bands are INCLUSIVE of their upper edge (investigator, 15 Sep):
    #   >40 = 0.00 | 31-40 = 0.40 | 21-30 = 0.80 | <=20 = 1.20
    # An ejection fraction of 30 is severely depressed by definition and belongs in
    # the severe band, not the 31-40 one. This also aligns the boundary with
    # EuroSCORE II, which places 30 in its "poor" class.
    lvef = _num(p.get("lvef"))
    if lvef is not None:
        if lvef <= 20:
            z += L1["ef_lt_20"]
        elif lvef <= 30:
            z += L1["ef_20_30"]
        elif lvef <= 40:
            z += L1["ef_30_40"]

    if p.get("nyha") == 3:
        z += L1["nyha3"]
    elif p.get("nyha") == 4:
        z += L1["nyha4"]
    if p.get("acuteDecomp"):
        z += L1["acute_decomp"]
    if p.get("miDays") == 7:
        z += L1["mi_7"]
    elif p.get("miDays") == 30:
        z += L1["mi_30"]
    elif p.get("miDays") == 90:
        z += L1["mi_90"]
    if p.get("afib"):
        z += L1["afib"]

    pasp = p.get("pasp")
    if pasp is not None:
        if pasp > 70:
            z += L1["pasp_gt_70"]
        elif pasp > 50:
            z += L1["pasp_50_70"]

    # Circulatory support: the single highest applicable level, never additive.
    if p.get("ecmo"):
        z += L1["ecmo"]
    elif p.get("impella"):
        z += L1["impella"]
    elif p.get("vtvf"):
        z += L1["vtvf"]
    elif p.get("iabp"):
        z += L1["iabp"]
    elif p.get("inot"):
        z += L1["inotropes"]

    # Sternotomy count, highest applicable, not additive.
    stern = p.get("sternotomy")
    if stern is not None and stern >= 3:
        z += L1["sternotomy3"] * BASELINE_A2["sternotomy_scale"]
    elif stern == 2 or p.get("prevCardiac"):
        z += L1["sternotomy2"] * BASELINE_A2["sternotomy_scale"]

    urg = p.get("urgency")
    if urg == "urgent":
        z += L1["urgent"]
    elif urg == "emergency":
        z += L1["emergency"]
    elif urg == "salvage":
        z += L1["salvage"]

    # The procedure table prices ASCENDING work for four categories, so the ascending
    # term is suppressed for those. It has no arch entry at all, so arch is additional
    # work in every case and always adds.
    if p.get("aorta") == "arch":
        z += L1["aortic_arch"]
    elif p.get("aorta") == "ascending" and p.get("procedure") not in AORTA_PRICED:
        z += L1["asc_aorta"]

    h, w = _num(p.get("height")), _num(p.get("weight"))
    if h and w:
        bmi = w / (h / 100.0) ** 2
        if bmi > 50:
            z += L1["bmi_gt_50"]
        elif bmi > 40:
            z += L1["bmi_40_50"]
        elif bmi > 30:
            z += L1["bmi_30_40"]

    if p.get("iddm"):
        z += L1["iddm"]
    if p.get("endocarditis"):
        z += L1["endocarditis"]
    if p.get("arteriopathy"):
        z += L1["arteriopathy"]
    if p.get("aorticAtheroma"):
        z += L1["aortic_atheroma"]
    if p.get("neuro"):
        z += L1["neuro"]
    vb = valve_burden(p.get("valves"))
    if vb:
        z += L1["valve_burden_per_04"] * (vb / 0.4)
    if p.get("immuno"):
        z += L1["immuno"]
    if p.get("radiation"):
        z += L1["radiation"]
    if p.get("procedure") in _PROC_W:
        z += _PROC_W[p["procedure"]]

    return min(max(100.0 / (1.0 + math.exp(-z)), 0.30), 50.0)


sts_estimate = physiology_baseline


# ---------------------------------------------------------------- the score
def ucsrs(baseline_pct: float, euro_pct: float, eft: int, meld: Optional[float],
          lvesvi=None, lvedd=None, syntax=None, tier: int = 0,
          map_mmhg=None, co=None, pvr=None, ci=None, tapse=None,
          pasp_rhc=None) -> Dict[str, Any]:
    S = SPEC
    br = min(baseline_pct, S["layer1"]["cap_br"])

    meld_corr = meld_correction(meld)
    pre_cfs = min(shift_log_odds(br, meld_corr), S["layer2a_meld"]["cap_pre_cfs"])

    mult = S["layer2b_eft"]["mult"][eft]
    base = min(pre_cfs * mult, S["layer2b_eft"]["cap"])

    lv, lv_source = 0.0, None
    v_lvesvi, v_lvedd = _num(lvesvi), _num(lvedd)
    if v_lvesvi is not None:
        lv, lv_source = band(v_lvesvi, S["layer2c"]["lvesvi"]), "LVESVI"
    elif v_lvedd is not None:
        lv, lv_source = band(v_lvedd, S["layer2c"]["lvedd"]), "LVEDD"

    v_syntax = _num(syntax)
    sx = band(v_syntax, S["layer2c"]["syntax"]) if v_syntax is not None else 0.0

    hemo, hemo_used = 0.0, False
    if tier >= 2:
        v_map, v_co = _num(map_mmhg) or 0, _num(co) or 0
        if v_map > 0 and v_co > 0:
            hemo += band(v_map * v_co / S["layer3"]["cpo_div"], S["layer3"]["cpo"])
            hemo_used = True
        v_pvr = _num(pvr) or 0
        if v_pvr > 0:
            hemo += band(v_pvr, S["layer3"]["pvr"])
            hemo_used = True
        v_ci = _num(ci) or 0
        if v_ci > 0:
            hemo += band(v_ci, S["layer3"]["ci"])
            hemo_used = True
        v_tapse, v_pasp = _num(tapse) or 0, _num(pasp_rhc) or 0
        if v_tapse > 0 and v_pasp > 0:
            hemo += band(v_tapse / v_pasp, S["layer3"]["tapse_pasp"])
            hemo_used = True

    # v3.0: Layer 2c is now a LOG-ODDS shift on the post-frailty subtotal, not an
    # additive slab of percentage points. Layer 3 remains percentage points.
    final = min(shift_log_odds(base, lv + sx) + hemo, S["layer3"]["cap_final"])

    return {"br": br, "meldCorr": meld_corr, "preCfs": pre_cfs, "mult": mult,
            "base": base, "lv": lv, "lvSource": lv_source, "syntax": sx,
            "syntaxGiven": v_syntax is not None, "hemo": hemo, "hemoUsed": hemo_used,
            "final": final}


# ---------------------------------------------------------------- companion outcomes
def ucsrs_outcomes(mort_pct: float,
                   f: Optional[Dict[str, Any]] = None) -> Dict[str, Optional[float]]:
    f = f or {}
    O = SPEC["outcomes"]
    M = O["modifiers"]
    p = min(max(mort_pct / 100.0, 0.0001), 0.9999)

    mods = {"vent": 0.0, "renal": 0.0, "stroke": 0.0, "reop": 0.0}

    lvef = _num(f.get("lvef"))
    if lvef is not None:
        if lvef < 30:
            mods["vent"] += M["vent"]["lvef_lt30"]
        elif lvef <= 50:
            mods["vent"] += M["vent"]["lvef_30_50"]

    if f.get("copd"):
        mods["vent"] += M["vent"]["copd"]
    if f.get("smoker"):
        mods["vent"] += M["vent"]["smoker"]
    if f.get("nyha") == 4:
        mods["vent"] += M["vent"]["nyha4"]
    if f.get("critical"):
        mods["vent"] += M["vent"]["critical"]
        mods["renal"] += M["renal"]["critical"]

    urgency = f.get("urgency")
    if urgency == "urgent":
        mods["vent"] += M["vent"]["urgent"]
    elif urgency == "emergency":
        mods["vent"] += M["vent"]["emergency"]
        mods["renal"] += M["renal"]["emergency"]
        mods["stroke"] += M["stroke"]["emergency"]
        mods["reop"] += M["reop"]["emergency"]
    elif urgency == "salvage":
        mods["vent"] += M["vent"]["salvage"]
        mods["renal"] += M["renal"]["salvage"]
        mods["reop"] += M["reop"]["salvage"]

    cc = _num(f.get("cc"))
    if cc is not None:
        if cc < 30:
            mods["renal"] += M["renal"]["cc_lt30"]
        elif cc < 60:
            mods["renal"] += M["renal"]["cc_30_60"]
    if f.get("iddm"):
        mods["renal"] += M["renal"]["iddm"]

    age = _num(f.get("age"))
    if age is not None and age > 75:
        mods["renal"] += M["renal"]["age_gt75"]
        mods["stroke"] += M["stroke"]["age_gt75"]

    if f.get("arteriopathy"):
        mods["stroke"] += M["stroke"]["arteriopathy"]
    if f.get("aorticAtheroma"):
        mods["stroke"] += M["stroke"]["aortic_atheroma"]
    if f.get("neuro"):
        mods["stroke"] += M["stroke"]["neuro"]
    if f.get("afib"):
        mods["stroke"] += M["stroke"]["afib"]
    if f.get("aorta"):
        mods["stroke"] += M["stroke"]["aorta"]
        mods["reop"] += M["reop"]["aorta"]
    if f.get("endocarditis"):
        mods["stroke"] += M["stroke"]["endocarditis"]
        mods["reop"] += M["reop"]["endocarditis"]
    if f.get("radiation"):
        mods["stroke"] += M["stroke"]["radiation"]
        mods["reop"] += M["reop"]["radiation"]
    if f.get("prevCardiac"):
        mods["reop"] += M["reop"]["prev_cardiac"]
    if f.get("immuno"):
        mods["reop"] += M["reop"]["immuno"]
    if f.get("anticoagulant"):
        mods["reop"] += M["reop"]["anticoagulant"]
    if f.get("critical"):
        mods["reop"] += M["reop"]["critical"]

    def logit(x: float) -> float:
        return math.log(x / (1 - x))

    out: Dict[str, Optional[float]] = {}
    for key, anchor in O["anchors"].items():
        # Damped slope: morbidity risk tracks mortality risk sub-proportionally on the
        # log-odds scale; the intercept anchors each endpoint at its typical rate for a
        # factor-free patient at typical mortality.
        slope = O["slopes"][key]
        intercept = logit(anchor / 100.0) - slope * logit(O["anchor_mort"] / 100.0)
        lp = slope * logit(p) + intercept + mods[key]
        out[key] = (1 / (1 + math.exp(-lp))) * 100

    # A patient already on dialysis cannot develop new post-operative renal failure in
    # the STS sense; the estimate is not applicable.
    if f.get("dialysis"):
        out["renal"] = None
    return out


# ---------------------------------------------------------------- CSV row -> score
def _flag(v) -> bool:
    """A submission file writes 0/1; be tolerant of 'yes'/'true'/'Y' from an export."""
    if v is None:
        return False
    s = str(v).strip().lower()
    if s in ("", "nan", "none", "null", "0", "no", "n", "false", "f"):
        return False
    return True


def _text(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "null") else s


def patient_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Map one row of the ATLAS submission file to the engine's patient object.

    This is the same mapping the calculator's form performs, expressed over column
    names instead of DOM elements. Keeping it in one function is what makes the
    trial's numbers and the published calculator's numbers the same numbers.
    """
    sex_f = _text(row.get("sex")).upper() == "F"
    hf = _text(row.get("heart_failure")) or "none"
    renal = _text(row.get("renal_status")) or "normal"
    pulm = _text(row.get("pulm_status")) or "none"
    shock = _text(row.get("shock_support")) or "none"
    arterio = _text(row.get("arteriopathy_site")) or "none"
    mi = _text(row.get("mi_recency")) or "none"
    procedure = _text(row.get("procedure")) or "other"
    chair = _text(row.get("chair_rise")) or None

    ventilated = pulm == "acute_vent"
    critical = shock != "none" or ventilated or renal == "acute"

    try:
        sternotomy = int(float(_text(row.get("operation_number")) or 1))
    except ValueError:
        sternotomy = 1

    # Heart failure: 'none' and NYHA I are both the published reference class; acute
    # decompensation scores as class IV plus an increment.
    if hf == "acute":
        nyha = 4
    elif hf in ("none", ""):
        nyha = 1
    else:
        try:
            nyha = int(hf)
        except ValueError:
            nyha = 1

    treated = PROC_VALVES.get(procedure, [])

    def valve(position: str, column: str) -> Dict[str, Any]:
        v = _text(row.get(column)) or "none"
        if v == "none":
            field: Dict[str, Any] = {"lesion": None, "severity": "none"}
        else:
            field = {"lesion": v[0], "severity": v[2:]}
        field["treated"] = position in treated
        return field

    hgb = _num(row.get("hgb_g_dl"))
    anemia = hgb is not None and hgb < (SPEC["layer2b_eft"]["hgb_lo_f"] if sex_f
                                        else SPEC["layer2b_eft"]["hgb_lo_m"])

    return {
        "age": _num(row.get("age_years")),
        "weight": _num(row.get("weight_kg")),
        "height": _num(row.get("height_cm")),
        "creatinine": _num(row.get("creatinine_mg_dl")),
        "female": sex_f,
        "dialysis": renal == "dialysis",
        "anuria": renal == "acute",
        "lvef": _num(row.get("lvef_pct")),
        "pasp": _num(row.get("pasp_mmhg")),
        "nyha": nyha,
        "heartFailure": hf,
        "pulmStatus": pulm,  # BUGFIX (15 Sep 2026, SPEC_VERSION 3.0.0 unchanged -- L1 coefficients did not
        # change, only this field-mapping wiring): physiology_baseline() reads
        # p.get("pulmStatus") for the pulmonary-status log-odds term; this key was
        # missing here, so that term was silently 0 for every submission-file
        # patient. No patients enrolled under v3.0/v4.0 yet, so fixed at the source
        # rather than papered over downstream. See
        # UCSRS_v4.0_ATLAS_Document_Update_Record.md for the finding.
        "acuteDecomp": hf == "acute",
        "ccs4": _flag(row.get("ccs_class_4")),
        "arteriopathy": arterio != "none",
        "aorticAtheroma": arterio in ("ascending", "arch"),
        "carotidDisease": arterio == "carotid",
        "mobility": _flag(row.get("poor_mobility")) or chair == "unable",
        "sternotomy": sternotomy,
        "prevCardiac": sternotomy >= 2,
        "endocarditis": _flag(row.get("endocarditis_active")),
        "critical": critical,
        "iddm": _text(row.get("diabetes")) == "insulin",
        "dmOral": _text(row.get("diabetes")) == "oral",
        "pulmonary": pulm in ("chronic", "chronic_o2"),
        "lungAny": pulm != "none",
        "homeOxygen": pulm == "chronic_o2",
        "ventilated": ventilated,
        "miDays": None if mi == "none" else int(mi),
        "recentMI": mi != "none",
        "htn": _flag(row.get("hypertension")),
        "afib": _flag(row.get("atrial_fibrillation")),
        "anemia": anemia,
        "neuro": _flag(row.get("neuro_dysfunction")),
        "smoker": _flag(row.get("smoker")),
        "radiation": _flag(row.get("mediastinal_radiation")),
        "immuno": _flag(row.get("immunosuppressed")),
        "shockLevel": shock,
        "inot": shock == "inotropes",
        "vtvf": shock == "vtvf",
        "iabp": shock == "iabp",
        "impella": shock == "impella",
        "ecmo": shock == "ecmo",
        "urgency": _text(row.get("urgency")) or "elective",
        "procedure": procedure,
        "interventionWeight": PROC_WEIGHT.get(procedure, "single"),
        "thoracicAorta": procedure in AORTA_PROCS,
        "valves": {
            "aortic": valve("aortic", "av_severity"),
            "mitral": valve("mitral", "mv_severity"),
            "tricuspid": valve("tricuspid", "tv_severity"),
        },
    }


def score_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Score one submission row end to end.

    Returns the layer decomposition, the companion outcome estimates, the internally
    computed EuroSCORE II, and a list of reasons the row could not be scored. A row
    missing any of age, weight, height, creatinine, hemoglobin or albumin returns
    ucsrs=None with the reason named — it is not silently dropped and not imputed.
    """
    p = patient_from_row(row)

    blockers: List[str] = []
    for key, label in (("age", "age_years"), ("weight", "weight_kg"),
                       ("height", "height_cm"), ("creatinine", "creatinine_mg_dl")):
        if p.get(key) is None:
            blockers.append(label)
    hgb, alb = _num(row.get("hgb_g_dl")), _num(row.get("albumin_g_dl"))
    if hgb is None:
        blockers.append("hgb_g_dl")
    if alb is None:
        blockers.append("albumin_g_dl")

    cog_raw = _text(row.get("cog_impaired"))
    cog = None if cog_raw == "" else cog_raw not in ("0", "no", "n", "false")
    eft = eft_score(p_chair(row), cog, hgb, alb, p["female"])

    if blockers:
        return {"ucsrs": None, "blockers": blockers, "eft": eft["points"],
                "eft_partial": eft["partial"]}

    baseline = physiology_baseline(p)
    euro = euroscore2(p)

    meld = None
    bili, inr = _num(row.get("bilirubin_mg_dl")), _num(row.get("inr"))
    if bili is not None and inr is not None:
        meld = meld_from_labs(bili, inr, p["creatinine"])

    # Volume index: submitted directly, or derived from the raw volume and BSA. The
    # site submits the raw measurement; the indexing happens here, for every site.
    lvesvi = _num(row.get("lvesvi_ml_m2"))
    if lvesvi is None:
        lvesv = _num(row.get("lvesv_ml"))
        bsa = bsa_mosteller(p["height"], p["weight"])
        if lvesv is not None and bsa:
            lvesvi = lvesv / bsa

    rhc_fields = ("rhc_map_mmhg", "rhc_co_l_min", "rhc_pvr_wu", "rhc_ci_l_min_m2",
                  "rhc_tapse_mm", "rhc_pasp_mmhg")
    tier = 2 if any(_num(row.get(c)) is not None for c in rhc_fields) else 0

    r = ucsrs(baseline, euro, eft["points"], meld,
              lvesvi=lvesvi, lvedd=_num(row.get("lvedd_mm")),
              syntax=_num(row.get("syntax_score")), tier=tier,
              map_mmhg=_num(row.get("rhc_map_mmhg")), co=_num(row.get("rhc_co_l_min")),
              pvr=_num(row.get("rhc_pvr_wu")), ci=_num(row.get("rhc_ci_l_min_m2")),
              tapse=_num(row.get("rhc_tapse_mm")), pasp_rhc=_num(row.get("rhc_pasp_mmhg")))

    outcomes = ucsrs_outcomes(r["final"], {
        "lvef": p["lvef"], "copd": p["lungAny"], "smoker": p["smoker"],
        "nyha": p["nyha"], "critical": p["critical"], "urgency": p["urgency"],
        "cc": creatinine_clearance(p["age"], p["weight"], p["creatinine"], p["female"]),
        "dialysis": p["dialysis"], "iddm": p["iddm"], "age": p["age"],
        "arteriopathy": p["arteriopathy"], "aorticAtheroma": p["aorticAtheroma"],
        "neuro": p["neuro"], "afib": p["afib"], "aorta": p["thoracicAorta"],
        "endocarditis": p["endocarditis"], "prevCardiac": p["prevCardiac"],
        "radiation": p["radiation"], "immuno": p["immuno"],
    })

    return {
        "ucsrs": r["final"], "blockers": [],
        "baseline_pct": baseline, "euroscore2_computed_pct": euro,
        "br": r["br"], "meld": meld, "meld_correction": r["meldCorr"],
        "pre_frailty": r["preCfs"], "eft": eft["points"], "eft_partial": eft["partial"],
        "eft_multiplier": r["mult"], "post_frailty": r["base"],
        "lv_increment": r["lv"], "lv_source": r["lvSource"],
        "syntax_increment": r["syntax"], "rhc_increment": r["hemo"], "tier": tier,
        "est_stroke_pct": outcomes["stroke"], "est_renal_pct": outcomes["renal"],
        "est_vent_pct": outcomes["vent"], "est_reop_pct": outcomes["reop"],
    }


def p_chair(row: Dict[str, Any]) -> Optional[str]:
    v = _text(row.get("chair_rise"))
    return v or None
