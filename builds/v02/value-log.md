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
- **The range's answered share.** It uses the held-out coverage (64.3%) with the two ends
  of the held-out wrong interval (16.1%, 38.9%), so the range is one held-out scenario.
  Cost per question comes from `v02-seen` everywhere. The seen figure can sit outside
  the held-out range, and the page says so.
- **The constant's file.** The ids, model and date live in `web/src/value-source.ts`,
  not `value.ts`, so the unit test can import them without loading the page and its CSS.
  It is still one constant in one place.

## What each figure reads
| Figure | Report | Field (Askwell row, `anthropic:claude-haiku-5-5`) |
|---|---|---|
| Model, run id | v02-seen, v02-holdout | `model`, `run_id` |
| Cost per question (calculator) | v02-seen | `mean_cost_usd` |
| Answered share, wrong rate (main figure) | v02-seen | `coverage.rate`, `wrong_answer_rate_given_answered.rate` |
| Range | v02-holdout | `coverage.rate`, `wrong_answer_rate_given_answered.ci95` |
| Held-out cost (shown only) | v02-holdout | `mean_cost_usd` |

## Tests
- `web/e2e/value-formula.spec.ts`: V3 (known inputs, zero answered share, checking slower
  than by hand), V5 (range = formula at the interval ends), clamp, and V2's constant
  check against `evals/reports/` and `askwell/config.py`'s default model. These are
  unit tests and open no browser.
- `web/e2e/value.spec.ts`: V1, V2 (cost to 6 decimals), V4 (example labels, sources,
  slider updates, clamping, no NaN or Infinity), V3 (formula shown), V6 (Tab and arrows
  only, accessible names, no animations under reduced motion, nothing wider than 375 px,
  the measured table included).
- A browser hands an overflowing entry such as `1e999` to the page as an empty value, so
  the box falls back to the value already in use. It does not clamp to the maximum.

## Note for the redesign
At the example inputs the seen figure is about +$6,300 a month. The held-out range is
about −$19,300 to −$4,600, because the risk term (answered × wrong rate × $200) dominates.
