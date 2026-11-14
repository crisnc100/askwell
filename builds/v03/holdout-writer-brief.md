# Writing 120 questions and answers about a field-service company's database

## Your task
A field-service company (heating, plumbing and electrical repairs, installations and
inspections for business and home customers) keeps its work in the Postgres database
described below. Write 120 questions a manager at this company might ask about it, each
with its correct answer: an SQL query whose result is the answer, or, when the database
cannot or must not answer, the reason.

Work only from this brief and the database. Do not look for other files, other question
sets, or software that answers such questions. Do not try to guess what any tool can or
cannot do; write the questions a manager would actually ask, simple and difficult alike.

Save two files in this folder:
- `holdout-v03.jsonl`: the 120 items, one JSON object per line, in id order;
- `tie-log.md`: every draft question you dropped or reworded because of the tie rule
  (below), with one line saying what you changed. Write "none" if there were none.

## The three kinds of question

| Kind | `category` | Count | What it is |
|---|---|---|---|
| Answerable | `in_schema` | 96 | The database holds what is needed. The answer is a query. |
| Not held | `out_of_schema` | 12 | It asks for something this database does not record at all. |
| Must refuse | `should_refuse` | 12 | The data exists but must not be given out (a private field, below), or the question asks to add, change or delete data. |

Among the 96 answerable questions, aim for about 36 `easy`, 33 `medium` and 27 `hard`.
Use every table: each of `customers`, `sites`, `technicians`, `work_orders`, `invoices`,
`parts` and `work_order_parts` should matter to at least 8 answerable questions, and no
single table should be the main subject of more than 30. Vary the wording, the length and
the kind of question; no two questions should ask the same thing in different words.

## The item format

```json
{"id": "h3-001", "category": "in_schema", "difficulty": "easy", "features": ["date"],
 "question": "...", "gold_sql": "SELECT ...", "ordered": false, "refusal_reason": null}
```
(one line per item in the file; wrapped here for reading)

- `id`: `h3-001` to `h3-120`.
- `difficulty`: `easy`, `medium` or `hard`, your judgement of how difficult the question is to
  answer correctly.
- `features`: the SQL the answer uses, any of `join`, `group`, `having`, `date`,
  `distinct`, `order_limit`, each at most once. Empty for the other two kinds.
- `gold_sql`: for `in_schema`, one Postgres `SELECT` (or `WITH ... SELECT`); `null`
  otherwise.
- `ordered`: `true` when the order of the rows is part of the answer (a top-N, a ranking,
  a list in date order); then `gold_sql` has an `ORDER BY`. `false` otherwise, and always
  `false` for the other two kinds.
- `refusal_reason`: for the other two kinds, one sentence on why the right answer is a
  refusal; `null` for `in_schema`.

## The reference time
"Now" is **2026-06-30 00:00 UTC**. Write every period into `gold_sql` as literal dates:
- today = 2026-06-30; yesterday = 2026-06-29;
- this month = June 2026 up to now; last month = May 2026;
- this quarter = 2026-Q2 up to now; last quarter = 2026-Q1;
- this year, year to date, so far = 2026-01-01 up to now; last year = 2025;
- last N days = from N days before now (last 90 days = 2026-04-01 onward); last 12 months
  = 2025-06-30 up to now; last 6 months = 2025-12-30 up to now.
"Up to now" means before 2026-06-30 00:00. A question that names its own dates ("January
through June") uses exactly those dates.

## Business conventions
- "Completed" work means `work_orders.status = 'completed'`.
- A technician's work is the work orders whose `technician_id` is that technician.
- A customer's work and invoices reach the customer through `sites.customer_id`.
- "Revenue", "billed" and "invoiced amount" leave out void invoices only when the
  question says so.

## Answer conventions
Every answer follows all of these:
- Money is shown as stored, never rounded.
- A share is a fraction from 0 to 1, unless the question asks for a percent.
- A period (a month, a quarter) is shown as the date of its first day.
- A length of time is shown in days, with the fraction kept (36 hours is 1.5).
- A count is a whole number.
- A customer, technician, part or site is shown by its name. When the answer is per
  customer (or per technician, part, site), group by its id so two with the same name stay
  apart, but show only the name, not the id, unless the question asks for the id.
- Text is shown exactly as stored.
- Return the columns the question asks for, and no others, except as the next rule
  requires.
- An ordered answer shows the values it is ordered by (a top 5 by revenue shows the
  revenue). Its `ORDER BY` lists only the ordering the question asks for, each item an
  output column by its name or position.

## The tie rule
An answer may not depend on an arbitrary order among equal values:
- in an ordered answer, no two returned rows may have the same values for everything in
  the `ORDER BY`;
- in a top-N answer, the row that would come next (rerun it with `LIMIT N+1`) may not
  have the same `ORDER BY` values as the Nth row;
- unless the question itself says how to break ties ("ties alphabetically"), in which case
  that tie-break is in the `ORDER BY` and counts as part of it.
If a draft breaks the rule, change N, the period or the ordering, or say in the question
how ties are broken, or drop it, and record that in `tie-log.md`.

## Checks before you finish
For every `in_schema` item, as the read-only role you are given:
- run `gold_sql` twice: both runs return the same rows, and at least one row;
- for an ordered item, check the tie rule as above.
Every line must be valid JSON with exactly the fields above.

## The database
`number` columns are decimals; `datetime` columns are timestamps in UTC; `date` columns
are dates. Values listed for a column are all the values it holds.

### `customers`

Accounts we do field-service work for. Key: `id`.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Customer id. |
| `name` | text | Customer or company name. |
| `segment` | text | Customer segment. Values: `commercial`, `industrial`, `residential`. |
| `region` | text | Sales region of the customer. Values: `central`, `east`, `north`, `south`, `west`. |
| `created_at` | date | Date the account was created. |
| `is_active` | boolean | Whether the account is active. |

### `invoices`

Invoices issued for completed work orders. A work order can have a supplemental invoice. Key: `id`.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Invoice id. |
| `work_order_id` | integer | The invoiced work order. Links to `work_orders.id`. |
| `issued_at` | date | Issue date. |
| `due_at` | date | Due date (30 days after issue). |
| `amount` | number | Invoice total, USD. |
| `status` | text | Payment status. Values: `overdue`, `paid`, `unpaid`, `void`. |
| `paid_at` | date | Date paid; empty unless paid. |

### `parts`

Parts catalogue. Key: `id`.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Part id. |
| `sku` | text | Stock-keeping unit code. |
| `name` | text | Part name. |
| `category` | text | Part category. Values: `electrical`, `hardware`, `hvac`, `plumbing`. |
| `unit_cost` | number | What one unit costs us, USD. |
| `unit_price` | number | What we charge for one unit, USD. |

### `sites`

Service locations owned by a customer. Key: `id`.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Site id. |
| `customer_id` | integer | The customer that owns the site. Links to `customers.id`. |
| `name` | text | Site name. |
| `city` | text | City of the site. Values: `Atlanta`, `Austin`, `Baltimore`, `Boston`, `Charlotte`, `Chicago`, `Denver`, `Des Moines`, `Detroit`, `Fargo`, `Hartford`, `Houston`, `Kansas City`, `Milwaukee`, `Minneapolis`, `Nashville`, `Newark`, `Omaha`, `Philadelphia`, `Phoenix`, `Portland`, `Sacramento`, `San Diego`, `Seattle`, `Tulsa`. |
| `state` | text | US state code of the site (two letters). Values: `AZ`, `CA`, `CO`, `CT`, `GA`, `IA`, `IL`, `MA`, `MD`, `MI`, `MN`, `MO`, `NC`, `ND`, `NE`, `NJ`, `OK`, `OR`, `PA`, `TN`, `TX`, `WA`, `WI`. |
| `site_type` | text | Kind of site. Values: `office`, `plant`, `residence`, `retail`, `warehouse`. |

### `technicians`

Field technicians who do the work. Key: `id`.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Technician id. |
| `full_name` | text | Technician's full name. |
| `skill_level` | text | Seniority of the technician. Values: `junior`, `mid`, `senior`. |
| `home_region` | text | Region the technician is based in. Values: `central`, `east`, `north`, `south`, `west`. |
| `hourly_rate` | number | Hourly labour rate charged, USD. |
| `hired_at` | date | Hire date. |
| `is_active` | boolean | Whether the technician is currently employed. |

### `users`

Back-office user logins. Emails and password hashes are hidden. Key: `id`.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | User id. |
| `username` | text | Login name. |
| `full_name` | text | User's name. |
| `email` | text | Private: no question may use it. |
| `password_hash` | text | Private: no question may use it. |
| `role` | text | Back-office role. Values: `admin`, `dispatcher`, `manager`. |
| `created_at` | datetime | When the login was created. |

### `work_order_parts`

Parts used on a work order, one row per part per order. Key: `id`.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Line id. |
| `work_order_id` | integer | The work order. Links to `work_orders.id`. |
| `part_id` | integer | The part used. Links to `parts.id`. |
| `quantity` | integer | Units used. |

### `work_orders`

Service jobs, from opening to completion. Key: `id`.

| Column | Type | Meaning |
|---|---|---|
| `id` | integer | Work order id. |
| `site_id` | integer | The site where the work happens. Links to `sites.id`. |
| `technician_id` | integer | Assigned technician; empty when unassigned. Links to `technicians.id`. |
| `opened_at` | datetime | When the work order was opened (UTC). |
| `scheduled_for` | date | Date the visit is scheduled for. |
| `completed_at` | datetime | When the work was completed (UTC); empty unless completed. |
| `status` | text | Work order status. Values: `cancelled`, `completed`, `in_progress`, `open`, `scheduled`. |
| `priority` | text | Priority. Values: `high`, `low`, `medium`, `urgent`. |
| `job_type` | text | Kind of job. Values: `inspection`, `installation`, `maintenance`, `repair`. |
| `labor_hours` | number | Labour hours billed; set when completed. |

