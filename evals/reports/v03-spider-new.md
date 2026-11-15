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

- `spider:379` (spider_cre_Doc_Template_Mgt, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:525` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:526` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (fan_out, unknown_metric). Tag: **untriaged**
- `spider:531` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:533` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:534` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:535` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — has_link. Tag: **untriaged**
- `spider:536` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:541` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:547` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:548` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:557` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:563` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (aggregate_type). Tag: **untriaged**
- `spider:567` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:575` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:578` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:579` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:583` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:584` (spider_student_transcripts_tracking, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:613` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:615` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:616` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:635` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:636` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:637` (spider_tvshow, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:641` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:642` (spider_tvshow, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:705` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:724` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:740` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:741` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:758` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:759` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:773` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:774` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:775` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:777` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:783` (spider_world_1, spider_ids_v03.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:817` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:818` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:821` (spider_world_1, spider_ids_v03.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**

## Where a baseline beat Ledgerline

None.

## Spider registries (generated by `registry init`, unedited, draft)

- spider_cre_Doc_Template_Mgt: `5f0220514fd4e8bf8bce7782302566866c6277388c1c7f002e91dd9b8b245b43`
- spider_student_transcripts_tracking: `f973380b3c4463106ed5ff1bfa59aa4fc83a0d0c88105637450f8d326cccb564`
- spider_tvshow: `264e1f54d8850297743f065cec48416db0640b66618368b0859618d2a230463f`
- spider_world_1: `05455671c743c6a3793eaf2480c30acb697c0b024bc085f4ea30b4d0eb09cd6b`
