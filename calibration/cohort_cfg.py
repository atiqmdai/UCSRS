"""CONFIGURABLE COPY of cohort.py for the 20 Sep quartile experiment.

Identical to cohort.py except that the three optional-domain availability rates are
module constants rather than literals, so an arm can force complete data. Nothing else
differs; the distributions the values are drawn from are untouched.

"""
_ORIGINAL_DOCSTRING = """Synthetic cohort generator for the UCSRS v3.0 registry-anchored calibration run.

METHOD (unchanged from the v2.1 precedent, UCSRS_Methods_Paper_In_Silico_Boundary.md 4.3):

  For each of the thirteen anchorable registries the target mean predicted risk is
  published observed mortality / published EuroSCORE II O/E. A single severity dial is
  then tuned until the synthetic cohort's mean EuroSCORE II equals that target.

  The patients are invented; the target is not. That is the only point at which
  real-world information enters the exercise.

  NO SIMULATED PATIENT IS ASSIGNED AN OUTCOME AT ANY STAGE, and no outcome model is
  used anywhere in this file.

CONSTRUCTION. One latent severity z ~ Normal(dial, 1) per patient. Every risk factor is
drawn conditional on z through a probit-style threshold or a monotone shift, so the mean
EuroSCORE II of the cohort is monotone in the dial and the solve is well posed in one
dimension. The dial is the ONLY quantity fitted per registry; every marginal below is
fixed across all thirteen cohorts and was set before any registry was scored.

Patients are emitted as ATLAS submission-file ROWS and scored through
ucsrs_engine.patient_from_row(), i.e. through exactly the code path a real enrolled
patient takes. Building the engine's patient object directly was rejected: that is the
route that silently dropped pulmStatus once already (see the 15 Sep BUGFIX note in
patient_from_row).

CASE-MIX MARGINALS are representative of a large adult cardiac surgical registry and are
investigator-facing assumptions, not fitted quantities. They materially affect the mean
UCSRS of each cohort and therefore the O/E result, which is one of the reasons this
exercise cannot support a claim of superiority over either comparator.
"""
import numpy as np

# ---- experiment knobs (default = identical behaviour to cohort.py) ----
EFT_COMPLETE = False    # True: chair rise and cognition recorded on every patient
MELD_COMPLETE = False   # True: bilirubin and INR recorded on every patient
RHC_RATE = None         # float: force a flat right-heart-catheter rate


# ---------------------------------------------------------------- case mix
# Procedure mix of a representative adult cardiac surgical population. Shares sum to 1.
# Index order is fixed; complexity rises left to right and the severity dial tilts the
# draw toward the right-hand tail.
PROCEDURES = [
    "cabg",                    # isolated CABG
    "avr",                     # isolated AVR
    "mv_repair",               # isolated MV repair
    "mvr",                     # isolated MV replacement
    "tv_repair",               # isolated TV repair
    "cabg_avr",                # CABG + AVR
    "cabg_mv_repair",          # CABG + MV repair
    "cabg_mvr",                # CABG + MVR
    "avr_mvr",                 # double valve
    "avr_mv_repair_tv_repair", # triple valve
    "asc_aorta",               # ascending aorta
    "avr_asc_aorta",           # AVR + ascending
    "avr_root_asc_aorta",      # Bentall
    "cabg_asc_aorta",          # CABG + ascending
    "other",
]
PROC_BASE = np.array([
    0.520, 0.105, 0.045, 0.035, 0.010,
    0.075, 0.030, 0.025, 0.030, 0.012,
    0.030, 0.015, 0.012, 0.011, 0.045,
])
PROC_BASE = PROC_BASE / PROC_BASE.sum()
# Complexity rank used to tilt the procedure draw with severity.
PROC_TILT = np.array([
    -0.35, -0.10, -0.15, 0.00, -0.10,
     0.15,  0.15,  0.25, 0.30,  0.50,
     0.25,  0.45,  0.55, 0.40,  0.00,
])


def _probit(p):
    """Threshold on a standard normal giving marginal probability p at dial 0."""
    from scipy.stats import norm
    return norm.ppf(1.0 - p)


class Cohort:
    """Draws n patients at a given severity dial. Vectorized; rows built on demand."""

    def __init__(self, seed):
        self.rng = np.random.default_rng(seed)

    def draw(self, n, dial):
        rng = self.rng
        z = dial + rng.standard_normal(n)          # latent severity
        u = lambda: rng.random(n)                   # independent uniforms

        # ---- demographics -------------------------------------------------
        age = np.clip(rng.normal(66.0, 11.0, n) + 2.6 * z, 18, 95)
        female = u() < 0.29
        height = np.where(female, rng.normal(162, 7, n), rng.normal(175, 7.5, n))
        height = np.clip(height, 140, 200)
        bmi = np.clip(rng.normal(27.5, 5.0, n), 15, 55)
        weight = np.clip(bmi * (height / 100.0) ** 2, 35, 200)

        # ---- procedure ----------------------------------------------------
        # Multiplicative tilt in log space, renormalized per patient.
        logw = np.log(PROC_BASE)[None, :] + np.outer(z, PROC_TILT)
        w = np.exp(logw - logw.max(axis=1, keepdims=True))
        w /= w.sum(axis=1, keepdims=True)
        cum = w.cumsum(axis=1)
        proc_idx = (cum < u()[:, None]).sum(axis=1).clip(0, len(PROCEDURES) - 1)
        procedure = np.array(PROCEDURES, dtype=object)[proc_idx]

        # ---- urgency: elective / urgent / emergency / salvage --------------
        ur = u()
        t_urgent = 0.70 + 0.11 * z
        t_emerg = 0.95 + 0.030 * z
        t_salv = 0.995 + 0.0035 * z
        urgency = np.where(ur < t_urgent, "elective",
                  np.where(ur < t_emerg, "urgent",
                  np.where(ur < t_salv, "emergency", "salvage")))

        # ---- sternotomy number --------------------------------------------
        sr = u()
        operation_number = np.where(sr < 0.940 - 0.052 * z, 1,
                            np.where(sr < 0.992 - 0.007 * z, 2, 3))

        # ---- renal ---------------------------------------------------------
        # Serum creatinine, lognormal with a severity shift. Dialysis and acute renal
        # failure are drawn as separate states.
        creat = np.exp(rng.normal(np.log(1.02), 0.30, n) + 0.145 * z)
        creat = np.clip(creat, 0.4, 12.0)
        rr = u()
        renal_status = np.where(rr < 0.012 + 0.011 * z, "dialysis",
                       np.where(rr < 0.022 + 0.018 * z, "acute", "normal"))

        # ---- ventricle ------------------------------------------------------
        lvef = np.clip(rng.normal(52.0, 11.0, n) - 5.2 * z, 8, 75)

        # ---- heart failure class -------------------------------------------
        hr = u()
        hf = np.where(hr < 0.25 - 0.085 * z, "none",
             np.where(hr < 0.65 - 0.075 * z, "2",
             np.where(hr < 0.92 - 0.020 * z, "3",
             np.where(hr < 0.985 + 0.004 * z, "4", "acute"))))

        # ---- pulmonary ------------------------------------------------------
        pr = u()
        pulm = np.where(pr < 0.780 - 0.090 * z, "none",
               np.where(pr < 0.930 - 0.030 * z, "chronic",
               np.where(pr < 0.970 - 0.005 * z, "chronic_o2",
               np.where(pr < 0.990 + 0.002 * z, "acute", "acute_vent"))))

        # ---- circulatory support -------------------------------------------
        sh = u()
        shock = np.where(sh < 0.952 - 0.060 * z, "none",
                np.where(sh < 0.977 - 0.020 * z, "inotropes",
                np.where(sh < 0.987 - 0.008 * z, "vtvf",
                np.where(sh < 0.995 - 0.004 * z, "iabp",
                np.where(sh < 0.998 - 0.001 * z, "impella", "ecmo")))))

        # ---- recent myocardial infarction ------------------------------------
        # CORRECTED 19 Sep 2026. This previously emitted "21" and "1", which are NOT in
        # the dictionary code list (none / 7 / 30 / 90 -- bands, not raw day counts).
        # physiology_baseline() matches those codes by exact equality, so an invalid
        # code scored ZERO in Layer 1 while still setting recentMI for EuroSCORE II.
        # 10.6% of the 30M run carried an invalid code and mean UCSRS under-read by 4.4%.
        mr = u()
        mi = np.where(mr < 0.760 - 0.075 * z, "none",
             np.where(mr < 0.880 - 0.030 * z, "90",
             np.where(mr < 0.955 - 0.012 * z, "30", "7")))

        # ---- arteriopathy ----------------------------------------------------
        ar = u()
        arterio = np.where(ar < 0.800 - 0.080 * z, "none",
                  np.where(ar < 0.880 - 0.025 * z, "peripheral",
                  np.where(ar < 0.945 - 0.012 * z, "carotid",
                  np.where(ar < 0.982 - 0.005 * z, "ascending", "arch"))))

        # ---- binary comorbidity ----------------------------------------------
        def flag(p0, slope):
            return (u() < np.clip(p0 + slope * z, 0.0, 0.98)).astype(np.int8)

        neuro = flag(0.042, 0.022)
        endocarditis = flag(0.021, 0.014)
        afib = flag(0.155, 0.055)
        smoker = flag(0.205, 0.020)
        radiation = flag(0.009, 0.004)
        immuno = flag(0.025, 0.014)
        htn = flag(0.700, 0.030)
        mobility = flag(0.060, 0.045)
        ccs4 = flag(0.085, 0.045)

        dr = u()
        diabetes = np.where(dr < 0.600 - 0.055 * z, "none",
                   np.where(dr < 0.870 - 0.020 * z, "oral", "insulin"))

        # ---- frailty laboratories (always drawn: taken in every surgical patient) ---
        hgb = np.clip(rng.normal(13.2, 1.75, n) - 0.62 * z, 5.0, 18.5)
        alb = np.clip(rng.normal(3.92, 0.46, n) - 0.16 * z, 1.5, 5.4)

        # ---- pulmonary artery systolic pressure --------------------------------
        pasp = np.clip(rng.normal(35.0, 11.0, n) + 4.4 * z, 12, 110)

        # ---- untreated valve lesions -------------------------------------------
        # Severity strings in the submission-file code list: '<lesion>_<severity>'.
        def valve_col(p_mild, p_mod, p_sev, lesion):
            vr = u()
            return np.where(vr < p_sev + 0.020 * z, lesion + "_severe",
                   np.where(vr < p_sev + p_mod + 0.045 * z, lesion + "_moderate",
                   np.where(vr < p_sev + p_mod + p_mild + 0.06 * z, lesion + "_mild",
                            "none")))

        av_sev = valve_col(0.10, 0.05, 0.030, "s")   # aortic stenosis
        mv_sev = valve_col(0.12, 0.06, 0.035, "r")   # mitral regurgitation
        tv_sev = valve_col(0.14, 0.07, 0.040, "r")   # tricuspid regurgitation

        # ---- optional domains, at the real-world rates of 6C ---------------------
        # Chair rise and cognition require a clinic encounter; most patients are scored
        # on the laboratory components alone (partial mEFT).
        assessed = np.ones(n, dtype=bool) if EFT_COMPLETE else (u() < np.clip(0.36 - 0.10 * z, 0.02, 0.95))
        cr_r = u()
        chair = np.where(~assessed, "",
                np.where(cr_r < 0.55 - 0.16 * z, "fast",
                np.where(cr_r < 0.88 - 0.10 * z, "slow", "unable")))
        cog = np.where(~assessed, "", np.where(u() < np.clip(0.11 + 0.055 * z, 0, 0.9), "1", "0"))

        # MELD is computed where bilirubin and INR are both recorded - liver disease and
        # right-heart failure cases, per the investigator's 15 Sep statement.
        meld_done = np.ones(n, dtype=bool) if MELD_COMPLETE else (u() < np.clip(0.20 + 0.075 * z, 0.02, 0.9))
        bili = np.where(meld_done, np.clip(np.exp(rng.normal(np.log(0.75), 0.55, n) + 0.22 * z), 0.2, 30), np.nan)
        inr = np.where(meld_done, np.clip(rng.normal(1.12, 0.22, n) + 0.09 * z, 0.8, 6.0), np.nan)

        # LV geometry: measured on any transthoracic echo, so close to complete.
        lvedd_done = u() < 0.56
        lvedd = np.where(lvedd_done, np.clip(rng.normal(51, 8, n) + 3.4 * z, 30, 90), np.nan)
        lvesvi_done = u() < 0.20
        lvesvi = np.where(lvesvi_done, np.clip(rng.normal(45, 20, n) + 13.0 * z, 10, 220), np.nan)

        # SYNTAX: most centres do not compute it (6C.2). Only meaningful in CABG cases.
        is_cabg = np.isin(proc_idx, [0, 5, 6, 7, 13])
        syntax_done = is_cabg & (u() < 0.08)
        syntax = np.where(syntax_done, np.clip(rng.normal(24, 9, n) + 3.0 * z, 0, 60), np.nan)

        # Right heart catheterization: a small minority.
        rhc_done = (u() < RHC_RATE) if RHC_RATE is not None else (u() < np.clip(0.045 + 0.02 * z, 0.0, 0.5))
        rhc_map = np.where(rhc_done, np.clip(rng.normal(82, 11, n) - 3.0 * z, 45, 130), np.nan)
        rhc_co = np.where(rhc_done, np.clip(rng.normal(4.6, 1.0, n) - 0.45 * z, 1.5, 9.0), np.nan)
        rhc_pvr = np.where(rhc_done, np.clip(rng.normal(2.3, 1.2, n) + 0.55 * z, 0.3, 14), np.nan)

        return dict(
            n=n, age=age, female=female, height=height, weight=weight,
            procedure=procedure, urgency=urgency, operation_number=operation_number,
            creat=creat, renal_status=renal_status, lvef=lvef, hf=hf, pulm=pulm,
            shock=shock, mi=mi, arterio=arterio, neuro=neuro,
            endocarditis=endocarditis, afib=afib, smoker=smoker, radiation=radiation,
            immuno=immuno, htn=htn, mobility=mobility, ccs4=ccs4, diabetes=diabetes,
            hgb=hgb, alb=alb, pasp=pasp, av=av_sev, mv=mv_sev, tv=tv_sev,
            chair=chair, cog=cog, bili=bili, inr=inr, lvedd=lvedd, lvesvi=lvesvi,
            syntax=syntax, rhc_map=rhc_map, rhc_co=rhc_co, rhc_pvr=rhc_pvr,
        )


def rows(d):
    """Yield ATLAS submission-file rows from a drawn block."""
    n = d["n"]
    age = d["age"]; female = d["female"]; height = d["height"]; weight = d["weight"]
    procedure = d["procedure"]; urgency = d["urgency"]; opn = d["operation_number"]
    creat = d["creat"]; renal = d["renal_status"]; lvef = d["lvef"]; hf = d["hf"]
    pulm = d["pulm"]; shock = d["shock"]; mi = d["mi"]; arterio = d["arterio"]
    neuro = d["neuro"]; endo = d["endocarditis"]; afib = d["afib"]; smoker = d["smoker"]
    radiation = d["radiation"]; immuno = d["immuno"]; htn = d["htn"]
    mobility = d["mobility"]; ccs4 = d["ccs4"]; diabetes = d["diabetes"]
    hgb = d["hgb"]; alb = d["alb"]; pasp = d["pasp"]
    av = d["av"]; mv = d["mv"]; tv = d["tv"]; chair = d["chair"]; cog = d["cog"]
    bili = d["bili"]; inr = d["inr"]; lvedd = d["lvedd"]; lvesvi = d["lvesvi"]
    syntax = d["syntax"]; rmap = d["rhc_map"]; rco = d["rhc_co"]; rpvr = d["rhc_pvr"]

    isnan = np.isnan
    for i in range(n):
        r = {
            "age_years": age[i], "sex": "F" if female[i] else "M",
            "height_cm": height[i], "weight_kg": weight[i],
            "creatinine_mg_dl": creat[i], "renal_status": renal[i],
            "lvef_pct": lvef[i], "heart_failure": hf[i], "pulm_status": pulm[i],
            "shock_support": shock[i], "mi_recency": mi[i],
            "arteriopathy_site": arterio[i], "procedure": procedure[i],
            "urgency": urgency[i], "operation_number": opn[i],
            "hgb_g_dl": hgb[i], "albumin_g_dl": alb[i], "pasp_mmhg": pasp[i],
            "diabetes": diabetes[i], "neuro_dysfunction": neuro[i],
            "endocarditis_active": endo[i], "atrial_fibrillation": afib[i],
            "smoker": smoker[i], "mediastinal_radiation": radiation[i],
            "immunosuppressed": immuno[i], "hypertension": htn[i],
            "poor_mobility": mobility[i], "ccs_class_4": ccs4[i],
            "av_severity": av[i], "mv_severity": mv[i], "tv_severity": tv[i],
        }
        if chair[i]:
            r["chair_rise"] = chair[i]
        if cog[i]:
            r["cog_impaired"] = cog[i]
        if not isnan(bili[i]):
            r["bilirubin_mg_dl"] = bili[i]; r["inr"] = inr[i]
        if not isnan(lvedd[i]):
            r["lvedd_mm"] = lvedd[i]
        if not isnan(lvesvi[i]):
            r["lvesvi_ml_m2"] = lvesvi[i]
        if not isnan(syntax[i]):
            r["syntax_score"] = syntax[i]
        if not isnan(rmap[i]):
            r["rhc_map_mmhg"] = rmap[i]; r["rhc_co_l_min"] = rco[i]
            r["rhc_pvr_wu"] = rpvr[i]
        yield r
