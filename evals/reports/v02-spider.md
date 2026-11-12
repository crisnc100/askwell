# Eval report `v02-spider`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `spider_ids.json`.

Status: complete. Spend: $0.1540.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| spider_car_1 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 58.0% [44-71] (29/50) | 58.0% [44-71] (29/50) | 100.0% [88-100] (29/29) | 42.0% [29-56] (21/50) | 0.0% [0-12] (0/29) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_car_1 | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 68.0% [54-79] (34/50) | 68.0% [54-79] (34/50) | 0.0% [0-7] (0/50) | 30.6% [20-45] (15/49) | n/a | 2.0% [0-10] (1/50) | spider_ids.json |
| spider_dog_kennels | ledgerline | anthropic:claude-haiku-5-5 | 1 | 60.0% [46-72] (30/50) | 46.0% [33-60] (23/50) | 76.7% [59-88] (23/30) | 40.0% [28-54] (20/50) | 23.3% [12-41] (7/30) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_dog_kennels | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 74.0% [60-84] (37/50) | 74.0% [60-84] (37/50) | 0.0% [0-7] (0/50) | 26.0% [16-40] (13/50) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_flight_2 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 44.0% [31-58] (22/50) | 42.0% [29-56] (21/50) | 95.5% [78-99] (21/22) | 56.0% [42-69] (28/50) | 4.5% [1-22] (1/22) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_flight_2 | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 82.0% [69-90] (41/50) | 82.0% [69-90] (41/50) | 0.0% [0-7] (0/50) | 12.8% [6-25] (6/47) | n/a | 6.0% [2-16] (3/50) | spider_ids.json |
| spider_network_1 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 46.0% [33-60] (23/50) | 46.0% [33-60] (23/50) | 100.0% [86-100] (23/23) | 54.0% [40-67] (27/50) | 0.0% [0-14] (0/23) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_network_1 | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 92.0% [81-97] (46/50) | 92.0% [81-97] (46/50) | 0.0% [0-7] (0/50) | 8.0% [3-19] (4/50) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_wta_1 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 94.0% [84-98] (47/50) | 88.0% [76-94] (44/50) | 93.6% [83-98] (44/47) | 6.0% [2-16] (3/50) | 6.4% [2-17] (3/47) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_wta_1 | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 86.0% [74-93] (43/50) | 86.0% [74-93] (43/50) | 0.0% [0-7] (0/50) | 12.2% [6-24] (6/49) | n/a | 2.0% [0-10] (1/50) | spider_ids.json |

## Ledgerline misses

- `spider:93` (spider_car_1, spider_ids.json, trial 1): refused — refused (fan_out, invalid_order_by, unknown_field). Tag: **misread**. The model used a metric alias as a field reference. Before: right. After: refused.
- `spider:95` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before: right. After: refused.
- `spider:96` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before: right. After: refused.
- `spider:101` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery for the earliest year. Before: a wrong answer. After: refused.
- `spider:104` (spider_car_1, spider_ids.json, trial 1): refused — refused (fan_out, one_to_many_join). Tag: **grammar_gap**. The gold needs DISTINCT rows; row lists in the intent grammar cannot ask for distinct rows. Before: a wrong answer. After: refused.
- `spider:117` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before and after: refused.
- `spider:126` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before and after: refused.
- `spider:132` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before: right. After: refused.
- `spider:135` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before and after: refused.
- `spider:136` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before and after: refused.
- `spider:152` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:159` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:160` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:165` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before: right. After: refused.
- `spider:167` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:168` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:170` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before and after: refused.
- `spider:171` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:172` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link from the car tables to the makers table, so the exclusion cannot be written. Before and after: refused.
- `spider:175` (spider_car_1, spider_ids.json, trial 1): refused — refused (fan_out, invalid_order_by, unknown_field, unknown_metric). Tag: **grammar_gap**. Needs a set operation. The intent grammar has none. Before: a wrong answer. After: refused.
- `spider:178` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:919` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:920` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:922` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:923` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:924` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs an anti-join or subquery to keep dogs with no treatments. The intent grammar has neither. Before: a wrong answer. After: refused.
- `spider:925` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:927` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:928` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them. Before and after: refused.
- `spider:929` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them. Before and after: refused.
- `spider:937` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold ranks owners by number of treatments; the question asks who spent the most. The v0.2 answer sums cost. Before: refused. After: a wrong answer.
- `spider:942` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold counts treatments; the question asks for at least two types of treatment. The answer counts distinct types. Before and after: a wrong answer.
- `spider:944` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:945` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:951` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The answer returns the size description column; the gold returns the size code column. Both answer the question. Before and after: a wrong answer.
- `spider:954` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:955` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:961` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Ambiguous: youngest by the age column (gold) or by date of birth (the answer). The two columns disagree in this data. Before and after: a wrong answer.
- `spider:972` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them. Before and after: refused.
- `spider:973` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them. Before and after: refused.
- `spider:974` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:978` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:987` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (aggregate_type). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before and after: refused.
- `spider:994` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them. Before and after: refused.
- `spider:995` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them. Before and after: refused.
- `spider:996` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The answer returns description columns; the gold returns the code columns. Both answer the question. Before and after: a wrong answer.
- `spider:998` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. The gold needs DISTINCT rows; row lists in the intent grammar cannot ask for distinct rows. Before and after: a wrong answer.
- `spider:999` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Same as spider:998: needs DISTINCT rows. Before and after: a wrong answer.
- `spider:198` (spider_flight_2, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing. Before and after: a wrong answer.
- `spider:207` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unknown_entity). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:208` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:209` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:210` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:214` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:215` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:216` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:217` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:218` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:219` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:220` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:224` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:226` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing. Before: a wrong answer. After: refused.
- `spider:228` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing. Before: a wrong answer. After: refused.
- `spider:229` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines, so airline names cannot be reached. Before: a wrong answer. After: refused.
- `spider:230` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines, so airline names cannot be reached. Before: a wrong answer. After: refused.
- `spider:231` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:233` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:238` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before: right. After: refused.
- `spider:240` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:245` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:246` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:251` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:252` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:254` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unknown_entity). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:255` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:257` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:258` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:885` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path, invalid_order_by). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:886` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:887` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:889` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use. Before: a wrong answer. After: refused.
- `spider:890` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:891` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:892` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:893` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:894` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:896` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:897` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:898` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:899` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:900` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:904` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:905` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:906` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use. Before: a wrong answer. After: refused.
- `spider:907` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use. Before: a wrong answer. After: refused.
- `spider:908` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path, invalid_order_by). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:909` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before: right. After: refused.
- `spider:910` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:911` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:912` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:913` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:914` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:915` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:917` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:451` (spider_wta_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:452` (spider_wta_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:463` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold reads rank points from an unaggregated column in a GROUP BY (SQLite returns an arbitrary row). The answer's maximum is a defined value. Before and after: a wrong answer.
- `spider:464` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Same gold pattern as spider:463: rank points from an unaggregated column. Before and after: a wrong answer.
- `spider:472` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold groups by first name, which merges different players who share one; the answer totals per player. Before and after: a wrong answer.
- `spider:488` (spider_wta_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.

## Where a baseline beat Ledgerline

- `spider:101` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:104` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:117` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:152` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:171` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:172` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:175` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:178` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:93` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:919` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:920` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:922` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:923` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:924` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:927` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:928` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:929` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:972` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:973` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:974` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:978` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:987` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:994` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:995` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:999` (spider_dog_kennels, spider_ids.json, trial 1): oneshot
- `spider:207` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:208` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:209` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:215` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:216` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:217` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:218` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:219` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:220` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:224` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:233` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:238` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:240` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:245` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:246` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:251` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:252` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:255` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:257` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:258` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:886` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:887` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:889` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:890` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:891` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:892` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:893` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:894` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:896` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:897` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:898` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:899` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:900` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:904` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:905` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:908` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:909` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:910` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:911` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:912` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:913` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:914` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:915` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:917` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:451` (spider_wta_1, spider_ids.json, trial 1): oneshot
- `spider:463` (spider_wta_1, spider_ids.json, trial 1): oneshot
- `spider:488` (spider_wta_1, spider_ids.json, trial 1): oneshot

## Spider registries (generated by `registry init`, unedited, draft)

- spider_car_1: `bfafa604590eb78ac55d142c41ebbbdf52308f2b0b98baded2aa8868d7309ca2`
- spider_dog_kennels: `ba7277f7739fd820d7ec8f4cfda282af060e5d4aa09828dcca20d512683bde78`
- spider_flight_2: `e69b8206b5403470249e458ce75b56ba6e3421c53b73d982f53e2fbe1646c940`
- spider_network_1: `b9991de76b27c3ecc644274d209d7c543c7c27dcd2ec7298e7ab729212639d4b`
- spider_wta_1: `807a938123c3f5467290fcab18b29cc9d79c341a9dab73eff6d096b5cb43345a`
