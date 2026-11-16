# Before and after: `v03-spider-new-before` vs `v03-spider-new-gated`

Question-level: right in more than half of the planned trials; an unfinished trial is not right. The p-value is the exact two-sided McNemar test on the questions where the two runs differ.

| Schema | System | Questions | Right before | Right after | Only after | Only before | p | Wrong/answered before | Wrong/answered after |
|---|---|---|---|---|---|---|---|---|---|
| spider_cre_Doc_Template_Mgt | ledgerline | 50 | 46 | 46 | 1 | 1 | 1.0000 | 0.0% (0/46) | 2.1% (1/47) |
| spider_student_transcripts_tracking | ledgerline | 50 | 29 | 29 | 3 | 3 | 1.0000 | 27.5% (11/40) | 25.6% (10/39) |
| spider_tvshow | ledgerline | 50 | 40 | 39 | 1 | 2 | 1.0000 | 2.4% (1/41) | 0.0% (0/39) |
| spider_world_1 | ledgerline | 50 | 34 | 30 | 0 | 4 | 0.1250 | 8.1% (3/37) | 16.7% (6/36) |

Wrong among answered, per trial:

- spider_cre_Doc_Template_Mgt ledgerline before: t1 0.0% (0/46)
- spider_cre_Doc_Template_Mgt ledgerline after: t1 2.1% (1/47)
- spider_student_transcripts_tracking ledgerline before: t1 27.5% (11/40)
- spider_student_transcripts_tracking ledgerline after: t1 25.6% (10/39)
- spider_tvshow ledgerline before: t1 2.4% (1/41)
- spider_tvshow ledgerline after: t1 0.0% (0/39)
- spider_world_1 ledgerline before: t1 8.1% (3/37)
- spider_world_1 ledgerline after: t1 16.7% (6/36)
