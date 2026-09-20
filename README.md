# UCSRS — Universal Cardiac Surgical Risk Score

Reference implementation of UCSRS, developed from the architecture specified in Section 3.3 of:

> Rehman A. Universal cardiac surgical risk score (UCSRS v1.0): a unified physiology-informed
> risk architecture for operative mortality prediction across all adult cardiac surgical
> procedures. *J Cardiothorac Surg* 2026. DOI 10.1186/s13019-026-04433-x

**Calculator:** https://ucsrs-calculator.netlify.app · Free for non-commercial (clinical, research, academic) use, [CC BY-NC 4.0](LICENSE)

## What is deployed: UCSRS v3.1 (SPEC_VERSION 3.1.0)

The deployed calculator implements **UCSRS v3.1**. Two changes sit on top of the published
v1.0 architecture, made at two different times for two different reasons:

- **v3.0 (19 September 2026) — architecture.** Layer 1 stopped blending with EuroSCORE II
  and became a single log-odds baseline computed only from the patient's own clinical
  variables; EuroSCORE II is still computed, but solely as an external comparator that never
  enters the UCSRS score. The renal term moved from creatinine clearance to serum creatinine
  read directly. The frailty instrument became the modified Essential Frailty Toolset (mEFT,
  0–6), adding a second haemoglobin point below 8.0 g/dL to the published EFT (0–5). Dialysis
  patients are scored, centrally, as if creatinine were 4.0 mg/dL, in both Layer 1 and MELD —
  sites/users submit the actual measured value; the substitution is applied by the engine.
- **v3.1 (20 September 2026) — calibration.** No architectural change. The single constant
  that sets Layer 1's overall level (`calibration_shift`) was re-derived and locked by a
  registry-anchored calibration: solved so that, across thirteen published surgical
  registries, UCSRS's mean predicted risk matches each registry's own published mortality
  divided by that registry's own published EuroSCORE II observed/expected ratio — targeting a
  median observed/expected ratio of 1.00. This is a real dependency on EuroSCORE II's
  published statistics, distinct from and in addition to Layer 1 no longer taking EuroSCORE II
  as a per-patient input; both are stated because they are different claims.

Two development runs at this step were found defective and discarded rather than corrected in
place: one where the synthetic-cohort generator emitted MI codes the engine's code list did
not match, silently zeroing recent-MI in Layer 1 for part of the cohort; and one where the
scoring wrapper called the published MELD formula instead of the creatinine-suppressed variant
the architecture actually uses. Both are disclosed, with what each run showed and why it was
voided, rather than deleted from the record. The calibration that shipped is a confirmatory run
followed by an independent locking run, each 30,000,000 synthetic patients, reproduced on two
further hold-out cohorts.

**No performance claim is made anywhere in this repository.** No simulated patient is assigned
an outcome at any stage, and no outcome model is used. What is matched is a population mean
predicted risk against a published population mean — not an individual prediction against an
individual outcome. Whether UCSRS's risk estimates track real 30-day outcomes is the question
the UCSRS ATLAS multinational validation study is designed to answer, and it remains open.

By investigator ruling, no coefficient or constant in this engine moves again before ATLAS
reaches 5,000 enrolled patients.

### Declared, open items carried into ATLAS

- **Creatinine is double-counted by design.** Layer 1's renal term and MELD both read serum
  creatinine. This was considered and kept deliberately (investigator ruling, 19 September
  2026) rather than removed, and it sets a structural floor on achievable MELD at high
  creatinine (roughly 15 at Cr 2.0 mg/dL, roughly 22 at Cr 4.0 mg/dL).
- **High-risk behaviour is unresolved.** A 1,000,000-patient high-risk validation run (complete
  mEFT and MELD) produced UCSRS estimates 17–45× EuroSCORE II's, with 40.1% of patients
  reaching the engine's 70% cap — most likely multiplicative compounding between the MELD and
  mEFT layers. This is disclosed as an open item, not corrected, pending ATLAS data.

## Departures from published v1.0 (v1.1 – v2.1, superseded by v3.0/v3.1 above)

Retained here as the dated development record; the architecture these entries describe is no
longer what is deployed — see "What is deployed" above.

**1. Layer 1 is independent** (v2.0, 27 Aug 2026). The published Section 3.3 specifies
`BR = (0.50 × STS-PROM%) + (0.50 × EuroSCORE II%)` with STS-PROM supplied by the site from
the official STS calculator. From v2.0 the baseline is computed from the patient's own
clinical variables instead. STS-PROM is **not an input**, in any version since.

**2. Frailty instrument** (v1.1). Layer 2b uses the Essential Frailty Toolset (EFT, 0–5)
rather than the Clinical Frailty Scale, at the request of participating sites, for
objectivity and inter-rater reliability. Extended to mEFT (0–6) at v3.0 — see above.

**3. Weights reduced** (v2.0). The frailty ladder and the MELD slopes were each reduced by
25% from the published values, inside the v2.0/v2.1 blended architecture. Superseded at v3.0,
where the blend itself was removed.

**4. The baseline was re-derived in log-odds** (v2.1, 28 Aug 2026), inside the 50/50 blend.
Superseded at v3.0, which removed the blend and re-derived Layer 1 again as a single model.

### What changed in v2.1 (historical — superseded at v3.0)

*The defect.* 85.6% of the v2.0 baseline's mass sat on variables EuroSCORE II already
scores. Under `BR = 0.5 × baseline + 0.5 × EuroSCORE II` a shared variable was therefore
counted about one and a half times — half of EuroSCORE's coefficient plus half of the
baseline's own increment — while a variable only UCSRS carries was counted at half weight.
Against published observed mortality across thirteen registries this showed as a median O/E
of 0.70. The v2.1 fix (log-odds form, doubled unique terms, a shared-term scale factor,
continuous age/creatinine-clearance/ejection-fraction, and dropping the hypertension term)
brought that to a median O/E of 0.97 across the same thirteen registries — still inside the
now-superseded blended architecture.

### The published worked cases no longer reproduce

| Published case | Paper prints | v2.1 produced |
|---|---|---|
| Case 1 | 4.80% | 4.35% |
| Case 2 | 7.35% | 6.20% |

The divergence is deliberate and dated, not an implementation error, and predates v3.0/v3.1.
`test_calculator.js` prints the published value alongside the current one at every affected
assertion.

## Files

| File | Purpose |
|---|---|
| `index.html` | The calculator. Self-contained; all computation in the browser; no data transmitted. |
| `test_calculator.js` | Acceptance test against the specification, including the worked cases, the mEFT scoring rules, and every EuroSCORE II coefficient (Nashef et al., EJCTS 2012, Table 6). |
| `ucsrs_engine.py` | Python port of the engine block, for the ATLAS analysis. The JavaScript is normative. `SPEC_VERSION` is written into every result. |
| `test_engine_parity.py`, `parity_runner.js` | Prove the port agrees with the calculator to within 0.005 percentage points on all reported quantities, over 4,000 random patients. Requires node. |
| `sw.js`, `manifest.json`, icons | Progressive-web-app shell for offline use. |
| `calibration/` | The v3.1 calibration run scripts, logs, and results — the auditable evidence for the registry-anchored calibration, including the two voided runs. |

## Model notes (current, v3.1)

- **Layer 1** — a single log-odds baseline computed from the patient's own clinical
  variables; band-derived age term, direct-creatinine renal term (`renal_k × ln(creatinine)`),
  pulmonary and ejection-fraction terms as specified in the Algorithm Specification of Record.
  Clamped to 0.40–50%. EuroSCORE II is computed in parallel from the published coefficients
  (Nashef et al. 2012, Table 6), unmodified, purely as a comparator — it never enters the
  UCSRS score.
- **Layer 2a** — MELD, additive, optional. Computed from bilirubin, INR and creatinine, with
  creatinine capped at 4.0 mg/dL; dialysis patients are substituted to creatinine 4.0
  centrally in both this layer and Layer 1.
- **Layer 2b** — modified Essential Frailty Toolset (mEFT, 0–6), multiplicative, mandatory
  (labs required; chair-rise and cognition may be deferred in urgent cases → partial-mEFT
  alert). Adds a second haemoglobin point below 8.0 g/dL to the published EFT.
- **Layer 2c** — LV dimensions (LVESVI preferred, LVEDD fallback) and SYNTAX, additive,
  optional.
- **Layer 3** — RHC haemodynamic corrections, additive, optional. Final cap 70%.
- **Calibration** — a single `calibration_shift` intercept, locked at v3.1 by a
  registry-anchored run against thirteen published surgical registries (median O/E ≈ 1.00).
  See `calibration/README.md` for the full run history, including both voided runs.

## Status

This is a **research tool**. It has not been prospectively validated against patient outcomes
and must not be the sole basis for any clinical decision. It does not replace the STS-PROM or
EuroSCORE II calculators in routine use. The UCSRS ATLAS multinational validation study will
test it against observed 30-day outcomes; no coefficient or constant moves again before ATLAS
reaches 5,000 enrolled patients.

## Version history

- **v3.1.0** (20 Sep 2026) — Registry-anchored calibration lock. `calibration_shift` re-derived
  and locked against thirteen published surgical registries (median O/E ≈ 1.00), after two
  development runs were found defective and discarded (an MI-code mismatch, and a
  MELD-formula/wrapper mismatch — both disclosed, not silently corrected). Confirmatory and
  locking runs of 30,000,000 patients each. High-risk behaviour (1,000,000-patient run)
  disclosed as an open item, not corrected. Dead code removed from both engines; user-facing
  version labels and stale comments corrected throughout.
- **v3.0.0** (19 Sep 2026) — Architectural release. Layer 1's 50/50 blend with EuroSCORE II
  removed; Layer 1 is now a single log-odds baseline, and EuroSCORE II is computed only as a
  comparator. Renal term moved from creatinine clearance to direct serum creatinine, with a
  centrally-applied creatinine = 4.0 mg/dL substitution for dialysis patients in both Layer 1
  and MELD (a declared, deliberate double-count with MELD, kept by investigator ruling).
  Frailty instrument extended to the modified Essential Frailty Toolset (mEFT, 0–6). The
  "independent of EuroSCORE II" claim was reframed: UCSRS does not take EuroSCORE II as a
  per-patient input, but (from v3.1) its calibration constant does depend on EuroSCORE II's
  published statistics — these are stated as two separate claims.
- **v2.1.0** (28 Aug 2026) — UCSRS v2.1. Layer 1 baseline re-derived in log-odds at a 3%
  reference to remove the double-counting of variables EuroSCORE II already scores; unique
  terms doubled; shared terms scaled by *k* = 1.15; age, creatinine clearance and ejection
  fraction read continuously; hypertension no longer weighted; baseline floor 0.50% → 0.30%;
  dialysis floored against the clearance term to remove an inversion below ~15 mL/min. The
  four companion estimates are unchanged. Published worked cases unchanged from v2.0.
  Superseded entirely by the v3.0 architecture above.
- **v2.0.0** (27 Aug 2026) — UCSRS v2.0. Layer 1 made independent: the score no longer takes
  STS-PROM as an input. Baseline floor lowered 1.50% → 0.50%. Frailty ladder and MELD slopes
  each reduced 25%. Published worked cases no longer reproduce (4.80 → 4.35, 7.35 → 6.20).
  Procedure list expanded to 24 categories with repair and replacement distinguished at every
  valve position; graded heart-failure, renal, pulmonary, shock, arteriopathy and infarct-recency
  fields; valve severity and etiology recorded. Fixed a wiring defect that had silently zeroed
  the untreated-severe-valve term.
- **v1.1.0** (Aug 2026) — Layer 2b frailty instrument changed from the Clinical Frailty Scale to
  the Essential Frailty Toolset (0–5), multiplier ladder unchanged at that point. Units toggle
  added for conventional and SI laboratory values.
- **v1.0** (Jul 2026) — initial release.
