# Prototype run — results

## What "working" meant (set before the first run, in expected.yaml)

1. All 5 screening calls match the hand-calculated expectation.
2. Every required flag is raised (e.g., the 005 broker mismatch, the 003 occupancy conflict).
3. Zero unsupported numbers: every extracted figure has a quote that exists verbatim in the package and contains that figure, or it is explicitly marked not stated.
4. No auto-declines: every Decline is labeled a recommendation for a person to confirm.

## Result: 5 of 5 pass (on the second run)

| Deal | Expected | Got | Notes |
|---|---|---|---|
| 001 Maple Run | Advance | Advance | Inside the box on every criterion. 23/23 quotes verified. |
| 002 Harborview | Decline | Decline (recommended) | Hotel exclusion, despite the "multifamily-adjacent" framing. Routed to the producer note. |
| 003 Birchwood | Needs review | Needs review | No T-12, no appraisal, no debt service. Stated 96% vs rent roll 78%. Possible value-add. |
| 004 Cedar Point | Needs review | Needs review | LTV 81.0% and liquidity 6.9 months, both near the line. |
| 005 Watermark | Needs review | Needs review | Broker's 75% / 1.30x is actually 82.0% / 1.18x. Rent roll explains only ~85% of EGI. |

## What the first run got wrong

- **003 was declined.** The engine scored occupancy at 78% from an 8-month-old rent roll that contradicts the sponsor's 96%, and that is below the band. The box says unreconciled occupancy is "a flag, not a number". Fix: a metric whose sources conflict can't drive a decline; it goes to a human. This was a rule-design error, not an extraction error.
- **005's extraction broke its own rule.** I recorded "not_stated" as a value instead of null. The quote check caught it.
- Neither fix touched expected.yaml or box.yaml.

## Negative tests

- I planted a fake debt service on 003. The quote check rejected it: the quote isn't in the package.
- Credit tightens the DSCR review band from 1.15x to 1.20x. 005 flips to Decline (recommended), and no other deal changes. This is the live-change demo.

## What I'd conclude, and the limits

- The split holds up. The model extracts with evidence, code does the math and applies the box, and humans make the calls. Most of the value is in catching what the broker summary hides (005) and refusing to invent numbers (003).
- **The calls depend on assumptions Credit hasn't confirmed:** the review bands, the integrity tolerances, and treating loan size as hard. 005 sits between Needs review and Decline depending on the band.
- **Extraction was done in the same session that wrote the rules, on 5 clean markdown files.** The real risk is extraction on PDFs, Excel rent rolls and scanned exhibits. Next test: 50+ real historical packages with known outcomes, extracted cold.
- The market check uses a 10-MSA illustrative list, so Charleston shows as "unverified". Production needs the real top-75 list from Credit/Data.
- For 002 the engine still computes "occupancy" from 12 residential units in a hotel. That's harmless here because the hard exclusion already decides it, but metrics should be suppressed once a hard criterion fails.
- **The packages have no sponsor names or received dates.** So repeat-sponsor protection and time-in-queue, which the producer and analyst care about most, can't be built yet. They need CRM / sponsor master data and intake timestamps.
