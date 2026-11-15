# Before and after: `v03-csv-new-before` vs `v03-csv-new`

Question-level: right in more than half of the planned trials; an unfinished trial is not right. The p-value is the exact two-sided McNemar test on the questions where the two runs differ.

| Schema | System | Questions | Right before | Right after | Only after | Only before | p | Wrong/answered before | Wrong/answered after |
|---|---|---|---|---|---|---|---|---|---|
| spider_cre_Doc_Template_Mgt | askwell_csv | 50 | 40 | 43 | 5 | 2 | 0.4531 | 2.4% (1/41) | 2.3% (1/44) |
| spider_student_transcripts_tracking | askwell_csv | 50 | 22 | 28 | 8 | 2 | 0.1094 | 33.3% (11/33) | 24.3% (9/37) |
| spider_tvshow | askwell_csv | 50 | 30 | 31 | 1 | 0 | 1.0000 | 11.8% (4/34) | 8.8% (3/34) |
| spider_world_1 | askwell_csv | 50 | 2 | 22 | 20 | 0 | 0.0000 | 0.0% (0/2) | 15.4% (4/26) |

Wrong among answered, per trial:

- spider_cre_Doc_Template_Mgt askwell_csv before: t1 2.4% (1/41)
- spider_cre_Doc_Template_Mgt askwell_csv after: t1 2.3% (1/44)
- spider_student_transcripts_tracking askwell_csv before: t1 33.3% (11/33)
- spider_student_transcripts_tracking askwell_csv after: t1 24.3% (9/37)
- spider_tvshow askwell_csv before: t1 11.8% (4/34)
- spider_tvshow askwell_csv after: t1 8.8% (3/34)
- spider_world_1 askwell_csv before: t1 0.0% (0/2)
- spider_world_1 askwell_csv after: t1 15.4% (4/26)
