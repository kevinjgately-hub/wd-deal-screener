// Checks that the browser engine (engine.js) gives exactly the same screening results as screen.py,
// and that its quote check accepts all five real extractions and rejects a planted number.
// Run after screen.py:  node test_engine.js
const fs = require("fs"), path = require("path");
const Engine = require("./engine.js");
const run = JSON.parse(fs.readFileSync(path.join(__dirname, "out/results.json"), "utf8"));
let fails = 0;
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const close = (a, b) => (a == null && b == null) || (a != null && b != null && Math.abs(a - b) < 1e-9);

for (const py of run.deals) {
  const js = Engine.screen(py.extraction, run.box);
  const checks = {
    status: eq(js.status, py.status),
    codes: eq(js.findings.map(f => f.code + ":" + f.result), py.findings.map(f => f.code + ":" + f.result)),
    open_items: js.open_items === py.open_items,
    cushion: close(js.cushion, py.cushion),
    fixed_outcome: js.fixed_outcome === py.fixed_outcome,
    unreliable: eq(js.unreliable_metrics, py.unreliable_metrics),
    metrics: Object.keys(py.metrics).every(k => close(js.metrics[k].value, py.metrics[k].value)),
  };
  const src = fs.readFileSync(path.join(__dirname, "deals", py.deal_id.toLowerCase() + ".md"), "utf8");
  const ver = Engine.verify(py.extraction, src);
  checks.quotes = ver.problems.length === 0;
  const bad = Object.entries(checks).filter(([, ok]) => !ok).map(([k]) => k);
  if (bad.length) fails++;
  console.log(`${bad.length ? "FAIL" : "PASS"}  ${py.deal_id}  python=${py.status}  js=${js.status}${bad.length ? "  mismatch: " + bad.join(", ") + (ver.problems.length ? " " + ver.problems.join("; ") : "") : ""}`);
}

// Planted number: must be discarded and push the deal to Needs review.
const d1 = run.deals.find(d => d.deal_id === "DEAL-001");
const tampered = JSON.parse(JSON.stringify(d1.extraction));
tampered.noi = { value: 3900000, quote: "Net operating income (NOI): $3,900,000", status: "stated" };
const src1 = fs.readFileSync(path.join(__dirname, "deals/deal-001.md"), "utf8");
const v1 = Engine.verify(tampered, src1), s1 = Engine.screen(v1.extraction, run.box);
const plantedOk = v1.problems.length === 1 && v1.extraction.noi.value === null && s1.status === "Needs review";
if (!plantedOk) fails++;
console.log(`${plantedOk ? "PASS" : "FAIL"}  planted NOI on DEAL-001 -> discarded, status ${s1.status}`);

// Abbreviated numbers must be accepted.
const abbrevOk = [[21500000, "Ask: $21.5M agency refi"], [1550000, "~$1.55M/yr"], [4200, "$4,200/unit"], [1.3, "around 1.30x"], [81, "LTV: 81%"]]
  .every(([n, q]) => Engine.numbersIn(q).some(x => Math.abs(x - n) <= Math.abs(n) * 1e-6));
if (!abbrevOk) fails++;
console.log(`${abbrevOk ? "PASS" : "FAIL"}  abbreviated numbers ($21.5M, ~$1.55M/yr, 1.30x) recognised`);

console.log(`\nOverall: ${fails ? "FAIL" : "PASS"}`);
process.exit(fails ? 1 : 0);
