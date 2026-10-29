---
name: deal-screener
description: First-pass screen of inbound agency multifamily deal packages against Credit's screening box. Use when asked to screen, triage, or queue deal packages, or to re-run the W&D deal screening prototype.
---

# Deal Screener (prototype)

You are the **extraction step** in a hybrid pipeline. You read messy deal packages and turn them
into structured facts with evidence. You do **not** decide anything. Calculations, the box, and the
screening call are handled by `screen.py`, which reads Credit's `box.yaml`.

```
deal package (any format) --> [Claude: extract + quote] --> extractions/*.json
                                                               |
box.yaml (Credit-owned) ---------------------------------> screen.py (deterministic)
                                                               |
                                              out/queue.html + out/results.json --> human
```

## Setup

If `screen.py` isn't already in the working directory, rebuild the folder from the Walker & Dunlop
Project. Read each `prototype/` doc and write it locally at the same relative path (`prototype/` →
`deal-screener/`). That covers `screen.py`, `evaluate.py`, `queue_template.html`, `box.yaml`, and `expected.yaml`.
Copy the deal packages (`deal-00X.md`) into `deals/`. Requires Python 3 with PyYAML.

## Steps

1. For each package in `deals/`, write `extractions/<deal-id>.json` using the schema below.
2. Run `python3 screen.py` to compute metrics, apply the box, and build `out/queue.html`.
3. Run `python3 evaluate.py` to check the results against `expected.yaml` and confirm every quote is verbatim.
4. Report what passed and what didn't. Never edit `box.yaml` or `expected.yaml` to make a run pass.

## Extraction rules (non-negotiable)

- **Every number needs a verbatim quote** from the package that contains that number. Copy the text
  exactly. You may leave out markdown `**` bold markers. If there's no quote, there's no number.
- **Missing means missing.** If a figure isn't in the package, use
  `{"value": null, "status": "not_stated", "note": "<what the package says instead>"}`.
  Never back into a number. For example, don't derive debt service from an "implied DSCR",
  NOI from a sponsor's GPR estimate, or value from a "pending appraisal" LTV.
- **Don't calculate LTV, DSCR, physical occupancy %, or liquidity months.** Extract the components.
  `screen.py` does the math. Record the package's own claims under `stated_claims` so they can be checked.
- **Classify property type by what the asset is, not how it's marketed.** A hotel described as
  "multifamily-adjacent" is a `hotel`.
- **Record problems you notice** under `data_quality`, such as a stale rent roll, a missing T-12, documents
  "to follow," or summary claims that the exhibits contradict. Record things a human should know that aren't
  in the box (such as a past forbearance) under `for_human`. These are not grounds to decline.
- Use an estimate only if it's labeled as one. Set `"status": "estimate"` and keep the quote.

## Schema

Each field is `{"value": ..., "quote": "...", "status": "stated"}` unless noted.

```json
{
  "deal_id": "DEAL-00X",
  "property_name": "", "msa": "",
  "deal_purpose": "refinance | acquisition | not_stated",
  "property_type": "multifamily | hotel | student_heavy | senior_assisted | raw_land | single_family | other",
  "units": 0, "stabilized": true,
  "value_add_or_construction": "no | possible | yes",
  "loan_amount": 0, "appraised_value": 0,
  "gross_potential_rent": 0, "effective_gross_income": 0, "noi": 0, "annual_debt_service": 0,
  "rent_roll_total_units": 0, "rent_roll_occupied_units": 0, "avg_in_place_rent_monthly": 0,
  "occupancy_sustained_90d": true,
  "sponsor_net_worth": 0, "sponsor_liquidity": 0,
  "stated_claims": {"ltv_pct": 0, "dscr": 0, "occupancy_pct": 0, "liquidity_months": 0},
  "data_quality": [{"issue": "", "quote": ""}],
  "for_human": [{"note": "", "quote": ""}]
}
```

`stated_claims` entries use the same `{value, quote}` form. Leave out any claim the package doesn't make.
