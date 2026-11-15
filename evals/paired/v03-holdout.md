# Before and after: `v03-holdout-before` vs `v03-holdout`

Question-level: right in more than half of the planned trials; an unfinished trial is not right. The p-value is the exact two-sided McNemar test on the questions where the two runs differ.

| Schema | System | Questions | Right before | Right after | Only after | Only before | p | Wrong/answered before | Wrong/answered after |
|---|---|---|---|---|---|---|---|---|---|
| fieldservice | ledgerline | 96 | 51 | 62 | 11 | 0 | 0.0010 | 7.3% (12/164) | 4.1% (8/193) |
| fieldservice | oneshot | 96 | 78 | 78 | 3 | 3 | 1.0000 | 9.0% (23/255) | 7.5% (19/255) |

Wrong among answered, per trial:

- fieldservice ledgerline before: t1 7.3% (4/55), t2 7.4% (4/54), t3 7.3% (4/55)
- fieldservice ledgerline after: t1 4.7% (3/64), t2 4.7% (3/64), t3 3.1% (2/65)
- fieldservice oneshot before: t1 9.5% (8/84), t2 10.7% (9/84), t3 6.9% (6/87)
- fieldservice oneshot after: t1 3.6% (3/84), t2 9.4% (8/85), t3 9.3% (8/86)
