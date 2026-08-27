# UCSRS — Universal Cardiac Surgical Risk Score

Reference implementation of UCSRS, developed from the architecture specified in Section 3.3 of:

> Rehman A. Universal cardiac surgical risk score (UCSRS v1.0): a unified physiology-informed
> risk architecture for operative mortality prediction across all adult cardiac surgical
> procedures. *J Cardiothorac Surg* 2026. DOI 10.1186/s13019-026-04433-x

**Calculator:** https://ucsrs-calculator.netlify.app · Open source (MIT)

## What is deployed: UCSRS v2.0

The deployed calculator implements **UCSRS v2.0**, which keeps the published layer
architecture and differs from the published v1.0 model in three respects. All three were
settled before the first enrolment of the ATLAS validation study, and all three are
documented rather than absorbed silently.

**1. Layer 1 is independent.** The published Section 3.3 specifies
`BR = (0.50 × STS-PROM%) + (0.50 × EuroSCORE II%)` with STS-PROM supplied by the site from
the official STS calculator. From v2.0 the baseline is computed from the patient's own
clinical variables instead. STS-PROM is **not an input**. Two reasons: requiring it means
computing three scores per patient indefinitely, and a score that consumes STS-PROM cannot
be fairly compared against it in validation. No value computed here is labelled STS-PROM;
the internal component is the *physiology-derived baseline*.

**2. Frailty instrument.** Layer 2b uses the Essential Frailty Toolset (EFT, 0–5) rather
than the Clinical Frailty Scale, at the request of participating sites, for objectivity and
inter-rater reliability.

**3. Weights reduced.** The frailty ladder and the MELD slopes are each reduced by 25% from
the published values, and the baseline floor is lowered from 1.50% to 0.50%.

### The published worked cases no longer reproduce

| Published case | Paper prints | v2.0 produces |
|---|---|---|
| Case 1 | 4.80% | **4.35%** |
| Case 2 | 7.35% | **6.20%** |

This is deliberate and dated, not an implementation error. `test_calculator.js` prints the
published value alongside the current one at every affected assertion, so the divergence stays
visible to anyone reading the tests.

## Files

| File | Purpose |
|---|---|
| `index.html` | The calculator. Self-contained; all computation in the browser; no data transmitted. |
| `test_calculator.js` | Acceptance test. Run `node test_calculator.js` — 227 checks against the specification, including the worked cases, the EFT scoring rules, the reduced ladder identity, and every EuroSCORE II coefficient (Nashef et al., EJCTS 2012, Table 6). |
| `sw.js`, `manifest.json`, icons | Progressive-web-app shell for offline use. |

## Model notes

- **Layer 1** — `0.50 × physiology-derived baseline + 0.50 × EuroSCORE II`, both computed
  internally from the entered clinical variables. Capped at 60%. Baseline floor 0.50%.
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
  regurgitation carries weight (+0.4 each). A lesion the operation corrects carries nothing, since
  the procedure term already prices it. Valve etiology is recorded and carries no weight.

## Status

This is a **research tool**. It has not been prospectively validated against patient outcomes
and must not be the sole basis for any clinical decision. It does not replace the STS-PROM or
EuroSCORE II calculators in routine use. The UCSRS ATLAS multinational validation study will
test it against observed 30-day outcomes; the correction terms are provisional until then.

## Version history

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
