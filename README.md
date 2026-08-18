# UCSRS — Universal Cardiac Surgical Risk Score

Reference implementation of UCSRS v1.0, as specified in Section 3.3 of:

> Rehman A. Universal cardiac surgical risk score (UCSRS v1.0): a unified physiology-informed
> risk architecture for operative mortality prediction across all adult cardiac surgical
> procedures. *J Cardiothorac Surg* 2026. DOI 10.1186/s13019-026-04433-x

**Calculator:** https://ucsrs-calculator.netlify.app · Open source (MIT)

## Files

| File | Purpose |
|---|---|
| `index.html` | The calculator. Self-contained; all computation in the browser; no data transmitted. |
| `test_calculator.js` | Acceptance test. Run `node test_calculator.js` — 80 checks against the published specification, including the paper's worked cases and every EuroSCORE II coefficient (Nashef et al., EJCTS 2012, Table 6). |
| `sw.js`, `manifest.json`, icons | Progressive-web-app shell for offline use. |

## Model notes

- Layer 1 is the mean of STS-PROM and EuroSCORE II (50/50), capped at 60%.
- **STS-PROM is entered by the user** from the STS ACSD calculator (acsdriskcalc.research.sts.org).
  The STS model coefficients are not published, so STS-PROM cannot be computed here and is never approximated.
- EuroSCORE II is computed from the published coefficients (Nashef et al. 2012, Table 6).
- MELD (additive), CFS (multiplicative, mandatory), LV dimensions / SYNTAX (additive, optional),
  and RHC corrections (additive, Tier 3) per the published specification.

## Version history

- **v1.0.1** (Aug 2026) — implementation aligned with the published Section 3.3 specification:
  50/50 baseline, MELD applied additively at full weight, LV/SYNTAX corrections active,
  EuroSCORE II coefficients verified against the source publication, STS-PROM changed to direct entry.
  Acceptance test added.
- **v1.0** (Jul 2026) — initial release.
