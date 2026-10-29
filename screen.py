#!/usr/bin/env python3
"""Deterministic screening step.

Reads Claude's extractions (extractions/*.json) and Credit's box (box.yaml).
Computes the metrics, applies the box, and writes out/results.json and out/queue.html.

Design rules:
  * No model in this file. Every number is either quoted from a package or computed here.
  * The box decides the official status. The model's notes can only escalate a deal to a
    human (Needs review). They can never advance or decline a deal.
  * "Decline" is always a recommendation that a human confirms.
"""
import json, sys, datetime, pathlib
import yaml

ROOT = pathlib.Path(__file__).parent
STATUS_ORDER = {"Advance": 0, "Needs review": 1, "Decline": 2}


def v(ext, key):
    f = ext.get(key)
    if isinstance(f, dict):
        return f.get("value")
    return f


def claim(ext, key):
    c = (ext.get("stated_claims") or {}).get(key)
    return c.get("value") if c else None


def compute_metrics(e):
    loan, appr = v(e, "loan_amount"), v(e, "appraised_value")
    noi, ads = v(e, "noi"), v(e, "annual_debt_service")
    occ, tot = v(e, "rent_roll_occupied_units"), v(e, "rent_roll_total_units")
    nw, liq = v(e, "sponsor_net_worth"), v(e, "sponsor_liquidity")
    rent, egi = v(e, "avg_in_place_rent_monthly"), v(e, "effective_gross_income")

    def ok(*xs):
        return all(isinstance(x, (int, float)) and x is not False for x in xs)

    m = {}
    m["ltv_pct"] = {"value": loan / appr * 100 if ok(loan, appr) and appr else None,
                    "formula": "loan ÷ appraised value", "inputs": ["loan_amount", "appraised_value"]}
    m["dscr"] = {"value": noi / ads if ok(noi, ads) and ads else None,
                 "formula": "NOI ÷ annual debt service", "inputs": ["noi", "annual_debt_service"]}
    m["occupancy_pct"] = {"value": occ / tot * 100 if ok(occ, tot) and tot else None,
                          "formula": "occupied units ÷ total units (rent roll)",
                          "inputs": ["rent_roll_occupied_units", "rent_roll_total_units"]}
    m["nw_to_loan"] = {"value": nw / loan if ok(nw, loan) and loan else None,
                       "formula": "sponsor net worth ÷ loan", "inputs": ["sponsor_net_worth", "loan_amount"]}
    m["liquidity_months"] = {"value": liq / (ads / 12) if ok(liq, ads) and ads else None,
                             "formula": "sponsor liquidity ÷ (annual debt service ÷ 12)",
                             "inputs": ["sponsor_liquidity", "annual_debt_service"]}
    m["rent_roll_annual"] = {"value": occ * rent * 12 if ok(occ, rent) else None,
                             "formula": "occupied units × avg in-place rent × 12",
                             "inputs": ["rent_roll_occupied_units", "avg_in_place_rent_monthly"]}
    m["egi"] = {"value": egi, "formula": "stated", "inputs": ["effective_gross_income"]}
    return m


GRADUATED = [
    # key, metric, direction, label, unit, code prefix
    ("ltv_max_pct", "ltv_pct", "max", "LTV", "%", "ltv"),
    ("dscr_min", "dscr", "min", "DSCR", "x", "dscr"),
    ("occupancy_min_pct", "occupancy_pct", "min", "Physical occupancy", "%", "occupancy"),
    ("sponsor_nw_to_loan_min", "nw_to_loan", "min", "Sponsor net worth ÷ loan", "x", "nw"),
    ("liquidity_months_min", "liquidity_months", "min", "Sponsor liquidity", " mo", "liquidity"),
]

MISSING_CODE = {
    "ltv_pct": lambda e: "missing_appraisal" if v(e, "appraised_value") is None else "missing_loan",
    "dscr": lambda e: "missing_noi" if v(e, "noi") is None else "missing_debt_service",
    "occupancy_pct": lambda e: "missing_rent_roll",
    "nw_to_loan": lambda e: "missing_net_worth",
    "liquidity_months": lambda e: "missing_debt_service" if v(e, "annual_debt_service") is None else "missing_liquidity",
}


def grade(value, direction, limit, band):
    if value is None:
        return "unknown"
    if direction == "max":
        return "pass" if value <= limit else ("near" if value <= band else "fail")
    return "pass" if value >= limit else ("near" if value >= band else "fail")


def fmt(x, unit):
    if x is None:
        return "n/a"
    if unit == "%":
        return f"{x:.1f}%"
    if unit == "x":
        return f"{x:.2f}x"
    return f"{x:.1f}{unit}"


def screen(e, box):
    hard, grad, integ = box["hard"], box["graduated"], box["integrity"]
    m = compute_metrics(e)
    F = []  # findings

    def add(code, kind, result, label, detail):
        F.append({"code": code, "kind": kind, "result": result, "label": label, "detail": detail})

    # ---- hard criteria ----
    ptype = v(e, "property_type")
    if ptype in hard["excluded_property_types"]:
        add("excluded_property_type", "hard", "fail", "Property type",
            f"Classified as {ptype.replace('_', ' ')}, which the box excludes.")
    elif ptype != hard["asset_type"]:
        add("asset_type_mismatch", "hard", "fail", "Asset type", f"Classified as {ptype}, not multifamily.")
    else:
        add("asset_type_ok", "hard", "pass", "Asset type", "Multifamily.")

    units = v(e, "units")
    if units is None:
        add("missing_units", "hard", "unknown", "Unit count", "Not stated.")
    elif units < hard["min_units"]:
        add("too_few_units", "hard", "fail", "Unit count", f"{units} units (minimum {hard['min_units']}).")

    stab = v(e, "stabilized")
    va = v(e, "value_add_or_construction")
    if va == "yes" or stab is False:
        add("not_stabilized", "hard", "fail", "Stabilized", "Construction, value-add, or not stabilized.")
    elif va == "possible":
        add("possible_value_add", "hard", "unknown", "Stabilized",
            "Package suggests an active renovation. A human should confirm the asset is stabilized, not value-add.")
    elif stab is None and ptype == hard["asset_type"]:
        add("stabilization_unknown", "hard", "unknown", "Stabilized", "Not stated.")

    loan = v(e, "loan_amount")
    if loan is None:
        add("missing_loan", "hard", "unknown", "Loan size", "Not stated.")
    elif not (hard["loan_min"] <= loan <= hard["loan_max"]):
        add("loan_size_outside_box", "hard", "fail", "Loan size", f"${loan:,.0f} is outside $5M–$75M.")

    msa = v(e, "msa")
    if msa not in hard["top75_msa_reference"]:
        add("market_unverified", "hard", "unknown", "Market",
            f"'{msa}' is not on the reference list. It needs checking against the full top-75 list, not an automatic decline.")

    # A metric whose sources contradict each other is not a number we can decline on.
    # (Box: "When they don't [reconcile], that's a flag, not a number to average.")
    unreliable = set()
    so, co = claim(e, "occupancy_pct"), m["occupancy_pct"]["value"]
    occ_conflict = so is not None and co is not None and abs(so - co) > integ["occupancy_conflict_tolerance_pts"]
    if occ_conflict:
        unreliable.add("occupancy_pct")

    # ---- graduated criteria ----
    for key, mk, direction, label, unit, prefix in GRADUATED:
        cfg = grad[key]
        val = m[mk]["value"]
        r = grade(val, direction, cfg["limit"], cfg["review_band"])
        sign = "≤" if direction == "max" else "≥"
        if mk in unreliable:
            add(f"{prefix}_conflicting", "graduated", "unknown", label,
                f"Sources disagree, so no reliable figure (rent roll gives {fmt(val, unit)}). A human resolves it before this criterion is scored.")
        elif r == "unknown":
            add(MISSING_CODE[mk](e), "graduated", "unknown", label,
                f"Can't compute ({m[mk]['formula']}): an input isn't in the package.")
        else:
            code = {"pass": f"{prefix}_ok", "near": f"{prefix}_near_line", "fail": f"{prefix}_outside_box"}[r]
            add(code, "graduated", r, label, f"{fmt(val, unit)} vs box {sign} {fmt(cfg['limit'], unit)}"
                + ("" if r == "pass" else f" (review band to {fmt(cfg['review_band'], unit)})"))

    sustained = v(e, "occupancy_sustained_90d")
    if ptype == hard["asset_type"] and sustained is not True:
        add("occupancy_history_missing", "graduated", "unknown", "Occupancy sustained 90+ days",
            "The package doesn't show occupancy over time.")

    # ---- integrity: components win, gaps get flagged ----
    for ck, mk, tol, code, unit in [
        ("ltv_pct", "ltv_pct", integ["stated_vs_computed_ltv_tolerance_pts"], "broker_ltv_mismatch", "%"),
        ("dscr", "dscr", integ["stated_vs_computed_dscr_tolerance"], "broker_dscr_mismatch", "x"),
    ]:
        stated, comp = claim(e, ck), m[mk]["value"]
        if stated is not None and comp is not None and abs(stated - comp) > tol:
            add(code, "integrity", "flag", "Stated vs computed",
                f"Package says {fmt(stated, unit)}; components give {fmt(comp, unit)}. The computed figure is used.")

    if occ_conflict:
        add("occupancy_conflict", "integrity", "flag", "Occupancy doesn't reconcile",
            f"Package says {so:.0f}%; rent roll shows {co:.1f}%. Not averaged; a human checks it.")

    rr, egi = m["rent_roll_annual"]["value"], m["egi"]["value"]
    if rr is not None and egi and ptype == hard["asset_type"]:
        gap = (egi - rr) / egi * 100
        if abs(gap) > integ["rent_roll_vs_egi_tolerance_pct"]:
            add("income_reconciliation_gap", "integrity", "flag", "Income doesn't reconcile",
                f"Rent roll supports ${rr:,.0f}/yr; T-12 EGI is ${egi:,.0f} ({gap:.0f}% gap).")

    for dq in e.get("data_quality", []):
        add("package_issue", "package", "flag", "Package issue", dq["issue"])

    # ---- decision ----
    results = {f["result"] for f in F}
    if "fail" in results:
        status = "Decline"
    elif results & {"near", "unknown", "flag"}:
        status = "Needs review"
    else:
        status = "Advance"

    # Fixed outcome without the five graduated metrics (used by the what-if sandbox in the page)
    metric_codes = {f["code"] for f in F if f["kind"] == "graduated" and f["code"] != "occupancy_history_missing"
                    and not f["code"].startswith("missing_") and not f["code"].endswith("_conflicting")}
    fixed = [f for f in F if f["code"] not in metric_codes]
    fixed_results = {f["result"] for f in fixed}
    fixed_outcome = "fail" if "fail" in fixed_results else ("review" if fixed_results & {"near", "unknown", "flag"} else "pass")

    # Box cushion: smallest headroom across the graduated metrics we could compute
    cushions = []
    for key, mk, direction, *_ in GRADUATED:
        val, lim = m[mk]["value"], grad[key]["limit"]
        if val is not None:
            cushions.append((lim - val) / lim if direction == "max" else (val - lim) / lim)

    return {
        "deal_id": e["deal_id"],
        "status": status,
        "status_label": "Decline (recommended, human confirms)" if status == "Decline" else status,
        "open_items": sum(1 for f in F if f["result"] != "pass"),
        "cushion": min(cushions) if cushions else None,
        "fixed_outcome": fixed_outcome,
        "unreliable_metrics": sorted(unreliable),
        "metrics": m,
        "findings": F,
        "extraction": e,
    }


def main():
    box = yaml.safe_load((ROOT / "box.yaml").read_text())
    exts = [json.loads(p.read_text()) for p in sorted((ROOT / "extractions").glob("*.json"))]
    if not exts:
        sys.exit("No extractions found in extractions/. Run the extraction step first.")
    res = [screen(e, box) for e in exts]
    res.sort(key=lambda r: (STATUS_ORDER[r["status"]], r["open_items"], -(r["cushion"] or -9)))
    skill = (ROOT / "SKILL.md").read_text()
    run = {
        "run_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "box": box,
        "deals": res,
        # The page's "Add a deal" uses the same extraction rules as the skill.
        "extraction_rules": skill[skill.find("## Extraction rules"):],
    }
    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    (out / "results.json").write_text(json.dumps(run, indent=2, ensure_ascii=False))
    template = (ROOT / "queue_template.html").read_text()
    engine = (ROOT / "engine.js").read_text().replace("</", "<\\/")
    html = (template.replace("/*__ENGINE__*/", engine)
            .replace("/*__DATA__*/null", json.dumps(run, ensure_ascii=False).replace("</", "<\\/")))
    (out / "queue.html").write_text(html)

    w = max(len(r["extraction"]["property_name"]["value"]) for r in res)
    print(f"Box {box['version']} ({box['owner']})  ·  {len(res)} deals\n")
    for r in res:
        name = r["extraction"]["property_name"]["value"]
        reasons = [f["code"] for f in r["findings"] if f["result"] != "pass"]
        print(f"{r['deal_id']}  {name:<{w}}  {r['status_label']:<38} {', '.join(reasons) or '—'}")
    print(f"\nWrote {out/'results.json'} and {out/'queue.html'}")


if __name__ == "__main__":
    main()
