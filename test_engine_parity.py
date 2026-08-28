#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prove that the Python engine and the published JavaScript calculator agree.

The calculator is the normative implementation: it is what is published, archived
and used at the bedside. ucsrs_engine.py is a port, and a port drifts unless
something holds it in place. This is that something.

It generates random patients across the whole input space — every procedure, every
urgency, every renal and shock and pulmonary state, missing and present optional
domains — scores each through both implementations, and fails on any disagreement
greater than 0.005 percentage points on any reported quantity.

Requires node. Sites do not need node; only this test does.
"""
import json
import random
import subprocess
import sys
from pathlib import Path

import ucsrs_engine as E

HERE = Path(__file__).resolve().parent
TOL = 0.005
N = 4000

PROCEDURES = list(E.PROC_INCREMENT.keys())
URGENCIES = ["elective", "urgent", "emergency", "salvage"]
RENAL = ["normal", "ckd", "acute", "dialysis"]
PULM = ["none", "acute", "acute_vent", "chronic", "chronic_o2"]
SHOCK = ["none", "inotropes", "vtvf", "iabp", "impella", "ecmo"]
ARTERIO = ["none", "carotid", "ascending", "arch", "peripheral"]
MI = ["none", "7", "30", "90"]
HF = ["none", "1", "2", "3", "4", "acute"]
SEVERITY = ["none", "s_mild", "s_moderate", "s_severe",
            "r_mild", "r_moderate", "r_severe"]
CHAIR = ["", "fast", "slow", "unable"]


def maybe(rng, value, p=0.5):
    """A blank in the submission file, half the time — the optional domains have to
    be exercised absent as well as present."""
    return value if rng.random() < p else ""


def random_row(rng):
    sex = rng.choice(["M", "F"])
    return {
        "age_years": rng.randint(18, 95),
        "sex": sex,
        "weight_kg": round(rng.uniform(38, 180), 1),
        "height_cm": rng.randint(145, 200),
        "procedure": rng.choice(PROCEDURES),
        "urgency": rng.choice(URGENCIES),
        "operation_number": rng.choice([1, 1, 1, 2, 3]),
        "lvef_pct": rng.randint(10, 75),
        "heart_failure": rng.choice(HF),
        "pasp_mmhg": maybe(rng, rng.randint(15, 110), 0.8),
        "ccs_class_4": rng.choice([0, 1]),
        "creatinine_mg_dl": round(rng.uniform(0.4, 8.0), 2),
        "renal_status": rng.choice(RENAL),
        "diabetes": rng.choice(["none", "oral", "insulin"]),
        "pulm_status": rng.choice(PULM),
        "arteriopathy_site": rng.choice(ARTERIO),
        "shock_support": rng.choice(SHOCK),
        "mi_recency": rng.choice(MI),
        "hypertension": rng.choice([0, 1]),
        "smoker": rng.choice([0, 1]),
        "neuro_dysfunction": rng.choice([0, 1]),
        "endocarditis_active": rng.choice([0, 1]),
        "atrial_fibrillation": rng.choice([0, 1]),
        "mediastinal_radiation": rng.choice([0, 1]),
        "immunosuppressed": rng.choice([0, 1]),
        "av_severity": rng.choice(SEVERITY),
        "mv_severity": rng.choice(SEVERITY),
        "tv_severity": rng.choice(SEVERITY),
        "hgb_g_dl": round(rng.uniform(6.0, 18.0), 1),
        "albumin_g_dl": round(rng.uniform(1.8, 5.2), 1),
        "chair_rise": rng.choice(CHAIR),
        "cog_impaired": rng.choice(["", "0", "1"]),
        "poor_mobility": rng.choice([0, 1]),
        "bilirubin_mg_dl": maybe(rng, round(rng.uniform(0.2, 25), 1), 0.7),
        "inr": maybe(rng, round(rng.uniform(0.9, 5.0), 2), 0.7),
        "lvesv_ml": maybe(rng, round(rng.uniform(15, 300)), 0.35),
        "lvesvi_ml_m2": maybe(rng, round(rng.uniform(12, 180), 1), 0.2),
        "lvedd_mm": maybe(rng, rng.randint(30, 85), 0.6),
        "syntax_score": maybe(rng, rng.randint(0, 60), 0.3),
        "rhc_map_mmhg": maybe(rng, rng.randint(40, 130), 0.15),
        "rhc_co_l_min": maybe(rng, round(rng.uniform(1.5, 9.0), 2), 0.15),
        "rhc_pvr_wu": maybe(rng, round(rng.uniform(0.3, 12), 2), 0.15),
        "rhc_ci_l_min_m2": maybe(rng, round(rng.uniform(0.9, 5.0), 2), 0.15),
        "rhc_tapse_mm": maybe(rng, rng.randint(6, 32), 0.15),
        "rhc_pasp_mmhg": maybe(rng, rng.randint(15, 110), 0.15),
    }


def js_case(row):
    """Build the JavaScript side's inputs through the SAME mapping the Python side
    uses, so the test compares the arithmetic rather than two mappings."""
    p = E.patient_from_row(row)
    cog_raw = E._text(row.get("cog_impaired"))
    frailty = {
        "chair": E._text(row.get("chair_rise")),
        "cogImpaired": None if cog_raw == "" else cog_raw == "1",
        "hgb": E._num(row.get("hgb_g_dl")),
        "albumin": E._num(row.get("albumin_g_dl")),
        "female": p["female"],
    }
    bili, inr = E._num(row.get("bilirubin_mg_dl")), E._num(row.get("inr"))
    meld = None if (bili is None or inr is None) else {
        "bili": bili, "inr": inr, "cr": p["creatinine"]}

    lvesvi = E._num(row.get("lvesvi_ml_m2"))
    if lvesvi is None:
        lvesv = E._num(row.get("lvesv_ml"))
        bsa = E.bsa_mosteller(p["height"], p["weight"])
        if lvesv is not None and bsa:
            lvesvi = lvesv / bsa

    rhc = ("rhc_map_mmhg", "rhc_co_l_min", "rhc_pvr_wu", "rhc_ci_l_min_m2",
           "rhc_tapse_mm", "rhc_pasp_mmhg")
    tier = 2 if any(E._num(row.get(c)) is not None for c in rhc) else 0

    return {
        "patient": p, "frailty": frailty, "meld": meld,
        "lvesvi": lvesvi, "lvedd": E._num(row.get("lvedd_mm")),
        "syntax": E._num(row.get("syntax_score")), "tier": tier,
        "map": E._num(row.get("rhc_map_mmhg")), "co": E._num(row.get("rhc_co_l_min")),
        "pvr": E._num(row.get("rhc_pvr_wu")), "ci": E._num(row.get("rhc_ci_l_min_m2")),
        "tapse": E._num(row.get("rhc_tapse_mm")), "pasprhc": E._num(row.get("rhc_pasp_mmhg")),
        "outcomeContext": {
            "lvef": p["lvef"], "copd": p["lungAny"], "smoker": p["smoker"],
            "nyha": p["nyha"], "critical": p["critical"], "urgency": p["urgency"],
            "cc": E.creatinine_clearance(p["age"], p["weight"], p["creatinine"], p["female"]),
            "dialysis": p["dialysis"], "iddm": p["iddm"], "age": p["age"],
            "arteriopathy": p["arteriopathy"], "aorticAtheroma": p["aorticAtheroma"],
            "neuro": p["neuro"], "afib": p["afib"], "aorta": p["thoracicAorta"],
            "endocarditis": p["endocarditis"], "prevCardiac": p["prevCardiac"],
            "radiation": p["radiation"], "immuno": p["immuno"],
        },
    }


def check_constants():
    """The procedure lookup tables live outside the engine block, in the calculator's
    form code, and the Python port duplicates them by hand. Random patients would not
    catch a table that had drifted for a procedure they happened not to draw, so
    compare the tables themselves."""
    proc = subprocess.run(["node", str(HERE / "parity_runner.js"), "--constants"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return [("node --constants failed", proc.stderr.strip()[:200], "")]
    js = json.loads(proc.stdout)
    problems = []

    if {k: sorted(v) for k, v in js["PROC_VALVES"].items()} != \
            {k: sorted(v) for k, v in E.PROC_VALVES.items()}:
        problems.append(("PROC_VALVES", sorted(E.PROC_VALVES), sorted(js["PROC_VALVES"])))
    if js["PROC_WEIGHT"] != E.PROC_WEIGHT:
        problems.append(("PROC_WEIGHT",
                         sorted(set(E.PROC_WEIGHT.items()) ^ set(js["PROC_WEIGHT"].items())), ""))
    if set(js["AORTA_PROCS"]) != E.AORTA_PROCS:
        problems.append(("AORTA_PROCS", E.AORTA_PROCS, js["AORTA_PROCS"]))

    jspec = js["SPEC"]
    if jspec["layer1"] != E.SPEC["layer1"]:
        problems.append(("layer1 weights", E.SPEC["layer1"], jspec["layer1"]))
    js_mult = {int(k): v for k, v in jspec["layer2b_eft"]["mult"].items()}
    if js_mult != E.SPEC["layer2b_eft"]["mult"]:
        problems.append(("frailty ladder", E.SPEC["layer2b_eft"]["mult"], js_mult))
    if jspec["euroscore2"] != E.SPEC["euroscore2"]:
        diff = {k for k in jspec["euroscore2"]
                if jspec["euroscore2"][k] != E.SPEC["euroscore2"].get(k)}
        problems.append(("EuroSCORE II coefficients", sorted(diff), ""))
    if jspec["outcomes"] != E.SPEC["outcomes"]:
        diff = [k for k in ("anchor_mort", "slopes", "anchors", "modifiers")
                if jspec["outcomes"].get(k) != E.SPEC["outcomes"].get(k)]
        problems.append(("companion outcome constants", diff, ""))
    if jspec["valve_severity"] != E.SPEC["valve_severity"]:
        problems.append(("valve severity weights",
                         E.SPEC["valve_severity"], jspec["valve_severity"]))
    if jspec["spec_version"] != E.SPEC_VERSION:
        problems.append(("spec_version", E.SPEC_VERSION, jspec["spec_version"]))

    # every procedure the calculator offers must be priced by the Python port
    for pr in js["PROC_WEIGHT"]:
        if pr not in E.PROC_INCREMENT:
            problems.append(("procedure missing from PROC_INCREMENT", pr, ""))
    return problems


def main():
    rng = random.Random(20260827)
    rows = [random_row(rng) for _ in range(N)]
    cases = [js_case(r) for r in rows]

    proc = subprocess.run(
        ["node", str(HERE / "parity_runner.js")],
        input=json.dumps(cases), capture_output=True, text=True)
    if proc.returncode != 0:
        print("node failed:\n" + proc.stderr, file=sys.stderr)
        return 2
    js = json.loads(proc.stdout)

    # keys compared: every layer, the final score, both derived quantities and all
    # four companion outcomes
    COMPARE = [
        ("baseline", "baseline_pct"), ("euro", "euroscore2_computed_pct"),
        ("br", "br"), ("meldCorr", "meld_correction"), ("preCfs", "pre_frailty"),
        ("mult", "eft_multiplier"), ("base", "post_frailty"),
        ("lv", "lv_increment"), ("syntax", "syntax_increment"), ("hemo", "rhc_increment"),
        ("final", "ucsrs"), ("stroke", "est_stroke_pct"), ("renal", "est_renal_pct"),
        ("vent", "est_vent_pct"), ("reop", "est_reop_pct"),
    ]

    failures = []
    for i, (row, j) in enumerate(zip(rows, js)):
        py = E.score_row(row)
        if py["ucsrs"] is None:
            failures.append((i, "python refused to score a complete row",
                             py["blockers"], ""))
            continue
        if py["eft"] != j["eft"]:
            failures.append((i, "eft", py["eft"], j["eft"]))
        if (py["meld"] or 0) != (j["meld"] or 0):
            failures.append((i, "meld", py["meld"], j["meld"]))
        for js_key, py_key in COMPARE:
            a, b = py.get(py_key), j.get(js_key)
            if a is None and b is None:
                continue
            if a is None or b is None:
                failures.append((i, py_key, a, b))
                continue
            if abs(a - b) > TOL:
                failures.append((i, py_key, a, b))

    print(f"UCSRS engine parity — Python port vs published JavaScript")
    print(f"cases: {N}   tolerance: {TOL} percentage points")

    const_problems = check_constants()
    if const_problems:
        print(f"\nFAILED — {len(const_problems)} constant table(s) disagree:")
        for name, a, b in const_problems:
            print(f"  {name}: python={a}  javascript={b}")
        return 1
    print("constant tables agree: procedure maps, layer 1 weights, frailty ladder, "
          "EuroSCORE II coefficients, valve weights, spec version.")

    if failures:
        print(f"\nFAILED — {len(failures)} disagreement(s); first 20:")
        for i, key, a, b in failures[:20]:
            print(f"  case {i}: {key}  python={a}  javascript={b}")
            if key == "ucsrs":
                print(f"    row: {json.dumps(rows[i])}")
        return 1

    scored = [E.score_row(r)["ucsrs"] for r in rows]
    lo, hi = min(scored), max(scored)
    print(f"\nPASSED — all {len(COMPARE)} reported quantities agree on every case.")
    print(f"scores ranged {lo:.2f}% to {hi:.2f}%, "
          f"{sum(1 for s in scored if s >= 69.99)} at the 70% cap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
