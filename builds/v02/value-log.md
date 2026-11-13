# PR-V value calculator: build log

## Owner's changes to the plan (2026-11-13)
- Logic first, design later: no `/impeccable` steps, V7 waived. The page uses the existing
  `style.css` with a few layout rules for the slider rows, and nothing beyond the plan.
- The report constant points at `v02-seen` from the start, labelled "measured on the
  seen questions". `v02-holdout` is shown beside it as the stricter figure. The range runs
  on the held-out wrong-answer interval.

## Choices the plan left open (sent to the orchestrator; easy to swap)
- **Run date.** The report JSON has no date. `SOURCE.date` is `2026-11-12`, the day
  9c8ebcf (which added both reports) landed on main. No test checks it, because CI's
  shallow checkout has no file history to test against.
- **Held-out drives the net value (orchestrator, 2026-11-13).** The headline uses the
  held-out coverage (64.3%) and the held-out point wrong rate (25.9%). The range uses the
  same coverage at the interval's two ends (16.1%, 38.9%), so the headline sits inside its
  own range. Cost per question comes from `v02-seen` everywhere. The seen rates (87.6%,
  1.8%) are one secondary line, "on the questions it was tuned on", and never feed the
  net value. The run date was approved as is.
- **The constant's file.** The ids, model and date live in `web/src/value-source.ts`,
  not `value.ts`, so the unit test can import them without loading the page and its CSS.
  It is still one constant in one place.

## What each figure reads
| Figure | Report | Field (Askwell row, `anthropic:claude-haiku-5-5`) |
|---|---|---|
| Model, run id | v02-seen, v02-holdout | `model`, `run_id` |
| Cost per question (calculator) | v02-seen | `mean_cost_usd` |
| Answered share, wrong rate (headline) | v02-holdout | `coverage.rate`, `wrong_answer_rate_given_answered.rate` |
| Range | v02-holdout | `coverage.rate`, `wrong_answer_rate_given_answered.ci95` |
| Seen rates (shown only) | v02-seen | `coverage`, `wrong_answer_rate_given_answered` |

## Tests
- `web/e2e/value-formula.spec.ts`: V3 (known inputs, zero answered share, checking slower
  than by hand), V5 (range = formula at the interval ends), clamp, and V2's constant
  check against `evals/reports/` and `askwell/config.py`'s default model. These are
  unit tests and open no browser.
- `web/e2e/value.spec.ts`: V1, V2 (cost to 6 decimals), a V3-style check that the
  headline is formula(held-out coverage, held-out point rate), not the seen rates, and
  sits inside its range, V4 (example labels, sources,
  slider updates, clamping, no NaN or Infinity), V3 (formula shown), V6 (Tab and arrows
  only, accessible names, no animations under reduced motion, nothing wider than 375 px,
  the measured table included).
- A browser hands an overflowing entry such as `1e999` to the page as an empty value, so
  the box falls back to the value already in use. It does not clamp to the maximum.

## Note for the redesign
At the example inputs the headline is about −$10,900 a month, in a range of about −$19,300
to −$4,600. The risk term (answered × wrong rate × $200) dominates. At the seen rates it
would be about +$6,300.

## README and verify
- The README paragraph sits in "Evaluation", after the Results page paragraph.
  `tests/test_docs.py` caps the walkthrough above "Setup details" at 600 words, and it
  had about 5 words to spare.
- `./verify.sh` green (1105 pytest, 24 Playwright), using this worktree's own compose db
  and seed on 56432, with Spider data copied from a sibling worktree's gitignored `data/spider`.
