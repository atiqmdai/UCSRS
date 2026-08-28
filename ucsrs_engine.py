#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UCSRS v2.1 — reference implementation in Python.

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

SPEC_VERSION = "2.1.0"

SPEC: Dict[str, Any] = {
    "layer1": {"w_sts": 0.50, "w_euro": 0.50, "cap_br": 60},
    "layer2a_meld": {"cap_pre_cfs": 65},
    # v2.0: the excess above 1.00 is reduced by 25% from the published ladder
    # (1.15/1.35/1.60/1.90/2.30). A deliberate departure, not a correction.
    "layer2b_eft": {
        "mult": {0: 1.00, 1: 1.1125, 2: 1.2625, 3: 1.45, 4: 1.675, 5: 1.975},
        "cap": 70, "hgb_lo_m": 13.0, "hgb_lo_f": 12.0, "alb_lo": 3.5,
    },
    "layer2c": {
        "lvesvi": [("lte", 60, 0.0), ("lte", 100, 0.5), ("gt", 100, 2.0)],
        "lvedd": [("lte", 55, 0.0), ("lte", 65, 0.5), ("gt", 65, 1.5)],
        "syntax": [("lte", 22, 0.0), ("lte", 32, 1.0), ("gt", 32, 2.5)],
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
            "reop": {"prev_cardiac": 0.20, "radiation": 0.20, "immuno": 0.15,
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
    """v2.0: every slope reduced by 25% from the published values
    (0.40/0.90/1.20 -> 0.30/0.675/0.90)."""
    if m is None:
        return 0.0
    if m < 9:
        return 0.0
    if m <= 15:
        return (m - 8) * 0.30
    if m <= 20:
        return 2.10 + (m - 15) * 0.675
    return 5.475 + (m - 20) * 0.90


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
    """Essential Frailty Toolset, 0-5 points. Missing chair rise or cognition gives a
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
        if h < (S["hgb_lo_f"] if female else S["hgb_lo_m"]):
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
    "reference_risk": 0.03,
    "k_shared": 1.15,
    "intercept": -6.0777,
    "unique_multiplier": 2.0,
    "continuous": {"age_per_decade_over_60": 0.26,
                   "log_clearance_below_90": 0.55,
                   "ef_per_10_below_50": 0.30},
}

_REF = BASELINE_A2["reference_risk"]
_K = BASELINE_A2["k_shared"]
_UM = BASELINE_A2["unique_multiplier"]
_C = BASELINE_A2["continuous"]


def _pp_to_logodds(pp):
    """Convert a percentage-point increment to a log-odds increment at the reference."""
    p2 = min(0.60, _REF + pp / 100.0)
    return math.log(p2 / (1 - p2)) - math.log(_REF / (1 - _REF))


# percentage-point increments from v2.0, tagged shared (EuroSCORE II also has it) or not
_TERMS = {
    "age_over_70_per_yr": (0.12, True), "age_over_80_per_yr": (0.20, True),
    "female": (0.40, True), "dialysis": (3.10, True), "iddm": (0.60, True),
    "lung_any": (0.70, True), "ventilated": (2.00, True), "arteriopathy": (1.00, True),
    "prev_cardiac": (2.50, True), "sternotomy3": (1.50, True), "endocarditis": (1.80, True),
    "mi_7": (1.40, True), "mi_30": (0.90, True), "mi_90": (0.50, True),
    "nyha3": (0.50, True), "nyha4": (1.20, True), "acute_decomp": (0.60, True),
    "vtvf": (2.00, True), "iabp": (1.50, True), "impella": (2.00, True),
    "ecmo": (3.50, True), "inotropes": (1.20, True), "anuria": (2.50, True),
    "urgent": (1.00, True), "emergency": (3.50, True), "salvage": (8.00, True),
    "neuro": (0.80, True),
    # absent from EuroSCORE II — doubled so the blend delivers them at full weight
    "anemia": (0.90, False), "afib": (0.40, False),
    "aortic_atheroma": (0.50, False), "valve_burden_per_04": (0.40, False),
}
_W = {k: _pp_to_logodds(pp) * (_K if sh else _UM) for k, (pp, sh) in _TERMS.items()}
_PROC_W = {k: _pp_to_logodds(v) * _K for k, v in PROC_INCREMENT.items()}


def physiology_baseline(p):
    """The UCSRS baseline. Reads no STS-PROM and no EuroSCORE II output."""
    z = BASELINE_A2["intercept"]
    age = p["age"]
    female = bool(p.get("female"))
    cc = creatinine_clearance(age, p.get("weight"), p.get("creatinine"), female)
    lvef = _num(p.get("lvef"))

    # continuous terms
    z += _K * _C["age_per_decade_over_60"] * max(0.0, age - 60) / 10.0
    if age > 70:
        z += _W["age_over_70_per_yr"] * (age - 70)
    if age > 80:
        z += _W["age_over_80_per_yr"] * (age - 80)
    # Renal. Clearance is read continuously below 90; dialysis carries its own term.
    # Dialysis is floored at whatever the same patient's clearance alone would score,
    # so that starting dialysis can never lower the estimate — with a continuous
    # clearance term the bare categorical would otherwise invert below about 15 mL/min.
    _cc_term = (_K * _C["log_clearance_below_90"] * max(0.0, math.log(90.0 / max(cc, 8.0)))
                if cc is not None else 0.0)
    if p.get("dialysis"):
        z += max(_W["dialysis"], _cc_term)
    else:
        z += _cc_term
    if lvef is not None:
        z += _K * _C["ef_per_10_below_50"] * max(0.0, 50.0 - lvef) / 10.0

    if female:
        z += _W["female"]
    if p.get("iddm"):
        z += _W["iddm"]
    if (p["lungAny"] if "lungAny" in p else p.get("pulmonary")):
        z += _W["lung_any"]
    if p.get("ventilated"):
        z += _W["ventilated"]
    vb = valve_burden(p.get("valves"))
    if vb:
        z += _W["valve_burden_per_04"] * (vb / 0.4)
    if p.get("arteriopathy"):
        z += _W["arteriopathy"]
    if p.get("aorticAtheroma"):
        z += _W["aortic_atheroma"]
    if p.get("prevCardiac"):
        z += _W["prev_cardiac"]
    if (p.get("sternotomy") or 1) >= 3:
        z += _W["sternotomy3"]
    if p.get("endocarditis"):
        z += _W["endocarditis"]
    md = p.get("miDays")
    if md in (7, 30, 90):
        z += _W[f"mi_{md}"]
    if p.get("acuteDecomp"):
        z += _W["acute_decomp"]
    if p.get("afib"):
        z += _W["afib"]
    if p.get("neuro"):
        z += _W["neuro"]
    if p.get("anemia"):
        z += _W["anemia"]
    for k in ("vtvf", "iabp", "impella", "ecmo"):
        if p.get(k):
            z += _W[k]
    if p.get("inot"):
        z += _W["inotropes"]
    if p.get("anuria"):
        z += _W["anuria"]
    n = p.get("nyha")
    if n == 3:
        z += _W["nyha3"]
    elif n == 4:
        z += _W["nyha4"]
    u = p.get("urgency")
    if u in ("urgent", "emergency", "salvage"):
        z += _W[u]
    z += _PROC_W.get(p.get("procedure"), 0.0)

    return min(max(100.0 / (1.0 + math.exp(-z)), 0.30), 50.0)


# backwards-compatible alias: the JavaScript name
sts_estimate = physiology_baseline


# ---------------------------------------------------------------- the score
def ucsrs(baseline_pct: float, euro_pct: float, eft: int, meld: Optional[float],
          lvesvi=None, lvedd=None, syntax=None, tier: int = 0,
          map_mmhg=None, co=None, pvr=None, ci=None, tapse=None,
          pasp_rhc=None) -> Dict[str, Any]:
    S = SPEC
    br = min(S["layer1"]["w_sts"] * baseline_pct + S["layer1"]["w_euro"] * euro_pct,
             S["layer1"]["cap_br"])

    meld_corr = meld_correction(meld)
    pre_cfs = min(br + meld_corr, S["layer2a_meld"]["cap_pre_cfs"])

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

    final = min(base + lv + sx + hemo, S["layer3"]["cap_final"])

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
