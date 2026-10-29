#!/usr/bin/env python3
"""Checks a run against expected.yaml (written before the first run).

1. Status matches the expected call.
2. Every required flag is raised.
3. Zero unsupported numbers: every quote is verbatim in the source package, and every
   number extracted appears in its own quote. Missing values must be marked not_stated.
4. No auto-declines: every Decline is labeled a recommendation.
"""
import json, re, pathlib, sys
import yaml

ROOT = pathlib.Path(__file__).parent
norm = lambda s: re.sub(r"\s+", " ", s.replace("**", "")).strip()


def digits_in(n):
    """Forms a number might take in text: 32000000 -> '32,000,000'; 1.3 -> '1.30' or '1.3'."""
    if isinstance(n, bool):
        return []
    if isinstance(n, int) or float(n).is_integer():
        i = int(n)
        return [f"{i:,}", str(i)]
    return [f"{n}", f"{n:.2f}", f"{n:.1f}"]


def check_quotes(ext, src):
    problems, checked = [], 0
    fields = [(k, f) for k, f in ext.items() if isinstance(f, dict) and ("value" in f)]
    fields += [(f"stated_claims.{k}", f) for k, f in (ext.get("stated_claims") or {}).items()]
    fields += [(f"data_quality[{i}]", f) for i, f in enumerate(ext.get("data_quality", []))]
    fields += [(f"for_human[{i}]", f) for i, f in enumerate(ext.get("for_human", []))]
    for k, f in fields:
        q = f.get("quote")
        if f.get("value") is None and "issue" not in f and "note" not in f:
            problems.append(f"{k}: null value without a not_stated note")
        if f.get("value") is None and "quote" not in f:
            continue
        if not q:
            if f.get("value") is not None:
                problems.append(f"{k}: value {f.get('value')!r} has no quote")
            continue
        checked += 1
        if norm(q) not in src:
            problems.append(f"{k}: quote not found verbatim in package: {q!r}")
        val = f.get("value")
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if not any(d in norm(q) for d in digits_in(val)):
                problems.append(f"{k}: number {val} does not appear in its quote")
    return checked, problems


def main():
    exp = yaml.safe_load((ROOT / "expected.yaml").read_text())["deals"]
    run = json.loads((ROOT / "out" / "results.json").read_text())
    total_ok, lines = True, []
    for d in sorted(run["deals"], key=lambda x: x["deal_id"]):
        did, e = d["deal_id"], exp[d["deal_id"]]
        codes = {f["code"] for f in d["findings"] if f["result"] != "pass"}
        missing = [c for c in e["required_flags"] if c not in codes]
        src = norm((ROOT / "deals" / f"{did.lower()}.md").read_text())
        n, qp = check_quotes(d["extraction"], src)
        decl_ok = d["status"] != "Decline" or "recommended" in d["status_label"]
        ok = d["status"] == e["expected"] and not missing and not qp and decl_ok
        total_ok &= ok
        lines.append(f"{'PASS' if ok else 'FAIL'}  {did}  expected {e['expected']:<13} got {d['status']:<13} "
                     f"flags {'ok' if not missing else 'MISSING ' + ','.join(missing)}  quotes {n - len(qp)}/{n} verified")
        for p in qp:
            lines.append(f"        - {p}")
    print("\n".join(lines))
    print(f"\nOverall: {'PASS' if total_ok else 'FAIL'}")
    sys.exit(0 if total_ok else 1)


if __name__ == "__main__":
    main()
