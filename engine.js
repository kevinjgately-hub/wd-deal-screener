// Screening engine for the browser. Mirrors screen.py rule for rule.
// test_engine.js checks that it gives the same results as screen.py on every deal.
// Used only for deals added from the page; the official run is screen.py.
const Engine = (() => {
  const isNum = x => typeof x === "number" && isFinite(x);
  const v = (e, k) => { const f = e[k]; return f && typeof f === "object" ? (f.value ?? null) : (f ?? null); };
  const claim = (e, k) => { const c = (e.stated_claims || {})[k]; return c ? (c.value ?? null) : null; };

  function fmt(x, unit) {
    if (x == null) return "n/a";
    if (unit === "%") return x.toFixed(1) + "%";
    if (unit === "x") return x.toFixed(2) + "x";
    return x.toFixed(1) + unit;
  }
  const money = x => "$" + Math.round(x).toLocaleString("en-US");

  function computeMetrics(e) {
    const loan = v(e, "loan_amount"), appr = v(e, "appraised_value"), noi = v(e, "noi"), ads = v(e, "annual_debt_service");
    const occ = v(e, "rent_roll_occupied_units"), tot = v(e, "rent_roll_total_units");
    const nw = v(e, "sponsor_net_worth"), liq = v(e, "sponsor_liquidity"), rent = v(e, "avg_in_place_rent_monthly"), egi = v(e, "effective_gross_income");
    const ok = (...xs) => xs.every(isNum);
    return {
      ltv_pct: { value: ok(loan, appr) && appr ? loan / appr * 100 : null, formula: "loan ÷ appraised value", inputs: ["loan_amount", "appraised_value"] },
      dscr: { value: ok(noi, ads) && ads ? noi / ads : null, formula: "NOI ÷ annual debt service", inputs: ["noi", "annual_debt_service"] },
      occupancy_pct: { value: ok(occ, tot) && tot ? occ / tot * 100 : null, formula: "occupied units ÷ total units (rent roll)", inputs: ["rent_roll_occupied_units", "rent_roll_total_units"] },
      nw_to_loan: { value: ok(nw, loan) && loan ? nw / loan : null, formula: "sponsor net worth ÷ loan", inputs: ["sponsor_net_worth", "loan_amount"] },
      liquidity_months: { value: ok(liq, ads) && ads ? liq / (ads / 12) : null, formula: "sponsor liquidity ÷ (annual debt service ÷ 12)", inputs: ["sponsor_liquidity", "annual_debt_service"] },
      rent_roll_annual: { value: ok(occ, rent) ? occ * rent * 12 : null, formula: "occupied units × avg in-place rent × 12", inputs: ["rent_roll_occupied_units", "avg_in_place_rent_monthly"] },
      egi: { value: egi, formula: "stated", inputs: ["effective_gross_income"] },
    };
  }

  const GRADUATED = [
    ["ltv_max_pct", "ltv_pct", "max", "LTV", "%", "ltv"],
    ["dscr_min", "dscr", "min", "DSCR", "x", "dscr"],
    ["occupancy_min_pct", "occupancy_pct", "min", "Physical occupancy", "%", "occupancy"],
    ["sponsor_nw_to_loan_min", "nw_to_loan", "min", "Sponsor net worth ÷ loan", "x", "nw"],
    ["liquidity_months_min", "liquidity_months", "min", "Sponsor liquidity", " mo", "liquidity"],
  ];
  const MISSING_CODE = {
    ltv_pct: e => v(e, "appraised_value") == null ? "missing_appraisal" : "missing_loan",
    dscr: e => v(e, "noi") == null ? "missing_noi" : "missing_debt_service",
    occupancy_pct: () => "missing_rent_roll",
    nw_to_loan: () => "missing_net_worth",
    liquidity_months: e => v(e, "annual_debt_service") == null ? "missing_debt_service" : "missing_liquidity",
  };
  const grade = (x, dir, lim, band) => x == null ? "unknown" : dir === "max" ? (x <= lim ? "pass" : x <= band ? "near" : "fail") : (x >= lim ? "pass" : x >= band ? "near" : "fail");

  function screen(e, box) {
    const hard = box.hard, grad = box.graduated, integ = box.integrity;
    const m = computeMetrics(e), F = [];
    const add = (code, kind, result, label, detail) => F.push({ code, kind, result, label, detail });

    const ptype = v(e, "property_type");
    if (hard.excluded_property_types.includes(ptype)) add("excluded_property_type", "hard", "fail", "Property type", `Classified as ${String(ptype).replaceAll("_", " ")}, which the box excludes.`);
    else if (ptype !== hard.asset_type) add("asset_type_mismatch", "hard", "fail", "Asset type", `Classified as ${ptype}, not multifamily.`);
    else add("asset_type_ok", "hard", "pass", "Asset type", "Multifamily.");

    const units = v(e, "units");
    if (units == null) add("missing_units", "hard", "unknown", "Unit count", "Not stated.");
    else if (units < hard.min_units) add("too_few_units", "hard", "fail", "Unit count", `${units} units (minimum ${hard.min_units}).`);

    const stab = v(e, "stabilized"), va = v(e, "value_add_or_construction");
    if (va === "yes" || stab === false) add("not_stabilized", "hard", "fail", "Stabilized", "Construction, value-add, or not stabilized.");
    else if (va === "possible") add("possible_value_add", "hard", "unknown", "Stabilized", "Package suggests an active renovation. A human should confirm the asset is stabilized, not value-add.");
    else if (stab == null && ptype === hard.asset_type) add("stabilization_unknown", "hard", "unknown", "Stabilized", "Not stated.");

    const loan = v(e, "loan_amount");
    if (loan == null) add("missing_loan", "hard", "unknown", "Loan size", "Not stated.");
    else if (!(hard.loan_min <= loan && loan <= hard.loan_max)) add("loan_size_outside_box", "hard", "fail", "Loan size", `${money(loan)} is outside $5M–$75M.`);

    const msa = v(e, "msa");
    if (!hard.top75_msa_reference.includes(msa)) add("market_unverified", "hard", "unknown", "Market", `'${msa ?? "Not stated"}' is not on the reference list. It needs checking against the full top-75 list, not an automatic decline.`);

    const unreliable = new Set();
    const so = claim(e, "occupancy_pct"), co = m.occupancy_pct.value;
    const occConflict = so != null && co != null && Math.abs(so - co) > integ.occupancy_conflict_tolerance_pts;
    if (occConflict) unreliable.add("occupancy_pct");

    for (const [key, mk, dir, label, unit, prefix] of GRADUATED) {
      const cfg = grad[key], val = m[mk].value, r = grade(val, dir, cfg.limit, cfg.review_band), sign = dir === "max" ? "≤" : "≥";
      if (unreliable.has(mk)) add(`${prefix}_conflicting`, "graduated", "unknown", label, `Sources disagree, so no reliable figure (rent roll gives ${fmt(val, unit)}). A human resolves it before this criterion is scored.`);
      else if (r === "unknown") add(MISSING_CODE[mk](e), "graduated", "unknown", label, `Can't compute (${m[mk].formula}): an input isn't in the package.`);
      else add({ pass: `${prefix}_ok`, near: `${prefix}_near_line`, fail: `${prefix}_outside_box` }[r], "graduated", r, label,
        `${fmt(val, unit)} vs box ${sign} ${fmt(cfg.limit, unit)}` + (r === "pass" ? "" : ` (review band to ${fmt(cfg.review_band, unit)})`));
    }
    if (ptype === hard.asset_type && v(e, "occupancy_sustained_90d") !== true)
      add("occupancy_history_missing", "graduated", "unknown", "Occupancy sustained 90+ days", "The package doesn't show occupancy over time.");

    for (const [ck, mk, tol, code, unit] of [
      ["ltv_pct", "ltv_pct", integ.stated_vs_computed_ltv_tolerance_pts, "broker_ltv_mismatch", "%"],
      ["dscr", "dscr", integ.stated_vs_computed_dscr_tolerance, "broker_dscr_mismatch", "x"]]) {
      const stated = claim(e, ck), comp = m[mk].value;
      if (stated != null && comp != null && Math.abs(stated - comp) > tol)
        add(code, "integrity", "flag", "Stated vs computed", `Package says ${fmt(stated, unit)}; components give ${fmt(comp, unit)}. The computed figure is used.`);
    }
    if (occConflict) add("occupancy_conflict", "integrity", "flag", "Occupancy doesn't reconcile", `Package says ${Math.round(so)}%; rent roll shows ${co.toFixed(1)}%. Not averaged; a human checks it.`);
    const rr = m.rent_roll_annual.value, egi = m.egi.value;
    if (rr != null && egi && ptype === hard.asset_type) {
      const gap = (egi - rr) / egi * 100;
      if (Math.abs(gap) > integ.rent_roll_vs_egi_tolerance_pct)
        add("income_reconciliation_gap", "integrity", "flag", "Income doesn't reconcile", `Rent roll supports ${money(rr)}/yr; T-12 EGI is ${money(egi)} (${Math.round(gap)}% gap).`);
    }
    for (const dq of e.data_quality || []) add("package_issue", "package", "flag", "Package issue", dq.issue);

    const results = new Set(F.map(f => f.result));
    const status = results.has("fail") ? "Decline" : ["near", "unknown", "flag"].some(r => results.has(r)) ? "Needs review" : "Advance";
    const metricCodes = new Set(F.filter(f => f.kind === "graduated" && f.code !== "occupancy_history_missing" && !f.code.startsWith("missing_") && !f.code.endsWith("_conflicting")).map(f => f.code));
    const fr = new Set(F.filter(f => !metricCodes.has(f.code)).map(f => f.result));
    const fixed_outcome = fr.has("fail") ? "fail" : ["near", "unknown", "flag"].some(r => fr.has(r)) ? "review" : "pass";
    const cushions = GRADUATED.map(([key, mk, dir]) => { const x = m[mk].value, lim = grad[key].limit; return x == null ? null : dir === "max" ? (lim - x) / lim : (x - lim) / lim; }).filter(x => x != null);

    return {
      deal_id: e.deal_id, status,
      status_label: status === "Decline" ? "Decline (recommended, human confirms)" : status,
      open_items: F.filter(f => f.result !== "pass").length,
      cushion: cushions.length ? Math.min(...cushions) : null,
      fixed_outcome, unreliable_metrics: [...unreliable].sort(), metrics: m, findings: F, extraction: e,
    };
  }

  // ---- Quote checks: the page's guard against numbers Claude can't support ----
  const norm = s => String(s ?? "").replaceAll("**", "").replace(/\s+/g, " ").trim();
  const SCALE = { k: 1e3, thousand: 1e3, m: 1e6, mm: 1e6, mn: 1e6, million: 1e6, b: 1e9, bn: 1e9, billion: 1e9 };
  // Every number written in the quote, including "$21.5M", "1.92 million", "4,200", "81%".
  function numbersIn(q) {
    const out = [];
    for (const mt of norm(q).matchAll(/(\d[\d,]*(?:\.\d+)?)\s*(thousand|million|billion|mm|mn|bn|k|m|b)?(?![a-wyz])/gi)) {  // "1.38x" is fine, "12abc" is not
      const n = parseFloat(mt[1].replaceAll(",", ""));
      out.push(n);
      if (mt[2]) out.push(n * SCALE[mt[2].toLowerCase()]);
    }
    return out;
  }
  const numberInQuote = (val, q) => numbersIn(q).some(n => Math.abs(n - val) <= Math.max(1e-9, Math.abs(val) * 1e-6));

  // Returns {extraction, problems}. Any number whose quote isn't in the package, or doesn't contain
  // that number, is discarded (value -> null, status "unverified") so it can never reach the box.
  function verify(ext, src) {
    const S = norm(src), problems = [];
    const check = (label, f) => {
      if (!f || typeof f !== "object" || f.value == null) return f;
      if (!f.quote) { problems.push(`${label}: no quote`); return { value: null, status: "unverified", note: "Claude gave no quote for this, so it was discarded." }; }
      if (!S.includes(norm(f.quote))) { problems.push(`${label}: quote not in package`); return { value: null, status: "unverified", quote_given: f.quote, note: "Claude's quote isn't in the package, so the value was discarded." }; }
      if (isNum(f.value) && !numberInQuote(f.value, f.quote)) { problems.push(`${label}: ${f.value} not in its quote`); return { value: null, status: "unverified", quote_given: f.quote, note: `${f.value} doesn't appear in the quoted line, so it was discarded.` }; }
      return f;
    };
    const out = { ...ext };
    for (const [k, f] of Object.entries(ext)) if (f && typeof f === "object" && !Array.isArray(f) && "value" in f) out[k] = check(k, f);
    out.stated_claims = Object.fromEntries(Object.entries(ext.stated_claims || {}).map(([k, f]) => [k, check("claim " + k, f)]).filter(([, f]) => f && f.value != null));
    const keepQuote = it => it.quote && !S.includes(norm(it.quote)) ? { ...it, quote: "", issue_note: "quote not found in package" } : it;
    out.data_quality = (ext.data_quality || []).map(keepQuote);
    out.for_human = (ext.for_human || []).map(it => keepQuote({ ...it }));
    if (problems.length) out.data_quality = [...out.data_quality, { issue: `Extraction check discarded ${problems.length} value${problems.length > 1 ? "s" : ""} that the package doesn't support (${problems.map(p => p.split(":")[0]).join(", ")}).`, quote: "" }];
    return { extraction: out, problems };
  }

  return { screen, verify, numbersIn, computeMetrics };
})();
if (typeof module !== "undefined") module.exports = Engine;
