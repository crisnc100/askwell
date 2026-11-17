import "./tokens.css";
import "./front.css";
import { ApiError, demo, type Answer } from "./api";
import { append, clear, h } from "./dom";
import schema from "./demo-schema.json";
import recorded from "./recorded-answer.json";

// Workspace links handed out before the app moved to /try/ were "/#ws=<id>"; they keep
// working by forwarding, with the id still only in the fragment. A link pasted into a
// tab already on this page changes only the hash, so that is watched too.
function forwardWorkspaceLink(): void {
  if (/(?:^#|&)ws=[0-9a-f]{32}(?:&|$)/.test(location.hash)) {
    location.replace(`/try/${location.hash}`);
  }
}
forwardWorkspaceLink();
window.addEventListener("hashchange", forwardWorkspaceLink);

type Json = Record<string, unknown>;
type Line = [label: string, value: string];

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const slip = $<HTMLElement>("slip");
const form = $<HTMLFormElement>("ask");
const input = $<HTMLInputElement>("question");
const askButton = $<HTMLButtonElement>("ask-button");
const starters = $<HTMLElement>("starters");
const formLines = $<HTMLElement>("form-lines");
const checkText = $<HTMLElement>("check-text");
const sql = $<HTMLElement>("sql");
const sqlNote = $<HTMLElement>("sql-note");
const rows = $<HTMLElement>("rows");
const stamps = Array.from(document.querySelectorAll<HTMLElement>(".stamp"));
const error = $<HTMLElement>("slip-error");
const announce = $<HTMLElement>("announce");
const slipNo = $<HTMLOutputElement>("slip-no");
const carbonTables = $<HTMLElement>("carbon-tables");
const carbonHidden = $<HTMLElement>("carbon-hidden");
const carbonRest = $<HTMLDetailsElement>("carbon-rest");
const moreButton = $<HTMLButtonElement>("more-starters-toggle");
const moreStarters = $<HTMLElement>("more-starters");
const steps = Array.from(document.querySelectorAll<HTMLElement>("#steps .step"));

const STEP_MS = 340;
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let timers: number[] = [];
let asked = 0;
const VISIBLE_STARTERS = 3;
const REFUSAL_STARTER = "Delete all void invoices.";

const AGG: Record<string, string> = {
  count: "Count",
  count_distinct: "Count distinct",
  sum: "Sum",
  avg: "Average",
  min: "Lowest",
  max: "Highest",
  ratio: "Share",
};

const ANSWER_AS: Record<string, string> = {
  summary: "One line of totals",
  grouped_summary: "Totals per group",
  row_list: "A list of rows",
  date_series: "Counts per period",
  unanswerable: "Can't answer safely",
};

const OPS: Record<string, string> = { eq: "=", neq: "≠", gt: ">", gte: "≥", lt: "<", lte: "≤" };

function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function words(token: string): string {
  return token.replace(/_/g, " ");
}

// The intent is model output: every reader below expects the worst and falls back to
// showing the raw value as text.
function fieldText(value: unknown): string {
  if (typeof value === "string") return value;
  if (isObject(value)) {
    const between = list(value.days_between);
    if (between.length === 2) return `days from ${fieldText(between[0])} to ${fieldText(between[1])}`;
    const op = { multiply: "×", subtract: "−", add: "+" }[String(value.op)];
    if (op) return `${fieldText(value.left)} ${op} ${fieldText(value.right)}`;
  }
  return JSON.stringify(value);
}

function valueText(value: unknown): string {
  if (isObject(value) && typeof value.of === "string") return `the ${words(value.of)}`;
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function condition(item: unknown): string {
  if (!isObject(item)) return JSON.stringify(item);
  if (Array.isArray(item.any_of)) return `either ${item.any_of.map(condition).join(" or ")}`;
  if (Array.isArray(item.all_of)) return item.all_of.map(condition).join(" and ");
  if (typeof item.has === "string") {
    const where = list(item.where).map(condition).join(" and ");
    return `${item.none ? "has no" : "has"} ${item.has}${where ? ` where ${where}` : ""}`;
  }
  const field = fieldText(item.field);
  const op = String(item.op);
  const against = item.other_field !== undefined ? fieldText(item.other_field) : valueText(item.value);
  if (OPS[op]) return `${field} ${OPS[op]} ${against}`;
  const values = list(item.values).map(valueText);
  if (op === "between") return `${field} between ${values[0]} and ${values[1]}`;
  if (op === "in") return `${field} is one of ${values.join(", ")}`;
  if (op === "is_null") return `${field} ${item.value === false ? "is not empty" : "is empty"}`;
  if (op === "ilike_contains") return `${field} contains “${valueText(item.value)}”`;
  return JSON.stringify(item);
}

function dateRange(range: Json): string {
  const field = typeof range.field === "string" ? `${range.field}: ` : "";
  if (typeof range.relative === "string") {
    const span = words(range.relative).replace(/\bn\b/, String(range.n ?? "n"));
    return field + span;
  }
  return `${field}from ${valueText(range.start)} to before ${valueText(range.end)}`;
}

function metricLine(metric: unknown): Line {
  if (!isObject(metric)) return ["Metric", JSON.stringify(metric)];
  const agg = String(metric.agg);
  if (agg === "ratio") {
    const percent = metric.as_percent === true ? ", as a percent" : "";
    return ["Share", `${String(metric.numerator)} ÷ ${String(metric.denominator)}${percent}`];
  }
  const what = metric.field === undefined ? "rows" : fieldText(metric.field);
  const where = list(metric.where).map(condition).join(" and ");
  return [AGG[agg] ?? agg, where ? `${what}, where ${where}` : what];
}

function intentLines(intent: unknown): Line[] {
  if (!isObject(intent)) return [];
  const lines: Line[] = [];
  const kind = String(intent.intent_type);
  lines.push(["Answer as", ANSWER_AS[kind] ?? kind]);
  if (typeof intent.unanswerable_reason === "string") lines.push(["Reason", intent.unanswerable_reason]);
  if (typeof intent.entity === "string") lines.push(["Table", intent.entity]);
  for (const metric of list(intent.metrics)) lines.push(metricLine(metric));
  if (typeof intent.grain === "string") lines.push(["Per", words(intent.grain)]);
  for (const item of list(intent.series)) {
    if (!isObject(item)) continue;
    const [agg, what] = metricLine(item.metric);
    lines.push(["Series", `${String(item.alias ?? "")}: ${agg.toLowerCase()} of ${what}, by ${fieldText(item.date_field)}`]);
  }
  const select = list(intent.select).map(fieldText);
  if (select.length) lines.push(["Show", select.join(", ")]);
  for (const item of list(intent.filters)) lines.push(["Filter", condition(item)]);
  if (isObject(intent.date_range)) lines.push(["Dates", dateRange(intent.date_range)]);
  for (const item of list(intent.group_by)) {
    if (!isObject(item)) continue;
    const grain = typeof item.grain === "string" ? `, by ${words(item.grain)}` : "";
    lines.push(["Group by", `${fieldText(item.field)}${grain}`]);
  }
  for (const item of list(intent.having)) {
    if (isObject(item)) lines.push(["Keep groups where", condition({ ...item, field: item.metric })]);
  }
  for (const item of list(intent.order_by)) {
    if (!isObject(item)) continue;
    const order = item.direction === "desc" ? "high to low" : "low to high";
    lines.push(["Sort", `${String(item.target)}, ${order}`]);
  }
  if (intent.limit !== undefined) lines.push(["Limit", String(intent.limit)]);
  return lines;
}

// Every "table.column" or bare column the form names, resolved against its base table.
function namedColumns(intent: unknown): Set<string> {
  const named = new Set<string>();
  if (!isObject(intent) || typeof intent.entity !== "string") return named;
  const base = intent.entity;
  named.add(`${base}.`);
  const add = (value: unknown) => {
    if (typeof value !== "string") return;
    named.add(value.includes(".") ? value : `${base}.${value}`);
    if (value.includes(".")) named.add(`${value.split(".")[0]}.`);
  };
  const walk = (node: unknown, key = ""): void => {
    if (Array.isArray(node)) {
      for (const item of node) walk(item, key);
    } else if (isObject(node)) {
      for (const [k, v] of Object.entries(node)) walk(v, k);
    } else if (["field", "date_field", "other_field", "select", "days_between", "left", "right"].includes(key)) {
      add(node);
    } else if (key === "has" && typeof node === "string") {
      named.add(`${node}.`);
    }
  };
  walk(intent);
  return named;
}

function columnCells(table: string, columns: string[]): HTMLElement {
  return h(
    "ul",
    { class: "cells", attrs: { "aria-label": `${table} columns` } },
    ...columns.map((column) =>
      h(
        "li",
        { attrs: { "data-column": `${table}.${column}` } },
        h("span", { class: "cname" }, column),
        h("span", { class: "cell", attrs: { "aria-label": "empty" } }),
      ),
    ),
  );
}

function tableBlock(table: (typeof schema)[number], named: Set<string>): HTMLElement {
  const block = h(
    "div",
    { class: "ctable", attrs: { "data-table": table.table } },
    h("p", { class: "ctable-name" }, table.table),
    columnCells(table.table, table.shown),
  );
  block.classList.toggle("is-used", named.has(`${table.table}.`));
  for (const li of block.querySelectorAll<HTMLElement>("[data-column]")) {
    li.classList.toggle("is-used", named.has(li.dataset.column ?? ""));
  }
  return block;
}

// The carbon opens on the tables the form named; every other table the AI was shown
// folds into one line, and the hidden columns always stay in view.
function drawCarbon(named: Set<string>, empty = "The form named no table."): void {
  const used = schema.filter((t) => named.has(`${t.table}.`));
  const rest = schema.filter((t) => !named.has(`${t.table}.`));
  clear(carbonTables);
  if (!used.length) carbonTables.appendChild(h("p", { class: "carbon-none" }, empty));
  for (const table of used) carbonTables.appendChild(tableBlock(table, named));

  clear(carbonHidden);
  append(
    carbonHidden,
    h("p", { class: "ctable-name" }, "Never shown"),
    h(
      "ul",
      { class: "cells", attrs: { "aria-label": "Hidden columns" } },
      ...schema.flatMap((t) =>
        t.hidden.map((column) =>
          h("li", { class: "is-hidden" }, h("span", { class: "cname" }, `${t.table}.${column}`), h("span", { class: "cell" }, "hidden")),
        ),
      ),
    ),
  );

  clear(carbonRest);
  carbonRest.hidden = rest.length === 0;
  const others = used.length ? `${rest.length} other ${rest.length === 1 ? "table" : "tables"}` : `${rest.length} tables`;
  append(
    carbonRest,
    h("summary", {}, `${others}: names only`),
    h("div", { class: "tables" }, ...rest.map((table) => tableBlock(table, named))),
  );
}

function cellText(value: unknown): string {
  if (value === null) return "";
  if (typeof value === "number" && !Number.isInteger(value)) {
    return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
  return String(value);
}

function sentence(text: string): string {
  const trimmed = text.trim().replace(/\.$/, "");
  return `${trimmed.charAt(0).toUpperCase()}${trimmed.slice(1)}.`;
}

function literal(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "number" || typeof value === "boolean") return String(value).toUpperCase();
  if (typeof value === "string") {
    const shown = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(value) ? value.replace("T", " ") : value;
    return `'${shown.replace(/'/g, "''")}'`;
  }
  return JSON.stringify(value);
}

const CAST = /::(?:TIMESTAMP WITHOUT TIME ZONE|TIMESTAMP WITH TIME ZONE|[A-Z]+)/;
const PARAM = new RegExp(`%\\((\\w+)\\)s(?:${CAST.source})?`, "g");
const CLAUSE = /\s+(FROM|WHERE|GROUP BY|HAVING|ORDER BY|LIMIT|UNION|(?:LEFT OUTER |LEFT |INNER )?JOIN)\b/g;

// For reading only: the query runs with its values passed as parameters and its short
// table aliases. Here each alias is swapped for its table's name, wherever one alias
// always means one table, and the values are written in. The values go in last, after
// every rewrite, so a value that looks like an alias or holds extra spaces stays as is.
function readableSql(text: string, params: Record<string, unknown> | null): string {
  let out = text;
  const tablesOf = new Map<string, Set<string>>();
  const aliasesOf = new Map<string, Set<string>>();
  for (const [, table, alias] of out.matchAll(/\b([a-z_][a-z0-9_]*) AS (t\d+)\b/g)) {
    tablesOf.set(alias, (tablesOf.get(alias) ?? new Set()).add(table));
    aliasesOf.set(table, (aliasesOf.get(table) ?? new Set()).add(alias));
  }
  for (const [alias, tables] of tablesOf) {
    const [table] = tables;
    if (tables.size !== 1 || aliasesOf.get(table)?.size !== 1) continue;
    out = out.replace(new RegExp(`\\b${table} AS ${alias}\\b`, "g"), table).replace(new RegExp(`\\b${alias}\\.`, "g"), `${table}.`);
  }
  out = out.replace(/\s+/g, " ").replace(CLAUSE, "\n$1").trim();
  return out.replace(PARAM, (match, name: string) => (params && name in params ? literal(params[name]) : match));
}

function stampWith(answered: boolean, value: string): void {
  for (const stamp of stamps) {
    clear(stamp);
    append(
      stamp,
      h("span", { class: "stamp-word" }, answered ? "Checked" : "Not answered"),
      h("span", { class: "stamp-value" }, value),
    );
    stamp.classList.toggle("is-refused", !answered);
  }
}

function fill(answer: Answer): void {
  clear(formLines);
  for (const [label, value] of intentLines(answer.intent)) {
    formLines.appendChild(h("div", {}, h("dt", {}, label), h("dd", {}, value)));
  }

  const attempts = answer.validation.attempts;
  const firstIssues = attempts.length > 1 ? attempts[0].issues : [];
  if (answer.refusal) {
    checkText.textContent = `Not answered. ${sentence(answer.refusal)} No query was run.`;
  } else if (answer.validation.ok) {
    checkText.textContent =
      firstIssues.length > 0
        ? `Passed on the second try. The first form failed: ${sentence(firstIssues[0].message)}`
        : "Passed. Every table and column on the form is one this database may show.";
  } else {
    const issues = attempts.length ? attempts[attempts.length - 1].issues : [];
    checkText.textContent = `Failed${issues.length ? `: ${sentence(issues[0].message)}` : "."} No query was run.`;
  }

  clear(sql);
  sql.appendChild(h("code", {}, answer.sql === null ? "No SQL was written." : readableSql(answer.sql, answer.params)));
  sqlNote.hidden = answer.sql === null;

  clear(rows);
  const answered = !answer.refusal && answer.sql !== null;
  if (!answered) {
    rows.appendChild(h("p", { class: "no-rows" }, "No rows. It said so instead of guessing."));
  } else {
    const numeric = answer.columns.map((_, i) => answer.rows.every((row) => row[i] === null || typeof row[i] === "number"));
    rows.appendChild(
      h(
        "div",
        { class: "rows-scroll", attrs: { tabindex: "0", role: "region", "aria-label": "Answer rows" } },
        h(
          "table",
          { class: "answer-rows" },
          h("thead", {}, h("tr", {}, ...answer.columns.map((c, i) => h("th", { class: numeric[i] ? "num" : "", attrs: { scope: "col" } }, c.replace("__", "."))))),
          h(
            "tbody",
            {},
            ...answer.rows.map((row) =>
              h("tr", {}, ...row.map((v, i) => h("td", { class: numeric[i] ? "num" : "" }, cellText(v)))),
            ),
          ),
        ),
      ),
    );
    if (answer.truncated) rows.appendChild(h("p", { class: "step-note" }, "Only the first rows are shown."));
    if (answer.tied_at_cutoff) rows.appendChild(h("p", { class: "step-note tie-note" }, "More rows tie with the last one shown."));
  }

  const count = answer.rows.length;
  const single = answered && count === 1 && answer.columns.length === 1 ? cellText(answer.rows[0][0]) : null;
  stampWith(answered, answered ? (single ?? `${count} ${count === 1 ? "row" : "rows"}`) : "Said so");
  drawCarbon(namedColumns(answer.intent));
  announce.textContent = answered
    ? `Answered and checked: ${count} ${count === 1 ? "row" : "rows"}. Rows sent to the AI: 0.`
    : `Not answered: ${answer.refusal ?? "the form failed the check"}.`;
}

// Once down, the stamp stays down: dropping the finished animation keeps a resize or a
// print from replaying it.
for (const stamp of stamps) {
  stamp.addEventListener("animationend", () => stamp.classList.add("is-set"));
}

const BLANK_FORM = ["Table", "Count", "Filter"];
const BLANK_CHECK = checkText.textContent ?? "";

// A new ask wipes the slip before it is sent, so nothing of the last answer can stand
// under the new question, even when the ask then fails.
function reset(): void {
  for (const id of timers) window.clearTimeout(id);
  timers = [];
  for (const step of steps) step.dataset.filled = "false";
  clear(formLines);
  for (const label of BLANK_FORM) formLines.appendChild(h("div", {}, h("dt", {}, label), h("dd", {})));
  checkText.textContent = BLANK_CHECK;
  clear(sql);
  sqlNote.hidden = true;
  clear(rows);
  for (const stamp of stamps) {
    stamp.classList.remove("is-down", "is-set", "is-refused");
    clear(stamp);
  }
  drawCarbon(new Set(), "Waiting for the form.");
  announce.textContent = "";
  error.hidden = true;
}

// The one orchestrated motion: the slip fills step by step, then the stamp comes down.
function reveal(): void {
  const gap = reducedMotion.matches ? 0 : STEP_MS;
  steps.forEach((step, i) => {
    timers.push(window.setTimeout(() => (step.dataset.filled = "true"), gap * i));
  });
  timers.push(window.setTimeout(() => stamps.forEach((s) => s.classList.add("is-down")), gap * steps.length));
}

function setBusy(busy: boolean): void {
  askButton.disabled = busy;
  slip.setAttribute("aria-busy", String(busy));
  for (const button of starters.querySelectorAll<HTMLButtonElement>("li button")) button.disabled = busy;
}

function failure(err: unknown): string {
  if (err instanceof ApiError && err.status === 409) {
    return "This demo has no recorded answer for that question, and live answers are off here. Pick one of the questions above.";
  }
  if (err instanceof ApiError && err.status !== 404) return err.message;
  return "Something went wrong. Try again in a minute.";
}

function show(answer: Answer): void {
  asked += 1;
  slipNo.value = String(asked).padStart(4, "0");
  fill(answer);
  slip.dataset.state = "answered";
  reveal();
}

async function ask(question: string): Promise<void> {
  if (!question || askButton.disabled) return;
  setBusy(true);
  reset();
  slip.dataset.state = "asking";
  try {
    show(await demo.ask(question));
  } catch (err) {
    slip.dataset.state = "idle";
    error.textContent = failure(err);
    error.hidden = false;
  } finally {
    setBusy(false);
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  void ask(input.value.trim());
});

moreButton.addEventListener("click", () => {
  const open = moreStarters.hidden;
  moreStarters.hidden = !open;
  moreButton.setAttribute("aria-expanded", String(open));
  moreButton.textContent = open ? "Fewer questions" : "More questions";
});

function starterItem(question: string): HTMLElement {
  const button = h("button", { attrs: { type: "button" } }, question);
  button.addEventListener("click", () => {
    input.value = question;
    void ask(question);
  });
  return h("li", {}, button);
}

async function loadStarters(): Promise<void> {
  let questions: string[];
  try {
    questions = await demo.examples();
  } catch {
    // The page still works with a typed question.
    return;
  }
  if (!questions.length) return;
  // The refusal example stays in view: saying no is part of what the demo shows.
  const first = questions.slice(0, VISIBLE_STARTERS);
  if (questions.includes(REFUSAL_STARTER) && !first.includes(REFUSAL_STARTER)) first.push(REFUSAL_STARTER);
  const later = questions.filter((q) => !first.includes(q));
  (starters.querySelector("ul") as HTMLUListElement).append(...first.map(starterItem));
  (moreStarters.querySelector("ul") as HTMLUListElement).append(...later.map(starterItem));
  moreButton.hidden = later.length === 0;
  starters.hidden = false;
  setBusy(askButton.disabled);
}

// The first starter's recorded answer ships with the page, so a visitor sees a whole
// answered slip before asking anything, at no cost to the live-answer budget.
input.value = recorded.question;
show(recorded as unknown as Answer);
void loadStarters();
