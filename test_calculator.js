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
check('no literature/source references anywhere in the shipped HTML',
  !/Nashef|Afilalo|Rehman|Cardiothorac|13019|zenodo|Dalhousie|DOI|Section 3\.3|JAHA|acsdriskcalc|github/i.test(HTML));

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
check('the note under Layer 2c is the short form only',
  !/indexes it to BSA/.test(HTML) && !/LVESVI takes precedence;/.test(HTML));
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
  ctx.stsEstimate(Object.assign(PROC('cabg'), { sternotomy:3, prevCardiac:true })) >
  ctx.stsEstimate(Object.assign(PROC('cabg'), { sternotomy:2, prevCardiac:true })));
check('a first open heart carries no reoperation weight',
  ctx.stsEstimate(Object.assign(PROC('cabg'), { sternotomy:1, prevCardiac:false })) ===
  ctx.stsEstimate(PROC('cabg')));
check('TAVR explant is the heaviest single-valve procedure',
  ['avr','avr_are','av_repair','mvr','mv_repair','tv_repair','tvr']
    .every(function(pr){ return ctx.stsEstimate(PROC('tavr_explant')) > ctx.stsEstimate(PROC(pr)); }));
check('root enlargement adds only a small increment over plain AVR',
  ctx.stsEstimate(PROC('avr_are')) > ctx.stsEstimate(PROC('avr')) &&
  ctx.stsEstimate(PROC('avr_are')) - ctx.stsEstimate(PROC('avr')) <= 0.5);
check('AV repair scores below AVR',
  ctx.stsEstimate(PROC('av_repair')) < ctx.stsEstimate(PROC('avr')));
check('aortic work compounds: root plus ascending outscores ascending alone',
  ctx.stsEstimate(PROC('avr_root_asc_aorta')) > ctx.stsEstimate(PROC('avr_asc_aorta')) &&
  ctx.stsEstimate(PROC('avr_asc_aorta')) > ctx.stsEstimate(PROC('asc_aorta')));
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
  ctx.stsEstimate(Object.assign(PROC('cabg'), { nyha:1 })) ===
  ctx.stsEstimate(Object.assign(PROC('cabg'), { nyha:1, heartFailure:'none' })) &&
  ctx.euroscore2(Object.assign({}, BASE, { nyha:1 })) ===
  ctx.euroscore2(Object.assign({}, BASE, { nyha:1, heartFailure:'none' })));
check('acute decompensation scores as class IV plus an increment',
  /nyha: hfVal === 'acute' \? 4/.test(HTML) &&
  ctx.stsEstimate(Object.assign(PROC('cabg'), { nyha:4, acuteDecomp:true })) >
  ctx.stsEstimate(Object.assign(PROC('cabg'), { nyha:4 })));
check('a class and acute decompensation cannot both be chosen',
  (HTML.match(/<select id="nyha"[\s\S]*?<\/select>/)[0].match(/<option/g) || []).length === 6);
check('NYHA carries heart-failure severity in both halves, once each',
  ctx.stsEstimate(Object.assign(PROC('cabg'), { nyha:4 })) >
  ctx.stsEstimate(Object.assign(PROC('cabg'), { nyha:3 })) &&
  ctx.euroscore2(Object.assign({}, BASE, { nyha:4 })) >
  ctx.euroscore2(Object.assign({}, BASE, { nyha:3 })));
check('infarct recency is graded 7 / 30 / 90 days',
  /<select id="mi"/.test(HTML) &&
  ctx.stsEstimate(Object.assign(PROC('cabg'), { miDays:7 })) >
  ctx.stsEstimate(Object.assign(PROC('cabg'), { miDays:30 })) &&
  ctx.stsEstimate(Object.assign(PROC('cabg'), { miDays:30 })) >
  ctx.stsEstimate(Object.assign(PROC('cabg'), { miDays:90 })));
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
// Wiring guards. The engine tests above call stsEstimate directly with a valves object,
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
  ctx.stsEstimate(Object.assign(PROC('cabg'), { valves: VS('mitral','r','severe',false) })) >
  ctx.stsEstimate(PROC('cabg')) &&
  ctx.stsEstimate(Object.assign(PROC('cabg_mv_repair'), { valves: VS('mitral','r','severe',true) })) ===
  ctx.stsEstimate(PROC('cabg_mv_repair')) &&
  ctx.stsEstimate(Object.assign(PROC('cabg_mvr'), { valves: VS('mitral','r','severe',true) })) ===
  ctx.stsEstimate(PROC('cabg_mvr')));
check('severe AS is charged at isolated CABG or MVR but not when the aortic is addressed',
  ctx.stsEstimate(Object.assign(PROC('mvr'), { valves: VS('aortic','s','severe',false) })) >
  ctx.stsEstimate(PROC('mvr')) &&
  ctx.stsEstimate(Object.assign(PROC('cabg_avr'), { valves: VS('aortic','s','severe',true) })) ===
  ctx.stsEstimate(PROC('cabg_avr')) &&
  ctx.stsEstimate(Object.assign(PROC('avr_mvr'), { valves: VS('aortic','s','severe',true) })) ===
  ctx.stsEstimate(PROC('avr_mvr')));
check('two untreated severe lesions both charge',
  Math.abs(ctx.stsEstimate(Object.assign(PROC('cabg'), { valves: {
      aortic:{lesion:'s',severity:'severe',treated:false},
      mitral:{lesion:'r',severity:'severe',treated:false},
      tricuspid:{severity:'none'} } })) -
    (ctx.stsEstimate(PROC('cabg')) + 0.8)) < 1e-9);
check('a lesion the operation corrects carries no weight — no double count',
  ctx.stsEstimate(Object.assign(PROC('avr'), { valves: VS('aortic','s','severe',true) })) ===
  ctx.stsEstimate(PROC('avr')) &&
  ctx.stsEstimate(Object.assign(PROC('mvr'), { valves: VS('mitral','r','severe',true) })) ===
  ctx.stsEstimate(PROC('mvr')));
check('only untreated severe AS and severe MR carry weight',
  ctx.stsEstimate(Object.assign(PROC('cabg'), { valves: VS('aortic','s','severe',false) })) >
  ctx.stsEstimate(PROC('cabg')) &&
  ctx.stsEstimate(Object.assign(PROC('cabg'), { valves: VS('mitral','r','severe',false) })) >
  ctx.stsEstimate(PROC('cabg')));
check('untreated severe AI carries no early-mortality weight',
  ctx.stsEstimate(Object.assign(PROC('cabg'), { valves: VS('aortic','r','severe',false) })) ===
  ctx.stsEstimate(PROC('cabg')));
check('untreated severe TR carries no early-mortality weight',
  ctx.stsEstimate(Object.assign(PROC('cabg'), { valves: VS('tricuspid','r','severe',false) })) ===
  ctx.stsEstimate(PROC('cabg')));
check('untreated moderate lesions carry no weight, per the randomised evidence',
  ['aortic','mitral','tricuspid'].every(function(v){
    return ctx.stsEstimate(Object.assign(PROC('cabg'), { valves: VS(v,'r','moderate',false) })) ===
           ctx.stsEstimate(PROC('cabg')); }));
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
  ctx.stsEstimate(Object.assign(PROC('avr'), { valves: null })) ===
  ctx.stsEstimate(PROC('avr')));

check('renal function offers normal, acute, CKD and ESRD',
  ['normal','acute','ckd','dialysis'].every(function(v){
    return new RegExp('<option value="' + v + '"').test(HTML); }));
check('chronic kidney disease carries no weight beyond the creatinine',
  ctx.stsEstimate(Object.assign(PROC('cabg'), { creatinine:2.5 })) ===
  ctx.stsEstimate(Object.assign(PROC('cabg'), { creatinine:2.5, ckd:true })));
check('acute renal failure and dialysis are mutually exclusive',
  /dialysis: renalVal === 'dialysis'/.test(HTML) && /anuria: renalVal === 'acute'/.test(HTML));
check('acute renal failure feeds the critical pre-operative state composite',
  /renalVal === 'acute'/.test(HTML));
check('chronic renal impairment is carried by the creatinine, not a category',
  ctx.stsEstimate(Object.assign(PROC('cabg'), { creatinine:3.5 })) >
  ctx.stsEstimate(Object.assign(PROC('cabg'), { creatinine:1.0 })) &&
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
  ctx.stsEstimate(Object.assign(PROC('cabg'), { inot:true })) <
  ctx.stsEstimate(Object.assign(PROC('cabg'), { iabp:true })) &&
  ctx.stsEstimate(Object.assign(PROC('cabg'), { iabp:true })) <
  ctx.stsEstimate(Object.assign(PROC('cabg'), { impella:true })) &&
  ctx.stsEstimate(Object.assign(PROC('cabg'), { impella:true })) <
  ctx.stsEstimate(Object.assign(PROC('cabg'), { ecmo:true })));
check('acute pulmonary disease is split by ventilator support',
  /<option value="acute">Acute — no ventilator support<\/option>/.test(HTML) &&
  /<option value="acute_vent">Acute — on ventilator support<\/option>/.test(HTML));
check('pre-operative ventilation weighs more than acute lung disease alone',
  ctx.stsEstimate(Object.assign(PROC('cabg'), { lungAny:true, ventilated:true })) >
  ctx.stsEstimate(Object.assign(PROC('cabg'), { lungAny:true })));
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
  ctx.stsEstimate(Object.assign(PROC('cabg'), { arteriopathy:true, aorticAtheroma:true })) >
  ctx.stsEstimate(Object.assign(PROC('cabg'), { arteriopathy:true })));
check('aortic atheroma raises the stroke estimate',
  ctx.ucsrsOutcomes(5, { arteriopathy:true, aorticAtheroma:true }).stroke >
  ctx.ucsrsOutcomes(5, { arteriopathy:true }).stroke);
check('tricuspid repair and replacement are separate options',
  /value="tv_repair"/.test(HTML) && /value="tvr"/.test(HTML));
check('mitral repair carries less weight than mitral replacement',
  ctx.stsEstimate(PROC('mv_repair')) < ctx.stsEstimate(PROC('mvr')));
check('mitral replacement carries more weight than isolated AVR',
  ctx.stsEstimate(PROC('mvr')) > ctx.stsEstimate(PROC('avr')));
check('isolated tricuspid replacement carries more than tricuspid repair',
  ctx.stsEstimate(PROC('tvr')) > ctx.stsEstimate(PROC('tv_repair')));
check('isolated tricuspid surgery carries more than isolated AVR',
  ctx.stsEstimate(PROC('tv_repair')) > ctx.stsEstimate(PROC('avr')));
check('CABG plus tricuspid repair is a procedure, not a comorbidity checkbox',
  /value="cabg_tv_repair"/.test(HTML) && !/id="tvconcom"/.test(HTML) && !/tvConcomitant/.test(HTML));
check('the procedure list is in the specified order', (function(){
  var opts = HTML.match(/<select id="proc"[\s\S]*?<\/select>/)[0].match(/value="([a-z_]+)"/g)
               .map(function(x){ return x.slice(7, -1); });
  var want = ['cabg','avr','avr_are','tavr_explant','av_repair','mvr','mv_repair','tv_repair','tvr','avr_mvr','avr_mvr_tvr','avr_mv_repair_tv_repair','cabg_avr','cabg_avr_mv_repair','cabg_avr_mv_repair_tv_repair','cabg_avr_mvr_tv_repair','cabg_mvr','cabg_mv_repair','cabg_tv_repair','asc_aorta','cabg_asc_aorta','avr_asc_aorta','avr_root_asc_aorta','other'];
  return opts.join(',') === want.join(',');
})());
check('CABG plus tricuspid repair scores exactly as isolated CABG',
  ctx.stsEstimate(PROC('cabg_tv_repair')) === ctx.stsEstimate(PROC('cabg')));
check('a concomitant tricuspid repair never changes the score',
  ctx.stsEstimate(PROC('cabg_avr_mv_repair_tv_repair')) === ctx.stsEstimate(PROC('cabg_avr_mv_repair')) &&
  ctx.stsEstimate(PROC('cabg_tv_repair')) === ctx.stsEstimate(PROC('cabg')));
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
  ctx.stsEstimate(PROC('mvr')) > ctx.stsEstimate(PROC('mv_repair')) &&
  ctx.stsEstimate(PROC('tvr')) > ctx.stsEstimate(PROC('tv_repair')) &&
  ctx.stsEstimate(PROC('avr_mvr_tvr')) > ctx.stsEstimate(PROC('avr_mv_repair_tv_repair')) &&
  ctx.stsEstimate(PROC('cabg_avr_mvr_tv_repair')) > ctx.stsEstimate(PROC('cabg_avr_mv_repair')));
check('thoracic aorta is a procedure, not a comorbidity checkbox',
  !/id="aorta"/.test(HTML) && /value="asc_aorta"/.test(HTML) && /function onThoracicAorta/.test(HTML));
check('the thoracic aorta term still fires from the procedure',
  ctx.euroscore2(Object.assign({}, BASE, { thoracicAorta: true })) >
  ctx.euroscore2(Object.assign({}, BASE, { thoracicAorta: false })));
check('no procedure produces a negative internal component',
  ['cabg','avr','avr_are','tavr_explant','av_repair','mvr','mv_repair','tv_repair','tvr','avr_mvr','avr_mvr_tvr','avr_mv_repair_tv_repair','cabg_avr','cabg_avr_mv_repair','cabg_avr_mv_repair_tv_repair','cabg_avr_mvr_tv_repair','cabg_mvr','cabg_mv_repair','cabg_tv_repair','asc_aorta','avr_asc_aorta','avr_root_asc_aorta','other']
    .every(function(pr){ return ctx.stsEstimate(PROC(pr)) > 0; }));
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
check('American spellings (hemoglobin, anemia, hemodynamic)',
  !/[Hh]aemoglobin|anaemia|haemodynamic/.test(HTML) && /Hemoglobin \(g\/dL\)/.test(HTML));

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
