# UCSRS v3.1 — calibration record

Everything needed to reproduce or audit the v3.1 calibration. Read
`UCSRS_v3.1_Calibration_and_Architecture_Review.md` first; it is the document of record
and the rest of this folder is its evidence.

**No simulated patient is assigned an outcome anywhere in this work. No outcome model is
used at any stage. No performance claim is made or implied.** The calibration is an
*anchoring*: a population mean predicted risk is matched against a published population
mean observed mortality. It is not a fit.

## The engine this record describes

`SPEC_VERSION` 3.1.0, `calibration_shift` 0.433039, Layer 1 floor 0.40%.
Engine SHA-256 (first 16) at the time of the locking run: `fb35c0ba2c967e1f`.

Every run gates before scoring a single patient: the worker engine must be byte-identical
to `../ucsrs_engine.py`, the version and constants must be the shipped ones, and the
scoring wrapper must agree with the engine's own `score_row()` on 400 rows to 1e-9. That
last gate exists because a wrapper built by swapping an import line once called a
superseded MELD function through two 30,000,000-patient runs before anyone noticed.

## Runs

| Log | What it is |
|---|---|
| `logs/30M_confirmatory_run_20Sep.log` | 30,000,000 patients. Confirmed the shipped constant after the v3.1 recalibration. Median O/E 0.998, 7/13 in band, reproduced on two hold-outs. |
| `logs/30M_locking_run_20Sep.log` | 30,000,000 patients. **The run of record.** Executed against the engine after dead-code removal and the `euro_pct` signature change. The constant was re-solved from scratch to 0.431392 against the shipped 0.433039 — 0.0016 log-odds, at the solver's tolerance. Median O/E 0.9965, 7/13 in band; hold-outs 0.9976 and 0.9971. By investigator instruction this is the **last calibration until ATLAS reaches 5,000 enrolled patients.** |
| `logs/1M_highrisk_eft_meld_20Sep.log` | 1,000,000 patients with complete mEFT and complete MELD data, in the high-risk profile the score is built for. Establishes that the two distinguishing layers separate UCSRS from EuroSCORE II by 17–45×, and that the 70% cap saturates on 40.1% of that population. Section 7b of the review. |
| `logs/quartile_experiment_20Sep.log` | Five arms, each re-anchored, testing what can move the Q3/Q4 reading against EuroSCORE II. Establishes that a Layer 1 *intercept* change cannot alter the shape — the solver absorbed +0.30 exactly — and that every lever trades the lower quartiles against the upper ones. |
| `logs/floor_experiment_20Sep.log` | Controlled 0.30 vs 0.40 floor comparison on one engine, one constant changed, each arm re-anchored. The floor is a first-quartile instrument: +0.059 at Q1, under 0.006 everywhere else. |

## Scripts

`run_lock_v31.py` is the locking run. `run_confirm_v31.py` is the earlier confirmatory
run. `run_highrisk_1M.py` is the high-risk validation. `exp_quartiles.py` and
`exp_floor.py` are diagnostics and write nothing to the engine.

`anchors.py` holds the thirteen registries with their published observed mortality and
published EuroSCORE II O/E. `cohort.py` is the synthetic generator. `cohort_cfg.py` is a
copy of it whose three optional-domain availability rates are module constants, used only
by the experiments; with the knobs off it reproduces `cohort.py` row for row.
`score_cand.py` holds the parallel scoring workers.

## Results

`results/definitive.json`, `holdout_1.json`, `holdout_2.json` and `shift.json` are the
locking run. `30M_confirmatory_definitive.json` is the earlier run.
`registry_dials.json` holds the thirteen severity dials, which are solved against
EuroSCORE II alone and therefore did not change between v3.0 and v3.1.
`highrisk_1M.json`, `quartile_experiment.json` and `floor_experiment.json` carry the
remaining runs. `provenance.json` records the engine hash and finish time of the locking
run.

## Two things not to misread

**In-band count is fragile.** It has run 7 or 8 of 13 across realisations. Quote the
median O/E and the mean absolute log O/E, or quote the range — never the in-band count
alone.

**A single summary ratio against EuroSCORE II is misleading.** The UCSRS-to-EuroSCORE II
ratio rises across the risk range, and cutting patients into quartiles by one score biases
the comparison against the other. The review reports the profile cut three ways, including
on the rank mean of both scores, which is the unbiased one.
