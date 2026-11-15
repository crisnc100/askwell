# Eval report `v03-spider-seen`

- sql_agent baseline not run: needs a live model (multi-step tool calls can't be honestly simulated in one pass).

Gold: `spider_ids.json`.

Status: complete. Spend: $0.1233.
Rates show the value, the Wilson 95% interval, and the counts. Trials are pooled.

| Schema | System | Model | Trials | Coverage | Exec. accuracy | Acc. given attempted | False refusals | Wrong given answered | Refusal recall | Exec. errors | Gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| spider_car_1 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 88.0% [76-94] (44/50) | 60.0% [46-72] (30/50) | 68.2% [53-80] (30/44) | 12.0% [6-24] (6/50) | 31.8% [20-47] (14/44) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_dog_kennels | ledgerline | anthropic:claude-haiku-5-5 | 1 | 70.0% [56-81] (35/50) | 50.0% [37-63] (25/50) | 71.4% [55-84] (25/35) | 30.0% [19-44] (15/50) | 28.6% [16-45] (10/35) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_flight_2 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 96.0% [87-99] (48/50) | 88.0% [76-94] (44/50) | 91.7% [80-97] (44/48) | 4.0% [1-13] (2/50) | 8.3% [3-20] (4/48) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_network_1 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 98.0% [90-100] (49/50) | 92.0% [81-97] (46/50) | 93.9% [83-98] (46/49) | 2.0% [0-10] (1/50) | 6.1% [2-17] (3/49) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |
| spider_wta_1 | ledgerline | anthropic:claude-haiku-5-5 | 1 | 98.0% [90-100] (49/50) | 86.0% [74-93] (43/50) | 87.8% [76-94] (43/49) | 2.0% [0-10] (1/50) | 12.2% [6-24] (6/49) | n/a | 0.0% [0-7] (0/50) | spider_ids.json |

## Ledgerline misses

- `spider:95` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before: right. After: refused.
- `spider:96` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before: right. After: refused.
- `spider:117` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before and after: refused.
- `spider:126` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before and after: refused.
- `spider:132` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before: right. After: refused.
- `spider:135` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before and after: refused.
- `spider:136` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before and after: refused.
- `spider:150` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **misread**. The model returned the maker's short code column, not the full name the question asks for. Before: a wrong answer. After: right.
- `spider:152` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:154` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:155` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:159` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:160` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:165` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before: right. After: refused.
- `spider:167` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:168` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:170` (spider_car_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **validator_false_reject**. The column is declared TEXT but holds numbers. Registry init keeps the declared type, so the validator rejects the arithmetic. Before and after: refused.
- `spider:171` (spider_car_1, spider_ids.json, trial 1): refused — refused (has_link). Tag: **grammar_gap**. Registry gap: registry init found no link between these tables, so the needed join does not exist. Before and after: refused.
- `spider:175` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a set operation. The intent grammar has none. Before: a wrong answer. After: refused.
- `spider:178` (spider_car_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:919` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:922` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:923` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:924` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs an anti-join or subquery to keep dogs with no treatments. The intent grammar has neither. Before: a wrong answer. After: refused.
- `spider:925` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:927` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:928` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them. Before and after: refused.
- `spider:929` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them. Before and after: refused.
- `spider:937` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold ranks owners by number of treatments; the question asks who spent the most. The v0.2 answer sums cost. Before: refused. After: a wrong answer.
- `spider:942` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold counts treatments; the question asks for at least two types of treatment. The answer counts distinct types. Before and after: a wrong answer.
- `spider:944` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:945` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:954` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:955` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:961` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Ambiguous: youngest by the age column (gold) or by date of birth (the answer). The two columns disagree in this data. Before and after: a wrong answer.
- `spider:972` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them. Before and after: refused.
- `spider:973` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them. Before and after: refused.
- `spider:976` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **untriaged**
- `spider:984` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:985` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:988` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:994` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them. Before and after: refused.
- `spider:995` (spider_dog_kennels, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **validator_false_reject**. By design: registry init hides email and phone-like fields, so the question cannot be answered. Spider's gold returns them. Before and after: refused.
- `spider:998` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. The gold needs DISTINCT rows; row lists in the intent grammar cannot ask for distinct rows. Before and after: a wrong answer.
- `spider:999` (spider_dog_kennels, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Same as spider:998: needs DISTINCT rows. Before and after: a wrong answer.
- `spider:198` (spider_flight_2, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing. Before and after: a wrong answer.
- `spider:226` (spider_flight_2, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing. Before: a wrong answer. After: refused.
- `spider:228` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **gold_issue**. The gold returns no rows: airport codes and cities are stored with trailing spaces, so the gold's equality joins and filters match nothing. Before: a wrong answer. After: refused.
- `spider:229` (spider_flight_2, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines, so airline names cannot be reached. Before: a wrong answer. After: refused.
- `spider:230` (spider_flight_2, spider_ids.json, trial 1): wrong — rows differ. Tag: **grammar_gap**. Registry gap: flights.airline has no declared or inferred link to airlines, so airline names cannot be reached. Before: a wrong answer. After: refused.
- `spider:238` (spider_flight_2, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before: right. After: refused.
- `spider:878` (spider_network_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:879` (spider_network_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:896` (spider_network_1, spider_ids.json, trial 1): wrong — ambiguous_path. Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:911` (spider_network_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Two foreign keys link the same pair of tables. The intent has no way to say which join to use, so it refuses rather than guess. Before and after: refused.
- `spider:439` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:447` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:452` (spider_wta_1, spider_ids.json, trial 1): refused — refused (unanswerable). Tag: **grammar_gap**. Needs a subquery, set operation or anti-join. The intent grammar has none of these. Before and after: refused.
- `spider:459` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **untriaged**
- `spider:463` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold reads rank points from an unaggregated column in a GROUP BY (SQLite returns an arbitrary row). The answer's maximum is a defined value. Before and after: a wrong answer.
- `spider:464` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. Same gold pattern as spider:463: rank points from an unaggregated column. Before and after: a wrong answer.
- `spider:470` (spider_wta_1, spider_ids.json, trial 1): wrong — rows differ. Tag: **gold_issue**. The gold's rows are cut by the row cap, and the answer's sort keeps a different set at the cut. Before: a wrong answer. After: right.

## Where a baseline beat Ledgerline

None.

## Spider registries (generated by `registry init`, unedited, draft)

- spider_car_1: `e10d9d276261c6b7afb033a4783aa5dd25e2fb024aad8e0153dadde00c301a82`
- spider_dog_kennels: `2af18fdfbece07cadab7e0ed61de67cc3b3a357a5ba84c5fbe2bf5ea2dcace2d`
- spider_flight_2: `1520c628da45d417a442672a273b62eb761a744b0b829500c57321ab2b1bdf37`
- spider_network_1: `60d51b4c9b99b72421e7f024dd0a7ad16e4eb4f02df299945e2e7228fe0213cb`
- spider_wta_1: `807a938123c3f5467290fcab18b29cc9d79c341a9dab73eff6d096b5cb43345a`
