# Eval report `v03-spider-new-gated`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `spider_ids_v03.json`.

Status: complete. Spend: $0.0925.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| spider_cre_Doc_Template_Mgt | ledgerline | anthropic:claude-haiku-5-5 | 1 | 94.0% [84-98] (47/50) | 92.0% [81-97] (46/50) | 97.9% [89-100] (46/47) | 6.0% [2-16] (3/50) | 2.1% [0-11] (1/47) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |
| spider_student_transcripts_tracking | ledgerline | anthropic:claude-haiku-5-5 | 1 | 78.0% [65-87] (39/50) | 58.0% [44-71] (29/50) | 74.4% [59-85] (29/39) | 22.0% [13-35] (11/50) | 25.6% [15-41] (10/39) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |
| spider_tvshow | ledgerline | anthropic:claude-haiku-5-5 | 1 | 78.0% [65-87] (39/50) | 78.0% [65-87] (39/50) | 100.0% [91-100] (39/39) | 22.0% [13-35] (11/50) | 0.0% [0-9] (0/39) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |
| spider_world_1 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 72.0% [58-83] (36/50) | 60.0% [46-72] (30/50) | 83.3% [68-92] (30/36) | 28.0% [17-42] (14/50) | 16.7% [8-32] (6/36) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |

## Ledgerline misses

- `spider:315` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:345` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:346` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:379` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Askwell wrong: it read a question needing both values as either value (an in-list), where two has filters, as the CSV path wrote, give the documents with both. Before: both right.
- `spider:526` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused (Askwell after fan_out): counting sections grouped by course answers it, as the gold does. Before: both refused.
- `spider:531` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both wrong: the substring kept a leading word of the question, where the gold matches only the key word. Before: both wrong.
- `spider:533` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Askwell grouped enrolments by student and semester, as the question says; the gold counts a student's enrolments across all semesters. Before: both systems wrong, grouped the same way.
- `spider:534` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Askwell and the CSV path grouped by student and semester, as the question says; the gold ignores the semester. Before: both wrong.
- `spider:535` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Both list one row per enrolment, so names repeat; the gold asks for distinct rows, which row lists cannot. Before: both wrong.
- `spider:536` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Same as spider:535: the gold needs distinct rows. Before: both wrong.
- `spider:541` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Two students tie for the most enrolments; the gold's single row is one of the tie, by table order. Before: both wrong.
- `spider:547` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Several courses tie for the most enrolments; the gold's single row is one of the tie. Before: both right (the tie fell the gold's way).
- `spider:548` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Same tie as spider:547. Before: both right.
- `spider:549` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has` and `link_roles`, which is off here.
- `spider:550` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has` and `link_roles`, which is off here.
- `spider:552` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. v03-spider-new-gated: wrong, it grouped the date by day and added a count column the gold does not return.
- `spider:557` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused, reading the question as asking for a status the data lacks; the gold reads it as the earliest leaving date. Before: both refused.
- `spider:563` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (aggregate_type). Tag: **grammar_gap**. The gold averages a datetime column (SQLite returns a number); the intent averages numeric fields only. Before: both refused.
- `spider:567` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused because no field marks a transcript as released; the gold counts every transcript. Before: both refused.
- `spider:575` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused as a set intersection; two has filters on semesters, as spider:379's CSV answer did, could likely express it. Before: both wrong.
- `spider:578` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (ambiguous_path, invalid_order_by). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has` and `link_roles`, which is off here.
- `spider:579` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both ordered by last name and selected every column; the gold sorts and returns the one free-text details column. Before: both wrong.
- `spider:581` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. v03-spider-new-gated: refused, though the first run answered it right without any switch.
- `spider:583` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `link_roles`, which is off here.
- `spider:584` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `link_roles`, which is off here.
- `spider:629` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. v03-spider-new-gated: refused, though the first run answered it right without any switch.
- `spider:635` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:636` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:637` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:638` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:641` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Both refused: it filters channels by a per-country count applied back to each row. The gold groups by country and returns one arbitrary id per country. Before: both refused.
- `spider:642` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Same gold as spider:641, with a question that reads as channels containing channels. Before: both refused.
- `spider:643` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:644` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:645` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:646` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:705` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both wrong: they counted every government form that includes the key word; the gold counts only the form that is exactly that word. A defensible reading the gold does not take. Before: Askwell wrong, CSV refused (files did not load).
- `spider:724` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both wrong: every government form including the key word counted, where the gold takes only the exact form, as in spider:705. Before: Askwell wrong, CSV refused.
- `spider:740` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Several countries tie for the most languages; the gold's single row is one of the tie. CSV path refused: no country link drawn. Before: Askwell right (the tie fell the gold's way), CSV refused.
- `spider:741` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Same tie as spider:740. Before: Askwell right, CSV refused.
- `spider:745` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:749` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:758` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Askwell wrong: every government form including the key word counted, as in spider:705, where the gold takes the exact form. CSV path refused: no country link drawn. Before: Askwell wrong, CSV refused.
- `spider:759` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused, reasoning that the count must be taken before the government-form filter; the gold filters first, then counts. Before: both refused.
- `spider:764` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:765` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:767` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:773` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Both refused: it compares with an aggregate over a different set of rows (another continent), which compare-with-an-aggregate refuses by design. Before: both refused.
- `spider:774` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Same as spider:773. Before: both refused.
- `spider:775` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Same as spider:773. Before: both refused.
- `spider:777` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Same as spider:773. Before: both refused.
- `spider:783` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. v03-spider-new-gated: refused. The first run's answer used `has`, which is off here.
- `spider:788` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. v03-spider-new-gated: wrong. Seven countries share the smallest population; comparing with the minimum returns all seven, where the gold's single row is one of the tie. Right in v03-spider-new and before (a sorted list with a limit of one, which picks the gold's row).
- `spider:817` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Both refused: the top language within each country is a rank within groups. Before: both refused.
- `spider:818` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Both refused (a rank within groups); the gold returns a count of one per country that speaks the language, not the countries where it leads. Before: both refused.
- `spider:821` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Both refused (a rank within groups); the gold returns every country where the language is spoken, not where it leads. Before: both refused.

## Where a baseline beat Ledgerline

None.

## Spider registries (generated by `registry init`, unedited, draft)

- spider_cre_Doc_Template_Mgt: `5f0220514fd4e8bf8bce7782302566866c6277388c1c7f002e91dd9b8b245b43`
- spider_student_transcripts_tracking: `f973380b3c4463106ed5ff1bfa59aa4fc83a0d0c88105637450f8d326cccb564`
- spider_tvshow: `b193ed5402b2c4958312b5c9a905052b094c71154b3e6b6b609d978aeb673a59`
- spider_world_1: `05455671c743c6a3793eaf2480c30acb697c0b024bc085f4ea30b4d0eb09cd6b`
