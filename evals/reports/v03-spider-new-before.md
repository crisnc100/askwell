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

- `spider:315` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:345` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:346` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:369` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): refused — refused (fan_out). Tag: **untriaged**
- `spider:520` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:526` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:531` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:533` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:534` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:535` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:536` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:537` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:538` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — unknown_field. Tag: **untriaged**
- `spider:541` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:549` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:550` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:557` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:563` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:567` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:575` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:578` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (ambiguous_path, invalid_order_by). Tag: **untriaged**
- `spider:579` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:581` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:583` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:584` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:623` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unknown_entity, unknown_field). Tag: **untriaged**
- `spider:635` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:636` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:637` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — invalid_order_by, unknown_field. Tag: **untriaged**
- `spider:641` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:642` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:643` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:644` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:645` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:646` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:705` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:724` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:745` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:758` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:759` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:764` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:765` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:767` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:773` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:774` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:775` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:777` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:783` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:817` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:818` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:821` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**

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
