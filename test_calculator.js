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

const ctx = {};
new Function('exports', engine + '\nexports.ucsrs=ucsrs;exports.euroscore2=euroscore2;' +
  'exports.meldCorrection=meldCorrection;exports.meldFromLabs=meldFromLabs;' +
  'exports.creatinineClearance=creatinineClearance;exports.UCSRS_SPEC=UCSRS_SPEC;' +
  'exports.riskCategory=riskCategory;exports.selfTest=selfTest;exports.stsEstimate=stsEstimate;exports.eftScore=eftScore;exports.ucsrsOutcomes=ucsrsOutcomes;')(ctx);

let failures = 0;
function check(name, ok, detail) {
  console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
  if (!ok) failures++;
}
function near(a, b, tol = 0.005) { return Math.abs(a - b) < tol; }

console.log('\n1. The published worked cases (J Cardiothorac Surg 2026, Section 5.4)');
const c1 = ctx.ucsrs({ stsPromPct: 2.8, euroPct: 3.2, eft: 3, meld: null, lvedd: 52, tier: 0 });
check('Case 1 — 65M SAVR, ×1.60 (was CFS 7, now EFT 3)', near(c1.final, 4.80), `got ${c1.final.toFixed(2)}%, paper prints 4.8%`);
const c2 = ctx.ucsrs({ stsPromPct: 3.5, euroPct: 2.0, eft: 0, meld: 17, lvedd: 50, tier: 0 });
check('Case 2 — 70M CABG, MELD 17', near(c2.final, 7.35), `got ${c2.final.toFixed(2)}%, paper prints 7.4%`);
const c3 = ctx.ucsrs({ stsPromPct: 7.0, euroPct: 9.0, eft: 1, meld: 15, lvedd: 62, syntax: 14, tier: 0 });
check('Case 3 — computes per Section 3.3', near(c3.final, 12.92),
  `got ${c3.final.toFixed(2)}%; the paper prints 18.2%, which Section 3.3 does not produce`);

console.log('\n2. Structural guards — these fail if the model drifts back');
check('Layer 1 STS weight is 0.50', ctx.UCSRS_SPEC.layer1.w_sts === 0.50, `is ${ctx.UCSRS_SPEC.layer1.w_sts}`);
check('Layer 1 Euro weight is 0.50', ctx.UCSRS_SPEC.layer1.w_euro === 0.50, `is ${ctx.UCSRS_SPEC.layer1.w_euro}`);
check('weights sum to 1.00 — no third or fourth term',
  ctx.UCSRS_SPEC.layer1.w_sts + ctx.UCSRS_SPEC.layer1.w_euro === 1.00);
check('no morbidity index anywhere in the file', !/morbIdx|morbidity_index|morbIndex/i.test(HTML));
check('no STS input field — score is free-standing', !/id="sts"/.test(HTML));
check('STS computed internally by stsEstimate', /function\s+stsEstimate/.test(engine) && /stsEstimate\(patient\)/.test(HTML));
check('Layer 2c LVESVI bands present', ctx.UCSRS_SPEC.layer2c.lvesvi.length === 3);
check('Layer 2c LVEDD bands present', ctx.UCSRS_SPEC.layer2c.lvedd.length === 3);
check('Layer 2c SYNTAX bands present', ctx.UCSRS_SPEC.layer2c.syntax.length === 3);
check('caps are 60 / 65 / 70',
  ctx.UCSRS_SPEC.layer1.cap_br === 60 && ctx.UCSRS_SPEC.layer2a_meld.cap_pre_cfs === 65 &&
  ctx.UCSRS_SPEC.layer2b_eft.cap === 70);

console.log('\n3. Layer 2c bands, hand-worked');
const L2C = [
  ['LVESVI 55 → +0.0', { lvesvi: 55 }, 0.0], ['LVESVI 80 → +0.5', { lvesvi: 80 }, 0.5],
  ['LVESVI 120 → +2.0', { lvesvi: 120 }, 2.0],
  ['LVEDD 50 → +0.0', { lvedd: 50 }, 0.0], ['LVEDD 60 → +0.5', { lvedd: 60 }, 0.5],
  ['LVEDD 70 → +1.5', { lvedd: 70 }, 1.5],
];
for (const [name, extra, want] of L2C) {
  const r = ctx.ucsrs(Object.assign({ stsPromPct: 4, euroPct: 4, eft: 0, meld: null, tier: 0 }, extra));
  check(name, near(r.lv, want), `got +${r.lv.toFixed(1)}`);
}
for (const [sx, want] of [[10, 0.0], [28, 1.0], [40, 2.5], [0, 0.0]]) {
  const r = ctx.ucsrs({ stsPromPct: 4, euroPct: 4, eft: 0, meld: null, syntax: sx, tier: 0 });
  check(`SYNTAX ${sx} → +${want.toFixed(1)}`, near(r.syntax, want), `got +${r.syntax.toFixed(1)}`);
}
const pref = ctx.ucsrs({ stsPromPct: 4, euroPct: 4, eft: 0, meld: null, lvesvi: 120, lvedd: 50, tier: 0 });
check('LVESVI takes precedence over LVEDD', pref.lvSource === 'LVESVI' && near(pref.lv, 2.0));

console.log('\n4. MELD is fully additive, not weighted at 0.10');
for (const [m, want] of [[8, 0.0], [12, 1.6], [15, 2.8], [18, 5.5], [20, 7.3], [30, 19.3], [40, 31.3]]) {
  check(`MELD ${m} → +${want}`, near(ctx.meldCorrection(m), want), `got +${ctx.meldCorrection(m).toFixed(2)}`);
}
const mA = ctx.ucsrs({ stsPromPct: 10, euroPct: 10, eft: 0, meld: null, tier: 0 });
const mB = ctx.ucsrs({ stsPromPct: 10, euroPct: 10, eft: 0, meld: 20, tier: 0 });
check('MELD 20 adds 7.30 points, not 0.73', near(mB.final - mA.final, 7.30),
  `adds ${(mB.final - mA.final).toFixed(2)}`);

console.log('\n5. Caps');
check('BR capped at 60', near(ctx.ucsrs({ stsPromPct: 90, euroPct: 90, eft: 0, meld: null, tier: 0 }).br, 60));
check('PRE_CFS capped at 65',
  near(ctx.ucsrs({ stsPromPct: 90, euroPct: 90, eft: 0, meld: 40, tier: 0 }).preCfs, 65));
check('final capped at 70',
  near(ctx.ucsrs({ stsPromPct: 90, euroPct: 90, eft: 5, meld: 40, lvesvi: 150, syntax: 50, tier: 0 }).final, 70));

console.log('\n6. Layer 3 haemodynamics');
const h = ctx.ucsrs({ stsPromPct: 4, euroPct: 4, eft: 0, meld: null, tier: 2,
  map: 60, co: 3.0, pvr: 6.0, ci: 1.8, tapse: 14, pasprhc: 50 });
check('all four derangements → +8.60', near(h.hemo, 8.60), `got +${h.hemo.toFixed(2)}`);
const h2 = ctx.ucsrs({ stsPromPct: 4, euroPct: 4, eft: 0, meld: null, tier: 2,
  map: 90, co: 5.5, pvr: 1.5, ci: 3.0, tapse: 22, pasprhc: 35 });
check('normal haemodynamics → +0.00', near(h2.hemo, 0));
const h3 = ctx.ucsrs({ stsPromPct: 4, euroPct: 4, eft: 0, meld: null, tier: 0,
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

console.log('\n7c. STS source behaviour');
check('estimator matches the previous calculator baseline (60M elective CABG = 1.50)',
  (function(){ try { return Math.abs(ctx.stsEstimate({age:60,weight:80,creatinine:0.9,female:false,dialysis:false,lvef:60,nyha:1,urgency:'elective',procedure:'cabg'}) - 1.5) < 1e-9; } catch(e){ return false; } })());

console.log('\n7d. Layer 2b — Essential Frailty Toolset (v1.1)');
const M = ctx.UCSRS_SPEC.layer2b_eft.mult;
check('multiplier ladder retained from published v1.0 (1.00/1.15/1.35/1.60/1.90/2.30)',
  M[0] === 1.00 && M[1] === 1.15 && M[2] === 1.35 && M[3] === 1.60 && M[4] === 1.90 && M[5] === 2.30,
  JSON.stringify(M));
check('EFT is 0-5 (six multiplier levels)', Object.keys(M).length === 6);
const efts = (f) => ctx.eftScore(Object.assign({ chairUnable: false, chairSec: 9, cogImpaired: false, hgb: 14, albumin: 4.0, female: false }, f));
check('robust patient → EFT 0', efts({}).points === 0);
check('chair rise >=15 s → 1 point', efts({ chairSec: 15 }).points === 1);
check('unable to rise → 2 points', efts({ chairUnable: true }).points === 2);
check('cognitive impairment → 1 point', efts({ cogImpaired: true }).points === 1);
check('Hgb 12.5 scores in men, not women',
  efts({ hgb: 12.5 }).points === 1 && efts({ hgb: 12.5, female: true }).points === 0);
check('Hgb threshold: women <12', efts({ hgb: 11.9, female: true }).points === 1);
check('albumin <3.5 → 1 point', efts({ albumin: 3.4 }).points === 1);
check('worst case → EFT 5', efts({ chairUnable: true, cogImpaired: true, hgb: 10, albumin: 3.0 }).points === 5);
check('missing chair + cognition → partial from labs',
  (function(){ const e = ctx.eftScore({ chairUnable: false, chairSec: null, cogImpaired: null, hgb: 11, albumin: 3.2, female: false });
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
check('no literature/source references anywhere in the shipped HTML',
  !/Nashef|Afilalo|Rehman|Cardiothorac|13019|zenodo|Dalhousie|DOI|Section 3\.3|JAHA|acsdriskcalc|github/i.test(HTML));

console.log('\n7g. MELD from labs (mg/dL) and units');
check('MELD floors at 6 for normal labs', ctx.meldFromLabs(0.8, 1.0, 0.9, false) === 6,
  `got ${ctx.meldFromLabs(0.8, 1.0, 0.9, false)}`);
check('MELD: bili 3.0, INR 1.8, Cr 2.0 -> 24', ctx.meldFromLabs(3.0, 1.8, 2.0, false) === 24,
  `got ${ctx.meldFromLabs(3.0, 1.8, 2.0, false)}`);
check('dialysed twice a week scores creatinine as 4.0 mg/dL',
  ctx.meldFromLabs(1.0, 1.0, 1.0, true) === ctx.meldFromLabs(1.0, 1.0, 4.0, false));
check('creatinine capped at 4.0 mg/dL',
  ctx.meldFromLabs(1.0, 1.0, 9.0, false) === ctx.meldFromLabs(1.0, 1.0, 4.0, false));
check('no umol/L units remain on the page', !/µmol|umol/i.test(HTML));
check('creatinine and bilirubin labelled mg/dL',
  /Creatinine \(mg\/dL\)/.test(HTML) && /Bilirubin \(mg\/dL\)/.test(HTML));
check('American spellings (hemoglobin, anemia, hemodynamic)',
  !/[Hh]aemoglobin|anaemia|haemodynamic/.test(HTML) && /Hemoglobin \(g\/dL\)/.test(HTML));

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
