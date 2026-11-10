**Verdict:** P5 rev 3 has four contradictions that make the build unverifiable as written, before any edge cases. Fix these in the plan first.

1. **Ask is a dead end for anyone's own data.** Free text is live-only, and the 2026-11-09 decision says there is no key. Replay is keyed by a hash of the messages, which include the registry view, so any new workspace is a guaranteed replay miss. The plan promises a stranger "asks questions and sees the SQL" and then makes that impossible. The plan must say what the Ask page does without a key, or reinstate a key with a spend cap for the beta.
2. **Hosting is undecided but the threat model assumes the public internet.** context.md still lists CSV upload, multi-tenancy and deployment as out of scope. If this runs on localhost, the 7-day expiry, rate limits and 128-bit ids solve nothing. If it is hosted, deployment is in scope, and so are disk quotas, model-spend caps and a privacy notice, none of which appear. Pick one and update context.md.
3. **Relative dates resolve against a fake clock.** Reference time is the fixed config value, default mid-2026, used by relative-date resolution. A stranger asking "orders last month" on their own data gets June 2026. BYOD needs wall-clock now, with a time zone, while evals keep the pin. Nothing in the plan separates them.
4. **The PR shape breaks the working agreement.** PR3 now holds an unauthenticated upload surface, a workspace lifecycle, a registry editor, a new results page, three new domains with generators and gold, three simulated eval runs, and all the docs. The upload path is the most security-relevant code in the project and the plan does not route it to the separate security review. The rev needs its own "N PRs" line.

## Gaps by area

**Privacy and data handling**
- `ask_log` stores the intent JSON, which carries literal filter values typed by the user. For BYOD that is user data copied into the app DB, and "Delete my data" does not mention it. Delete must cover ask_log rows, raw uploaded CSVs if kept, and SQLite sidecar files like WAL and journal.
- Category values go to the model by default. Auto-hide matches column names only, so a `notes`, `diagnosis` or `reason` column with few distinct values is sent to a third party. For BYOD the safer default is opt-in per field, or at least a visible warning on Confirm. The "isn't name-like" heuristic is undefined.
- The workspace id is a bearer token. If it lives in the URL path it lands in uvicorn access logs, browser history and Referer headers. The plan should say where it travels and set `Referrer-Policy`.
- No privacy statement anywhere in the pages. A no-auth beta with 7-day retention that sends schema and category values to a model provider needs one line telling people not to upload personal data.

**Abuse**
- Rate limits are named but never defined, and no acceptance criterion tests them. Per-IP behind a proxy needs an `X-Forwarded-For` trust decision. Per-workspace adds little once per-IP exists.
- No disk quota. Ten files of ten MB per workspace, unlimited workspaces, and a sweep every seven days means the disk fills in minutes. Need a global byte cap and a per-IP live-workspace cap.
- No model-spend cap on the API. The budget guard covers eval runs. A hosted Ask page spends Cristian's money per stranger question, so it needs a global daily cap and a kill switch.
- Size limits must be enforced server-side on the stream, not on the client and not after Starlette buffers the body. A CSV bomb can also be one row with a million columns or one ten MB cell. Add column-count, row-count and cell-size caps. SQLite refuses more than two thousand columns anyway, with an ugly error.
- Validation messages, filenames, header names and result cells are all user-supplied strings rendered in the browser. Nothing in L13 or L17 catches `innerHTML` XSS. Add an escaping test.
- Workspace ids must come from `secrets`, and the isolation test should try a crafted id with path separators, not just B's valid id.

**Data formats the Check will meet on day one**
- UTF-8 BOM, so the first header becomes `\ufeffid` and the ID check fails with a baffling message. CRLF, trailing delimiters, quoted embedded newlines, and `;` delimiters from European Excel. The plan says "encoding" and "ragged rows" and nothing else.
- Null encoding is undefined. Blank, `NULL`, `NA`, `N/A` and `-` all appear in real exports. Without a rule, every column with blanks fails "type consistency", or nulls load as the string `NA`.
- Excel damage: thousands separators, currency symbols, percentages, `1.2E+11` for long IDs, and leading zeros. SQLite INTEGER affinity turns `00123` into `123`, so ID and zip columns need text affinity when any value has a leading zero.
- FK type mismatch: `customer_id` inferred as integer in one file and text in another joins to zero rows silently. The orphan check must compare with the same affinity the loader uses, and store FKs with the referenced key's type.
- "ISO dates" is ambiguous about datetimes, time zones, and mixed date and datetime columns. State which are accepted and what the grain compiler does with each.
- The naming rule `<table>_id` with table `customers` means `customers_id`, which nobody writes. Say whether the ID column is `id` or `<singular>_id`, how singularisation works, and what happens to link tables with two FKs and no ID of their own. Those violate "one ID column per table" and are the most common table in retail data.
- Filenames become table names. `Customers (final).csv`, `2024_orders.csv`, `orders.CSV` and `Orders.csv` beside `orders.csv` all need slug rules and collision detection, which the check list lacks. Same for headers that collide after slugging, like `Order Date` and `order_date`.
- Fifty thousand bad rows produce fifty thousand messages. Cap and summarise per file.
- Check and load can diverge. A file can pass every listed check and still fail SQLite insert, and "all-or-nothing" then means a crash with no fix message. A test should prove that anything passing Check loads.

**UX dead ends**
- One failing file among ten blocks loading. The plan never says whether the user re-uploads one file or all ten, or whether same-name upload replaces.
- Lose the workspace id and the data is orphaned until the sweep, with no way to use "Delete my data". Show the URL to bookmark and the expiry date. Also define expiry as from creation or last activity.
- The state machine is missing. Can you upload after Confirm, and does a re-check wipe registry edits? Can you Ask before Confirm, or does `allow_draft` block with a developer error?
- Refusal reasons are validator error codes like `fan_out` and `ambiguous_path`. The Ask page needs plain-English mappings or the "clear" product promise fails on the first join.
- A replay miss in the API must become a friendly "this demo answers the example questions only", not a 500.
- Per-value hiding of category values is undefined. If hidden values are also removed from `allowed_values`, the validator refuses a user who types the value themselves. If not, the prompt and validator disagree. Pick one and write it down.
- The Confirm preview must use the same renderer and truncation as the interpret prompt, or it shows the user something the model never sees.

**Server plumbing the plan calls "the same pipeline"**
- `config/schemas.yaml` is static. Workspaces need a second, dynamic schema source, a per-workspace executor and per-workspace registry, which touches reviewed P3 code.
- The sweep needs an owner. An in-process scheduler duplicates per uvicorn worker and may want a new dependency, which needs a callback. A `ledgerline sweep` command on cron is simpler. It must also tolerate deleting a file while a query holds it open.
- Compose still carries Postgres for fieldservice while the product data is SQLite. Two engines in one deploy for a solo beta is worth questioning.

## Where the acceptance bar lets a bad build through

- **L16** tests one minimal bad file per rule and nothing messy-but-valid. Add a fixture corpus with BOM, CRLF, quoted commas, blanks and leading zeros that must load and round-trip values exactly.
- **L17** covers the happy path and one bad file. It never proves a Confirm edit took effect. Rename a field, hide another, then ask and check the exported prompt.
- **L18** omits ask_log and raw uploads from Delete, and the isolation test as written passes trivially.
- **L20** has no stated test method and no schema for the report JSON, so a report format change breaks the page silently.
- **L21** "under 2 minutes of reading" cannot be checked. Use a word cap.
- **Missing entirely:** server-side size enforcement, rate limits, disk cap, XSS escaping, coverage floor for the new validator and workspace modules, and the gold rules for the three new domains. L8's git-order check and the per-category minimums do not extend to them, and "≥ 25" has no category split.

## Over-building for a solo free beta

- **Three new synthetic domains** is the biggest item and the weakest evidence. They are schemas the author tunes, so they do not support the "works on schemas it was not tuned on" claim, which Spider already carries. Each is roughly P1.2 plus P1.5 again, and simulating the SQL agent trajectories with a subagent for them is the least credible number on the page. Drop them, or run Ledgerline only on one.
- **The registry editor** with rename, aliases, descriptions and per-value hiding is a form-builder project. Hide and unhide plus a description field covers the product promise. Aliases can wait.
- **Drag-and-drop**, a downloadable template and a sample dataset: a file input and the sample are enough.
- **Per-workspace rate limits** on top of per-IP add a second limiter for no threat it alone stops.
- **An in-process scheduler** when a CLI command and one cron line do the job.
- **Playwright across four pages** when the risky code is the CSV check and the loader, which unit tests cover far cheaper.

Resolve the four contradictions at the top, cut the three domains, and the remaining scope is a defensible single feature: upload, check, confirm, ask on SQLite, plus a results page read from JSON.
