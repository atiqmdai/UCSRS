# UCSRS — Universal Cardiac Surgical Risk Score

Reference implementation of UCSRS, based on the architecture specified in Section 3.3 of:

> Rehman A. Universal cardiac surgical risk score (UCSRS v1.0): a unified physiology-informed
> risk architecture for operative mortality prediction across all adult cardiac surgical
> procedures. *J Cardiothorac Surg* 2026. DOI 10.1186/s13019-026-04433-x

**Calculator:** https://ucsrs-calculator.netlify.app · Open source (MIT)

The deployed calculator implements **UCSRS v1.1**: identical to the published v1.0
architecture except that the Layer 2b frailty instrument is the Essential Frailty
Toolset (EFT, 0–5) in place of the Clinical Frailty Scale. The published multiplier
ladder (×1.00–×2.30) is retained verbatim; only the instrument mapping changed. The
modification was made before first enrolment of the ATLAS validation study, at the
request of participating sites, for objectivity and inter-rater reliability.

## Files

| File | Purpose |
|---|---|
| `index.html` | The calculator. Self-contained; all computation in the browser; no data transmitted. |
| `test_calculator.js` | Acceptance test. Run `node test_calculator.js` — 90+ checks against the specification, including the paper's worked cases, the EFT scoring rules, and every EuroSCORE II coefficient (Nashef et al., EJCTS 2012, Table 6). |
| `sw.js`, `manifest.json`, icons | Progressive-web-app shell for offline use. |

## Model notes

- Layer 1 is the mean of an internally estimated STS component and EuroSCORE II (50/50), capped at 60%.
- EuroSCORE II is computed from the published coefficients (Nashef et al. 2012, Table 6).
- Layer 2a: MELD, additive at full weight (optional).
- Layer 2b: Essential Frailty Toolset, multiplicative, **mandatory** (labs required; chair rise
  and cognition may be deferred in urgent cases → partial-EFT alert). EFT 0–5 maps to
  ×1.00 / ×1.15 / ×1.35 / ×1.60 / ×1.90 / ×2.30.
- Layer 2c: LV dimensions (LVESVI preferred, LVEDD fallback) and SYNTAX, additive (optional).
- Layer 3: RHC haemodynamic corrections, additive (Tier 3 only). Final cap 70%.

## Version history

- **v2.0.0** (Aug 2026) — implements UCSRS v1.1: Layer 2b frailty instrument changed from
  the Clinical Frailty Scale to the Essential Frailty Toolset (0–5), multiplier ladder
  unchanged. Pre-enrolment modification for the ATLAS validation study. Acceptance test
  extended with EFT scoring checks.
- **v1.1.0** (Aug 2026) — free-standing score: STS component computed internally; no external
  score entry required. Implementation aligned with the published Section 3.3 specification:
  50/50 baseline, MELD applied additively at full weight, LV/SYNTAX corrections active,
  EuroSCORE II coefficients verified against the source publication. Acceptance test added.
- **v1.0** (Jul 2026) — initial release.
