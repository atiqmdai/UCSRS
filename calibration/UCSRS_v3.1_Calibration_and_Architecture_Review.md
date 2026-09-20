# UCSRS v3.1 — Calibration and Architecture Review

**Prepared 20 September 2026 · Atiq Rehman, MD, Coordinator, UCSRS ATLAS Consortium**

This document exists so that the v3.1 work can be reviewed without reading the development thread from the beginning. It records what changed, why each change was made, what was verified, what was ruled on, what went wrong along the way, and what is still outstanding. Where a decision was taken on judgment rather than evidence, it says so. Where an earlier statement in the project record is now wrong, it says that too.

**No performance claim is made anywhere in this document. No simulated patient is assigned an outcome at any stage, and no outcome model was used at any point in the calibration.**

---

## 1. What v3.1 is

v3.1 is a recalibration of Layer 1, not a new architecture. The layer structure, the variable list, and the scored path through the engine are those of v3.0. Six things moved: the calibration constant, the age ladder, the renal coefficient, the pulmonary severe-end coefficients, the Layer 1 floor, and the grading of albumin inside the modified Essential Frailty Toolset. Coefficients moved, so this is a minor-version release rather than a patch.

Three further questions that had been carried as open were closed by ruling rather than by a code change: the creatinine overlap between Layer 1 and MELD, the Layer 3 percentage-point scale, and the ejection-fraction coefficients. Each is recorded in section 5.

The repository state is eleven commits on `v2.3.0-repair`, working tree clean, all three verification suites green, and the locking calibration run of section 7 executed against the engine exactly as it now stands. **Nothing has been pushed.** Section 8 lists what remains before a push should be considered.

---

## 2. The calibration method, stated plainly

The score is anchored to thirteen registries that publish both an observed operative mortality and a EuroSCORE II O/E ratio. For each registry, dividing the published observed mortality by the published EuroSCORE II O/E gives the mean EuroSCORE II that registry's own case mix must have produced. A synthetic cohort is then generated and a single severity dial is solved, by root-finding, until that cohort's mean EuroSCORE II equals that target. The dial is solved against EuroSCORE II alone and therefore did not change between v3.0 and v3.1, because EuroSCORE II did not change.

With the thirteen cohorts fixed, every patient is scored through the full UCSRS engine. For each registry, O/E is the published observed mortality divided by the mean UCSRS. A single uniform constant — `calibration_shift`, an intercept shift in log-odds, added once inside Layer 1 — is then solved so that the **median** O/E across the thirteen is 1.00.

Two properties of this method should be understood before the results are read.

It is an anchoring, not a fit. Nothing is regressed against an outcome; no patient in any of the thirty million has an outcome. What is being matched is a population mean against a published population mean. A registry whose case mix the synthetic generator reproduces poorly will sit off 1.00 no matter what the constant is, and no single constant can move thirteen registries onto 1.00 at once.

It inherits EuroSCORE II's dependence. The targets are derived through EuroSCORE II's published O/E at each registry. That dependence is real and must be declared in the methods paper rather than left for a reviewer to find. It is the reason the median, not the mean, is the anchored statistic: the median is insensitive to the two or three registries where the derivation is weakest.

---

## 3. The design target that was withdrawn

Through v3.0, `calibration_shift` was described in both engines as "solved so a normal-risk 70-year-old man having an isolated elective first-time CABG reads 1.15× EuroSCORE II," and carried the value 1.451532.

**That target is withdrawn.** It is arithmetically incompatible with median O/E 1.00, and the incompatibility is not a matter of degree. EuroSCORE II's own median published O/E across these thirteen registries is 0.85 — that is, across this set of registries EuroSCORE II over-predicts observed mortality by about 18% at the median. A Layer 1 deliberately pinned 15% above EuroSCORE II therefore over-predicts observed mortality by roughly a third before any layer above Layer 1 has fired. Run at 1.451532, the score's median O/E is 0.575 with 3 of 13 registries in band.

The two positions cannot be reconciled by re-weighting the upper layers, because the gap exists at Layer 1, before those layers contribute anything. The choice was between them, and the choice made was median O/E = 1.00.

The comment describing the withdrawn target survived the v3.1 recalibration in both `ucsrs_engine.py` and `index.html` by oversight and was corrected on 20 September. `UCSRS_v3.0_Calibration_Protocol.md` documents the withdrawn target and is superseded on this point; it has not been rewritten, because it is the correct record of what was decided at the time.

---

## 4. The final configuration, coefficient by coefficient

`SPEC_VERSION` 3.1.0, carried identically in `ucsrs_engine.py`, `index.html`, `sw.js` and `manifest.json`.

**`calibration_shift` 1.451532 → 0.433039.** Registry-anchored as described above. Provenance: the locking 30,000,000-patient run of 20 September (section 7), in which the constant was re-solved from scratch to 0.431392 — 0.0016 log-odds from the shipped value, at the solver's tolerance — and confirmed on two independent hold-out realisations.

**Age ladder, steepened from 65 up.** The bands below 65 are untouched, so the healthy end of the score does not move. From 65: −0.09→0.05, 0.06→0.30, 0.20→0.55, 0.44→0.85, 0.60→1.10, 0.83→1.40 for the 65–69, 70–74, 75–79, 80–84, 85–89 and ≥90 bands respectively. Two distinct justifications apply to two distinct parts of this change, and they should not be conflated.

The *level* correction, in the 65–79 range, answers a measured deficit. A term-by-term decomposition on 19 September found the 70–74 band charging +0.06 log-odds where EuroSCORE II charges +0.314 at age 70 — a deficit of 0.254 log-odds applying to every patient of that age regardless of physiology. That is a defect, and it is what made frail seventy-year-olds read below EuroSCORE II.

The *acceleration* above 80 is a deliberate departure, not a correction. It rises from +0.17 at 80–84 to +0.33 at 90+ relative to EuroSCORE II's own slope. Its justification is the KROK on-pump octogenarian arm (n=2,729, observed 8.21% against predicted 5.06%, O/E 1.62). The on-pump arm is the applicable one because 22 of the 24 UCSRS procedure codes are obligate on-pump. Against ln(1.62) = 0.482, the acceleration is conservative. This coefficient was recommended for removal on 19 September on the strength of a PLOS One series reporting O/E near 1.10; the investigator's position — that mortality above 80 is real and that nonagenarian cases go on pump — was correct, the series was not procedure-matched, and the recommendation was withdrawn.

**`renal_k` 1.10 → 1.30.** UCSRS reads serum creatinine continuously through `renal_k × ln(creatinine)`. EuroSCORE II's `cc_le50` band is flat below a creatinine clearance of 50, so the comparator cannot distinguish a patient at clearance 45 from one at 20. At 1.10 UCSRS stayed below EuroSCORE II across the whole renal range; at 1.30 it crosses near creatinine 1.8, which is where a continuously read term should overtake a banded one. Cockcroft-Gault remains deleted from the scored path — it carries age, sex and weight, all of which UCSRS scores separately — and survives only inside `euroscore2()`, which requires it by published method.

**Pulmonary, severe end lifted.** Chronic with home oxygen 0.50→0.60, acute 0.40→0.50, acute on ventilator 0.95→1.10. EuroSCORE II has one binary pulmonary term at 0.1886564; the graded UCSRS term was reading below it at the severe end, which is the wrong direction for a term whose purpose is to discriminate within a category the comparator treats as flat.

**Ejection fraction, UNCHANGED at 0.40 / 0.80 / 1.20.** A departure above EuroSCORE II (0.55 / 1.10 / 1.60) was proposed on 19 September and withdrawn the same day. It should be recorded why. The coefficients were set by reasoning backwards from a desired output — the score was reading low in frail patients and a higher EF weight would raise it — which is not a method. A literature check then found a single usable adjusted estimate: OR 2.761 (95% CI 1.763–4.323) for EF ≤ 30 against normal, n = 4,789. That interval contains EuroSCORE II's own 0.808 in log-odds, the estimate is binary rather than graded, and it held for CABG but not for valve surgery. There is no evidence for the departure, and it was reverted.

**Layer 1 floor 0.30% → 0.40%.** Set just under EuroSCORE II's own structural floor of 0.4987%. The floor exists because a logistic model with no intercept floor will hand a young healthy patient an implausibly small number, and the clinical convention is that no sternotomy is risk-free. 18.9% of a representative case mix sits on the floor, and the practical consequence is that a routine elective CABG patient reads 0.400% flat from age 55 to 69 and begins to separate from 70 up. The investigator's ruling was that this is clinically correct: the same score from 55 to 69 matches practice, and 70 and above is where separation actually begins to matter.

**Albumin, graded inside the modified EFT.** Two points below 3.0 g/dL, one point below 3.5. This closes the standing "grading albumin" open item. The published Essential Frailty Toolset scores albumin as one binary point; grading it makes the instrument a *modified* EFT and it must be described as such wherever it is cited. The ladder is clamped at 6, because graded albumin can otherwise reach 7 and the multiplier table stops at 6.

---

## 5. Three questions closed by ruling

**The creatinine overlap with MELD — published MELD retained, overlap declared.** Creatinine is scored in Layer 1 and again inside MELD at Layer 2a. A creatinine-suppressed variant was built and tested (`meld_hepatic()`, retained in the engine as documented dead code, not on the scored path) and it measurably under-read severity in exactly the patients the accepted MELD bands are built on. The investigator's reasoning was clinical and decisive: in practice a surgeon computes STS or EuroSCORE II and MELD separately, each carrying creatinine, and reads them together; a MELD above 15 is high risk and above 20 is effectively prohibitive precisely because that is what published MELD says. Suppressing creatinine produces a number that is internally tidier and clinically wrong. The published form is retained, the overlap is deliberate and declared rather than concealed, and the Layer 1 renal coefficient and the Layer 2a slope are calibrated jointly with the overlap in place. ATLAS resolves it by joint estimation.

**Layer 3 scale and additivity — accepted, not deferred.** Layer 3 is denominated in percentage points while Layers 1, 2a, 2b and 2c are log-odds, and its four terms add rather than taking the highest applicable. The previous commit listed this as a known inconsistency to be resolved at the ATLAS re-estimation. The investigator's ruling of 20 September supersedes that framing. The worst-case stack is 8.6 percentage points, attainable only by a patient with cardiac power output below 0.6, pulmonary vascular resistance above 5, cardiac index below 2.0 and a TAPSE/PASP ratio below 0.406 simultaneously — severe biventricular failure with pulmonary vascular disease. Such a patient already carries a Layer 1–2c baseline of roughly 5–10% through low ejection fraction, raised pulmonary artery systolic pressure and circulatory support, so the stack lands them at 14–19%, which reads correctly as very high risk to inoperable. The flat-slab objection — that 8.6 points means something different at a 1% baseline than at 40% — is theoretical at the top of the range, because no patient meeting all four criteria has a 1% baseline. Layer 3 fires in about 3.5% of patients and contributes under 2% of the population mean, so the registry calibration is unaffected on either scale. Revisit only if ATLAS shows otherwise.

**Ejection fraction — no departure from EuroSCORE II.** Recorded in section 4.

---

## 6. What was independently verified

**EuroSCORE II was checked before anything was concluded from it.** All nineteen coefficients in the engine were compared against the Nashef 2012 published table and match. A separate hand implementation was written from the published coefficients alone, without reference to the engine, and agrees with the engine to floating point on every patient tested. Where this document says a UCSRS term reads above or below EuroSCORE II, the comparator is correct.

**STS-PROM was run through the live STS calculator**, not reimplemented, on a 128-patient factorial grid (age 70/80 × male/female × EF 60/28 × creatinine 1.0/2.0 × albumin 4.0/2.9 × INR 1.4/2.0 × bilirubin 0.9/2.5), with haematocrit 38, platelets 250,000 and white cell count 8 held constant across all patients. Two handling notes: the calculator recomputes asynchronously and returns stale values if read immediately, which required a wait and a re-read; and platelets are entered in cells/µL, not thousands.

**The general STS ACSD calculator collects creatinine, haematocrit, white cell count and platelets only** — no albumin, no INR, no bilirubin. This confirms the project's own four-pass finding of 8 September. Albumin, bilirubin and INR appear only in the multi-valve calculator and the ascending aorta/aortic root calculator. Do not state "STS uses albumin" without naming the calculator.

**Three verification suites, re-run after every change and green at the current head:** the acceptance suite (258 checks), Python/JavaScript parity across 4,000 cases on 15 reported quantities at 0.005 percentage-point tolerance including constant-table agreement, and end-to-end form wiring (39 keys read by the engine, 0 unassigned).

---

## 7. The 30,000,000-patient runs — including the two that were void

Three 30M runs were executed. Two were void. The reasons are recorded here in full because both were defects of mine, both were silent, and both would have been carried into the record as valid results had they not been caught.

**Void run 1 — the MI code defect.** The synthetic generator emitted recent-myocardial-infarction codes "21" and "1", neither of which is in the data dictionary's code list (none / 7 / 30 / 90). The engine matches by exact equality, so 10.6% of patients scored zero for recent MI in Layer 1 while still setting the flag for EuroSCORE II — a silent asymmetry between the score and its comparator. Mean UCSRS under-read by 4.4%. Fixed in `cohort.py`, with the defect recorded in a comment rather than quietly corrected.

**Void run 2 — the scoring wrapper called the wrong MELD.** The candidate wrapper was built by copying the working wrapper and swapping only the import line. It therefore still called `meld_from_labs(bilirubin, INR, creatinine)` — published MELD — at a point in the development when the creatinine-suppressed `meld_hepatic()` was the intended architecture. Both 30M runs of 19 September were scored with a function the run was not supposed to be using. This was found only by re-verifying the solved constant against the engine directly and getting a different answer: median O/E 1.092 where the run had reported 0.996.

Two things follow from that, and the second matters more than the first. The run was recoverable, because published MELD is the architecture finally chosen, so the constant it solved is valid for the configuration that shipped. But the reason the bug survived is that two contradictory constants were on record — 0.555211 and 0.438507 — and I assumed the newer was correct rather than checking. The assumption is the defect; the wrapper bug is what the assumption concealed.

**The fix is procedural, not a patch.** `run_confirm_v31.py` now runs a three-part gate before any patient is scored: the worker engine must be byte-identical by SHA-256 to the shipped `/home/claude/UCSRS/ucsrs_engine.py`; `SPEC_VERSION` and `calibration_shift` must be the shipped values; and the wrapper's scoring path must agree with the engine's own `score_row()` on 400 rows to 1×10⁻⁹. The third gate is the one that would have caught the wrapper bug on the day it was introduced.

**A fourth gap, found and closed on 20 September.** The 30M run of 19 September validated `calibration_shift` = 0.438507 against a Layer 1 floor of 0.30%. The floor was then raised to 0.40% by ruling and the constant re-solved to 0.433039 — but at pilot scale only. The shipped configuration had therefore never itself been run at registry scale. A confirmatory 30M run of the engine exactly as shipped was executed on 20 September and is reported below. It is the run that characterises v3.1.

### LOCKING RUN, 20 September 2026 — shipped engine, `calibration_shift` 0.433039

This is the run of record. By investigator instruction it is **the last calibration until
the ATLAS trial reaches 5,000 enrolled patients.** It was executed after the session's
final changes — dead code cleared from both engines, the unused `euro_pct` parameter
removed, eight stale comments corrected — because "behaviour-neutral on 3,000 patients
through one entry point" is a narrower claim than "holds across thirteen registry case
mixes at thirty million," and the `euro_pct` removal touched a positional signature at
five call sites, which is the defect class that voided two earlier runs.

Engine SHA-256 (first 16) `fb35c0ba2c967e1f`, identical between the worker and the
repository. Three gates passed before any patient was scored, including an assertion that
the deleted creatinine-suppressed MELD variant has not returned.

**The constant was re-solved from scratch, not assumed.** Root-finding was run without
reference to the shipped value, from a bracket of −1.0 to 3.0. It converged to
**0.431392** against the shipped **0.433039** — a difference of 0.0016 log-odds, which is
at the solver's own tolerance and corresponds to a 0.16% change in odds. The shipped
constant is retained; the independent solve is the confirmation, not a correction.

30,000,000 patients, 2,307,692 per registry, scored at both constants.

| Registry | Observed % | Mean ESII % | Mean UCSRS % | O/E | In band |
|---|---|---|---|---|---|
| STS ACSD | 2.40 | 3.338 | 2.874 | 0.835 | yes |
| CMS Medicare | 3.10 | 4.569 | 4.506 | 0.688 | no |
| SWEDEHEART | 1.50 | 2.589 | 2.010 | 0.746 | no |
| KROK | 4.10 | 3.717 | 3.349 | 1.224 | yes |
| German Registry | 3.20 | 3.264 | 2.780 | 1.151 | yes |
| BCIS/NICOR | 2.80 | 3.294 | 2.820 | 0.993 | yes |
| ANZCTS | 2.60 | 3.305 | 2.827 | 0.920 | yes |
| JCVSD | 4.10 | 2.891 | 2.341 | 1.752 | no |
| Indian cohort | 1.50 | 1.893 | 1.306 | 1.148 | yes |
| Brazilian | 4.30 | 2.695 | 2.121 | 2.028 | no |
| Turkish cohort | 5.30 | 6.375 | 7.301 | 0.726 | no |
| EuroHeart | 3.50 | 3.845 | 3.512 | 0.997 | yes |
| Korean Registry | 3.80 | 2.961 | 2.423 | 1.568 | no |

**Median O/E 0.9965. Mean |log O/E| 0.2662. In band (0.80–1.25): 7 of 13. Dynamic range
5.59×.**

Two hold-out realisations on seeds that took no part in the solve, 2,600,000 patients
each: median O/E 0.9976 and 0.9971, mean |log O/E| 0.2635 and 0.2650, 7 of 13 in band on
both. At the freshly solved 0.431392 the definitive run gives median O/E 0.9979 — the two
constants are not distinguishable at this resolution.

### Where UCSRS sits against EuroSCORE II across the risk range

New in this run, and it should be read before the score is described to anyone. Within
each registry the patients were split into EuroSCORE II quartiles and the ratio of mean
UCSRS to mean EuroSCORE II taken in each, then pooled across the thirteen:

| EuroSCORE II quartile | Mean UCSRS ÷ EuroSCORE II | Range across registries |
|---|---|---|
| Q1 (lowest risk) | 0.723 | 0.681–0.882 |
| Q2 | 0.736 | 0.602–1.029 |
| Q3 | 0.815 | 0.636–1.175 |
| Q4 (highest risk) | 0.921 | 0.735–1.175 |

The ratio rises monotonically. UCSRS reads about 28% below EuroSCORE II in the healthiest
quarter and converges to about 8% below it in the sickest, and in the top quartile it
exceeds EuroSCORE II in some registries. This is the intended shape rather than a
surprise — the Layer 1 floor sits at 0.40% against EuroSCORE II's structural 0.4987%, and
the v3.1 age and renal steepening acts from 65 and from creatinine 1.8 upward — but it is
a real property of the score and should be stated rather than discovered by a reviewer.
It also means **a single summary ratio against EuroSCORE II is misleading**; quote the
quartile profile or nothing.

**How to read the six registries out of band, honestly.** They are not a failure of the constant — no single intercept can move thirteen registries onto 1.00 at once — but neither are they noise, and they should not be presented as such. Four sit above 1.25 (JCVSD 1.75, Brazilian 2.03, Korean 1.57, and KROK at 1.22 close to the edge) and two below 0.80 (CMS Medicare 0.69, SWEDEHEART 0.75, Turkish 0.73). The pattern follows the registries whose published EuroSCORE II O/E is furthest from 1.00 in either direction: Brazilian 1.59 and JCVSD 1.42 at one end, SWEDEHEART 0.58 and CMS 0.68 at the other. Where EuroSCORE II is furthest from observed mortality, the derived target for the synthetic case mix is least trustworthy, and the synthetic generator is being asked to reproduce a case mix from a single severity dial. **In-band count is fragile and should never be quoted alone** — it has run 7 or 8 of 13 across realisations. Quote the median O/E and the mean |log O/E|, or quote the range.

---

## 7b. High-risk validation — does the architecture earn its keep where it matters?

Added 20 September 2026 at the investigator's direction. The registry calibration in
section 7 anchors the whole population. It says nothing about the patient the score is
actually built for: the one a heart team is deciding whether to operate on. As the
investigator put it, low and intermediate risk is never the question — every cardiac
surgeon consulting a risk score at the margin is asking about the high-risk patient.

The test profile, specified by the investigator: age 70 and 80, ejection fraction normal,
no pulmonary disease, haemoglobin 9 g/dL, haematocrit 27%, platelets 150,000/µL,
creatinine 2.0 and 4.0 mg/dL, albumin 3.0 g/dL, INR 2.0, bilirubin 2.5 mg/dL, chair rise
over 15 seconds, cognition poor, elective first-time isolated CABG. Both distinguishing
layers therefore fire at once: MELD 24 at creatinine 2.0 and 31 at 4.0, and a modified
EFT of 4 points carrying a ×2.60 multiplier.

| age | sex | Cr | MELD | Layer 1 | UCSRS | EuroSCORE II | ratio |
|---|---|---|---|---|---|---|---|
| 70 | M | 2.0 | 24 | 1.17 | 27.43 | 1.56 | 17.6× |
| 70 | M | 4.0 | 31 | 2.83 | 70.00 | 1.56 | 44.9× |
| 70 | F | 2.0 | 24 | 1.42 | 32.74 | 1.93 | 16.9× |
| 70 | F | 4.0 | 31 | 3.43 | 70.00 | 1.93 | 36.2× |
| 80 | M | 2.0 | 24 | 2.01 | 44.14 | 2.06 | 21.4× |
| 80 | M | 4.0 | 31 | 4.81 | 70.00 | 2.06 | 33.9× |
| 80 | F | 2.0 | 24 | 2.44 | 51.96 | 2.56 | 20.3× |
| 80 | F | 4.0 | 31 | 5.81 | 70.00 | 2.56 | 27.4× |

Over 1,000,000 patients drawn around that profile with clinically plausible spread
(`registries/run_highrisk_1M.py`, log and JSON archived): EuroSCORE II mean 2.22%, median
2.12%, tenth-to-ninetieth percentile 1.52% to 3.01%. UCSRS mean 52.26%, median 59.13%.
Ratio of means 23.5×.

**The finding is the reverse of the concern that prompted it.** The two layers do not fail
to separate UCSRS from its comparator in these patients; they separate it by a factor of
seventeen to forty-five. EuroSCORE II reads 1.5–2.6% because it cannot see any of the
relevant physiology: it has no albumin, no INR, no bilirubin, no haemoglobin and no
frailty instrument. Across the million its entire spread is 2.0-fold — it is not
discriminating this population, it is calling all of it low risk. That gap is the
architecture working as designed, and it is the clearest statement in this document of
what the added layers are for.

Two properties were exposed by the same exercise, and both are recorded because they cut
against the score rather than for it.

**The 70% cap saturates.** 40.1% of the million sit exactly on it, and four of the eight
exact cells return 70.00%. A 70-year-old and an 80-year-old at creatinine 4.0 are
clinically distinct and the score returns one number for both. In precisely the
operate-or-decline population the score is built for, it stops ranking at the top.

**MELD and frailty compound multiplicatively.** MELD is added in log-odds and the mEFT
multiplier is then applied to the already-inflated result, so the two interact rather
than sum. The layers also overlap physiologically — INR and bilirubin inside MELD,
albumin inside the mEFT, all reading hepatic synthetic function. At MELD 20 with
creatinine 2.0 at age 70, Layer 1 contributes about 1.2 percentage points, MELD takes it
to roughly 7.9, and frailty takes it to 20.5: the multiplier adds more in absolute terms
than MELD does. The published cardiac series underlying the MELD slope reports 31.2%
mortality at MELD ≥ 20, while the median patient in this million reads 59%.

**Where the gradient is checked against clinical expectation, it lands.** Holding the mEFT
at 4 points and moving MELD alone, at normal creatinine: MELD 8 reads 1.2–2.2%, MELD 15
reads 3.6–6.2%, MELD 20 reads 8.7–14.8%. That reproduces the investigator's own stated
bands — under 10 low risk, 15–20 high risk at roughly 10–15% — without having been tuned
to them.

**A structural consequence of the declared creatinine overlap, made concrete.** Because
MELD carries creatinine, a raised creatinine sets a floor under MELD: at creatinine 2.0
the lowest attainable MELD is 15, and at 4.0 it is 22. "MELD 8 with creatinine 2.0" is not
a patient this engine can represent. This is not a defect — it follows directly from the
ruling in section 5 — but it should be understood before the two numbers are read as
independent.

**One boundary worth knowing at the bedside.** The albumin test is strictly less-than, so
an albumin of exactly 3.0 g/dL scores 1 point, not 2. At 2.9 it scores 2, the multiplier
moves from ×2.60 to ×3.10, and the 80-year-old man at creatinine 2.0 moves from 44.1% to
52.6%. The knife-edge sits on the round number laboratories most often report.

**Nothing was changed in response to any of this.** The investigator's ruling stands: the
configuration is as expected and ATLAS decides the rest. The saturation at the cap and the
multiplicative compounding are recorded here as the two things to examine first when real
outcome data arrives.

---

## 8. Outstanding before any push

The calibration is closed. By investigator instruction the locking run in section 7 is the last calibration until ATLAS reaches 5,000 enrolled patients; no coefficient and no constant is to move before then, and the high-risk validation in section 7b was run under that lock and changed nothing. What follows is documentation and release sequencing, not model work.

Nothing has been pushed. The push that lands this engine also flips the public Netlify calculator, while enrolled sites hold packages citing v2.1/v2.2, so it is a deliberate decision and not a routine step.

1. **Correct `UCSRS_v3.0_Registry_Anchored_Calibration_30M.md`.** It reports a void run — the one carrying the MI-code defect. It should be superseded by this document's section 7 rather than quietly edited.
2. **Write the v3.1 Specification of Record.** The v3.0 specification is the current one of record and does not describe the shipped coefficients.
3. **SAP §1.5.1 and §8 amendments.** §1.5.1 carries the provisional-intercept disclosure, which is now a registry-anchored constant with a different provenance and a different dependency to declare.
4. **Withdraw the independence claim where it is overstated.** The score does not read EuroSCORE II, but it is calibrated through EuroSCORE II's published O/E. Those are different claims and the site-facing documents do not currently separate them.
5. **Add the declared creatinine overlap to the Validation Study Synopsis**, per the investigator's instruction of 19 September.
6. **Data dictionary decisions**, including whether `UCSRS_ATLAS_Model_Change_Statement_v3.0.docx` is written or the reference to it is struck. The Data Dictionary currently points a site at a document that does not exist.
7. **Check the site package's `Analysis_Software` copies** of `ucsrs_engine.py` and the JS suites against the repository before the next issuance. This was logged open on 14 September and has not been closed.
8. **Decide the push and the release separately.** Zenodo mints a version on a GitHub release, not a push; no release has been cut since 2.2.0.

---

## 9. Standing positions, unchanged

No performance claim. No simulated patient has an outcome, and no outcome model was used at any stage of the calibration. Times New Roman throughout every document. Signed as Coordinator, UCSRS ATLAS Consortium. Nothing reaches GitHub without an explicit decision to push.
