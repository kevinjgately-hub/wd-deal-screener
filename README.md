# Deal Screener: Walker & Dunlop AI Enablement case prototype

This is a small working prototype of a first-pass screen for inbound agency multifamily deals. It sorts deals into a ranked queue for the people who decide. It does not make credit decisions.

> **Illustrative only.** The screening box (`box.yaml`) and the five deal packages are made-up material for the exercise. They are not Walker & Dunlop credit policy or real deals.

## How it works

```
deal package (any format) --> [Claude: extract + quote] --> extractions/*.json
                                                               |
box.yaml (Credit-owned) ---------------------------------> screen.py (deterministic)
                                                               |
                                              out/queue.html + out/results.json --> human
```

- **Claude extracts.** It turns each package into structured fields. Every number carries a quote copied word for word from the package, or is marked `not_stated`. Claude doesn't calculate anything and doesn't decide anything. The rules are in `SKILL.md`.
- **Code decides the screen.** `screen.py` calculates LTV, DSCR, occupancy, sponsor net worth ÷ loan, and liquidity in months. It applies Credit's box and checks the package's own claims against the calculated figures.
- **People decide the deal.** Each deal gets one of three results:
  - **Advance:** worth a full underwriting look.
  - **Needs review:** a person decides.
  - **Decline (recommended):** a person confirms.
- **Model notes can only send a deal to a person.** Nothing the model writes can advance or decline a deal.

## The queue (`out/queue.html`)

- **Credit's box:** shown read-only and versioned. Only this sets each deal's status.
- **Your view:** filters for received date, loan size, market, deal purpose, status and number of open items. Sort by open items, oldest or newest received, room inside the box, or loan size, with or without grouping by status. Each card shows how long the deal has been waiting.
- **My bar:** each user can set their own threshold on any metric. Deals that miss it are marked and moved down, or hidden if the user prefers. Their status doesn't change.
- **What-if:** a sandbox showing which deals would change if Credit moved a limit. It never changes the official status.
- **Never silently hidden:** a banner names every deal the current view hides.
- **Decision log:** records who decided what and when, along with the view settings they were using. Declines and overrides need a written reason. On the published page, decisions are saved with the page and reopening a deal keeps the history.
- **Add a deal:** on the published page, drop in a new package (.md or .txt). It goes through four steps:
  1. Claude extracts it using the same rules as `SKILL.md`.
  2. The page checks every quote against the package and throws out any figure it can't find.
  3. `engine.js` applies Credit's box with the same rules as `screen.py`. `test_engine.js` checks that the two agree on every deal.
  4. The deal joins the queue, labeled "Added here · not in official run", and is saved so it's still there after a reload.

  To make it official, add the package to `deals/` and run the normal Claude extraction and `screen.py`. `samples/deal-006-broker-email.md` is a messy broker email to try it with.

## Run it

```bash
pip install pyyaml
python3 screen.py      # applies the box to extractions/, writes out/queue.html
python3 evaluate.py    # checks results against expected.yaml
node test_engine.js    # checks the page's engine.js matches screen.py
```

Open `out/queue.html` in a browser. To re-extract the deals, follow `SKILL.md` with Claude.

## Definition of "working" (written before the first run)

1. All 5 screening calls match `expected.yaml`.
2. Every required flag is raised.
3. Every quote appears word for word in the source package and contains its number.
4. Every Decline is a recommendation for a person to confirm.

**Result: 5 of 5 pass.** See `RESULTS.md` for:
- what the first run got wrong (deal 003 was declined on conflicting occupancy data)
- the negative tests
- the assumptions that still need Credit's sign-off, especially the "near the line" review bands

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | Extraction instructions and schema for Claude |
| `box.yaml` | Screening criteria, owned by Credit; review bands are flagged as assumptions |
| `screen.py` | Deterministic metrics, box application, and queue generation |
| `queue_template.html` | Front end for the queue |
| `expected.yaml` | Expected results, written before the first run |
| `evaluate.py` | Pass/fail check, including verification that quotes match the source |
| `engine.js` | The same screening rules for the page's "Add a deal", plus the quote check |
| `test_engine.js` | Confirms `engine.js` and `screen.py` agree, and that a made-up number is thrown out |
| `samples/` | A new deal (messy broker email) for trying "Add a deal" |
| `deals/` | The five sample packages |
| `deals/intake.yaml` | Received dates. These are illustrative; in production they'd come from the intake system |
| `extractions/` | Claude's structured extractions with source quotes |
| `out/` | Latest run output |
| `RESULTS.md` | Honest report of what worked and what didn't |
