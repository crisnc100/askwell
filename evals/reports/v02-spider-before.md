# Eval report `v02-spider-before`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `spider_ids.json`.

Status: complete. Spend: $0.1325.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| spider_car_1 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 72.0% [58-83] (36/50) | 62.0% [48-74] (31/50) | 86.1% [71-94] (31/36) | 28.0% [17-42] (14/50) | 13.9% [6-29] (5/36) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_car_1 | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 64.0% [50-76] (32/50) | 64.0% [50-76] (32/50) | 0.0% [0-7] (0/50) | 34.7% [23-49] (17/49) | n/a | 2.0% [0-10] (1/50) | spider_ids.json |
| spider_dog_kennels | ledgerline | anthropic:claude-haiku-5-5 | 1 | 60.0% [46-72] (30/50) | 44.0% [31-58] (22/50) | 73.3% [56-86] (22/30) | 40.0% [28-54] (20/50) | 26.7% [14-44] (8/30) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_dog_kennels | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 74.0% [60-84] (37/50) | 74.0% [60-84] (37/50) | 0.0% [0-7] (0/50) | 26.0% [16-40] (13/50) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_flight_2 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 52.0% [39-65] (26/50) | 42.0% [29-56] (21/50) | 80.8% [62-91] (21/26) | 48.0% [35-61] (24/50) | 19.2% [9-38] (5/26) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_flight_2 | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 84.0% [71-92] (42/50) | 84.0% [71-92] (42/50) | 0.0% [0-7] (0/50) | 12.5% [6-25] (6/48) | n/a | 4.0% [1-13] (2/50) | spider_ids.json |
| spider_network_1 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 54.0% [40-67] (27/50) | 48.0% [35-61] (24/50) | 88.9% [72-96] (24/27) | 46.0% [33-60] (23/50) | 11.1% [4-28] (3/27) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_network_1 | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 92.0% [81-97] (46/50) | 92.0% [81-97] (46/50) | 0.0% [0-7] (0/50) | 8.0% [3-19] (4/50) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_wta_1 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 94.0% [84-98] (47/50) | 82.0% [69-90] (41/50) | 87.2% [75-94] (41/47) | 6.0% [2-16] (3/50) | 12.8% [6-25] (6/47) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_wta_1 | oneshot | anthropic:claude-haiku-5-5 | 1 | 100.0% [93-100] (50/50) | 86.0% [74-93] (43/50) | 86.0% [74-93] (43/50) | 0.0% [0-7] (0/50) | 12.2% [6-24] (6/49) | n/a | 2.0% [0-10] (1/50) | spider_ids.json |

## Ledgerline misses

- `spider:919` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:920` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (aggregate_type). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:922` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:923` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:924` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:925` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:927` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:928` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them.
- `spider:929` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them.
- `spider:937` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unknown_field). Tag: **gold_issue**. The gold ranks owners by number of treatments; the question asks who spent the most. The answer sums cost.
- `spider:942` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold counts treatments; the question asks for at least two types of treatment. The answer counts distinct types.
- `spider:944` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:945` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:951` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The answer returns the size description column; the gold returns the size code column. Both answer the question.
- `spider:954` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:955` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:961` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Ambiguous: youngest by the age column (gold) or by date of birth (the answer). The two columns disagree in this data.
- `spider:972` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them.
- `spider:973` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them.
- `spider:974` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:978` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (fan_out, one_to_many_join). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:987` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (aggregate_type). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic.
- `spider:994` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them.
- `spider:995` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them.
- `spider:996` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:997` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:998` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. The gold needs DISTINCT rows; row lists in the intent grammar cannot ask for distinct rows.
- `spider:999` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Same as spider:998: needs DISTINCT rows.
- `spider:101` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs a subquery for the earliest year. The model returned all cars sorted by year instead of refusing: a wrong answer.
- `spider:103` (spider_car_1, spider_ids.json, trial 1): refused — refused (fan_out, invalid_order_by, unknown_field). Tag: **untriaged**
- `spider:104` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:116` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:117` (spider_car_1, spider_ids.json, trial 1): refused — refused (aggregate_type). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic.
- `spider:126` (spider_car_1, spider_ids.json, trial 1): refused — refused (operator_type). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic.
- `spider:135` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic.
- `spider:136` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic.
- `spider:150` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **misread**. The question is answerable by grouping model_list by maker. The model kept the base on car_makers, hit fan_out twice and gave up.
- `spider:152` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: car_names.model references model_list.model, which is not a primary key, so registry init skips the link and the tables cannot be joined.
- `spider:159` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:160` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:167` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:168` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:170` (spider_car_1, spider_ids.json, trial 1): refused — refused (aggregate_type). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic.
- `spider:171` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: car_names.model references model_list.model, which is not a primary key, so registry init skips the link and the tables cannot be joined.
- `spider:172` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **misread**. With no join path to the maker, the model filtered on the model name instead of refusing, and added a count column: a wrong answer.
- `spider:175` (spider_car_1, spider_ids.json, trial 1): wrong — unknown_field. Tag: **grammar_gap**. Needs an INTERSECT of two conditions. The model answered only the first: a wrong answer.
- `spider:178` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: car_names.model references model_list.model, which is not a primary key, so registry init skips the link and the tables cannot be joined.
- `spider:198` (spider_flight_2, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing.
- `spider:207` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:208` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path, unknown_entity). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:209` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path, unknown_entity). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:210` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:214` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:215` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:216` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:217` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:218` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:219` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:220` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:224` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path, unknown_entity). Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing.
- `spider:226` (spider_flight_2, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing.
- `spider:228` (spider_flight_2, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing.
- `spider:229` (spider_flight_2, spider_ids.json, trial 1): wrong — rows differ. Tag: **misread**. With no link to airlines, the model returned an airline id and count instead of refusing: a wrong answer.
- `spider:230` (spider_flight_2, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:231` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:233` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:239` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:240` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:245` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:246` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:251` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path, unknown_entity). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:252` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path, unknown_entity). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:254` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path, unknown_entity). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:255` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:257` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:258` (spider_flight_2, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:449` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:451` (spider_wta_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **misread**. The names and country codes need a join with two equally short paths (winner or loser). The model grouped by winner_id instead of refusing, so it returned ids rather than the requested columns: a wrong answer.
- `spider:452` (spider_wta_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:463` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold reads rank points from an unaggregated column in a GROUP BY (SQLite returns an arbitrary row). The answer's maximum is a defined value.
- `spider:464` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Same gold pattern as spider:463: rank points from an unaggregated column.
- `spider:470` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:472` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold groups by first name, which merges different players who share one; the answer totals per player.
- `spider:486` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:488` (spider_wta_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:885` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:886` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:887` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path, invalid_order_by). Tag: **misread**. After the validator refused the ambiguous join, the model answered with student ids instead of names: a wrong answer.
- `spider:889` (spider_network_1, spider_ids.json, trial 1): wrong — ambiguous_path. Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:890` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:891` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:892` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:893` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:894` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:896` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:897` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:898` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:899` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:900` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:904` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:905` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:906` (spider_network_1, spider_ids.json, trial 1): wrong — ambiguous_path. Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:907` (spider_network_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:908` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path, invalid_order_by, unknown_metric). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:910` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path, invalid_order_by). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:911` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path, invalid_order_by). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:912` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:913` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:914` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:915` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:917` (spider_network_1, spider_ids.json, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.

## Where a baseline beat Ledgerline

- `spider:101` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:103` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:104` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:116` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:117` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:150` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:171` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:172` (spider_car_1, spider_ids.json, trial 1): oneshot
- `spider:178` (spider_car_1, spider_ids.json, trial 1): oneshot
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
- `spider:210` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:216` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:217` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:218` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:219` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:220` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:224` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:233` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:239` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:240` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:245` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:246` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:251` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:252` (spider_flight_2, spider_ids.json, trial 1): oneshot
- `spider:254` (spider_flight_2, spider_ids.json, trial 1): oneshot
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
- `spider:910` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:911` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:912` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:913` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:914` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:915` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:917` (spider_network_1, spider_ids.json, trial 1): oneshot
- `spider:449` (spider_wta_1, spider_ids.json, trial 1): oneshot
- `spider:451` (spider_wta_1, spider_ids.json, trial 1): oneshot
- `spider:486` (spider_wta_1, spider_ids.json, trial 1): oneshot
- `spider:488` (spider_wta_1, spider_ids.json, trial 1): oneshot

## Spider registries (generated by `registry init`, unedited, draft)

- spider_car_1: `bfafa604590eb78ac55d142c41ebbbdf52308f2b0b98baded2aa8868d7309ca2`
- spider_dog_kennels: `ba7277f7739fd820d7ec8f4cfda282af060e5d4aa09828dcca20d512683bde78`
- spider_flight_2: `e69b8206b5403470249e458ce75b56ba6e3421c53b73d982f53e2fbe1646c940`
- spider_network_1: `b9991de76b27c3ecc644274d209d7c543c7c27dcd2ec7298e7ab729212639d4b`
- spider_wta_1: `807a938123c3f5467290fcab18b29cc9d79c341a9dab73eff6d096b5cb43345a`
