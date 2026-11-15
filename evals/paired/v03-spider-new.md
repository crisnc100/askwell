# Before and after: `v03-spider-new-before` vs `v03-spider-new`

Question-level: right in more than half of the planned trials; an unfinished trial is not right. The p-value is the exact two-sided McNemar test on the questions where the two runs differ.

| Schema | System | Questions | Right before | Right after | Only after | Only before | p | Wrong/answered before | Wrong/answered after |
|---|---|---|---|---|---|---|---|---|---|
| spider_cre_Doc_Template_Mgt | ledgerline | 50 | 46 | 49 | 4 | 1 | 0.3750 | 0.0% (0/46) | 2.0% (1/50) |
| spider_student_transcripts_tracking | ledgerline | 50 | 29 | 32 | 6 | 3 | 0.5078 | 27.5% (11/40) | 27.3% (12/44) |
| spider_tvshow | ledgerline | 50 | 40 | 42 | 5 | 3 | 0.7266 | 2.4% (1/41) | 12.5% (6/48) |
| spider_world_1 | ledgerline | 50 | 34 | 36 | 4 | 2 | 0.6875 | 8.1% (3/37) | 14.3% (6/42) |

Wrong among answered, per trial:

- spider_cre_Doc_Template_Mgt ledgerline before: t1 0.0% (0/46)
- spider_cre_Doc_Template_Mgt ledgerline after: t1 2.0% (1/50)
- spider_student_transcripts_tracking ledgerline before: t1 27.5% (11/40)
- spider_student_transcripts_tracking ledgerline after: t1 27.3% (12/44)
- spider_tvshow ledgerline before: t1 2.4% (1/41)
- spider_tvshow ledgerline after: t1 12.5% (6/48)
- spider_world_1 ledgerline before: t1 8.1% (3/37)
- spider_world_1 ledgerline after: t1 14.3% (6/42)
