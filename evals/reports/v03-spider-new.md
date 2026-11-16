# Eval report `v03-spider-new`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `spider_ids_v03.json`.

Status: complete. Spend: $0.0991.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| spider_cre_Doc_Template_Mgt | ledgerline | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 98.0% [90-100] (49/50) | 98.0% [90-100] (49/50) | 0.0% [0-7] (0/50) | 2.0% [0-10] (1/50) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |
| spider_student_transcripts_tracking | ledgerline | anthropic:claude-haiku-5-5 | 1 | 88.0% [76-94] (44/50) | 64.0% [50-76] (32/50) | 72.7% [58-84] (32/44) | 12.0% [6-24] (6/50) | 27.3% [16-42] (12/44) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |
| spider_tvshow | ledgerline | anthropic:claude-haiku-5-5 | 1 | 96.0% [87-99] (48/50) | 84.0% [71-92] (42/50) | 87.5% [75-94] (42/48) | 4.0% [1-13] (2/50) | 12.5% [6-25] (6/48) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |
| spider_world_1 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 84.0% [71-92] (42/50) | 72.0% [58-83] (36/50) | 85.7% [72-93] (36/42) | 16.0% [8-29] (8/50) | 14.3% [7-28] (6/42) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |

## Ledgerline misses

- `spider:379` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Askwell wrong: it read a question needing both values as either value (an in-list), where two has filters, as the CSV path wrote, give the documents with both. Before: both right.
- `spider:525` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused, saying a grouped count would drop courses with no sections; the gold is that grouped count (an inner join), so counting from the sections side answers it. Before: Askwell right, CSV refused.
- `spider:526` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (fan_out, unknown_metric). Tag: **misread**. Both refused (Askwell after fan_out): counting sections grouped by course answers it, as the gold does. Before: both refused.
- `spider:531` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both wrong: the substring kept a leading word of the question, where the gold matches only the key word. Before: both wrong.
- `spider:533` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Askwell grouped enrolments by student and semester, as the question says; the gold counts a student's enrolments across all semesters. Before: both systems wrong, grouped the same way.
- `spider:534` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Askwell and the CSV path grouped by student and semester, as the question says; the gold ignores the semester. Before: both wrong.
- `spider:535` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — has_link. Tag: **grammar_gap**. Both list one row per enrolment, so names repeat; the gold asks for distinct rows, which row lists cannot. Before: both wrong.
- `spider:536` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Same as spider:535: the gold needs distinct rows. Before: both wrong.
- `spider:541` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Two students tie for the most enrolments; the gold's single row is one of the tie, by table order. Before: both wrong.
- `spider:547` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Several courses tie for the most enrolments; the gold's single row is one of the tie. Before: both right (the tie fell the gold's way).
- `spider:548` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Same tie as spider:547. Before: both right.
- `spider:557` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused, reading the question as asking for a status the data lacks; the gold reads it as the earliest leaving date. Before: both refused.
- `spider:563` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (aggregate_type). Tag: **grammar_gap**. The gold averages a datetime column (SQLite returns a number); the intent averages numeric fields only. Before: both refused.
- `spider:567` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused because no field marks a transcript as released; the gold counts every transcript. Before: both refused.
- `spider:575` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused as a set intersection; two has filters on semesters, as spider:379's CSV answer did, could likely express it. Before: both wrong.
- `spider:578` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Askwell listed the addresses that have students (the question asks which ones); the gold returns only their count. CSV path refused: the address links are not drawn from the files. Before: both refused.
- `spider:579` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both ordered by last name and selected every column; the gold sorts and returns the one free-text details column. Before: both wrong.
- `spider:583` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Askwell compared the country as written in the data; the gold compares a lowercased value that matches no row, so only the phone match remains. CSV path refused: no address link drawn. Before: both refused.
- `spider:584` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Same as spider:583. Before: both refused.
- `spider:613` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Askwell wrong: it sorted by rating descending where the question asks plain sorted (ascending); the CSV path sorted ascending and is right. Before: Askwell right (the text sort matched), CSV wrong.
- `spider:615` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Same rows and values as the gold; the gold returns the rating as the stored text ('5.8') and both systems return the number, which the scorer counts as different. Askwell reads it as a number through numeric_text; the CSV path through the upload. Before: Askwell right, CSV wrong.
- `spider:616` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Same as spider:615: right values, the gold keeps the rating as text. Before: Askwell right, CSV wrong.
- `spider:635` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Askwell wrong (has none): it listed channels without such a cartoon, where the gold keeps countries none of whose channels play one. CSV path refused: no channel link drawn. Before: both refused.
- `spider:636` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Same as spider:635, counted per country. CSV path refused: no channel link. Before: both refused.
- `spider:637` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Askwell wrong: it read a question needing both directors as either director (an in-list); two has filters, as in its own right answer to spider:638, give the channels with both. CSV path refused: no channel link. Before: Askwell wrong, CSV refused.
- `spider:641` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Both refused: it filters channels by a per-country count applied back to each row. The gold groups by country and returns one arbitrary id per country. Before: both refused.
- `spider:642` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Same gold as spider:641, with a question that reads as channels containing channels. Before: both refused.
- `spider:705` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both wrong: they counted every government form that includes the key word; the gold counts only the form that is exactly that word. A defensible reading the gold does not take. Before: Askwell wrong, CSV refused (files did not load).
- `spider:724` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both wrong: every government form including the key word counted, where the gold takes only the exact form, as in spider:705. Before: Askwell wrong, CSV refused.
- `spider:740` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Several countries tie for the most languages; the gold's single row is one of the tie. CSV path refused: no country link drawn. Before: Askwell right (the tie fell the gold's way), CSV refused.
- `spider:741` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Same tie as spider:740. Before: Askwell right, CSV refused.
- `spider:758` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Askwell wrong: every government form including the key word counted, as in spider:705, where the gold takes the exact form. CSV path refused: no country link drawn. Before: Askwell wrong, CSV refused.
- `spider:759` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused, reasoning that the count must be taken before the government-form filter; the gold filters first, then counts. Before: both refused.
- `spider:773` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Both refused: it compares with an aggregate over a different set of rows (another continent), which compare-with-an-aggregate refuses by design. Before: both refused.
- `spider:774` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Same as spider:773. Before: both refused.
- `spider:775` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Same as spider:773. Before: both refused.
- `spider:777` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Same as spider:773. Before: both refused.
- `spider:783` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Askwell wrong: the has none part is right, but it excluded every government form including the key word where the gold excludes only the exact form, as in spider:705. CSV path refused: no country link drawn. Before: both refused.
- `spider:817` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Both refused: the top language within each country is a rank within groups. Before: both refused.
- `spider:818` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Both refused (a rank within groups); the gold returns a count of one per country that speaks the language, not the countries where it leads. Before: both refused.
- `spider:821` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Both refused (a rank within groups); the gold returns every country where the language is spoken, not where it leads. Before: both refused.

## Where a baseline beat Ledgerline

None.

## Spider registries (generated by `registry init`, unedited, draft)

- spider_cre_Doc_Template_Mgt: `5f0220514fd4e8bf8bce7782302566866c6277388c1c7f002e91dd9b8b245b43`
- spider_student_transcripts_tracking: `f973380b3c4463106ed5ff1bfa59aa4fc83a0d0c88105637450f8d326cccb564`
- spider_tvshow: `264e1f54d8850297743f065cec48416db0640b66618368b0859618d2a230463f`
- spider_world_1: `05455671c743c6a3793eaf2480c30acb697c0b024bc085f4ea30b4d0eb09cd6b`
