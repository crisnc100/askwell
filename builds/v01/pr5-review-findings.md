### 2026-11-11-23-46-38-fe438a f1 MEDIUM ledgerline/llm/gateway.py:202
Response-loss retries can bypass spend limits. A read timeout or dropped response can occur after the provider completed and billed the request. AnthropicTransport retries these errors under the original reservation, while the gateway charges only the final response or refunds everything when retries fail. Reproduction showed two HTTP attempts sharing one reservation; five exhausted timeouts left recorded daily spend at zero.
Trigger: A live Anthropic ask loses its response after the provider processes it, causing APIConnectionError/APITimeoutError and a retry.
Suggestion: Retain worst-case charges for ambiguous post-send failures and precheck/reserve each retry separately. Refund only failures known to be unbilled.

### 2026-11-11-23-46-38-fe438a f2 MEDIUM ledgerline/pipeline/service.py:126
Anthropic-only startup still depends on OpenRouter availability. This unconditional fetch raises before the provider router or kill switch is installed. Mocking an OpenRouter connection failure prevented build_gateway from returning with the Anthropic default, both with live answers enabled and disabled. During an OpenRouter outage, the beta therefore cannot start or provide its healthz probe and plain kill-switch 503.
Trigger: Start the live beta with the default Anthropic model while OpenRouter's /models endpoint times out or returns an error.
Suggestion: Fetch OpenRouter prices lazily when an OpenRouter model needs pricing; allow Anthropic-only and disabled deployments to initialize without that request.

### 2026-11-11-23-46-38-fe438a f3 MEDIUM ledgerline/llm/spike.py:268
The spike gateway omits both new global controls. ledgerline spike uses this factory, so daily defaults to None and live_answers_off defaults to False regardless of configuration. Running the CLI path with mocked provider responses, LEDGERLINE_LIVE_ANSWERS_OFF=1 and a zero daily cap still made all five calls and reported spend.
Trigger: Run ledgerline spike with a valid OpenRouter key while the kill switch is enabled or the configured daily allowance is exhausted.
Suggestion: Pass the configured DailySpend and kill-switch value into the spike gateway, sharing the same spend database as other live calls.

### 2026-11-11-23-44-33-33d679 f1 MEDIUM ledgerline/invite.py:89
Header and cookie authentication bypass the invite-attempt limit. The limiter runs only in POST /invite; middleware checks unlimited credentials directly. Reproduced 25 incorrect header guesses from one address, followed by a successful login, without exhausting the ten-attempt allowance.
Trigger: Repeatedly request /schemas with incorrect X-Invite-Code headers or invite cookies instead of submitting POST /invite.
Suggestion: Apply a shared attempt limit to every credential-entry path while preserving ordinary authenticated browsing.

### 2026-11-11-23-44-33-33d679 f2 MEDIUM ledgerline/invite.py:111
Valid non-Latin-1 invite codes cause login to return 500. Configuration and validation accept UTF-8 codes, but writing the raw code into a cookie raises UnicodeEncodeError when Starlette encodes the response header. Reproduced with 招待コード: validation succeeds, login returns 500, and subsequent requests remain unauthorized.
Trigger: Configure LEDGERLINE_INVITE_CODES with a code containing characters outside Latin-1, then submit that valid code through the invite form.
Suggestion: Encode cookie credentials into an ASCII-safe representation and decode before comparison, or validate and reject unsupported configured codes at startup.

### 2026-11-11-23-44-33-33d679 s1 MEDIUM ledgerline/invite.py:89
The invite gate's brute-force limit does not cover the path that actually checks codes. The `_gate` middleware validates a code from the `ledgerline_invite` cookie or the `X-Invite-Code` header on every request and answers 401 or 200 with no attempt counting. Only `POST /invite` calls `attempts.allow(...)`. An unauthenticated client can therefore test unlimited codes per second with `GET /schemas` plus `X-Invite-Code: <guess>`, using the 200/401 as the oracle and never touching `/invite`. The module docstring's claim that wrong codes are rate limited per address is false for this path, and `test_wrong_codes_are_rate_limited` only exercises `POST /invite`. Harmed principal: the operator. A guessed code gives a stranger live model spend up to the daily cap, plus workspace creation and uploads up to the disk cap. How exploitable it is depends on code entropy, which nothing enforces or documents (`.env.beta.example` gives no guidance; the test codes are `alpha-123` style). Evidence: read `ledgerline/invite.py` lines 83-94 and 100-108 at HEAD.
Trigger: Any unauthenticated client of the hosted beta looping `curl -H 'X-Invite-Code: <guess>' https://<host>/schemas` (or setting the cookie directly); each request is a free guess with a 200/401 answer.
Suggestion: Count wrong presented codes in the middleware with the same per-address limiter. When a non-empty cookie or header value fails `is_valid`, call `attempts.allow(client_ip(request))` and return 429 once the window is full. Do not count requests that present no code. Delete the cookie on a wrong-cookie 401 so a visitor whose code was removed does not burn the limit on every asset request. Add a test that sends more than ATTEMPTS_PER_HOUR wrong `X-Invite-Code` values to `/schemas` and expects 429. Also state a minimum code strength in `.env.beta.example` (for example `python -c "import secrets; print(secrets.token_urlsafe(16))"`).

### 2026-11-11-23-44-33-33d679 s2 MEDIUM ledgerline/invite.py:102
`POST /invite` is open to unauthenticated callers and buffers the whole request body in memory (`await request.body()`) with no size cap, and it does so before the rate-limit check. The comment says the limit is checked before the code, but the body is read before the limit. Nothing in the app caps it, and the README's Caddyfile is a bare `reverse_proxy` with no `request_body` limit (unverified — that Caddy and uvicorn apply no default body limit is from memory, not checked this session). `compose.prod.yaml` sets no memory limit on the container. A stranger without an invite code can post a multi-gigabyte body, or several in parallel, and exhaust memory on the single beta host. That kills the app for invited users and resets the in-process rate limiters on restart. Every other body-reading route sits behind the gate, so this is the one unauthenticated way in. Harmed principals: the operator and invited users (availability).
Trigger: `curl -X POST --data-binary @multi-gigabyte-file https://<host>/invite` from any address, with no invite code needed; repeat in parallel.
Suggestion: Call `attempts.allow(...)` before reading anything. Then refuse a `Content-Length` above a small bound (for example 4 KB) with 413, and read the body through `request.stream()`, stopping once that bound is passed. A code is at most 200 characters. As defense in depth, add `request_body { max_size ... }` to the README's Caddyfile and a `mem_limit` to the `app` service.

### 2026-11-11-23-44-44-2369b3 f1 MEDIUM ledgerline/workspace/fields.py:239
A refused re-confirmation can change the active registry. If registry.yaml fits but edits.json does not, the second write raises DiskFullError after the registry has been replaced. The workspace remains confirmed, so subsequent questions use the refused changes while the Confirm page displays the old saved edits. An in-memory probe reproduced this inconsistent state.
Trigger: Re-confirm an existing workspace when remaining capacity accommodates the registry growth but not the subsequent edits growth.
Suggestion: Reserve capacity for the complete confirmation before replacing files, and preserve the previous registry, edits and state if any step fails.

### 2026-11-11-23-44-44-2369b3 f2 MEDIUM ledgerline/workspace/store.py:566
The upload timeout can leak a disk reservation. Cancelling the await does not stop the worker thread, which can reserve space without returning its size to `reserved`. Cleanup then releases only the previous amount. A probe with a reservation scan crossing the deadline left 262144 bytes reserved after the upload returned 408 and the worker finished; repeated occurrences eventually block uploads and Checks until restart.
Trigger: A chunked upload reaches its 120-second deadline while awaiting `_reserve_more`, such as when the disk-usage scan or capacity lock is slow.
Suggestion: Make reservation ownership cancellation-safe: wait for an outstanding reservation operation to finish and release its allocation before completing timeout cleanup.

### 2026-11-11-23-44-44-2369b3 s1 MEDIUM ledgerline/workspace/store.py:358
A visit is refused with 507 whenever disk usage plus reservations is above the cap, although the docstring says a same-size rewrite never fails on a full disk. `write_counted` calls `capacity.reserve(0)` for a zero-growth write, and `reserve` raises `DiskFullError` when `usage() + reserved + 0 > cap`. Every touch-open (`open` -> `locked` -> `save` -> `write_counted`) goes through it, so show, upload, check, fields, preview, confirm and ask all fail for every user. Usage can pass the cap because `audit.sqlite` growth from asks is never reserved (only store.py and fields.py call the capacity), and briefly because a committed upload or Check is counted in both usage and its reservation until release. Harmed: every beta user with a workspace. An invited user who fills the cap and then asks one question locks all workspaces until their own expire (7 days) or the operator steps in. At base, `Workspace.save()` was uncounted, so a full disk only refused uploads and Checks.
Trigger: Fill the disk to within a few KiB of the 2 GiB cap (uploads from a few addresses), then POST /api/workspace/ask once on a confirmed workspace: audit.sqlite grows uncounted, usage > cap, and every later GET /api/workspace (any user) returns 507. Also reached without an attacker when the disk is nearly full and an upload or Check commits while another request opens a workspace.
Suggestion: Skip the reservation when `growth == 0` (or return early from `Capacity.reserve` for `size <= 0`), so a rewrite that adds no bytes never consults the cap. Add a test that opens a workspace with usage above the cap.

### 2026-11-11-23-44-44-2369b3 s2 MEDIUM ledgerline/workspace/store.py:420
`create` leaves an orphan folder when the metadata write is refused for space, and nothing bounds how many. The workspace folder and `uploads/` are made first; `self.save` now reserves the metadata's bytes and raises `DiskFullError` on a full disk, with no cleanup. Orphans have no `meta.json`, so `live()` skips them and the 3-per-address limit never applies; POST /api/workspaces has no rate limit of its own; `disk_usage` counts file bytes only, so the folders are invisible to the cap; `sweep` removes them only after `idle_days`. Harmed: the operator and every user. Each failed create costs two directories on the /data volume shared with spend.sqlite and app.sqlite, and every request's `capacity.reserve` walks all of them under the global capacity lock, so a loop of creates slows the whole service. At base the save was uncounted, so create always succeeded and counted against the per-address limit.
Trigger: With the disk at the cap (free space smaller than one meta.json, about 250 bytes, or over the cap as in the previous finding), send POST /api/workspaces with a JSON body in a loop: each returns 507 and leaves root/<id>/uploads behind.
Suggestion: Wrap the three steps after `workspace.dir.mkdir` in try/except BaseException that `shutil.rmtree(workspace.dir, ignore_errors=True)` and re-raises, or reserve the metadata's bytes before creating the folder.

### 2026-11-11-23-43-40-aa5d7f f1 MEDIUM scripts/select_model.py:106
When every candidate fails a gate, the selector can choose a cheaper, weaker model instead of the best model required by ADR-004 step 7. Reproduced with two candidates failing latency: the cheaper model scored 32 correct versus 35, yet became the default while the report claimed it was the best.
Trigger: Run model selection when every candidate fails at least one gate and a cheaper candidate is within three correct answers of the best.
Suggestion: Set default to best when eligible is empty; add coverage where the cheaper failing candidate is only one to three correct answers behind.

### 2026-11-11-23-43-40-aa5d7f f2 MEDIUM scripts/select_model.py:93
Direct Anthropic model names are treated as distinct vendors. For anthropic:<id>, this returns the entire name, whereas an OpenRouter anthropic/<id> returns anthropic. Reproduced choose() selecting the same Anthropic model through another transport as the second model, despite an eligible Google candidate. This violates the different-vendor requirement.
Trigger: Select from a mixed-provider fieldservice run containing eligible direct Anthropic and OpenRouter Anthropic candidates.
Suggestion: Normalize anthropic:<id> names to vendor anthropic before comparing vendors, and test mixed direct/API-router candidates.

### 2026-11-11-23-42-46-d120b2 f1 MEDIUM docs/adr/ADR-004-model-choice.md:191
The documented replay invocation does not reproduce the selection run. Running `ledgerline eval --mode replay --run-id select-2026-11-11` exits 2 with `give --schema or --all`. Adding only `--schema fieldservice` uses the current Haiku default: `--run-id` does not restore the original four candidate models. On a fresh checkout this produces a different benchmark under the original report name.
Trigger: Follow Amendment 2's instructions to reproduce the four-model selection report from a fresh checkout.
Suggestion: Document the complete replay command, including `--schema fieldservice` and `--models` listing all four original candidates.

