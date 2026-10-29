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


SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "mn": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}
NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(thousand|million|billion|mm|mn|bn|k|m|b)?(?![a-wyz])", re.I)


def numbers_in(q):
    """Every number written in a quote, including '$21.5M', '1.92 million', '4,200', '81%', '1.38x'.
    Same rule as engine.js, so the page and the official check agree."""
    out = []
    for mt in NUM.finditer(q):
        n = float(mt.group(1).replace(",", ""))
        out.append(n)
        if mt.group(2):
            out.append(n * SCALE[mt.group(2).lower()])
    return out


def number_in_quote(val, q):
    return any(abs(n - val) <= max(1e-9, abs(val) * 1e-6) for n in numbers_in(q))


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
            if not number_in_quote(val, norm(q)):
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
