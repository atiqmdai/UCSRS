// Parity runner. Loads the engine block out of the calculator exactly as
// test_calculator.js does, reads a JSON array of patient cases on stdin, and prints
// one JSON result per case. test_engine_parity.py compares these against the Python
// port and fails on any disagreement beyond 0.005 percentage points.
const fs = require("fs");
const path = require("path");

// The calculator ships as index.html in the source repository and as
// UCSRS_Calculator.index.html in the trial package. Try both, exactly as
// test_calculator.js does, and say plainly which names were tried if neither is here.
const CANDIDATES = ["index.html", "UCSRS_Calculator.index.html"];
const HTML = (function () {
  for (const name of CANDIDATES) {
    const candidate = path.join(__dirname, name);
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error("calculator not found beside this script; tried " + CANDIDATES.join(", "));
})();
const START = "// ===== UCSRS ENGINE START =====";
const END = "// ===== UCSRS ENGINE END =====";

const src = fs.readFileSync(HTML, "utf8");
const a = src.indexOf(START);
const b = src.indexOf(END);
if (a < 0 || b < 0) throw new Error("engine markers not found in " + HTML);
const engine = src.slice(a, b + END.length);

const sandbox = {};
new Function("global", engine + "\nObject.assign(global, {UCSRS_SPEC, ucsrs, euroscore2, " +
  "stsEstimate, eftScore, meldFromLabs, meldCorrection, bsaMosteller, " +
  "creatinineClearance, valveBurden, ucsrsOutcomes, band});")(sandbox);

// --constants: emit the lookup tables that live OUTSIDE the engine block (the form's
// procedure maps). The Python port duplicates them, so they have to be checked too.
if (process.argv.includes("--constants")) {
  // Each is declared as `var NAME = <literal>;` — take the text from the `=` to the
  // first `;` that closes the literal, and evaluate it.
  const grab = (name, close) => {
    const i = src.indexOf("var " + name + " =");
    if (i < 0) throw new Error("declaration not found: " + name);
    const j = src.indexOf(close + ";", i);
    if (j < 0) throw new Error("terminator not found for: " + name);
    const literal = src.slice(src.indexOf("=", i) + 1, j + close.length);
    return new Function("return (" + literal + ")")();
  };
  process.stdout.write(JSON.stringify({
    PROC_VALVES: grab("PROC_VALVES", "}"),
    PROC_WEIGHT: grab("PROC_WEIGHT", "}"),
    AORTA_PROCS: grab("AORTA_PROCS", "]"),
    SPEC: sandbox.UCSRS_SPEC,
  }));
  process.exit(0);
}

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const out = input.map(function (c) {
  const p = c.patient;
  const baseline = sandbox.stsEstimate(p);
  const euro = sandbox.euroscore2(p);
  const eft = sandbox.eftScore(c.frailty);
  const meld = c.meld === null || c.meld === undefined
    ? null
    : sandbox.meldFromLabs(c.meld.bili, c.meld.inr, c.meld.cr);
  const r = sandbox.ucsrs({
    stsPromPct: baseline, euroPct: euro, eft: eft.points, meld: meld,
    lvesvi: c.lvesvi, lvedd: c.lvedd, syntax: c.syntax, tier: c.tier,
    map: c.map, co: c.co, pvr: c.pvr, ci: c.ci, tapse: c.tapse, pasprhc: c.pasprhc,
  });
  const oc = sandbox.ucsrsOutcomes(r.final, c.outcomeContext || {});
  return {
    baseline: baseline, euro: euro, eft: eft.points, meld: meld,
    br: r.br, meldCorr: r.meldCorr, preCfs: r.preCfs, mult: r.mult, base: r.base,
    lv: r.lv, syntax: r.syntax, hemo: r.hemo, final: r.final,
    stroke: oc.stroke, renal: oc.renal, vent: oc.vent, reop: oc.reop,
    bsa: sandbox.bsaMosteller(p.height, p.weight),
    cc: sandbox.creatinineClearance(p.age, p.weight, p.creatinine, p.female),
  };
});
process.stdout.write(JSON.stringify(out));
