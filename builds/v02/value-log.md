# PR-V value calculator: build log

## Owner's changes to the plan (2026-11-13)
- Logic first, design later: no `/impeccable` steps, V7 waived. The page uses the existing
  `style.css` with a few layout rules for the slider rows, and nothing beyond the plan.
- The report constant points at `v02-seen` from the start, labelled "measured on the
  seen questions". `v02-holdout` is shown beside it as the stricter figure. The range runs
  on the held-out wrong-answer interval.

## The framing (owner's decision, 2026-11-13)
The page shows the value of a tool like this: the hours it saves against what it costs
to run.
- The dollar-risk term and the cost-of-a-wrong-answer input are removed. Net value =
  value of time − running cost. Time saved still subtracts the minutes to check, because
  checking is how a wrong answer gets caught; the page says "Every answer shows its query;
  the check time is counted."
- The headline uses the held-out answered share (64.3%). The range runs to the seen share
  (87.6%), labelled "on questions it never saw" and "on questions it was tuned on".
- The wrong-answer rates (held-out 25.9%, 95% range 16.1–38.9%; seen 1.8%) stay on the
  page as a measured block with their sources. They do not feed the formula.
- "Cristian's API credits are not counted" becomes "Model cost is the provider's list price."
- The plan's PR-V formula section and V5 are updated to match.

## Choices the plan left open (sent to the orchestrator; easy to swap)
- **Run date.** The report JSON has no date. `SOURCE.date` is `2026-11-12`, the day
  9c8ebcf (which added both reports) landed on main. No test checks it, because CI's
  shallow checkout has no file history to test against.
- The run date was approved as is.
- **The constant's file.** The ids, model and date live in `web/src/value-source.ts`,
  not `value.ts`, so the unit test can import them without loading the page and its CSS.
  It is still one constant in one place.

## What each figure reads
| Figure | Report | Field (Askwell row, `anthropic:claude-haiku-5-5`) |
|---|---|---|
| Model, run id | v02-seen, v02-holdout | `model`, `run_id` |
| Cost per question (calculator) | v02-seen | `mean_cost_usd` |
| Answered share (headline, one range end) | v02-holdout | `coverage.rate` |
| Answered share (other range end) | v02-seen | `coverage.rate` |
| Wrong-answer rates (shown only) | v02-holdout, v02-seen | `wrong_answer_rate_given_answered` |

## Tests
- `web/e2e/value-formula.spec.ts`: V3 (known inputs, zero answered share, checking slower
  than by hand), V5 (range = formula at the two answered shares), clamp, and V2's constant
  check against `evals/reports/` and `askwell/config.py`'s default model. These are
  unit tests and open no browser.
- `web/e2e/value.spec.ts`: V1, V2 (cost to 6 decimals), a V3-style check that the
  headline is formula(held-out share), not the seen share, that the range ends are the two
  shares, and that the risk term, its input and the credits note are gone, V4 (example labels, sources,
  slider updates, clamping, no NaN or Infinity), V3 (formula shown), V6 (Tab and arrows
  only, accessible names, no animations under reduced motion, nothing wider than 375 px,
  the measured table included).
- A browser hands an overflowing entry such as `1e999` to the page as an empty value, so
  the box falls back to the value already in use. It does not clamp to the maximum.

## Note for the redesign
At the example inputs the headline is about $5,775 a month on questions it never saw,
and about $7,873 on questions it was tuned on.

## README and verify
- The README paragraph sits in "Evaluation", after the Results page paragraph.
  `tests/test_docs.py` caps the walkthrough above "Setup details" at 600 words, and it
  had about 5 words to spare.
- `./verify.sh` green (1105 pytest, 24 Playwright, after the framing change), using this worktree's own compose db
  and seed on 56432, with Spider data copied from a sibling worktree's gitignored `data/spider`.
