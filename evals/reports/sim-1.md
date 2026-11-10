> **Model responses simulated by claude-haiku-5-5, standing in for openai/gpt-oss-120b. This is not an OpenRouter measurement.**

# Eval report `sim-1`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).
- One target model (openai/gpt-oss-120b). A second model runs once there is an OpenRouter key: simulating a second vendor with the same stand-in would add no real diversity.
- Trials: 1. Repeating trials with the same stand-in would measure the stand-in's variance, not the target model's.

Status: complete. Spend: $0.0000.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors |
|---|---|---|---|---|---|---|---|---|---|---|
| fieldservice | ledgerline | openai/gpt-oss-120b | 1 | 88.4% [76-95] (38/43) | 76.7% [62-87] (33/43) | 86.8% [73-94] (33/38) | 11.6% [5-24] (5/43) | 13.2% [6-27] (5/38) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) |
| fieldservice | oneshot | openai/gpt-oss-120b | 1 | 100.0% [92-100] (43/43) | 69.8% [55-81] (30/43) | 69.8% [55-81] (30/43) | 0.0% [0-8] (0/43) | 30.2% [19-45] (13/43) | 100.0% [86-100] (24/24) | 0.0% [0-5] (0/67) |
| spider_car_1 | ledgerline | openai/gpt-oss-120b | 1 | 72.0% [58-83] (36/50) | 66.0% [52-78] (33/50) | 91.7% [78-97] (33/36) | 28.0% [17-42] (14/50) | 8.3% [3-22] (3/36) | n/a | 0.0% [0-7] (0/50) |
| spider_car_1 | oneshot | openai/gpt-oss-120b | 1 | 100.0% [93-100] (50/50) | 74.0% [60-84] (37/50) | 74.0% [60-84] (37/50) | 0.0% [0-7] (0/50) | 26.0% [16-40] (13/50) | n/a | 0.0% [0-7] (0/50) |
| spider_dog_kennels | ledgerline | openai/gpt-oss-120b | 1 | 60.0% [46-72] (30/50) | 48.0% [35-61] (24/50) | 80.0% [63-90] (24/30) | 40.0% [28-54] (20/50) | 20.0% [10-37] (6/30) | n/a | 0.0% [0-7] (0/50) |
| spider_dog_kennels | oneshot | openai/gpt-oss-120b | 1 | 100.0% [93-100] (50/50) | 70.0% [56-81] (35/50) | 70.0% [56-81] (35/50) | 0.0% [0-7] (0/50) | 30.0% [19-44] (15/50) | n/a | 0.0% [0-7] (0/50) |
| spider_flight_2 | ledgerline | openai/gpt-oss-120b | 1 | 52.0% [39-65] (26/50) | 42.0% [29-56] (21/50) | 80.8% [62-91] (21/26) | 48.0% [35-61] (24/50) | 19.2% [9-38] (5/26) | n/a | 0.0% [0-7] (0/50) |
| spider_flight_2 | oneshot | openai/gpt-oss-120b | 1 | 100.0% [93-100] (50/50) | 88.0% [76-94] (44/50) | 88.0% [76-94] (44/50) | 0.0% [0-7] (0/50) | 12.0% [6-24] (6/50) | n/a | 0.0% [0-7] (0/50) |
| spider_network_1 | ledgerline | openai/gpt-oss-120b | 1 | 48.0% [35-61] (24/50) | 46.0% [33-60] (23/50) | 95.8% [80-99] (23/24) | 52.0% [39-65] (26/50) | 4.2% [1-20] (1/24) | n/a | 0.0% [0-7] (0/50) |
| spider_network_1 | oneshot | openai/gpt-oss-120b | 1 | 100.0% [93-100] (50/50) | 86.0% [74-93] (43/50) | 86.0% [74-93] (43/50) | 0.0% [0-7] (0/50) | 14.0% [7-26] (7/50) | n/a | 0.0% [0-7] (0/50) |
| spider_wta_1 | ledgerline | openai/gpt-oss-120b | 1 | 94.0% [84-98] (47/50) | 86.0% [74-93] (43/50) | 91.5% [80-97] (43/47) | 6.0% [2-16] (3/50) | 8.5% [3-20] (4/47) | n/a | 0.0% [0-7] (0/50) |
| spider_wta_1 | oneshot | openai/gpt-oss-120b | 1 | 100.0% [93-100] (50/50) | 82.0% [69-90] (41/50) | 82.0% [69-90] (41/50) | 0.0% [0-7] (0/50) | 16.3% [9-29] (8/49) | n/a | 2.0% [0-10] (1/50) |

## Floor check: fieldservice, openai/gpt-oss-120b (plan.md L11)

- Execution accuracy >= 80%: 76.7% [62-87] (33/43), NOT met
- Wrong answers among answered <= 5%: 13.2% [6-27] (5/38), NOT met

Result: **not met** in v0.1 (simulated run).
Why: For questions the intent grammar cannot express, the stand-in model often answers a nearby question instead of refusing. Example: asked for a percentage, it returned a count per status. Each such answer is a wrong answer, not a refusal.
Next: v0.2 changes the prompt to refuse first when a question needs something the grammar lacks, then measures it on a fresh run. The v0.1 prompt is not changed after seeing these results.

## Ledgerline misses

- `fs-022` (fieldservice, trial 1): wrong — rows differ. Tag: **gold_issue**. Ambiguous date: the answer filtered on completion date (when parts are used), the gold on opening date. Both readings are defensible.
- `fs-024` (fieldservice, trial 1): wrong — rows differ. Tag: **gold_issue**. Ambiguous date: 'did work for last month' was read as completed last month; the gold uses opened last month.
- `fs-025` (fieldservice, trial 1): refused — Average days to complete needs the elapsed time between work_orders.opened_at and work_orders.completed_at, and the registry has no way to compute a difference between two date fields. Metrics aggregate a single field only.. Tag: **grammar_gap**. Needs the difference between two dates (opened to completed). Refused correctly.
- `fs-028` (fieldservice, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs a ratio of two counts. The model returned counts per status instead of refusing: a wrong answer, not a refusal.
- `fs-030` (fieldservice, trial 1): refused — Parts revenue needs quantity times unit_price per line, and the registry has no computed line-revenue field. A metric aggregates a single field, so summing unit_price or quantity alone would give a different number.. Tag: **grammar_gap**. Needs a computed value (quantity times unit price). Refused correctly.
- `fs-035` (fieldservice, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs two date fields in one monthly series. The model counted completions among the orders opened each month instead of refusing: a wrong answer.
- `fs-037` (fieldservice, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs a distinct count of months in HAVING. The model returned per-technician monthly counts instead of refusing: a wrong answer.
- `fs-039` (fieldservice, trial 1): refused — The question needs a 2-day elapsed-time test between completed_at and opened_at and a ratio of two counts; the intent language supports neither a date arithmetic comparison nor a share metric.. Tag: **grammar_gap**. Needs date arithmetic and a ratio. Refused correctly.
- `fs-041` (fieldservice, trial 1): refused — The question needs two different row sets at once: a sum over unpaid and overdue invoices, and a count of overdue invoices only per customer. Filters apply to every row and having applies to whole groups, so the registry cannot express a conditional count alongside the sum.. Tag: **grammar_gap**. Needs a conditional count beside a sum. Refused correctly.
- `fs-042` (fieldservice, trial 1): refused — Finding sites with no work orders in a window needs an anti-join (sites with no matching work_orders rows), which this intent format cannot express. Filters on work_orders fields only return sites that do have matching rows.. Tag: **grammar_gap**. Needs an anti-join (sites with no work orders). Refused correctly.
- `spider:919` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:920` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:922` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:923` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:924` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:925` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:927` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:928` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them.
- `spider:929` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them.
- `spider:937` (spider_dog_kennels, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold ranks owners by number of treatments; the question asks who spent the most. The answer sums cost.
- `spider:942` (spider_dog_kennels, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold counts treatments; the question asks for at least two types of treatment. The answer counts distinct types.
- `spider:944` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:945` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:951` (spider_dog_kennels, trial 1): wrong — rows differ. Tag: **gold_issue**. The answer returns the size description column; the gold returns the size code column. Both answer the question.
- `spider:954` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:955` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:961` (spider_dog_kennels, trial 1): wrong — rows differ. Tag: **gold_issue**. Ambiguous: youngest by the age column (gold) or by date of birth (the answer). The two columns disagree in this data.
- `spider:972` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them.
- `spider:973` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them.
- `spider:974` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:978` (spider_dog_kennels, trial 1): refused — refused (fan_out). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:987` (spider_dog_kennels, trial 1): refused — refused (aggregate_type). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic.
- `spider:994` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them.
- `spider:995` (spider_dog_kennels, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them.
- `spider:998` (spider_dog_kennels, trial 1): wrong — rows differ. Tag: **grammar_gap**. The gold needs DISTINCT rows; row lists in the intent grammar cannot ask for distinct rows.
- `spider:999` (spider_dog_kennels, trial 1): wrong — rows differ. Tag: **grammar_gap**. Same as spider:998: needs DISTINCT rows.
- `spider:101` (spider_car_1, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs a subquery for the earliest year. The model returned all cars sorted by year instead of refusing: a wrong answer.
- `spider:111` (spider_car_1, trial 1): refused — refused (unanswerable). Tag: **misread**. The model looked for the car in the wrong field's allowed values and refused an answerable question.
- `spider:117` (spider_car_1, trial 1): refused — refused (aggregate_type). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic.
- `spider:126` (spider_car_1, trial 1): refused — refused (operator_type). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic.
- `spider:135` (spider_car_1, trial 1): refused — refused (aggregate_type). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic.
- `spider:136` (spider_car_1, trial 1): refused — refused (aggregate_type). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic.
- `spider:150` (spider_car_1, trial 1): refused — refused (fan_out, unknown_metric). Tag: **misread**. The question is answerable by grouping model_list by maker. The model kept the base on car_makers, hit fan_out twice and gave up.
- `spider:152` (spider_car_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: car_names.model references model_list.model, which is not a primary key, so registry init skips the link and the tables cannot be joined.
- `spider:159` (spider_car_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:160` (spider_car_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:167` (spider_car_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:168` (spider_car_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:170` (spider_car_1, trial 1): refused — refused (aggregate_type). Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic.
- `spider:171` (spider_car_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: car_names.model references model_list.model, which is not a primary key, so registry init skips the link and the tables cannot be joined.
- `spider:172` (spider_car_1, trial 1): wrong — rows differ. Tag: **misread**. With no join path to the maker, the model filtered on the model name instead of refusing, and added a count column: a wrong answer.
- `spider:175` (spider_car_1, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs an INTERSECT of two conditions. The model answered only the first: a wrong answer.
- `spider:178` (spider_car_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: car_names.model references model_list.model, which is not a primary key, so registry init skips the link and the tables cannot be joined.
- `spider:198` (spider_flight_2, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing.
- `spider:207` (spider_flight_2, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:208` (spider_flight_2, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:209` (spider_flight_2, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:210` (spider_flight_2, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:214` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:215` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:216` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:217` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:218` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:219` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:220` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:224` (spider_flight_2, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing.
- `spider:226` (spider_flight_2, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing.
- `spider:228` (spider_flight_2, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing.
- `spider:229` (spider_flight_2, trial 1): wrong — rows differ. Tag: **misread**. With no link to airlines, the model returned an airline id and count instead of refusing: a wrong answer.
- `spider:230` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:231` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:233` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:239` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:240` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:245` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:246` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines (the column is not named like airlines' key), so airline names cannot be reached.
- `spider:251` (spider_flight_2, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:252` (spider_flight_2, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:254` (spider_flight_2, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:255` (spider_flight_2, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:257` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:258` (spider_flight_2, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:439` (spider_wta_1, trial 1): wrong — rows differ. Tag: **misread**. 'Highest rank' means rank 1; the model took the maximum rank number.
- `spider:451` (spider_wta_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:452` (spider_wta_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:463` (spider_wta_1, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold reads rank points from an unaggregated column in a GROUP BY (SQLite returns an arbitrary row). The answer's maximum is a defined value.
- `spider:464` (spider_wta_1, trial 1): wrong — rows differ. Tag: **gold_issue**. Same gold pattern as spider:463: rank points from an unaggregated column.
- `spider:479` (spider_wta_1, trial 1): wrong — rows differ. Tag: **builder_bug**. Registry init typed ranking_date as a date (its declared type), but it holds eight-digit integers (YYYYMMDD). The day grain then returns NULL. Init should check the values, not just the declaration.
- `spider:488` (spider_wta_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:885` (spider_network_1, trial 1): refused — refused (ambiguous_path, invalid_order_by). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:886` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:887` (spider_network_1, trial 1): wrong — ambiguous_path. Tag: **misread**. After the validator refused the ambiguous join, the model answered with student ids instead of names: a wrong answer.
- `spider:889` (spider_network_1, trial 1): refused — refused (ambiguous_path, invalid_order_by). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:890` (spider_network_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:891` (spider_network_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:892` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:893` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:894` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:896` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:897` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:898` (spider_network_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:899` (spider_network_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:900` (spider_network_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:904` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:905` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:906` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:907` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:908` (spider_network_1, trial 1): refused — refused (ambiguous_path, invalid_order_by). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:909` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:910` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:911` (spider_network_1, trial 1): refused — refused (ambiguous_path, invalid_order_by). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:912` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:913` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:914` (spider_network_1, trial 1): refused — refused (ambiguous_path). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so the validator refuses rather than guess.
- `spider:915` (spider_network_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.
- `spider:917` (spider_network_1, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation, anti-join or OR across an aggregate. The intent grammar has none of these.

## Where a baseline beat Ledgerline

- `fs-025` (fieldservice, trial 1): oneshot
- `fs-030` (fieldservice, trial 1): oneshot
- `fs-037` (fieldservice, trial 1): oneshot
- `fs-042` (fieldservice, trial 1): oneshot
- `spider:101` (spider_car_1, trial 1): oneshot
- `spider:111` (spider_car_1, trial 1): oneshot
- `spider:117` (spider_car_1, trial 1): oneshot
- `spider:135` (spider_car_1, trial 1): oneshot
- `spider:136` (spider_car_1, trial 1): oneshot
- `spider:150` (spider_car_1, trial 1): oneshot
- `spider:152` (spider_car_1, trial 1): oneshot
- `spider:171` (spider_car_1, trial 1): oneshot
- `spider:178` (spider_car_1, trial 1): oneshot
- `spider:919` (spider_dog_kennels, trial 1): oneshot
- `spider:922` (spider_dog_kennels, trial 1): oneshot
- `spider:923` (spider_dog_kennels, trial 1): oneshot
- `spider:924` (spider_dog_kennels, trial 1): oneshot
- `spider:927` (spider_dog_kennels, trial 1): oneshot
- `spider:928` (spider_dog_kennels, trial 1): oneshot
- `spider:929` (spider_dog_kennels, trial 1): oneshot
- `spider:972` (spider_dog_kennels, trial 1): oneshot
- `spider:973` (spider_dog_kennels, trial 1): oneshot
- `spider:974` (spider_dog_kennels, trial 1): oneshot
- `spider:978` (spider_dog_kennels, trial 1): oneshot
- `spider:987` (spider_dog_kennels, trial 1): oneshot
- `spider:994` (spider_dog_kennels, trial 1): oneshot
- `spider:995` (spider_dog_kennels, trial 1): oneshot
- `spider:207` (spider_flight_2, trial 1): oneshot
- `spider:208` (spider_flight_2, trial 1): oneshot
- `spider:209` (spider_flight_2, trial 1): oneshot
- `spider:210` (spider_flight_2, trial 1): oneshot
- `spider:214` (spider_flight_2, trial 1): oneshot
- `spider:215` (spider_flight_2, trial 1): oneshot
- `spider:216` (spider_flight_2, trial 1): oneshot
- `spider:217` (spider_flight_2, trial 1): oneshot
- `spider:218` (spider_flight_2, trial 1): oneshot
- `spider:219` (spider_flight_2, trial 1): oneshot
- `spider:220` (spider_flight_2, trial 1): oneshot
- `spider:224` (spider_flight_2, trial 1): oneshot
- `spider:233` (spider_flight_2, trial 1): oneshot
- `spider:239` (spider_flight_2, trial 1): oneshot
- `spider:240` (spider_flight_2, trial 1): oneshot
- `spider:245` (spider_flight_2, trial 1): oneshot
- `spider:246` (spider_flight_2, trial 1): oneshot
- `spider:251` (spider_flight_2, trial 1): oneshot
- `spider:252` (spider_flight_2, trial 1): oneshot
- `spider:254` (spider_flight_2, trial 1): oneshot
- `spider:255` (spider_flight_2, trial 1): oneshot
- `spider:257` (spider_flight_2, trial 1): oneshot
- `spider:258` (spider_flight_2, trial 1): oneshot
- `spider:886` (spider_network_1, trial 1): oneshot
- `spider:887` (spider_network_1, trial 1): oneshot
- `spider:889` (spider_network_1, trial 1): oneshot
- `spider:890` (spider_network_1, trial 1): oneshot
- `spider:891` (spider_network_1, trial 1): oneshot
- `spider:892` (spider_network_1, trial 1): oneshot
- `spider:893` (spider_network_1, trial 1): oneshot
- `spider:896` (spider_network_1, trial 1): oneshot
- `spider:897` (spider_network_1, trial 1): oneshot
- `spider:898` (spider_network_1, trial 1): oneshot
- `spider:899` (spider_network_1, trial 1): oneshot
- `spider:900` (spider_network_1, trial 1): oneshot
- `spider:908` (spider_network_1, trial 1): oneshot
- `spider:909` (spider_network_1, trial 1): oneshot
- `spider:910` (spider_network_1, trial 1): oneshot
- `spider:911` (spider_network_1, trial 1): oneshot
- `spider:912` (spider_network_1, trial 1): oneshot
- `spider:913` (spider_network_1, trial 1): oneshot
- `spider:914` (spider_network_1, trial 1): oneshot
- `spider:915` (spider_network_1, trial 1): oneshot
- `spider:917` (spider_network_1, trial 1): oneshot
- `spider:439` (spider_wta_1, trial 1): oneshot
- `spider:451` (spider_wta_1, trial 1): oneshot
- `spider:463` (spider_wta_1, trial 1): oneshot
- `spider:479` (spider_wta_1, trial 1): oneshot
- `spider:488` (spider_wta_1, trial 1): oneshot

## Spider registries (generated by `registry init`, unedited, draft)

- spider_car_1: `bfafa604590eb78ac55d142c41ebbbdf52308f2b0b98baded2aa8868d7309ca2`
- spider_dog_kennels: `ba7277f7739fd820d7ec8f4cfda282af060e5d4aa09828dcca20d512683bde78`
- spider_flight_2: `e69b8206b5403470249e458ce75b56ba6e3421c53b73d982f53e2fbe1646c940`
- spider_network_1: `b9991de76b27c3ecc644274d209d7c543c7c27dcd2ec7298e7ab729212639d4b`
- spider_wta_1: `afc40c0f94f040485945f79fb21fafab91fd69e9278211a15b94442190f7f54b`
