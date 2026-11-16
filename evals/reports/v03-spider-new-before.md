# Eval report `v03-spider-new-before`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `spider_ids_v03.json`.

Status: complete. Spend: $0.1183.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| spider_cre_Doc_Template_Mgt | ledgerline | anthropic:claude-haiku-5-5 | 1 | 92.0% [81-97] (46/50) | 92.0% [81-97] (46/50) | 100.0% [92-100] (46/46) | 8.0% [3-19] (4/50) | 0.0% [0-8] (0/46) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |
| spider_cre_Doc_Template_Mgt | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 92.0% [81-97] (46/50) | 92.0% [81-97] (46/50) | 0.0% [0-7] (0/50) | 8.0% [3-19] (4/50) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |
| spider_student_transcripts_tracking | ledgerline | anthropic:claude-haiku-5-5 | 1 | 80.0% [67-89] (40/50) | 58.0% [44-71] (29/50) | 72.5% [57-84] (29/40) | 20.0% [11-33] (10/50) | 27.5% [16-43] (11/40) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |
| spider_student_transcripts_tracking | oneshot | anthropic:claude-haiku-5-5 | 1 | 98.0% [90-100] (49/50) | 62.0% [48-74] (31/50) | 63.3% [49-75] (31/49) | 2.0% [0-10] (1/50) | 35.4% [23-50] (17/48) | n/a | 2.0% [0-10] (1/50) | spider_ids_v03.json |
| spider_tvshow | ledgerline | anthropic:claude-haiku-5-5 | 1 | 82.0% [69-90] (41/50) | 80.0% [67-89] (40/50) | 97.6% [87-100] (40/41) | 18.0% [10-31] (9/50) | 2.4% [0-13] (1/41) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |
| spider_tvshow | oneshot | anthropic:claude-haiku-5-5 | 1 | 98.0% [90-100] (49/50) | 86.0% [74-93] (43/50) | 87.8% [76-94] (43/49) | 2.0% [0-10] (1/50) | 10.4% [5-22] (5/48) | n/a | 2.0% [0-10] (1/50) | spider_ids_v03.json |
| spider_world_1 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 74.0% [60-84] (37/50) | 68.0% [54-79] (34/50) | 91.9% [79-97] (34/37) | 26.0% [16-40] (13/50) | 8.1% [3-21] (3/37) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |
| spider_world_1 | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 72.0% [58-83] (36/50) | 72.0% [58-83] (36/50) | 0.0% [0-7] (0/50) | 28.0% [17-42] (14/50) | n/a | 0.0% [0-7] (0/50) | spider_ids_v03.json |

## Ledgerline misses

- `spider:315` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Before: refused (has none was not in the grammar). After: right with has none.
- `spider:345` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. Askwell right with has none. CSV path refused: the template-type link is not drawn from the uploaded files (a code column, not <name>_id). Before: both refused.
- `spider:346` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. Askwell right with has none. CSV path refused: the template-type link is not drawn from the uploaded files. Before: both refused.
- `spider:369` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): refused — refused (fan_out). Tag: **misread**. CSV path refused for fan_out after putting the count on the wrong side; Askwell right counting from the many side. Before: Askwell refused, CSV right.
- `spider:520` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Before: wrong, counting distinct program ids where the gold counts distinct summary names. After: right.
- `spider:526` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused (Askwell after fan_out): counting sections grouped by course answers it, as the gold does. Before: both refused.
- `spider:531` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both wrong: the substring kept a leading word of the question, where the gold matches only the key word. Before: both wrong.
- `spider:533` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Askwell grouped enrolments by student and semester, as the question says; the gold counts a student's enrolments across all semesters. Before: both systems wrong, grouped the same way.
- `spider:534` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Askwell and the CSV path grouped by student and semester, as the question says; the gold ignores the semester. Before: both wrong.
- `spider:535` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Both list one row per enrolment, so names repeat; the gold asks for distinct rows, which row lists cannot. Before: both wrong.
- `spider:536` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Same as spider:535: the gold needs distinct rows. Before: both wrong.
- `spider:537` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Before: wrong, counting distinct students where the gold counts enrolment rows. After: right.
- `spider:538` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — unknown_field. Tag: **misread**. Same as spider:537. Before: wrong. After: right.
- `spider:541` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Two students tie for the most enrolments; the gold's single row is one of the tie, by table order. Before: both wrong.
- `spider:549` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. Askwell right with a named link and has none. CSV path refused: the current-address column does not follow the <name>_id rule, so no link to addresses is drawn. Before: both refused.
- `spider:550` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. Same as spider:549. Before: both refused.
- `spider:557` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused, reading the question as asking for a status the data lacks; the gold reads it as the earliest leaving date. Before: both refused.
- `spider:563` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. The gold averages a datetime column (SQLite returns a number); the intent averages numeric fields only. Before: both refused.
- `spider:567` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused because no field marks a transcript as released; the gold counts every transcript. Before: both refused.
- `spider:575` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both refused as a set intersection; two has filters on semesters, as spider:379's CSV answer did, could likely express it. Before: both wrong.
- `spider:578` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (ambiguous_path, invalid_order_by). Tag: **gold_issue**. Askwell listed the addresses that have students (the question asks which ones); the gold returns only their count. CSV path refused: the address links are not drawn from the files. Before: both refused.
- `spider:579` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both ordered by last name and selected every column; the gold sorts and returns the one free-text details column. Before: both wrong.
- `spider:581` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Askwell right. CSV path refused, saying no section was named. Before: both refused.
- `spider:583` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Askwell compared the country as written in the data; the gold compares a lowercased value that matches no row, so only the phone match remains. CSV path refused: no address link drawn. Before: both refused.
- `spider:584` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Same as spider:583. Before: both refused.
- `spider:623` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unknown_entity, unknown_field). Tag: **validator_false_reject**. Askwell right. CSV path refused: the channel column does not follow the <name>_id rule, so no link to the channel table is drawn from the files. Before: both refused.
- `spider:635` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Askwell wrong (has none): it listed channels without such a cartoon, where the gold keeps countries none of whose channels play one. CSV path refused: no channel link drawn. Before: both refused.
- `spider:636` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Same as spider:635, counted per country. CSV path refused: no channel link. Before: both refused.
- `spider:637` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — invalid_order_by, unknown_field. Tag: **misread**. Askwell wrong: it read a question needing both directors as either director (an in-list); two has filters, as in its own right answer to spider:638, give the channels with both. CSV path refused: no channel link. Before: Askwell wrong, CSV refused.
- `spider:641` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Both refused: it filters channels by a per-country count applied back to each row. The gold groups by country and returns one arbitrary id per country. Before: both refused.
- `spider:642` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Same gold as spider:641, with a question that reads as channels containing channels. Before: both refused.
- `spider:643` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. Askwell right. CSV path refused: the channel column does not follow the <name>_id rule, so no link to the channel table is drawn from the files. Before: both refused.
- `spider:644` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. Askwell right. CSV path refused: the channel column does not follow the <name>_id rule, so no link to the channel table is drawn from the files. Before: both refused.
- `spider:645` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. Askwell right. CSV path refused: the channel column does not follow the <name>_id rule, so no link to the channel table is drawn from the files. Before: both refused.
- `spider:646` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. Askwell right. CSV path refused: the channel column does not follow the <name>_id rule, so no link to the channel table is drawn from the files. Before: both refused.
- `spider:705` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both wrong: they counted every government form that includes the key word; the gold counts only the form that is exactly that word. A defensible reading the gold does not take. Before: Askwell wrong, CSV refused (files did not load).
- `spider:724` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Both wrong: every government form including the key word counted, where the gold takes only the exact form, as in spider:705. Before: Askwell wrong, CSV refused.
- `spider:745` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. Askwell right. CSV path refused: the language table's country-code column does not follow the <name>_id rule, so no link to the country table is drawn from the files. Before: both refused.
- `spider:758` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **misread**. Askwell wrong: every government form including the key word counted, as in spider:705, where the gold takes the exact form. CSV path refused: no country link drawn. Before: Askwell wrong, CSV refused.
- `spider:759` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Both refused, reasoning that the count must be taken before the government-form filter; the gold filters first, then counts. Before: both refused.
- `spider:764` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. Askwell right with has none. CSV path refused: the drafted registry lists no values for the official-language flag, so the model would not guess its coding. Before: both refused.
- `spider:765` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. Askwell right. CSV path refused: the language table's country-code column does not follow the <name>_id rule, so no link to the country table is drawn from the files. Before: both refused.
- `spider:767` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. Askwell right. CSV path refused: the language table's country-code column does not follow the <name>_id rule, so no link to the country table is drawn from the files. Before: both refused.
- `spider:773` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Both refused: it compares with an aggregate over a different set of rows (another continent), which compare-with-an-aggregate refuses by design. Before: both refused.
- `spider:774` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Same as spider:773. Before: both refused.
- `spider:775` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Same as spider:773. Before: both refused.
- `spider:777` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Same as spider:773. Before: both refused.
- `spider:783` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **misread**. Askwell wrong: the has none part is right, but it excluded every government form including the key word where the gold excludes only the exact form, as in spider:705. CSV path refused: no country link drawn. Before: both refused.
- `spider:817` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Both refused: the top language within each country is a rank within groups. Before: both refused.
- `spider:818` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Both refused (a rank within groups); the gold returns a count of one per country that speaks the language, not the countries where it leads. Before: both refused.
- `spider:821` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. Both refused (a rank within groups); the gold returns every country where the language is spoken, not where it leads. Before: both refused.

## Where a baseline beat Ledgerline

- `spider:315` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): oneshot
- `spider:345` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): oneshot
- `spider:346` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): oneshot
- `spider:520` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): oneshot
- `spider:535` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): oneshot
- `spider:536` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): oneshot
- `spider:538` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): oneshot
- `spider:567` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): oneshot
- `spider:575` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): oneshot
- `spider:581` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): oneshot
- `spider:623` (spider_tvshow, spider_ids_v03.json, trial 1): oneshot
- `spider:637` (spider_tvshow, spider_ids_v03.json, trial 1): oneshot
- `spider:643` (spider_tvshow, spider_ids_v03.json, trial 1): oneshot
- `spider:644` (spider_tvshow, spider_ids_v03.json, trial 1): oneshot
- `spider:645` (spider_tvshow, spider_ids_v03.json, trial 1): oneshot
- `spider:745` (spider_world_1, spider_ids_v03.json, trial 1): oneshot
- `spider:764` (spider_world_1, spider_ids_v03.json, trial 1): oneshot
- `spider:765` (spider_world_1, spider_ids_v03.json, trial 1): oneshot
- `spider:767` (spider_world_1, spider_ids_v03.json, trial 1): oneshot
- `spider:775` (spider_world_1, spider_ids_v03.json, trial 1): oneshot

## Spider registries (generated by `registry init`, unedited, draft)

- spider_cre_Doc_Template_Mgt: `168bd288b02b1d4c772f1c864a7dc61dea5671338ad660766634b03af00a2a23`
- spider_student_transcripts_tracking: `829f664a0b5205c7713c58b0e68fc320416b250dbc3cffdd770b435bd90d7e40`
- spider_tvshow: `190952ddb56c9abdee48493a702086d5e006f41862829b0e1c4530c68deb65d7`
- spider_world_1: `813492cb14715818a128d80297a4b59a9cc450945af0760cc93f6c7a7aaadfab`
