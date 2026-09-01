# UCSRS — Universal Cardiac Surgical Risk Score

Reference implementation of UCSRS, developed from the architecture specified in Section 3.3 of:

> Rehman A. Universal cardiac surgical risk score (UCSRS v1.0): a unified physiology-informed
> risk architecture for operative mortality prediction across all adult cardiac surgical
> procedures. *J Cardiothorac Surg* 2026. DOI 10.1186/s13019-026-04433-x

**Calculator:** https://ucsrs-calculator.netlify.app · Open source (MIT)

## What is deployed: UCSRS v2.1

The deployed calculator implements **UCSRS v2.1**. The published layer architecture is
unchanged — Layer 1 is still `0.50 × baseline + 0.50 × EuroSCORE II`, and Layers 2a, 2b, 2c
and 3 are untouched — but the baseline inside Layer 1 has been re-derived and one weight has
been removed. The four companion 30-day estimates are unchanged. Every departure from the
published v1.0 model is listed below, dated, and settled **before the first enrolment** of
the ATLAS validation study.

### Departures from published v1.0

**1. Layer 1 is independent** (v2.0, 27 Aug 2026). The published Section 3.3 specifies
`BR = (0.50 × STS-PROM%) + (0.50 × EuroSCORE II%)` with STS-PROM supplied by the site from
the official STS calculator. From v2.0 the baseline is computed from the patient's own
clinical variables instead. STS-PROM is **not an input**. Two reasons: requiring it means
computing three scores per patient indefinitely, and a score that consumes STS-PROM cannot
be fairly compared against it in validation. No value computed here is labelled STS-PROM;
the internal component is the *physiology-derived baseline*.

**2. Frailty instrument** (v1.1). Layer 2b uses the Essential Frailty Toolset (EFT, 0–5)
rather than the Clinical Frailty Scale, at the request of participating sites, for
objectivity and inter-rater reliability.

**3. Weights reduced** (v2.0). The frailty ladder and the MELD slopes are each reduced by
25% from the published values.

**4. The baseline is re-derived in log-odds** (v2.1, 28 Aug 2026). See below.

### What changed in v2.1

*The defect.* 85.6% of the v2.0 baseline's mass sat on variables EuroSCORE II already
scores. Under `BR = 0.5 × baseline + 0.5 × EuroSCORE II` a shared variable was therefore
counted about one and a half times — half of EuroSCORE's coefficient plus half of the
baseline's own increment — while a variable only UCSRS carries was counted at half weight.
The redundant part was inflated and the distinctive part was halved. Against published
observed mortality across thirteen registries this showed as a median O/E of 0.70: the
score over-predicted, and it over-predicted most in the patients at least risk.

*The fix, in four moves, all inside the published 50/50:*

1. **Log-odds form.** Increments move from percentage points to log-odds at a 3% reference
   risk. Odds multiply, so risk fans out; the additive-percentage form compressed the range
   to about 5× across the registry cohorts against EuroSCORE II's 9.2×. The relative
   ordering of every weight is preserved exactly.
2. **Unique terms doubled.** Anaemia, atrial fibrillation, ascending or arch atheroma and
   the untreated-severe-valve burden are multiplied by two, so that after the 0.5 blend
   they arrive at full strength rather than half.
3. **Shared terms scaled, and three read continuously.** One factor *k* = 1.15 shrinks the
   duplicated terms. Age, creatinine clearance and ejection fraction move from bands to
   continuous functions — EuroSCORE II reads age continuously and STS reads creatinine
   continuously, and banding was discarding most of their information.
4. **Hypertension is no longer weighted.** Neither parent model weights it for operative
   mortality, and at roughly 70% prevalence a +0.30 percentage-point increment was adding
   risk to two patients in three. The field is still collected as a descriptor.

*How the constants were set.* `k` and the intercept were solved together against
**published observed mortality** across thirteen registries — not against either
comparator — for a median O/E of 1.00, then checked on two independent cohort
realisations that took no part in the fit (medians 1.000 / 1.007 / 1.002). Fitting the
baseline to EuroSCORE II was considered and rejected: it would collapse Layer 1 onto
EuroSCORE II and undo the independence won in v2.0.

*What this is not.* **No performance claim is made.** The cohorts used to set the
constants are synthetic; no simulated patient has an outcome. Whether the score's
divergence from its comparators is correct can only be answered by ATLAS.

| | median O/E | in 0.80–1.25 | mean \|log O/E\| | dynamic range |
|---|---|---|---|---|
| UCSRS v2.0 | 0.70 | 4/13 | 0.395 | 5.0× |
| **UCSRS v2.1** | **0.97** | **8/13** | **0.235** | **8.7×** |
| EuroSCORE II (published) | 0.85 | 5/13 | 0.258 | 9.2× |
| STS-PROM (published) | 1.10 | 8/12 | 0.295 | — |


### The published worked cases no longer reproduce

| Published case | Paper prints | v2.1 produces |
|---|---|---|
| Case 1 | 4.80% | **4.35%** |
| Case 2 | 7.35% | **6.20%** |

Unchanged from v2.0: the paper supplies these two cases' baseline and EuroSCORE II as given
inputs, and v2.1 changed only how a baseline is derived, not the layer arithmetic. The
divergence is deliberate and dated, not an implementation error. `test_calculator.js` prints
the published value alongside the current one at every affected assertion.

## Files

| File | Purpose |
|---|---|
| `index.html` | The calculator. Self-contained; all computation in the browser; no data transmitted. |
| `test_calculator.js` | Acceptance test. Run `node test_calculator.js` — 233 checks against the specification, including the worked cases, the EFT scoring rules, the reduced ladder identity, the v2.1 log-odds behaviour and every EuroSCORE II coefficient (Nashef et al., EJCTS 2012, Table 6). |
| `ucsrs_engine.py` | Python port of the engine block, for the ATLAS analysis. The JavaScript is normative. |
| `test_engine_parity.py`, `parity_runner.js` | Prove the port agrees with the calculator to within 0.005 percentage points on all 15 reported quantities, over 4,000 random patients. Requires node. |
| `sw.js`, `manifest.json`, icons | Progressive-web-app shell for offline use. |

## Model notes

- **Layer 1** — `0.50 × physiology-derived baseline + 0.50 × EuroSCORE II`, both computed
  internally from the entered clinical variables. Capped at 60%. The baseline is a logistic
  function of a sum of log-odds increments at a 3% reference (intercept −6.0777, shared
  scale *k* = 1.15, unique terms ×2), clamped to 0.30–50%.
- **EuroSCORE II** is computed from the published coefficients (Nashef et al. 2012, Table 6),
  unmodified.
- **Layer 2a** — MELD, additive, optional. Computed from bilirubin, INR and creatinine, with
  creatinine capped at 4.0 mg/dL and no dialysis substitution. Slopes 0.30 / 0.675 / 0.90
  (published: 0.40 / 0.90 / 1.20).
- **Layer 2b** — Essential Frailty Toolset, multiplicative, **mandatory** (labs required; chair
  rise and cognition may be deferred in urgent cases → partial-EFT alert). EFT 0–5 maps to
  ×1.00 / ×1.1125 / ×1.2625 / ×1.45 / ×1.675 / ×1.975. Each multiplier is
  `1 + 0.75 × (published multiplier − 1)`, so the excess above unity is reduced by exactly 25%
  and EFT 0 is unchanged.
- **Layer 2c** — LV dimensions (LVESVI preferred, LVEDD fallback) and SYNTAX, additive, optional.
- **Layer 3** — RHC haemodynamic corrections, additive, Tier 3 only. Final cap 70%.
- **Valve severity** — only an untreated severe aortic stenosis or untreated severe mitral
  regurgitation carries weight. A lesion the operation corrects carries nothing, since the
  procedure term already prices it. Valve etiology is recorded and carries no weight. From
  v2.1 the burden is a log-odds increment per lesion rather than +0.4 percentage points, so
  two untreated lesions charge two equal steps on the odds scale.
- **Renal** — clearance is read continuously below 90 mL/min. Dialysis carries its own term,
  floored at whatever the same patient's clearance alone would score, so starting dialysis can
  never lower the estimate. Without that floor a continuous clearance term overtakes the bare
  categorical below about 15 mL/min.

## Status

This is a **research tool**. It has not been prospectively validated against patient outcomes
and must not be the sole basis for any clinical decision. It does not replace the STS-PROM or
EuroSCORE II calculators in routine use. The UCSRS ATLAS multinational validation study will
test it against observed 30-day outcomes; every correction term, and the v2.1 baseline
coefficients, are provisional until then.

## Version history

- **v2.1.0** (28 Aug 2026) — UCSRS v2.1. Layer 1 baseline re-derived in log-odds at a 3%
  reference to remove the double-counting of variables EuroSCORE II already scores; unique
  terms doubled; shared terms scaled by *k* = 1.15; age, creatinine clearance and ejection
  fraction read continuously; hypertension no longer weighted; baseline floor 0.50% → 0.30%;
  dialysis floored against the clearance term to remove an inversion below ~15 mL/min. The
  four companion estimates are unchanged. Published worked cases unchanged from v2.0.
  Acceptance test extended to 233 checks.
- **v2.0.0** (27 Aug 2026) — UCSRS v2.0. Layer 1 made independent: the score no longer takes
  STS-PROM as an input. Baseline floor lowered 1.50% → 0.50%. Frailty ladder and MELD slopes
  each reduced 25%. Published worked cases no longer reproduce (4.80 → 4.35, 7.35 → 6.20).
  Procedure list expanded to 24 categories with repair and replacement distinguished at every
  valve position; graded heart-failure, renal, pulmonary, shock, arteriopathy and infarct-recency
  fields; valve severity and etiology recorded. Fixed a wiring defect that had silently zeroed
  the untreated-severe-valve term. Acceptance test extended to 227 checks.
- **v1.1.0** (Aug 2026) — Layer 2b frailty instrument changed from the Clinical Frailty Scale to
  the Essential Frailty Toolset (0–5), multiplier ladder unchanged at that point. Units toggle
  added for conventional and SI laboratory values.
- **v1.0** (Jul 2026) — initial release.
