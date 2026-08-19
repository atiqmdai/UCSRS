# UCSRS — Universal Cardiac Surgical Risk Score

Free-standing implementation of UCSRS v1.0, as specified in Section 3.3 of:

> Rehman A. Universal cardiac surgical risk score (UCSRS v1.0): a unified physiology-informed
> risk architecture for operative mortality prediction across all adult cardiac surgical
> procedures. *J Cardiothorac Surg* 2026. DOI 10.1186/s13019-026-04433-x

**Calculator:** https://ucsrs-calculator.netlify.app · Open source (MIT)

## Files

| File | Purpose |
|---|---|
| `index.html` | The calculator. Self-contained and free-standing: all inputs on one page, all computation in the browser, no data transmitted. |
| `test_calculator.js` | Acceptance test. Run `node test_calculator.js` — checks the full model against the published specification, including the paper's worked cases. |
| `sw.js`, `manifest.json`, icons | Progressive-web-app shell for offline use. |

## Model structure (per the published Section 3.3 specification)

- **Layer 1** — baseline risk: mean of two component scores computed internally from the
  entered clinical variables (50/50), capped at 60%.
- **Layer 2a** — MELD correction (optional): additive percentage points, banded, capped at 65%.
- **Layer 2b** — Clinical Frailty Scale (mandatory): multiplicative, ×1.00–×2.30, capped at 70%.
- **Layer 2c** — LV dimensions and SYNTAX (optional): additive after the frailty multiplier.
- **Layer 3** — RHC haemodynamic corrections (optional, Tier 3): additive; final result capped at 70%.

Absent optional domains contribute 0.0% and display an informational alert. The score
calculates at every level of data completeness.

## Version history

- **v1.1.0** (Aug 2026) — free-standing release: all components computed internally from the
  entered clinical variables; single calculator file; in-page self-test on load.
- **v1.0.1** (Aug 2026) — implementation aligned with the published Section 3.3 specification
  (50/50 baseline, MELD applied additively at full weight, LV/SYNTAX corrections active);
  acceptance test added.
- **v1.0** (Jul 2026) — initial release.
