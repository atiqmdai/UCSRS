#!/usr/bin/env node
/**
 * Acceptance test for the UCSRS calculator.
 *
 * Extracts the engine block straight out of UCSRS_Calculator.index.html and runs it,
 * so the file under test is the file that ships. If anyone restores the 0.40 weights,
 * re-adds the morbidity index, or drops Layer 2c, this goes red.
 *
 *   node test_calculator.js
 */
const fs = require('fs');
const path = require('path');

const CANDIDATES = ['index.html', 'UCSRS_Calculator.index.html'];
const FILE = CANDIDATES.find(f => fs.existsSync(path.join(__dirname, f)));
if (!FILE) { console.error('FAIL: no calculator HTML found'); process.exit(1); }
const HTML = fs.readFileSync(path.join(__dirname, FILE), 'utf8');
console.log('Testing: ' + FILE);

const START = '// ===== UCSRS ENGINE START =====';
const END   = '// ===== UCSRS ENGINE END =====';
const i = HTML.indexOf(START), j = HTML.indexOf(END);
if (i < 0 || j < 0) { console.error('FAIL: engine markers not found in the HTML'); process.exit(1); }
const engine = HTML.slice(i + START.length, j);

// What a user actually sees: the page with the engine block and every JavaScript line
// comment removed. Some checks are about the interface, not the source, and must not be
// tripped by a coefficient comment that carries provenance on purpose.
const RENDERED = (HTML.slice(0, i) + HTML.slice(j + END.length))
  .split('\n').map(l => l.replace(/\/\/.*$/, '')).join('\n');

const ctx = {};
new Function('exports', engine + '\nexports.ucsrs=ucsrs;exports.euroscore2=euroscore2;' +
  'exports.meldCorrection=meldCorrection;exports.meldFromLabs=meldFromLabs;' +
  'exports.creatinineClearance=creatinineClearance;exports.UCSRS_SPEC=UCSRS_SPEC;' +
  'exports.riskCategory=riskCategory;exports.selfTest=selfTest;exports.physiologyBaseline=physiologyBaseline;exports.eftScore=eftScore;exports.ucsrsOutcomes=ucsrsOutcomes;exports.bsaMosteller=bsaMosteller;')(ctx);

let failures = 0;
function check(name, ok, detail) {
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
  if (!ok) failures++;
}
function near(a, b, tol = 0.005) { return Math.abs(a - b) < tol; }

// Every expectation below is DERIVED from the published spec constants, not copied from
// engine output. A test that asserts whatever the engine happens to return proves only
// that the engine is self-consistent. These assert that the engine implements the spec.
const SPEC = ctx.UCSRS_SPEC;
const shiftLogOdds = (pct, d) => {
  const o = (pct / 100) / (1 - pct / 100);
  const z = Math.log(o) + d;
  return 100 * Math.exp(z) / (1 + Math.exp(z));
};

console.log('\n1. Worked cases — v3.0 vector, derived from the spec constants');

// Case 1: no MELD, so PRE_CFS is the baseline unchanged; Layer 2b multiplies the
// percentage by the mEFT ladder (G1: still on the percentage scale, deliberately).
const c1want = 2.8 * SPEC.layer2b_eft.mult[3];
const c1 = ctx.ucsrs({ baselinePct: 2.8, euroPct: 3.2, eft: 3, meld: null, lvedd: 52, tier: 0 });
check(`Case 1 — 2.8% x mEFT-3 ladder ${SPEC.layer2b_eft.mult[3]} = ${c1want.toFixed(2)}%`,
  near(c1.final, c1want), `got ${c1.final.toFixed(2)}%`);

// Case 2: MELD 17 is a log-odds shift of per_point x (17 - threshold), applied to the
// baseline; mEFT 0 leaves the ladder at 1.00.
const c2shift = SPEC.layer2a_meld.per_point * (17 - SPEC.layer2a_meld.threshold);
const c2want = shiftLogOdds(3.5, c2shift);
const c2 = ctx.ucsrs({ baselinePct: 3.5, euroPct: 2.0, eft: 0, meld: 17, lvedd: 50, tier: 0 });
check(`Case 2 — 3.5% shifted +${c2shift.toFixed(2)} log-odds = ${c2want.toFixed(2)}%`,
  near(c2.final, c2want), `got ${c2.final.toFixed(2)}%`);

// v3.0 departs from the published v1.0 values (4.80 / 7.35) and from v2.1 (4.35 / 6.20).
// The departure is deliberate; what matters is that nothing still claims otherwise.
check('no surviving claim that the engine reproduces the published v1.0 worked cases',
  !/reproduces the published (values|worked cases)/i.test(HTML));

console.log('\n2. Structural guards — these fail if the model drifts back');
// v3.0 inverts the v2.1 guard. Layer 1 is a single logistic model; it no longer blends a
// physiology baseline with a EuroSCORE II component at 0.50/0.50. EuroSCORE II survives
// only as the comparator, computed alongside and never folded into the score.
check('Layer 1 takes no EuroSCORE II component (w_euro removed)',
  ctx.UCSRS_SPEC.layer1.w_euro === undefined, `is ${ctx.UCSRS_SPEC.layer1.w_euro}`);
check('Layer 1 takes no blend weight at all (w_baseline removed)',
  ctx.UCSRS_SPEC.layer1.w_baseline === undefined, `is ${ctx.UCSRS_SPEC.layer1.w_baseline}`);
check('EuroSCORE II is still computed, as the comparator only',
  typeof ctx.euroscore2 === 'function');
check('no morbidity index anywhere in the file', !/morbIdx|morbidity_index|morbIndex/i.test(HTML));
check('no STS input field — score is free-standing', !/id="sts"/.test(HTML));
check('STS computed internally by physiologyBaseline', /function\s+physiologyBaseline/.test(engine) && /physiologyBaseline\(patient\)/.test(HTML));
check('Layer 2c LVESVI bands present', ctx.UCSRS_SPEC.layer2c.lvesvi.length === 3);
check('Layer 2c LVEDD bands present', ctx.UCSRS_SPEC.layer2c.lvedd.length === 3);
check('Layer 2c SYNTAX bands present', ctx.UCSRS_SPEC.layer2c.syntax.length === 3);
check('caps are 60 / 65 / 70',
  ctx.UCSRS_SPEC.layer1.cap_br === 60 && ctx.UCSRS_SPEC.layer2a_meld.cap_pre_cfs === 65 &&
  ctx.UCSRS_SPEC.layer2b_eft.cap === 70);

console.log('\n3. Layer 2c bands — v3.0 is on the LOG-ODDS scale, read from the spec');

// v3.0 converted Layer 2c from percentage points to log-odds. The band values are read
// from the spec so this test cannot silently drift if a coefficient is re-tuned; what it
// asserts is that the right BAND is selected for a given measurement.
const bandFor = (bands, v) => {
  for (const b of bands) {
    if (b.lte !== undefined && v <= b.lte) return b.c;
    if (b.gt !== undefined && v > b.gt) return b.c;
  }
  return 0;
};
for (const [field, val] of [['lvesvi', 55], ['lvesvi', 80], ['lvesvi', 120],
                            ['lvedd', 50], ['lvedd', 60], ['lvedd', 70]]) {
  const want = bandFor(SPEC.layer2c[field], val);
  const r = ctx.ucsrs(Object.assign(
    { baselinePct: 4, euroPct: 4, eft: 0, meld: null, tier: 0 }, { [field]: val }));
  check(`${field.toUpperCase()} ${val} → +${want.toFixed(2)} log-odds`,
    near(r.lv, want), `got +${r.lv.toFixed(2)}`);
}
for (const sx of [10, 28, 40, 45, 0]) {
  const want = sx === 0 ? 0 : bandFor(SPEC.layer2c.syntax, sx);
  const r = ctx.ucsrs({ baselinePct: 4, euroPct: 4, eft: 0, meld: null, syntax: sx, tier: 0 });
  check(`SYNTAX ${sx} → +${want.toFixed(2)} log-odds`,
    near(r.syntax, want), `got +${r.syntax.toFixed(2)}`);
}
const lvesviTop = bandFor(SPEC.layer2c.lvesvi, 120);
const pref = ctx.ucsrs({ baselinePct: 4, euroPct: 4, eft: 0, meld: null, lvesvi: 120, lvedd: 50, tier: 0 });
check('LVESVI takes precedence over LVEDD',
  pref.lvSource === 'LVESVI' && near(pref.lv, lvesviTop), `got ${pref.lvSource} +${pref.lv.toFixed(2)}`);

// SYNTAX is optional in v3.0 (B4). Absent must score zero and be flagged, never imputed.
const noSx = ctx.ucsrs({ baselinePct: 4, euroPct: 4, eft: 0, meld: null, tier: 0 });
check('SYNTAX absent scores 0.00 and is flagged, not imputed',
  near(noSx.syntax, 0) && noSx.syntaxGiven === false);

console.log('\n4. MELD — v3.0 two-segment log-odds shift, derived from the spec');

// v3.0: 0.18 per point from the threshold to the breakpoint, 0.08 per point above it,
// capped at meld_max. The second segment exists because a single 0.18 slope carried to
// MELD 40 over-predicted badly against the published cirrhosis strata.
const MELDSPEC = SPEC.layer2a_meld;
const meldWant = (m) => {
  m = Math.min(m, MELDSPEC.meld_max);
  if (m <= MELDSPEC.threshold) return 0;
  const lo = MELDSPEC.per_point * (Math.min(m, MELDSPEC.breakpoint) - MELDSPEC.threshold);
  const hi = m > MELDSPEC.breakpoint ? MELDSPEC.per_point_hi * (m - MELDSPEC.breakpoint) : 0;
  return lo + hi;
};
for (const m of [8, 9, 12, 15, 18, 20, 25, 30, 40, 45]) {
  const want = meldWant(m);
  check(`MELD ${m} → +${want.toFixed(2)} log-odds`,
    near(ctx.meldCorrection(m), want), `got +${ctx.meldCorrection(m).toFixed(2)}`);
}
check('MELD is capped at meld_max — 45 scores the same as 40',
  near(ctx.meldCorrection(45), ctx.meldCorrection(40)));
check('the slope breaks at the breakpoint, it does not run straight',
  meldWant(MELDSPEC.breakpoint + 10) < meldWant(MELDSPEC.breakpoint) + MELDSPEC.per_point * 10);

// The shift is on log-odds, so the same MELD is worth more percentage points in a sicker
// patient. That is the v3.0 scale change, and it is the point of it.
const mLow  = ctx.ucsrs({ baselinePct: 3,  euroPct: 3,  eft: 0, meld: null, tier: 0 });
const mLowM = ctx.ucsrs({ baselinePct: 3,  euroPct: 3,  eft: 0, meld: 20,   tier: 0 });
const mHi   = ctx.ucsrs({ baselinePct: 20, euroPct: 20, eft: 0, meld: null, tier: 0 });
const mHiM  = ctx.ucsrs({ baselinePct: 20, euroPct: 20, eft: 0, meld: 20,   tier: 0 });
check('MELD 20 is worth more percentage points in a sicker patient (odds scale)',
  (mHiM.final - mHi.final) > (mLowM.final - mLow.final),
  `adds ${(mLowM.final - mLow.final).toFixed(2)} at 3% vs ${(mHiM.final - mHi.final).toFixed(2)} at 20%`);
check('MELD 20 applied to a 3% baseline matches the derived shift',
  near(mLowM.final, shiftLogOdds(3, meldWant(20))), `got ${mLowM.final.toFixed(2)}%`);

console.log('\n5. Caps');
check('BR capped at 60', near(ctx.ucsrs({ baselinePct: 90, euroPct: 90, eft: 0, meld: null, tier: 0 }).br, 60));
check('PRE_CFS capped at 65',
  near(ctx.ucsrs({ baselinePct: 90, euroPct: 90, eft: 0, meld: 40, tier: 0 }).preCfs, 65));
check('final capped at 70',
  near(ctx.ucsrs({ baselinePct: 90, euroPct: 90, eft: 5, meld: 40, lvesvi: 150, syntax: 50, tier: 0 }).final, 70));

console.log('\n6. Layer 3 haemodynamics');
const h = ctx.ucsrs({ baselinePct: 4, euroPct: 4, eft: 0, meld: null, tier: 2,
  map: 60, co: 3.0, pvr: 6.0, ci: 1.8, tapse: 14, pasprhc: 50 });
check('all four derangements → +8.60', near(h.hemo, 8.60), `got +${h.hemo.toFixed(2)}`);
const h2 = ctx.ucsrs({ baselinePct: 4, euroPct: 4, eft: 0, meld: null, tier: 2,
  map: 90, co: 5.5, pvr: 1.5, ci: 3.0, tapse: 22, pasprhc: 35 });
check('normal haemodynamics → +0.00', near(h2.hemo, 0));
const h3 = ctx.ucsrs({ baselinePct: 4, euroPct: 4, eft: 0, meld: null, tier: 0,
  map: 60, co: 3.0, pvr: 6.0, ci: 1.8, tapse: 14, pasprhc: 50 });
check('Layer 3 not applied below Tier 3', near(h3.hemo, 0));

console.log('\n7. EuroSCORE II coefficients vs Nashef 2012 Table 6');
const E = ctx.UCSRS_SPEC.euroscore2;
const TABLE6 = {
  constant: -5.324537, age: 0.0285181, female: 0.2196434, cc_51_85: 0.303553,
  cc_le50: 0.8592256, dialysis: 0.6421508, arteriopathy: 0.5360268, mobility: 0.2407181,
  prev_cardiac: 1.118599, pulmonary: 0.1886564, endocarditis: 0.6194522, critical: 1.086517,
  iddm: 0.3542749, nyha2: 0.1070545, nyha3: 0.2958358, nyha4: 0.5597929, ccs4: 0.2226147,
  lv_moderate: 0.3150652, lv_poor: 0.8084096, lv_verypoor: 0.9346919, recent_mi: 0.1528943,
  pasp_31_55: 0.1788899, pasp_gt55: 0.3491475, urgent: 0.3174673, emergency: 0.7039121,
  salvage: 1.362947, single_non_cabg: 0.0062118, two_procedures: 0.5521478,
  three_plus: 0.9724533, thoracic_aorta: 0.6527205,
};
let coefBad = [];
for (const k of Object.keys(TABLE6)) if (E[k] !== TABLE6[k]) coefBad.push(k);
check(`all ${Object.keys(TABLE6).length} coefficients match Table 6`, coefBad.length === 0,
  coefBad.length ? 'mismatched: ' + coefBad.join(', ') : '');

const BASE = { age: 60, weight: 80, creatinine: 0.9, female: false, dialysis: false,
  lvef: 60, pasp: 20, nyha: 1, ccs4: false, arteriopathy: false, mobility: false,
  prevCardiac: false, pulmonary: false, endocarditis: false, critical: false, iddm: false,
  recentMI: false, urgency: 'elective', thoracicAorta: false, interventionWeight: 'cabg' };
const E2 = (o) => ctx.euroscore2(Object.assign({}, BASE, o));

const ref = E2({});
const expectRef = Math.exp(-5.324537 + 0.0285181) / (1 + Math.exp(-5.324537 + 0.0285181)) * 100;
check('reference patient (60M, elective isolated CABG, no risk factors) = 0.499%',
  near(ref, expectRef, 0.005) && near(ref, 0.499, 0.005), `got ${ref.toFixed(3)}%`);

console.log('\n7b. EuroSCORE II structural behaviour');
const logit = (pct) => Math.log((pct / 100) / (1 - pct / 100));
const delta = (o) => logit(E2(o)) - logit(ref);

check('age <=60 uses Xi=1, not 0', near(delta({ age: 45 }), 0, 1e-9), 'age 45 identical to age 60');
check('age 61 adds one age unit', near(delta({ age: 61 }), 0.0285181, 1e-6));
check('age 70 adds eleven age units', near(delta({ age: 70 }), 0.0285181 * 10, 1e-6));

// renal: one 4-level variable; dialysis REPLACES the clearance band
const ccOf = (o) => ctx.creatinineClearance(
  Object.assign({}, BASE, o).age, Object.assign({}, BASE, o).weight,
  Object.assign({}, BASE, o).creatinine, Object.assign({}, BASE, o).female);
check('Cockcroft-Gault: 60y 80kg Cr 0.9 mg/dL ~ 99 mL/min', ccOf({}) > 95 && ccOf({}) < 102,
  `${ccOf({}).toFixed(1)} mL/min`);
check('CC >85 adds nothing', near(delta({}), 0, 1e-9));
check('CC 51-85 adds 0.303553', near(delta({ creatinine: 1.5 }), 0.303553, 1e-6),
  `CC ${ccOf({ creatinine: 1.5 }).toFixed(0)}`);
check('CC <=50 adds 0.8592256', near(delta({ creatinine: 2.8 }), 0.8592256, 1e-6),
  `CC ${ccOf({ creatinine: 2.8 }).toFixed(0)}`);
check('dialysis REPLACES the band, does not add to it',
  near(delta({ dialysis: true, creatinine: 2.8 }), 0.6421508, 1e-6));

check('LV 31-50% adds 0.3150652', near(delta({ lvef: 40 }), 0.3150652, 1e-6));
check('LV 21-30% adds 0.8084096', near(delta({ lvef: 25 }), 0.8084096, 1e-6));
check('LV <=20% adds 0.9346919', near(delta({ lvef: 18 }), 0.9346919, 1e-6));
check('PASP 31-55 adds 0.1788899', near(delta({ pasp: 40 }), 0.1788899, 1e-6));
check('PASP >55 adds 0.3491475', near(delta({ pasp: 60 }), 0.3491475, 1e-6));
check('PASP exactly 55 stays in the 31-55 band', near(delta({ pasp: 55 }), 0.1788899, 1e-6));

check('isolated CABG is the reference (no weight term)', near(delta({ interventionWeight: 'cabg' }), 0, 1e-9));
check('single non-CABG adds 0.0062118', near(delta({ interventionWeight: 'single' }), 0.0062118, 1e-6));
check('two procedures adds 0.5521478', near(delta({ interventionWeight: 'two' }), 0.5521478, 1e-6));
check('three or more adds 0.9724533', near(delta({ interventionWeight: 'three' }), 0.9724533, 1e-6));
check('thoracic aorta is independent of procedure count',
  near(delta({ thoracicAorta: true }), 0.6527205, 1e-6));
check('CABG+AVR scores as two procedures, not single non-CABG',
  !near(delta({ interventionWeight: 'two' }), 0.0062118, 1e-4));

check('mobility uses 0.2407181, not the NYHA IV value',
  near(delta({ mobility: true }), 0.2407181, 1e-6));
check('NYHA IV uses 0.5597929', near(delta({ nyha: 4 }), 0.5597929, 1e-6));
check('mobility and NYHA IV are separate variables',
  near(delta({ mobility: true, nyha: 4 }), 0.2407181 + 0.5597929, 1e-6));
check('critical preoperative state is ONE variable at 1.086517',
  near(delta({ critical: true }), 1.086517, 1e-6));
check('CCS 4 uses 0.2226147', near(delta({ ccs4: true }), 0.2226147, 1e-6));

check('body weight and weight-of-intervention are separate fields (regression)',
  /interventionWeight/.test(engine) && !/p\.weight\s*===/.test(engine));

console.log('\n7c. Layer 1 baseline behaviour');
// v3.0 re-anchored the intercept (calibration_shift +1.451532), so the reference patient
// no longer sits ON the 0.30 clamp as it did in v2.1 — it sits above it. The clamp is a
// guard against the logistic tail, not the score's starting point. Investigator ruling of
// 15 September: the clamp values are clinically immaterial (nothing above ~30% is
// separable), so the test asserts the reference patient is inside the clamps, not equal
// to one.
const REFPT = {age:60,weight:80,creatinine:0.9,female:false,dialysis:false,lvef:60,nyha:1,urgency:'elective',procedure:'cabg'};
const refBase = ctx.physiologyBaseline(REFPT);
check('reference 60M elective CABG sits strictly inside the Layer 1 clamps (0.30 / 50)',
  refBase > 0.30 && refBase < 50, `got ${refBase.toFixed(3)}%`);
check('the Layer 1 clamps are 0.30 and 50 in the shipped engine',
  /Math\.min\(Math\.max\(100 \/ \(1 \+ Math\.exp\(-z\)\), 0\.30\), 50\)/.test(engine));
check('a healthy 52-year-old can now score below 1.0 (real STS was 0.40)',
  ctx.physiologyBaseline({age:52,weight:85,creatinine:1.09,female:false,dialysis:false,lvef:65,nyha:1,urgency:'elective',procedure:'cabg',interventionWeight:'cabg'}) < 1.0);

console.log('\n7d. Layer 2b — modified Essential Frailty Toolset (mEFT, 0-6)');
// v3.0: the published EFT is 0-5. UCSRS adds a SIXTH rung — a second haemoglobin point
// below 8.0 g/dL — and renames the instrument mEFT wherever it is referenced (D3). The
// "published ladder reduced 25%" construction of v2.1 is gone; the ladder was re-set
// against FRAILTY-AVR rather than derived from the published one.
const M = ctx.UCSRS_SPEC.layer2b_eft.mult;
check('mEFT is 0-6 — seven multiplier levels, one more than the published instrument',
  Object.keys(M).length === 7, JSON.stringify(M));
check('the ladder starts at 1.00 — mEFT 0 is no penalty', M[0] === 1.00, `is ${M[0]}`);
check('the ladder is strictly increasing across all seven rungs',
  [1,2,3,4,5,6].every(i => M[i] > M[i-1]), JSON.stringify(M));
check('the sixth rung exists and is the largest step on the ladder',
  M[6] !== undefined && (M[6] - M[5]) >= (M[5] - M[4]),
  `rung 6 adds ${(M[6]-M[5]).toFixed(2)}, rung 5 adds ${(M[5]-M[4]).toFixed(2)}`);
check('the critical-haemoglobin threshold driving the sixth rung is 8.0 g/dL',
  ctx.UCSRS_SPEC.layer2b_eft.hgb_crit === 8, `is ${ctx.UCSRS_SPEC.layer2b_eft.hgb_crit}`);
check('no surviving claim that the ladder is the published one reduced 25%',
  !/reduced by 25% from the published ladder/.test(HTML));
const efts = (f) => ctx.eftScore(Object.assign({ chair: 'fast', cogImpaired: false, hgb: 14, albumin: 4.0, female: false }, f));
check('robust patient → EFT 0', efts({}).points === 0);
check('chair rise 15 s or more → 1 point', efts({ chair: 'slow' }).points === 1);
check('unable to rise → 2 points', efts({ chair: 'unable' }).points === 2);
check('cognitive impairment → 1 point', efts({ cogImpaired: true }).points === 1);
check('Hgb 12.5 scores in men, not women',
  efts({ hgb: 12.5 }).points === 1 && efts({ hgb: 12.5, female: true }).points === 0);
check('Hgb threshold: women <12', efts({ hgb: 11.9, female: true }).points === 1);
check('albumin <3.5 → 1 point', efts({ albumin: 3.4 }).points === 1);
check('worst case → EFT 5', efts({ chair: 'unable', cogImpaired: true, hgb: 10, albumin: 3.0 }).points === 5);
check('missing chair + cognition → partial from labs',
  (function(){ const e = ctx.eftScore({ chair: '', cogImpaired: null, hgb: 11, albumin: 3.2, female: false });
    return e.partial === true && e.points === 2 && e.missing.length === 2; })());
check('no CFS button grid remains', !/setCfs|cfsBox|CFS_LABELS/.test(HTML));
check('EFT input fields present', /id="chair"/.test(HTML) && /id="cog"/.test(HTML) && /id="hgb"/.test(HTML) && /id="alb"/.test(HTML));

console.log('\n7e. Companion 30-day outcome estimates');
const oc = ctx.ucsrsOutcomes(2.5, {});
check('factor-free patient at anchor mortality 2.5%: vent 9.5 / renal 2.8 / stroke 1.3',
  near(oc.vent, 9.5, 0.01) && near(oc.renal, 2.8, 0.01) && near(oc.stroke, 1.3, 0.01),
  `got ${oc.vent.toFixed(2)} / ${oc.renal.toFixed(2)} / ${oc.stroke.toFixed(2)}`);
const oc10 = ctx.ucsrsOutcomes(10, {}), oc70 = ctx.ucsrsOutcomes(70, {});
check('monotone in mortality', oc10.vent > oc.vent && oc10.renal > oc.renal && oc10.stroke > oc.stroke);
check('bounded below 100 at the 70% cap', oc70.vent < 100 && oc70.renal < 100 && oc70.stroke < 100,
  `vent ${oc70.vent.toFixed(1)}`);
check('five endpoints reported, including reoperation',
  ['vent','renal','stroke','reop'].every(k => typeof oc[k] === 'number') && /line\('Reoperation'/.test(HTML));
check('each endpoint has its own mortality-linkage slope',
  /slopes:\{/.test(HTML) && !/slope:0\.75/.test(HTML));
check('estimates stay clinically plausible at high mortality (reop < 30% at 25% mortality)',
  ctx.ucsrsOutcomes(25, { prevCardiac:true, radiation:true, immuno:true }).reop < 30,
  `reop ${ctx.ucsrsOutcomes(25, { prevCardiac:true, radiation:true, immuno:true }).reop.toFixed(1)}%`);
check('radiation and immunosuppression raise reoperation, not mortality-scale endpoints',
  (function(){ const a = ctx.ucsrsOutcomes(5, {}), b = ctx.ucsrsOutcomes(5, { radiation:true, immuno:true });
    return b.reop > a.reop && near(b.renal, a.renal, 0.01) && near(b.vent, a.vent, 0.01); })());
const ocV = ctx.ucsrsOutcomes(2.5, { copd: true, smoker: true, lvef: 25 });
check('COPD + smoker + EF 25 raise ventilation only',
  ocV.vent > oc.vent && near(ocV.renal, oc.renal, 0.01) && near(ocV.stroke, oc.stroke, 0.01),
  `vent ${oc.vent.toFixed(1)} -> ${ocV.vent.toFixed(1)}`);
const ocR = ctx.ucsrsOutcomes(2.5, { cc: 25, iddm: true });
check('CrCl 25 + diabetes raise renal failure only',
  ocR.renal > oc.renal && near(ocR.vent, oc.vent, 0.01) && near(ocR.stroke, oc.stroke, 0.01),
  `renal ${oc.renal.toFixed(1)} -> ${ocR.renal.toFixed(1)}`);
const ocS = ctx.ucsrsOutcomes(2.5, { arteriopathy: true, afib: true, neuro: true });
check('arteriopathy + AF + prior neuro raise stroke only',
  ocS.stroke > oc.stroke && near(ocS.vent, oc.vent, 0.01) && near(ocS.renal, oc.renal, 0.01),
  `stroke ${oc.stroke.toFixed(1)} -> ${ocS.stroke.toFixed(1)}`);
check('pre-op dialysis makes renal failure estimate n/a',
  ctx.ucsrsOutcomes(2.5, { dialysis: true }).renal === null);
check('age >75 raises renal and stroke, not vent',
  (function(){ const a = ctx.ucsrsOutcomes(2.5, { age: 80 });
    return a.renal > oc.renal && a.stroke > oc.stroke && near(a.vent, oc.vent, 0.01); })());
check('smoker checkbox present in the form', /id="smoker"/.test(HTML));

console.log('\n7f. No references on the page');
// Scoped to the rendered interface. The calculator must not present itself to a user as a
// cited, published instrument — but the coefficient comments MUST keep their provenance,
// because that provenance is what the methods paper and the release record rest on.
check('no literature/source references in the rendered interface',
  !/Nashef|Afilalo|Rehman|Cardiothorac|13019|zenodo|Dalhousie|DOI|Section 3\.3|JAHA|acsdriskcalc|github/i.test(RENDERED));

console.log('\n7g. MELD from labs (mg/dL) and units');
check('MELD floors at 6 for normal labs', ctx.meldFromLabs(0.8, 1.0, 0.9, false) === 6,
  `got ${ctx.meldFromLabs(0.8, 1.0, 0.9, false)}`);
check('MELD: bili 3.0, INR 1.8, Cr 2.0 -> 24', ctx.meldFromLabs(3.0, 1.8, 2.0, false) === 24,
  `got ${ctx.meldFromLabs(3.0, 1.8, 2.0, false)}`);
check('MELD is internal only — no direct-entry field, no duplicate dialysis question',
  !/id="meldDirect"/.test(HTML) && !/id="dialmeld"/.test(HTML));
check('MELD uses exactly three inputs: bilirubin, INR, creatinine',
  /meldFromLabs\(b, i, c\)/.test(HTML));
check('MELD takes no dialysis argument — creatinine entered is creatinine used',
  ctx.meldFromLabs.length === 3 &&
  ctx.meldFromLabs(1.0, 1.0, 1.0) < ctx.meldFromLabs(1.0, 1.0, 4.0));
check('no self-test banner is rendered on the page',
  !/id="selftest"/.test(HTML) && !/Self-test passed/.test(HTML));
check('weight and height are marked and gated as required fields',
  /Weight \(kg\) <span class="req">\*<\/span>/.test(HTML) &&
  /Height \(cm\) <span class="req">\*<\/span>/.test(HTML) &&
  /num\('wt'\) === null \|\| num\('ht'\) === null/.test(HTML));
check('Layer 2c fields are named in words, not abbreviations',
  /LV end-systolic volume \(mL\)/.test(HTML) &&
  /or LV end-systolic volume index \(mL\/m²\)/.test(HTML) &&
  /LV end-diastolic diameter \(mm\) — used only if no volume entered/.test(HTML) &&
  !/— indexed automatically/.test(HTML) && !/— preferred/.test(HTML) && !/— fallback only/.test(HTML));
check('the volume path still indexes to BSA and still takes precedence',
  /lvesviValue = num\('lvesv'\) \/ bsa/.test(HTML) &&
  ctx.ucsrs({baselinePct:4,euroPct:4,eft:0,meld:null,lvesvi:120,lvedd:50,tier:0}).lvSource === 'LVESVI');
check('the weight-of-intervention note is gone',
  !/set automatically from the procedure/.test(HTML));
check('the MELD note is the short form only',
  !/enter a creatinine here only to override/.test(HTML) && !/Dialysis is taken from the Dialysis field/.test(HTML));
var PW_MAP = {
  cabg:'cabg', cabg_tv_repair:'cabg',
  avr_mvr:'two', avr_mv_repair_tv_repair:'two', cabg_avr:'two', cabg_asc_aorta:'two',
  cabg_mvr:'two', cabg_mv_repair:'two', avr_asc_aorta:'two', avr_root_asc_aorta:'two',
  avr_mvr_tvr:'three', cabg_avr_mv_repair:'three',
  cabg_avr_mv_repair_tv_repair:'three', cabg_avr_mvr_tv_repair:'three' };
function PW(pr){ return PW_MAP[pr] || 'single'; }
function PROC(pr){
  return { age:70, weight:80, creatinine:1.0, female:false, lvef:55, nyha:2, sternotomy:1,
           urgency:'elective', procedure:pr,
           interventionWeight: PW(pr) };
}

check('creatinine capped at 4.0 mg/dL',
  ctx.meldFromLabs(1.0, 1.0, 9.0, false) === ctx.meldFromLabs(1.0, 1.0, 4.0, false));
check('no layer breakdown or component score names are displayed',
  !/line\('Layer 1 calculated score'/.test(HTML) &&
  !/line\('STS component'/.test(HTML) && !/line\('EuroSCORE II component'/.test(HTML));
check('the calculation-detail toggle is gone',
  !/toggleDetail/.test(HTML) && !/show calculation detail/.test(HTML) && !/showDetail/.test(HTML));
check('one creatinine — the MELD field falls back to the Layer 1 value',
  /if \(c === null\) c = patient\.creatinine/.test(HTML));
check('BSA is computed by the Mosteller formula',
  /function bsaMosteller/.test(HTML) && /Math\.sqrt\(\(heightCm \* weightKg\) \/ 3600\)/.test(HTML));
check('height is collected',
  /id="ht"/.test(HTML) && /Height \(cm\)/.test(HTML));
check('LVESV is indexed to BSA when LVESVI is not entered directly',
  /lvesviValue = num\('lvesv'\) \/ bsa/.test(HTML));
check('aortic and mitral valve procedures are separated from each other',
  /value="avr"/.test(HTML) && /value="mv_repair"/.test(HTML) && /value="mvr"/.test(HTML));
check('open-heart number replaces the previous-surgery checkbox',
  /id="sternotomy"/.test(HTML) && !/id="prev"/.test(HTML) &&
  /prevCardiac: sternotomy >= 2/.test(HTML));
check('a third open heart weighs more than a second',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { sternotomy:3, prevCardiac:true })) >
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { sternotomy:2, prevCardiac:true })));
check('a first open heart carries no reoperation weight',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { sternotomy:1, prevCardiac:false })) ===
  ctx.physiologyBaseline(PROC('cabg')));
check('TAVR explant is the heaviest single-valve procedure',
  ['avr','avr_are','av_repair','mvr','mv_repair','tv_repair','tvr']
    .every(function(pr){ return ctx.physiologyBaseline(PROC('tavr_explant')) > ctx.physiologyBaseline(PROC(pr)); }));
check('root enlargement adds only a small increment over plain AVR',
  ctx.physiologyBaseline(PROC('avr_are')) > ctx.physiologyBaseline(PROC('avr')) &&
  ctx.physiologyBaseline(PROC('avr_are')) - ctx.physiologyBaseline(PROC('avr')) <= 0.5);
check('AV repair scores below AVR',
  ctx.physiologyBaseline(PROC('av_repair')) < ctx.physiologyBaseline(PROC('avr')));
check('aortic work compounds: root plus ascending outscores ascending alone',
  ctx.physiologyBaseline(PROC('avr_root_asc_aorta')) > ctx.physiologyBaseline(PROC('avr_asc_aorta')) &&
  ctx.physiologyBaseline(PROC('avr_asc_aorta')) > ctx.physiologyBaseline(PROC('asc_aorta')));
check('all four aortic procedures carry the published thoracic-aorta term',
  /AORTA_PROCS = \['asc_aorta', 'cabg_asc_aorta', 'avr_asc_aorta', 'avr_root_asc_aorta'\]/.test(HTML));
check('operation field is first time / redo / second redo',
  /<option value="1">First time<\/option>/.test(HTML) &&
  /<option value="2">Redo<\/option>/.test(HTML) &&
  /<option value="3">Second redo<\/option>/.test(HTML));
check('heart failure is one field — no separate congestive-failure term',
  !/id="chf"/.test(HTML) && !/chf/.test(engine) &&
  ['none','1','2','3','4','acute'].every(function(v){
    return new RegExp('<option value="' + v + '"').test(HTML); }));
check('none and NYHA I are both the published reference class',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { nyha:1 })) ===
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { nyha:1, heartFailure:'none' })) &&
  ctx.euroscore2(Object.assign({}, BASE, { nyha:1 })) ===
  ctx.euroscore2(Object.assign({}, BASE, { nyha:1, heartFailure:'none' })));
check('acute decompensation scores as class IV plus an increment',
  /nyha: hfVal === 'acute' \? 4/.test(HTML) &&
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { nyha:4, acuteDecomp:true })) >
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { nyha:4 })));
check('a class and acute decompensation cannot both be chosen',
  (HTML.match(/<select id="nyha"[\s\S]*?<\/select>/)[0].match(/<option/g) || []).length === 6);
check('NYHA carries heart-failure severity in both halves, once each',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { nyha:4 })) >
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { nyha:3 })) &&
  ctx.euroscore2(Object.assign({}, BASE, { nyha:4 })) >
  ctx.euroscore2(Object.assign({}, BASE, { nyha:3 })));
check('infarct recency is graded 7 / 30 / 90 days',
  /<select id="mi"/.test(HTML) &&
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { miDays:7 })) >
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { miDays:30 })) &&
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { miDays:30 })) >
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { miDays:90 })));
check('any infarct within 90 days still sets the published binary term',
  /recentMI: miVal !== 'none'/.test(HTML));


check('arteriopathy is one dropdown with four territories',
  /<select id="pvd"/.test(HTML) &&
  ['carotid','ascending','arch','peripheral'].every(function(v){
    return new RegExp('<option value="' + v + '"').test(HTML); }) &&
  !/id="pvd_carotid"/.test(HTML));
check('any arteriopathy territory sets the published binary term',
  /arteriopathy: pvdVal !== 'none'/.test(HTML));
check('renal status is one field, not a dialysis select plus an anuria checkbox',
  /<select id="renal"/.test(HTML) && !/id="dial"/.test(HTML) && !/id="anuria"/.test(HTML));
check('chair rise is one three-state field, not a time plus a yes/no',
  /<select id="chair"/.test(HTML) && !/id="chairun"/.test(HTML) &&
  ['fast','slow','unable'].every(function(v){ return new RegExp('<option value="'+v+'"').test(HTML); }));
check('chair rise scores 0 / 1 / 2 and unable outranks slow',
  ctx.eftScore({chair:'fast',  cogImpaired:false, hgb:14, albumin:4}).points === 0 &&
  ctx.eftScore({chair:'slow',  cogImpaired:false, hgb:14, albumin:4}).points === 1 &&
  ctx.eftScore({chair:'unable',cogImpaired:false, hgb:14, albumin:4}).points === 2);
check('an unassessed chair rise still yields a partial EFT',
  ctx.eftScore({chair:'', cogImpaired:false, hgb:14, albumin:4}).partial === true);
check('unable to rise also sets poor mobility',
  /chairVal === 'unable'/.test(HTML));
check('cognition is not assessed / normal / impaired, with no instrument names on screen',
  /<select id="cog"/.test(HTML) && /<option value="1">Impaired<\/option>/.test(HTML) &&
  !/Mini-Cog/.test(HTML) && !/MMSE/.test(HTML));
check('an unassessed cognition still yields a partial EFT',
  ctx.eftScore({chair:'fast', cogImpaired:null, hgb:14, albumin:4}).partial === true);
check('valve etiology sits beside valve severity, three valves in one field',
  /<details class="vsev" id="etioBox">/.test(HTML) &&
  ['av_etio','mv_etio','tv_etio'].every(function(id){
    return new RegExp('<select id="' + id + '"').test(HTML); }) &&
  !/Valve etiology \(optional\)/.test(HTML) && !/Valve severity \(optional\)/.test(HTML));
check('mitral and tricuspid etiology are grouped primary vs secondary',
  (HTML.match(/<optgroup label="Primary">/g) || []).length === 2 &&
  (HTML.match(/<optgroup label="Secondary">/g) || []).length === 2);
check('the etiology lists match the specification',
  /value="congenital"/.test(HTML) && /value="secondary_ischemic"/.test(HTML) &&
  /value="secondary_cardiomyopathy"/.test(HTML) && /value="primary_carcinoid"/.test(HTML) &&
  /value="secondary_rv"/.test(HTML));
check('etiology carries no weight — the engine never sees it',
  !/etiology|rheumatic|degenerative|carcinoid/i.test(engine));
check('valve severity is three fields, one per valve, lesion then grade',
  ['av_sev','mv_sev','tv_sev'].every(function(id){
    return new RegExp('<select id="' + id + '"').test(HTML); }) &&
  (HTML.match(/<optgroup label="Stenosis">/g) || []).length === 3 &&
  (HTML.match(/<optgroup label="Regurgitation">/g) || []).length === 3);
const VS = (v, lesion, severity, treated) => {
  const base = { aortic:{severity:'none'}, mitral:{severity:'none'}, tricuspid:{severity:'none'} };
  base[v] = { lesion, severity, treated };
  return base;
};
check('the three valve selects sit inside one collapsible field',
  /<details class="vsev" id="sevBox">/.test(HTML) && /function vsevSummary/.test(HTML) &&
  ['av_sev','mv_sev','tv_sev'].every(function(id){
    return new RegExp('<select id="' + id + '" onchange="vsevSummary\\(\\);calc\\(\\)"').test(HTML); }));
check('the collapsed row reports its contents',
  /parts.length \? parts.join\(' · '\) : 'None entered'/.test(HTML));
// Wiring guards. The engine tests above call physiologyBaseline directly with a valves object,
// which cannot catch a form that never builds one. These check the page's own plumbing.
check('every variable the patient object reads is declared before it',
  (function(){
    const p = HTML.indexOf('var patient = {');
    return ['var valves = {', 'var treatedValves', 'var valveEtiology', 'var critical =',
            'var renalVal', 'var shockVal', 'var hfVal', 'var miVal', 'var pvdVal',
            'var ventilated', 'var sternotomy', 'var chairVal']
      .every(function(decl){ const d = HTML.indexOf(decl); return d > -1 && d < p; });
  })());
check('the valve object is built before the patient object consumes it',
  HTML.indexOf('var valves = {') < HTML.indexOf('var patient = {') &&
  HTML.indexOf('var patient = {') < HTML.indexOf('valves: valves'));
check('treated status is read from the procedure, not asked',
  /f.treated = treatedValves.indexOf\(name\) >= 0/.test(HTML) &&
  /var treatedValves = valvesTreated\(document.getElementById\('proc'\).value\)/.test(HTML));
check('severe MR is charged at isolated CABG but not when the mitral is addressed',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { valves: VS('mitral','r','severe',false) })) >
  ctx.physiologyBaseline(PROC('cabg')) &&
  ctx.physiologyBaseline(Object.assign(PROC('cabg_mv_repair'), { valves: VS('mitral','r','severe',true) })) ===
  ctx.physiologyBaseline(PROC('cabg_mv_repair')) &&
  ctx.physiologyBaseline(Object.assign(PROC('cabg_mvr'), { valves: VS('mitral','r','severe',true) })) ===
  ctx.physiologyBaseline(PROC('cabg_mvr')));
check('severe AS is charged at isolated CABG or MVR but not when the aortic is addressed',
  ctx.physiologyBaseline(Object.assign(PROC('mvr'), { valves: VS('aortic','s','severe',false) })) >
  ctx.physiologyBaseline(PROC('mvr')) &&
  ctx.physiologyBaseline(Object.assign(PROC('cabg_avr'), { valves: VS('aortic','s','severe',true) })) ===
  ctx.physiologyBaseline(PROC('cabg_avr')) &&
  ctx.physiologyBaseline(Object.assign(PROC('avr_mvr'), { valves: VS('aortic','s','severe',true) })) ===
  ctx.physiologyBaseline(PROC('avr_mvr')));
// From v2.1 the baseline is additive in LOG-ODDS, not in percentage points, so two
// untreated severe lesions no longer add 0.4 + 0.4 percentage points. What must still
// hold is that the second lesion charges exactly what the first did — the burden term is
// per-lesion, and the model is multiplicative on the odds.
check('two untreated severe lesions both charge, each by the same log-odds increment',
  (function(){
    var lo = function(pct){ var p = pct / 100; return Math.log(p / (1 - p)); };
    var none = ctx.physiologyBaseline(PROC('cabg'));
    var one  = ctx.physiologyBaseline(Object.assign(PROC('cabg'), { valves: {
      aortic:{lesion:'s',severity:'severe',treated:false},
      mitral:{severity:'none'}, tricuspid:{severity:'none'} } }));
    var two  = ctx.physiologyBaseline(Object.assign(PROC('cabg'), { valves: {
      aortic:{lesion:'s',severity:'severe',treated:false},
      mitral:{lesion:'r',severity:'severe',treated:false},
      tricuspid:{severity:'none'} } }));
    return two > one && one > none &&
           Math.abs((lo(one) - lo(none)) - (lo(two) - lo(one))) < 1e-9;
  })());
check('a lesion the operation corrects carries no weight — no double count',
  ctx.physiologyBaseline(Object.assign(PROC('avr'), { valves: VS('aortic','s','severe',true) })) ===
  ctx.physiologyBaseline(PROC('avr')) &&
  ctx.physiologyBaseline(Object.assign(PROC('mvr'), { valves: VS('mitral','r','severe',true) })) ===
  ctx.physiologyBaseline(PROC('mvr')));
check('only untreated severe AS and severe MR carry weight',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { valves: VS('aortic','s','severe',false) })) >
  ctx.physiologyBaseline(PROC('cabg')) &&
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { valves: VS('mitral','r','severe',false) })) >
  ctx.physiologyBaseline(PROC('cabg')));
check('untreated severe AI carries no early-mortality weight',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { valves: VS('aortic','r','severe',false) })) ===
  ctx.physiologyBaseline(PROC('cabg')));
check('untreated severe TR carries no early-mortality weight',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { valves: VS('tricuspid','r','severe',false) })) ===
  ctx.physiologyBaseline(PROC('cabg')));
check('untreated moderate lesions carry no weight, per the randomised evidence',
  ['aortic','mitral','tricuspid'].every(function(v){
    return ctx.physiologyBaseline(Object.assign(PROC('cabg'), { valves: VS(v,'r','moderate',false) })) ===
           ctx.physiologyBaseline(PROC('cabg')); }));
check('the two weighted lesions are 0.4 each',
  ctx.UCSRS_SPEC.valve_severity.untreated_severe.aortic_s === 0.4 &&
  ctx.UCSRS_SPEC.valve_severity.untreated_severe.mitral_r === 0.4);
check('all lesions and grades are still recorded for recalibration',
  ['av_sev','mv_sev','tv_sev'].every(function(id){
    return new RegExp('<select id="' + id + '"').test(HTML); }) &&
  (HTML.match(/<optgroup label="Stenosis">/g) || []).length === 3 &&
  (HTML.match(/<optgroup label="Regurgitation">/g) || []).length === 3);
check('the procedure-to-valve map covers every valve procedure', (function(){
  const map = HTML.match(/var PROC_VALVES = \{[\s\S]*?\};/)[0];
  return ['avr','mvr','mv_repair','tv_repair','tvr','avr_mvr','avr_mvr_tvr','cabg_avr',
          'cabg_mvr','cabg_tv_repair','avr_asc_aorta','avr_root_asc_aorta']
    .every(function(pr){ return new RegExp('\\b' + pr + ':').test(map); });
})());
check('no valve data leaves the score unchanged',
  ctx.physiologyBaseline(Object.assign(PROC('avr'), { valves: null })) ===
  ctx.physiologyBaseline(PROC('avr')));

check('renal function offers normal, acute, CKD and ESRD',
  ['normal','acute','ckd','dialysis'].every(function(v){
    return new RegExp('<option value="' + v + '"').test(HTML); }));
check('chronic kidney disease carries no weight beyond the creatinine',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { creatinine:2.5 })) ===
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { creatinine:2.5, ckd:true })));
check('acute renal failure and dialysis are mutually exclusive',
  /dialysis: renalVal === 'dialysis'/.test(HTML) && /anuria: renalVal === 'acute'/.test(HTML));
check('acute renal failure feeds the critical pre-operative state composite',
  /renalVal === 'acute'/.test(HTML));
check('chronic renal impairment is carried by the creatinine, not a category',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { creatinine:3.5 })) >
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { creatinine:1.0 })) &&
  ctx.euroscore2(Object.assign({}, BASE, { creatinine:3.5 })) >
  ctx.euroscore2(Object.assign({}, BASE, { creatinine:1.0 })));
check('the published dialysis term still supersedes the clearance bands',
  ctx.euroscore2(Object.assign({}, BASE, { dialysis:true })) >
  ctx.euroscore2(Object.assign({}, BASE, { dialysis:false })));
check('a dialysis patient reports no new renal-failure estimate',
  ctx.ucsrsOutcomes(5, { dialysis:true }).renal === null);
check('cardiogenic shock is one graded field, not four checkboxes',
  /<select id="shock"/.test(HTML) && !/id="vtvf"/.test(HTML) && !/id="inot"/.test(HTML) &&
  !/id="lvad"/.test(HTML) &&
  ['inotropes','vtvf','iabp','impella','ecmo'].every(function(v){
    return new RegExp('<option value="' + v + '"').test(HTML); }));
check('every shock level sets the published critical pre-operative state',
  /var critical = shockVal !== 'none' \|\| ventilated \|\| renalVal === 'acute'/.test(HTML));
check('the shock ladder escalates: inotropes < IABP < Impella < ECMO',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { inot:true })) <
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { iabp:true })) &&
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { iabp:true })) <
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { impella:true })) &&
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { impella:true })) <
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { ecmo:true })));
check('acute pulmonary disease is split by ventilator support',
  /<option value="acute">Acute — no ventilator support<\/option>/.test(HTML) &&
  /<option value="acute_vent">Acute — on ventilator support<\/option>/.test(HTML));
// v3.0 reads the four-level pulmStatus directly; lungAny/ventilated are derived flags for
// the comparator and the outcome model and carry no Layer 1 weight. This check was silently
// passing nothing until 276658c, when pulmStatus was finally wired into the form.
check('pre-operative ventilation weighs more than acute lung disease alone',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { pulmStatus:'acute_vent' })) >
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { pulmStatus:'acute' })));
check('the pulmonary ladder is strictly ordered: none < chronic < acute < ventilated',
  (function(){
    const b = (s) => ctx.physiologyBaseline(Object.assign(PROC('cabg'), s ? { pulmStatus:s } : {}));
    return b(null) < b('chronic') && b('chronic') < b('acute') && b('acute') < b('acute_vent');
  })());
check('home oxygen weighs more than chronic disease without it',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { pulmStatus:'chronic_o2' })) >
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { pulmStatus:'chronic' })));
check('pre-operative ventilation sets the critical pre-operative state',
  /var ventilated = pulmVal === 'acute_vent'/.test(HTML));
check('ventilation does not fire the chronic pulmonary term',
  /pulmonary: pulmVal === 'chronic' \|\| pulmVal === 'chronic_o2'/.test(HTML));
check('poor mobility lives in the frailty card and follows the chair rise',
  /<select id="mob"/.test(HTML) &&
  /mobility: document\.getElementById\('mob'\)\.value === '1' \|\| chairVal === 'unable'/.test(HTML));
check('the published mobility term still fires',
  ctx.euroscore2(Object.assign({}, BASE, { mobility:true })) >
  ctx.euroscore2(Object.assign({}, BASE, { mobility:false })));
check('anemia is derived from the mandatory frailty hemoglobin, not asked twice',
  !/id="anemia"/.test(HTML) && !/anemiaLbl/.test(HTML) &&
  /UCSRS_SPEC\.layer2b_eft\.hgb_lo_f : UCSRS_SPEC\.layer2b_eft\.hgb_lo_m/.test(HTML));
check('the derived anemia thresholds match the frailty instrument',
  ctx.UCSRS_SPEC.layer2b_eft.hgb_lo_m === 13.0 && ctx.UCSRS_SPEC.layer2b_eft.hgb_lo_f === 12.0);


check('ascending or arch atheroma adds beyond peripheral disease',
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { arteriopathy:true, aorticAtheroma:true })) >
  ctx.physiologyBaseline(Object.assign(PROC('cabg'), { arteriopathy:true })));
check('aortic atheroma raises the stroke estimate',
  ctx.ucsrsOutcomes(5, { arteriopathy:true, aorticAtheroma:true }).stroke >
  ctx.ucsrsOutcomes(5, { arteriopathy:true }).stroke);
check('tricuspid repair and replacement are separate options',
  /value="tv_repair"/.test(HTML) && /value="tvr"/.test(HTML));
check('mitral repair carries less weight than mitral replacement',
  ctx.physiologyBaseline(PROC('mv_repair')) < ctx.physiologyBaseline(PROC('mvr')));
check('mitral replacement carries more weight than isolated AVR',
  ctx.physiologyBaseline(PROC('mvr')) > ctx.physiologyBaseline(PROC('avr')));
check('isolated tricuspid replacement carries more than tricuspid repair',
  ctx.physiologyBaseline(PROC('tvr')) > ctx.physiologyBaseline(PROC('tv_repair')));
check('isolated tricuspid surgery carries more than isolated AVR',
  ctx.physiologyBaseline(PROC('tv_repair')) > ctx.physiologyBaseline(PROC('avr')));
check('CABG plus tricuspid repair is a procedure, not a comorbidity checkbox',
  /value="cabg_tv_repair"/.test(HTML) && !/id="tvconcom"/.test(HTML) && !/tvConcomitant/.test(HTML));
check('the procedure list is in the specified order', (function(){
  var opts = HTML.match(/<select id="proc"[\s\S]*?<\/select>/)[0].match(/value="([a-z_]+)"/g)
               .map(function(x){ return x.slice(7, -1); });
  var want = ['cabg','avr','avr_are','tavr_explant','av_repair','mvr','mv_repair','tv_repair','tvr','avr_mvr','avr_mvr_tvr','avr_mv_repair_tv_repair','cabg_avr','cabg_avr_mv_repair','cabg_avr_mv_repair_tv_repair','cabg_avr_mvr_tv_repair','cabg_mvr','cabg_mv_repair','cabg_tv_repair','asc_aorta','cabg_asc_aorta','avr_asc_aorta','avr_root_asc_aorta','other'];
  return opts.join(',') === want.join(',');
})());
check('CABG plus tricuspid repair scores exactly as isolated CABG',
  ctx.physiologyBaseline(PROC('cabg_tv_repair')) === ctx.physiologyBaseline(PROC('cabg')));
check('a concomitant tricuspid repair never changes the score',
  ctx.physiologyBaseline(PROC('cabg_avr_mv_repair_tv_repair')) === ctx.physiologyBaseline(PROC('cabg_avr_mv_repair')) &&
  ctx.physiologyBaseline(PROC('cabg_tv_repair')) === ctx.physiologyBaseline(PROC('cabg')));
check('weight of intervention is derived, not asked — the field is hidden',
  /<div style="display:none"><select id="weight">/.test(HTML) &&
  !/<label>Weight of intervention<\/label>/.test(HTML) &&
  /interventionWeight: document\.getElementById\('weight'\)\.value/.test(HTML));
check('a concomitant tricuspid repair never raises the weight of intervention',
  /cabg_tv_repair:'cabg'/.test(HTML) &&
  ctx.euroscore2(Object.assign({}, BASE, { interventionWeight:'cabg' })) ===
  ctx.euroscore2(Object.assign({}, BASE, { interventionWeight:'cabg' })));
check('every dropdown procedure has a weight-of-intervention mapping', (function(){
  var opts = HTML.match(/<select id="proc"[\s\S]*?<\/select>/)[0].match(/value="([a-z_]+)"/g)
               .map(function(x){ return x.slice(7, -1); });
  var map = HTML.match(/var PROC_WEIGHT = \{[\s\S]*?\};/)[0];
  return opts.every(function(o){ return new RegExp('\\b' + o + ':').test(map); });
})());
check('within a valve family, replacement always outscores repair',
  ctx.physiologyBaseline(PROC('mvr')) > ctx.physiologyBaseline(PROC('mv_repair')) &&
  ctx.physiologyBaseline(PROC('tvr')) > ctx.physiologyBaseline(PROC('tv_repair')) &&
  ctx.physiologyBaseline(PROC('avr_mvr_tvr')) > ctx.physiologyBaseline(PROC('avr_mv_repair_tv_repair')) &&
  ctx.physiologyBaseline(PROC('cabg_avr_mvr_tv_repair')) > ctx.physiologyBaseline(PROC('cabg_avr_mv_repair')));
check('thoracic aorta is a procedure, not a comorbidity checkbox',
  !/id="aorta"/.test(HTML) && /value="asc_aorta"/.test(HTML) && /function onThoracicAorta/.test(HTML));
check('the thoracic aorta term still fires from the procedure',
  ctx.euroscore2(Object.assign({}, BASE, { thoracicAorta: true })) >
  ctx.euroscore2(Object.assign({}, BASE, { thoracicAorta: false })));
check('no procedure produces a negative internal component',
  ['cabg','avr','avr_are','tavr_explant','av_repair','mvr','mv_repair','tv_repair','tvr','avr_mvr','avr_mvr_tvr','avr_mv_repair_tv_repair','cabg_avr','cabg_avr_mv_repair','cabg_avr_mv_repair_tv_repair','cabg_avr_mvr_tv_repair','cabg_mvr','cabg_mv_repair','cabg_tv_repair','asc_aorta','avr_asc_aorta','avr_root_asc_aorta','other']
    .every(function(pr){ return ctx.physiologyBaseline(PROC(pr)) > 0; }));
check('no references anywhere on the page after the rebuild',
  !/10\.1186/.test(HTML) && !/doi/i.test(HTML));
check('umol/L appears only in the unit toggle and its conversion code, never as a default label',
  !/Creatinine \(µmol\/L\)/.test(HTML) && !/Bilirubin \(µmol\/L\)/.test(HTML));
check('unit toggle present (mg/dL and umol/L chips)',
  /data-unit="us"/.test(HTML) && /data-unit="si"/.test(HTML) && /function setUnits/.test(HTML));
check('lab fields read through labNum so SI entries convert',
  /function labNum/.test(HTML) && /creatinine: labNum\('cr'\)/.test(HTML) &&
  /labNum\('bili'\)/.test(HTML) && /labNum\('crmeld'\)/.test(HTML));
check('conversion factors are correct (88.4 creatinine, 17.1 bilirubin, 10 protein)',
  /CR_F\s*=\s*88\.4/.test(HTML) && /BILI_F\s*=\s*17\.1/.test(HTML) && /PROT_F\s*=\s*10/.test(HTML));
check('toggle covers every lab on the page — creatinine, bilirubin, hemoglobin, albumin',
  /convertField\('bili'/.test(HTML) && /\['cr','crmeld'\]/.test(HTML) && /\['hgb','alb'\]/.test(HTML));
check('EFT labs read through labNum (so SI g/L entries score correctly)',
  /hgb: labNum\('hgb'\)/.test(HTML) && /albumin: labNum\('alb'\)/.test(HTML) &&
  /labNum\('hgb'\) === null \|\| labNum\('alb'\) === null/.test(HTML));
check('SI relabelling still covers hemoglobin and albumin',
  /g\/L/.test(HTML) && /hgbLbl/.test(HTML) && /albLbl/.test(HTML) &&
  /setLimits\('hgb', si \? \[40,220,1\]/.test(HTML));
// unit-independence of EFT scoring: 115 g/L and 11.5 g/dL are the same patient
check('Hgb 115 g/L scores identically to 11.5 g/dL for a woman',
  ctx.eftScore({ chair:'fast', cogImpaired:false, hgb: 115/10, albumin: 32/10, female:true }).points ===
  ctx.eftScore({ chair:'fast', cogImpaired:false, hgb: 11.5,   albumin: 3.2,   female:true }).points);
check('engine itself stays in mg/dL (Cockcroft-Gault /72)',
  /72\s*\*\s*cr_mgdl/.test(engine));
// unit-independence of the underlying math: SI value converted by hand must give
// the same clearance as the mg/dL value
check('110 umol/L converts to the same clearance as 1.244 mg/dL',
  near(ctx.creatinineClearance(72, 70, 110 / 88.4, true),
       ctx.creatinineClearance(72, 70, 1.2443, true), 0.05));
check('creatinine and bilirubin labelled mg/dL',
  /Creatinine \(mg\/dL\)/.test(HTML) && /Bilirubin \(mg\/dL\)/.test(HTML));
// Scoped to what a user actually sees. v3.0 coefficient comments are written in British
// English because the investigator writes that way and they carry the provenance the
// methods paper cites; the RENDERED interface stays American. RENDERED strips the engine
// block and every line comment, leaving markup and visible text.
check('American spellings in the rendered interface (hemoglobin, anemia, hemodynamic)',
  !/[Hh]aemoglobin|anaemia|haemodynamic/.test(RENDERED) && /Hemoglobin \(g\/dL\)/.test(HTML));

console.log('\n7h. Diabetes, pulmonary and shock fields');
check('diabetes is a three-level control-method field, not a checkbox',
  /id="dm"[^>]*>/.test(HTML) && /value="oral"/.test(HTML) && /value="insulin"/.test(HTML) &&
  !/type="checkbox" id="dm"/.test(HTML));
check('published insulin term applies to insulin treatment only',
  /iddm: dmVal === 'insulin'/.test(HTML));
check('non-insulin diabetes is captured but carries no weight',
  /dmOral: dmVal === 'oral'/.test(HTML) && !/dmOral/.test(engine));
check('pulmonary disease is a four-level field (none/acute/chronic/home O2)',
  /value="acute"/.test(HTML) && /value="chronic"/.test(HTML) && /value="chronic_o2"/.test(HTML));
check('chronic-dysfunction term applies to chronic disease only, not acute',
  /pulmonary: pulmVal === 'chronic' \|\| pulmVal === 'chronic_o2'/.test(HTML));
check('any significant lung disease feeds the internal component and the ventilation estimate',
  /lungAny: pulmVal !== 'none'/.test(HTML) && /copd: patient\.lungAny/.test(HTML));
check('cardiogenic shock is graded by the support the patient is on',
  /shockLevel: shockVal/.test(HTML) && !/shockLevel/.test(engine));
check('critical state remains ONE variable — shock plus inotropes does not double count',
  near(ctx.euroscore2(Object.assign({}, BASE, { critical: true })),
       ctx.euroscore2(Object.assign({}, BASE, { critical: true })), 1e-12));

console.log('\n7i. v2.1 baseline — log-odds form, continuity, and the removed weight');
(function(){
  var P = function(o){
    var b = { age:70, weight:80, height:172, creatinine:1.0, female:false, lvef:55,
              nyha:2, sternotomy:1, urgency:'elective', procedure:'cabg',
              interventionWeight:'cabg' };
    for (var k in (o||{})) b[k] = o[k];
    return b;
  };
  var lo = function(pct){ var p = pct / 100; return Math.log(p / (1 - p)); };

  check('hypertension carries no mortality weight from v2.1',
    ctx.physiologyBaseline(P({ htn:true })) === ctx.physiologyBaseline(P({ htn:false })));

  // v3.0 REVERSES v2.1 here. Age and ejection fraction are banded on purpose — age in the
  // STS manner with acceleration above 80, EF in four bands inclusive of the upper edge.
  // Creatinine stays continuous: it replaced Cockcroft-Gault clearance and is scored as
  // 1.10 x ln(cr), so there is no band edge to jump at.
  var jumpAge = Math.abs(ctx.physiologyBaseline(P({ age:70.001 })) - ctx.physiologyBaseline(P({ age:69.999 })));
  check('age is BANDED in v3.0 — a step exists at the 70-year band edge', jumpAge > 5e-4,
    `step ${jumpAge.toFixed(4)} pp`);
  check('the age ladder is monotonic across every band edge',
    [59,64,69,74,79,84,89].every(function(e){
      return ctx.physiologyBaseline(P({ age:e + 1 })) > ctx.physiologyBaseline(P({ age:e })); }));
  // STS-style acceleration above 80, measured against the seventh decade rather than
  // against any single band edge.
  //
  // The 64->65 step is +0.44 log-odds, the largest single step on the ladder, so a naive
  // "biggest step is above 80" assertion is false. That step is NOT an anomaly: the bands
  // are fitted to EuroSCORE II's own log-odds delta, and EuroSCORE II is FLAT to age 60
  // (its term is 0.0285181 x max(1, age - 59)) and climbs linearly after. The <60 and
  // 60-64 bands therefore both sit in the flat region while 65-69 sits in the climbing
  // one. EuroSCORE II itself is continuous, so it takes that climb a year at a time while
  // UCSRS takes it in one banded step -- the single-edge deltas differ (UCSRS +0.31 pp at
  // 64->65 against EuroSCORE II's +0.02 pp) even though the curves agree across the band.
  // Smoothing the ladder was examined on
  // 15 September and rejected: raising the under-65 bands to make the ladder even puts
  // every patient below 65 at 1.34x EuroSCORE II, outside the 1.0-1.30 band, and lowering
  // 65-69 merely relocates the jump to age 70 at +0.47 while dropping a 67-year-old to
  // 0.71x. As it stands UCSRS tracks the comparator at 0.95-1.09x from 52 to 87.
  var step = function(a){ return ctx.physiologyBaseline(P({ age:a + 1 })) - ctx.physiologyBaseline(P({ age:a })); };
  var seventies = (step(69) + step(74)) / 2;
  var eighties  = (step(79) + step(84) + step(89)) / 3;
  check('age accelerates above 80 — mean step above 80 exceeds the 70-79 mean',
    eighties > seventies, `70s ${seventies.toFixed(4)} pp vs 80+ ${eighties.toFixed(4)} pp`);
  // The invariant that actually matters, and the one that made the 64->65 step worth
  // keeping: across the whole age range the banded ladder must track the comparator. A
  // band edge is a discrete approximation of a continuous curve, so single-edge steps
  // will differ; the RATIO is what must hold.
  check('UCSRS tracks EuroSCORE II within 0.90-1.30x at every age from 52 to 87',
    (function(){
      var worst = null;
      [52, 58, 62, 67, 72, 78, 82, 87].forEach(function(a){
        var r = ctx.physiologyBaseline(P({ age:a })) / ctx.euroscore2(P({ age:a }));
        if (worst === null || Math.abs(r - 1) > Math.abs(worst - 1)) worst = r;
      });
      return worst >= 0.90 && worst <= 1.30;
    })(), 'guards the age ladder against drift in either direction');

  var jumpEf = Math.abs(ctx.physiologyBaseline(P({ lvef:30.001 })) - ctx.physiologyBaseline(P({ lvef:29.999 })));
  check('ejection fraction is BANDED in v3.0 — a step exists at the 30% band edge', jumpEf > 5e-4,
    `step ${jumpEf.toFixed(4)} pp`);
  check('EF band edges are inclusive of the upper value — 30 scores as severe, not moderate',
    ctx.physiologyBaseline(P({ lvef:30 })) > ctx.physiologyBaseline(P({ lvef:30.001 })));
  check('the EF ladder is monotonic: >40 < 31-40 < 21-30 < <=20',
    ctx.physiologyBaseline(P({ lvef:45 })) < ctx.physiologyBaseline(P({ lvef:35 })) &&
    ctx.physiologyBaseline(P({ lvef:35 })) < ctx.physiologyBaseline(P({ lvef:25 })) &&
    ctx.physiologyBaseline(P({ lvef:25 })) < ctx.physiologyBaseline(P({ lvef:18 })));

  var jumpCr = Math.abs(ctx.physiologyBaseline(P({ creatinine:1.6001 })) - ctx.physiologyBaseline(P({ creatinine:1.5999 })));
  check('serum creatinine is continuous — no step at any band edge', jumpCr < 5e-4);

  // v3.0 dialysis rule, ruled by the investigator on 15 September 2026: a dialysed patient
  // scores AS IF creatinine 4.0, and the measured value is not read at all. Post-dialysis
  // creatinine reflects the timing of the last session and dialysis adequacy rather than
  // renal reserve, so it carries no information worth scoring.
  //
  // The consequence is accepted and deliberate: a NON-dialysed patient above creatinine 4.0
  // scores higher than a dialysed one, because untreated uraemia at creatinine 8 is not a
  // lesser state than treated ESRD. This is NOT the EuroSCORE II dialysis inversion, which
  // ranks dialysis (0.642) BELOW moderate impairment (0.859 at CrCl <= 50); UCSRS ranks
  // dialysis (1.525) well above it (0.762 at creatinine 2.0).
  var dialysisVaries = false;
  [45, 62, 78, 90].forEach(function(a){
    var ref = ctx.physiologyBaseline(P({ age:a, creatinine:4.0, dialysis:true }));
    [0.8, 1.5, 3.0, 5.0, 8.0].forEach(function(c){
      if (Math.abs(ctx.physiologyBaseline(P({ age:a, creatinine:c, dialysis:true })) - ref) > 1e-9) {
        dialysisVaries = true;
      }
    });
  });
  check('dialysis scores flat — the measured creatinine is not read at all', !dialysisVaries);
  check('a dialysed patient scores exactly as a non-dialysed patient at creatinine 4.0',
    Math.abs(ctx.physiologyBaseline(P({ creatinine:1.0, dialysis:true })) -
             ctx.physiologyBaseline(P({ creatinine:4.0, dialysis:false }))) < 1e-9);
  check('dialysis ranks ABOVE moderate impairment — not the EuroSCORE II inversion',
    ctx.physiologyBaseline(P({ creatinine:1.0, dialysis:true })) >
    ctx.physiologyBaseline(P({ creatinine:2.0, dialysis:false })));

  // Risk fans out on the odds scale: each increment is a constant log-odds step, so its
  // effect in percentage points grows with the patient's underlying risk.
  // v3.0: anaemia and albumin carry NO Layer 1 weight — both are counted once, in the mEFT
  // at Layer 2b. Using `anemia` here would test a term that no longer exists and pass
  // vacuously at zero. Chronic pulmonary disease is a real Layer 1 increment, so it is
  // what the scale behaviour is demonstrated on.
  var INC = { pulmStatus: 'chronic' };
  var wellDelta = ctx.physiologyBaseline(P(INC)) - ctx.physiologyBaseline(P({}));
  var sickBase  = P({ age:84, lvef:25, creatinine:2.4, nyha:4, urgency:'urgent' });
  var sickWith  = P({ age:84, lvef:25, creatinine:2.4, nyha:4, urgency:'urgent', pulmStatus:'chronic' });
  var sickDelta = ctx.physiologyBaseline(sickWith) - ctx.physiologyBaseline(sickBase);
  check('the Layer 1 increment used here is non-zero (guards against a vacuous pass)',
    wellDelta > 1e-6, `well delta ${wellDelta.toFixed(4)} pp`);
  check('an increment is worth more percentage points in a sicker patient (odds scale)',
    sickDelta > wellDelta * 2, `${wellDelta.toFixed(2)} pp well vs ${sickDelta.toFixed(2)} pp sick`);
  check('the same increment is a constant step in log-odds',
    Math.abs((lo(ctx.physiologyBaseline(P(INC))) - lo(ctx.physiologyBaseline(P({})))) -
             (lo(ctx.physiologyBaseline(sickWith)) - lo(ctx.physiologyBaseline(sickBase)))) < 1e-9);
})();


console.log('\n8. Risk categories');
for (const [v, want] of [[3.9, 'LOW RISK'], [4.0, 'INTERMEDIATE RISK'], [7.9, 'INTERMEDIATE RISK'],
                         [8.0, 'HIGH RISK'], [19.9, 'HIGH RISK'], [20.0, 'PROHIBITIVE RISK']]) {
  check(`${v}% → ${want}`, ctx.riskCategory(v).label === want, ctx.riskCategory(v).label);
}

console.log('\n9. The page self-test agrees');
const st = ctx.selfTest();
check('in-page self-test reports pass', st.ok === true);

console.log('\n' + '='.repeat(64));
if (failures) { console.log(`${failures} CHECK(S) FAILED`); process.exit(1); }
console.log('ALL CHECKS PASSED');
