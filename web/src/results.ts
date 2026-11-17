import "./tokens.css";
import "./results.css";
import { append, clear, h } from "./dom";

// The shape of evals/reports/<id>.json; evals/report.schema.json is its full definition.
interface Rate {
  n: number;
  of: number;
  rate: number | null;
  ci95: [number, number] | null;
}

interface Row {
  schema: string;
  system: string;
  model: string;
  trials: number;
  coverage: Rate;
  execution_accuracy: Rate;
  accuracy_given_attempted: Rate;
  false_refusal_rate: Rate;
  wrong_answer_rate_given_answered: Rate;
  refusal_recall: Rate;
  execution_error_rate: Rate;
}

interface QuestionLevel {
  schema: string;
  system: string;
  right: Rate;
}

interface Floor {
  schema: string;
  model: string | null;
  met: boolean;
  checks: { metric: string; rule: string; rate: Rate; met: boolean }[];
  status_note: string | null;
  cause: string | null;
  next: string | null;
}

interface Miss {
  schema: string;
  system?: string;
  item_id: string;
  trial: number;
  outcome: string;
  tag: string;
  note: string;
}

interface Report {
  run_id: string;
  simulation: string | null;
  notes: string[];
  status: string;
  trials?: number;
  table: Row[];
  question_level?: QuestionLevel[];
  floors: Floor[];
  misses: Miss[];
  triage_files: string[];
}

interface Summary {
  id: string;
  simulation: string | null;
  schemas: string[];
}

type MetricKey = Exclude<keyof Row, "schema" | "system" | "model" | "trials">;

// The committed reports the plain statement is read from. ADR-008 names them: the v0.3
// held-out run and the same questions on the code before v0.3, then the deploy gate's
// untriaged Spider runs (the gated repeat is the one the gate was read on) and its CSV runs.
const HEADLINE = "v03-holdout";
const BEFORE = "v03-holdout-before";
const GATE = {
  spider: { before: "v03-spider-new-before", after: "v03-spider-new-gated", system: "ledgerline" },
  csv: { before: "v03-csv-new-before", after: "v03-csv-new", system: "askwell_csv" },
};
// The gate's rule is written in ADR-008, not in any report: per database, the wrong rate
// among answered may rise by at most 5 points.
const GATE_RISE = 0.05;
const ADR_008 = "https://github.com/crisnc100/askwell/blob/main/docs/adr/ADR-008-accuracy-v03.md";
// Askwell's system id, as recorded in the committed reports.
const ASKWELL = "ledgerline";
const DIRECT = "oneshot";

// Each metric in the order the table shows it, with the words a reader needs to read it.
const METRICS: { key: MetricKey; label: string; better: "higher" | "lower"; definition: string }[] = [
  {
    key: "execution_accuracy",
    label: "Execution accuracy",
    better: "higher",
    definition:
      "Of the questions the database can answer, the share where the system returned the same rows as the gold answer.",
  },
  {
    key: "wrong_answer_rate_given_answered",
    label: "Wrong answers among answered",
    better: "lower",
    definition:
      "Of every question where the system returned rows, the share whose rows were wrong. This is the safety number: a refusal is honest, a wrong table of numbers is not.",
  },
  {
    key: "coverage",
    label: "Coverage",
    better: "higher",
    definition: "Of the questions the database can answer, the share the system tried to answer instead of refusing.",
  },
  {
    key: "accuracy_given_attempted",
    label: "Accuracy when it answered",
    better: "higher",
    definition: "Of the answerable questions the system tried, the share it got right.",
  },
  {
    key: "false_refusal_rate",
    label: "False refusals",
    better: "lower",
    definition: "Of the questions the database can answer, the share the system refused.",
  },
  {
    key: "refusal_recall",
    label: "Refusal recall",
    better: "higher",
    definition:
      "Of the questions that should be refused (data that does not exist, hidden fields, requests to change data), the share the system refused. Spider has no such questions, so it shows n/a.",
  },
  {
    key: "execution_error_rate",
    label: "Execution errors",
    better: "lower",
    definition: "Of all questions, the share where the SQL failed to run.",
  },
];

const SYSTEMS: Record<string, string> = {
  ledgerline: "Askwell",
  askwell_csv: "Askwell, CSV upload",
  oneshot: "One-shot baseline",
  sql_agent: "SQL agent baseline",
};

const TAGS: Record<string, string> = {
  grammar_gap: "the question needs something an intent cannot express",
  misread: "the model misunderstood the question",
  validator_false_reject: "the safety check refused a valid intent",
  builder_bug: "the SQL builder wrote the wrong query",
  gold_issue: "the gold answer itself is doubtful",
  untriaged: "not yet reviewed",
};

const main = document.getElementById("app") as HTMLElement;
const statement = document.getElementById("statement") as HTMLElement;
const lead = document.getElementById("lead") as HTMLElement;

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function points(value: number): string {
  const p = (value * 100).toFixed(1);
  return value > 0 ? `+${p}` : value < 0 ? `−${p.slice(1)}` : "0.0";
}

// "1 in N" from the counts themselves: answered divided by wrong, rounded.
function oneIn(rate: Rate): string {
  return rate.n === 0 ? "none" : `1 in ${Math.round(rate.of / rate.n)}`;
}

function jsonHref(id: string): string {
  return `/api/reports/${encodeURIComponent(id)}`;
}

function jsonLink(id: string): HTMLElement {
  return h("a", { class: "json", attrs: { href: jsonHref(id) } }, `evals/reports/${id}.json`);
}

function row(report: Report | undefined, system: string, schema?: string): Row | undefined {
  return report?.table.find((r) => r.system === system && (schema === undefined || r.schema === schema));
}

function right(report: Report | undefined, system: string): Rate | undefined {
  return report?.question_level?.find((q) => q.system === system)?.right;
}

function trialsOf(report: Report): number {
  return report.trials ?? row(report, ASKWELL)?.trials ?? 1;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(response.status === 404 ? "No report has that name." : "The report could not be loaded.");
  return (await response.json()) as T;
}

const loaded = new Map<string, Promise<Report>>();
function load(id: string): Promise<Report> {
  let pending = loaded.get(id);
  if (!pending) {
    pending = getJson<Report>(jsonHref(id));
    loaded.set(id, pending);
  }
  return pending;
}

// A report the list doesn't name is missing; one it names that won't load has failed.
// The page says which, so a network fault never reads as "nothing to show".
interface Loaded {
  id: string;
  report?: Report;
  state: "loaded" | "missing" | "failed";
}

async function loadIf(listed: Set<string>, id: string): Promise<Loaded> {
  if (!listed.has(id)) return { id, state: "missing" };
  try {
    return { id, report: await load(id), state: "loaded" };
  } catch {
    return { id, state: "failed" };
  }
}

function unloaded(results: Loaded[]): HTMLElement | null {
  const failed = results.filter((r) => r.state === "failed").map((r) => r.id);
  const missing = results.filter((r) => r.state === "missing").map((r) => r.id);
  if (!failed.length && !missing.length) return null;
  return h(
    "div",
    { class: "notice error unloaded", attrs: { role: "alert" } },
    failed.length ? h("p", {}, `Couldn't load ${failed.length === 1 ? "this report" : "these reports"}: ${failed.join(", ")}. Reloading the page may help.`) : null,
    missing.length ? h("p", {}, `Not among the committed reports: ${missing.join(", ")}.`) : null,
  );
}


interface Line {
  key: string;
  ask: string;
  figure: string;
  detail: string;
  means: string;
}

// Of the questions Askwell got wrong at question level (missed in more than half its
// trials), how many it turned down in every trial. Shown only when the miss records
// account for exactly the question-level misses, so the two counts can't disagree.
function missesRefused(report: Report, rightNow: Rate, trials: number): { refused: number; missed: number } | null {
  const byItem = new Map<string, string[]>();
  for (const m of report.misses) {
    if ((m.system ?? ASKWELL) !== ASKWELL) continue;
    byItem.set(m.item_id, [...(byItem.get(m.item_id) ?? []), m.outcome]);
  }
  const needed = Math.floor(trials / 2) + 1;
  const missed = [...byItem.values()].filter((outcomes) => outcomes.length > trials - needed);
  if (missed.length !== rightNow.of - rightNow.n) return null;
  const refused = missed.filter((o) => o.length === trials && o.every((x) => x === "refused")).length;
  return { refused, missed: missed.length };
}

function lines(now: Report, before: Report | undefined): Line[] | null {
  const askwell = row(now, ASKWELL);
  const rightNow = right(now, ASKWELL);
  if (!askwell || !rightNow) return null;
  const rightBefore = right(before, ASKWELL);
  const wrongBefore = row(before, ASKWELL)?.wrong_answer_rate_given_answered;
  const wrong = askwell.wrong_answer_rate_given_answered;
  const refused = askwell.refusal_recall;
  const trials = trialsOf(now);
  const shouldRefuse = refused.of / trials;
  const allRefused = refused.n === refused.of;
  const refusedMisses = missesRefused(now, rightNow, trials);
  return [
    {
      key: "right",
      ask: "How often it's right",
      figure: `${rightNow.n} of ${rightNow.of}`,
      detail: `questions it had never seen${rightBefore ? `, up from ${rightBefore.n} before v0.3` : ""}.`,
      means:
        `Most questions your data can answer get the right answer. When one doesn't, it is usually because Askwell said it couldn't answer${refusedMisses ? ` (${refusedMisses.refused} of the ${refusedMisses.missed} misses)` : ""}, not because it guessed.`,
    },
    {
      key: "wrong",
      ask: "How often it's confidently wrong",
      figure: `About ${oneIn(wrong)}`,
      detail: `answers it gave was wrong${wrongBefore ? `, down from ${oneIn(wrongBefore)} before v0.3` : ""}.`,
      means:
        "A number it hands you is very likely right, and every answer comes with the SQL behind it, so the rare wrong one can be checked.",
    },
    {
      key: "unsure",
      ask: "What it does when unsure",
      figure: allRefused ? `All ${shouldRefuse}` : `${refused.n} of ${refused.of}`,
      detail: allRefused
        ? `questions it should not answer: it said so every time, in all ${trials} runs, instead of guessing.`
        : `times it turned down a question it should have, over ${trials} runs of ${shouldRefuse} questions.`,
      means:
        "Ask for data that isn't there, for private fields such as passwords, or to change or delete your data, and you get a plain “can't answer that”, not a made-up number.",
    },
  ];
}

function stamp(now: Report): HTMLElement | null {
  if (now.simulation || now.status !== "complete") return null;
  const trials = trialsOf(now);
  return h(
    "div",
    { class: "stamp", attrs: { "aria-hidden": "true" } },
    h("span", { class: "stamp-word" }, "Measured"),
    h("span", { class: "stamp-value" }, `${trials} ${trials === 1 ? "run" : "runs"}`),
  );
}

function renderStatement(now: Report | undefined, before: Report | undefined): void {
  const head = statement.querySelector(".statement-head");
  clear(statement);
  if (head) statement.appendChild(head);
  statement.removeAttribute("aria-busy");
  const plain = now ? lines(now, before) : null;
  if (!now || !plain) {
    append(
      statement,
      h(
        "p",
        { class: "statement-wait", attrs: { role: "alert" } },
        "The measured figures could not be loaded. The reports they come from are listed below.",
      ),
    );
    return;
  }
  const askwell = row(now, ASKWELL);
  const trials = trialsOf(now);
  const answerable = right(now, ASKWELL)?.of;
  if (askwell && answerable !== undefined) {
    const refuse = askwell.refusal_recall.of / trials;
    lead.textContent = `We asked it ${answerable + refuse} questions it had never seen, ${trials} times each: ${answerable} the data could answer, and ${refuse} it should turn down.`;
  }

  const list = h("dl", { class: "lines" });
  for (const line of plain) {
    append(
      list,
      h(
        "div",
        { class: "line", attrs: { "data-line": line.key } },
        h("dt", { class: "label" }, line.ask),
        h("dd", { class: "figure" }, h("strong", {}, line.figure), " ", h("span", {}, line.detail)),
        h("dd", { class: "means" }, line.means),
      ),
    );
  }
  const mark = stamp(now);
  append(
    statement,
    list,
    h(
      "div",
      { class: "statement-foot" },
      h(
        "p",
        {},
        now.simulation || now.status !== "complete"
          ? "These figures are not from a finished measurement with a real model. "
          : `Measured with a real model, ${trials} runs of every question. `,
        "Every figure here is read from a measurement report saved with the code. ",
        h("a", { attrs: { href: "#sources" } }, "Where each figure comes from"),
      ),
      mark,
    ),
  );
  if (mark) {
    mark.addEventListener("animationend", () => mark.classList.add("is-set"));
    requestAnimationFrame(() => mark.classList.add("is-down"));
  }
}


function comparison(now: Report | undefined): HTMLElement | null {
  const askwell = row(now, ASKWELL);
  const direct = row(now, DIRECT);
  const askwellRight = right(now, ASKWELL);
  const directRight = right(now, DIRECT);
  if (!now || !askwell || !direct || !askwellRight || !directRight) return null;
  const trials = trialsOf(now);
  const refusedCell = (r: Rate) =>
    r.n === r.of ? `All ${r.of / trials}` : `${r.n} of ${r.of} times`;
  const wrongCell = (r: Rate) =>
    h("td", {}, h("strong", {}, `About ${oneIn(r)}`), h("span", { class: "small" }, ` (${pct(r.rate ?? 0)})`));
  const tableRows: [string, HTMLElement, HTMLElement][] = [
    [
      "Questions it got right",
      h("td", {}, h("strong", {}, `${askwellRight.n} of ${askwellRight.of}`)),
      h("td", {}, h("strong", {}, `${directRight.n} of ${directRight.of}`)),
    ],
    ["Answers it gave that were wrong", wrongCell(askwell.wrong_answer_rate_given_answered), wrongCell(direct.wrong_answer_rate_given_answered)],
    [
      "Said so on questions it should not answer",
      h("td", {}, h("strong", {}, refusedCell(askwell.refusal_recall))),
      h("td", {}, h("strong", {}, refusedCell(direct.refusal_recall))),
    ],
  ];
  return h(
    "section",
    { class: "compare", attrs: { "aria-labelledby": "compare-title", id: "compare" } },
    h("h2", { attrs: { id: "compare-title" } }, "Against letting the AI write the SQL itself"),
    h(
      "p",
      {},
      "We gave the same AI the same questions and let it write the SQL directly, with no form and no check in between.",
    ),
    h(
      "table",
      { class: "compare-ledger" },
      h(
        "thead",
        {},
        h("tr", {}, h("td", {}), h("th", { attrs: { scope: "col" } }, "Askwell"), h("th", { attrs: { scope: "col" } }, "AI writing SQL")),
      ),
      h(
        "tbody",
        {},
        ...tableRows.map(([label, a, b]) => h("tr", {}, h("th", { attrs: { scope: "row" } }, label), a, b)),
      ),
    ),
    h(
      "p",
      {},
      `Writing SQL directly gets more questions right. It attempts every one, though ${direct.execution_error_rate.n} of its queries failed to run, so ${direct.wrong_answer_rate_given_answered.of} of its ${direct.coverage.n} tries came back with an answer, and more of those answers are wrong. Askwell answers fewer questions so that fewer of the numbers it gives are confidently wrong; if you would rather have more answers and check each one yourself, writing SQL directly gets more right.`,
    ),
  );
}


function fold(id: string, title: string, definition: string, ...body: (HTMLElement | null)[]): HTMLDetailsElement {
  return h(
    "details",
    { class: "fold", attrs: { id } },
    h("summary", {}, title),
    h("div", { class: "fold-body" }, h("p", { class: "fold-def" }, definition), ...body.filter((b): b is HTMLElement => b !== null)),
  );
}

function sourcesFold(now: Report | undefined, before: Report | undefined): HTMLDetailsElement {
  const askwell = row(now, ASKWELL);
  const rows: [string, string, string, string][] = [];
  if (now && askwell) {
    const r = right(now, ASKWELL);
    const d = right(now, DIRECT);
    const direct = row(now, DIRECT);
    const t = trialsOf(now);
    if (r) rows.push([`${r.n} of ${r.of} right`, HEADLINE, `question_level, system ${ASKWELL}: right`, `${r.n} of ${r.of} (${pct(r.rate ?? 0)})`]);
    const rb = right(before, ASKWELL);
    if (rb) rows.push([`${rb.n} before v0.3`, BEFORE, `question_level, system ${ASKWELL}: right`, `${rb.n} of ${rb.of} (${pct(rb.rate ?? 0)})`]);
    const w = askwell.wrong_answer_rate_given_answered;
    rows.push([`About ${oneIn(w)} wrong`, HEADLINE, `table, system ${ASKWELL}: wrong_answer_rate_given_answered`, `${w.n} of ${w.of} (${pct(w.rate ?? 0)})`]);
    const wb = row(before, ASKWELL)?.wrong_answer_rate_given_answered;
    if (wb) rows.push([`${oneIn(wb)} before v0.3`, BEFORE, `table, system ${ASKWELL}: wrong_answer_rate_given_answered`, `${wb.n} of ${wb.of} (${pct(wb.rate ?? 0)})`]);
    const rr = askwell.refusal_recall;
    rows.push([`All ${rr.of / t} turned down`, HEADLINE, `table, system ${ASKWELL}: refusal_recall, over ${t} trials`, `${rr.n} of ${rr.of}`]);
    const mr = r ? missesRefused(now, r, t) : null;
    if (mr)
      rows.push([`${mr.refused} of the ${mr.missed} misses turned down`, HEADLINE, `misses, system ${ASKWELL}: outcome refused in all ${t} trials`, `${mr.refused} questions`]);
    if (d) rows.push([`${d.n} of ${d.of} right, SQL written directly`, HEADLINE, `question_level, system ${DIRECT}: right`, `${d.n} of ${d.of} (${pct(d.rate ?? 0)})`]);
    if (direct) {
      const dw = direct.wrong_answer_rate_given_answered;
      rows.push([`About ${oneIn(dw)} wrong, SQL written directly`, HEADLINE, `table, system ${DIRECT}: wrong_answer_rate_given_answered`, `${dw.n} of ${dw.of} (${pct(dw.rate ?? 0)})`]);
    }
  }
  return fold(
    "sources",
    "Where each figure comes from",
    "Held-out questions are questions kept from the people building Askwell until its code was frozen, so it could not be tuned to them; the one-shot baseline is the same model writing SQL directly.",
    h(
      "p",
      {},
      "Askwell appears in the reports as ledgerline, its earlier name. A question counts as right when Askwell returned the gold answer's rows in at least 2 of its 3 trials; wrong answers and refusals are counted over every answer in every trial. ",
      "The before figures are the same questions run on the code before v0.3.",
    ),
    rows.length
      ? h(
          "div",
          { class: "scroll" },
          h(
            "table",
            { class: "sources" },
            h("thead", {}, h("tr", {}, ...["Figure", "Report", "Field", "Value"].map((c) => h("th", { attrs: { scope: "col" } }, c)))),
            h(
              "tbody",
              {},
              ...rows.map(([figure, id, field, value]) =>
                h("tr", {}, h("th", { attrs: { scope: "row" } }, figure), h("td", {}, jsonLink(id)), h("td", {}, h("code", {}, field)), h("td", {}, value)),
              ),
            ),
          ),
        )
      : null,
  );
}

interface GateLine {
  schema: string;
  before: Rate;
  after: Rate;
  rise: number;
  failed: boolean;
}

function gateLines(before: Report | undefined, after: Report | undefined, system: string): GateLine[] {
  if (!before || !after) return [];
  const out: GateLine[] = [];
  for (const r of after.table.filter((t) => t.system === system)) {
    const b = row(before, system, r.schema)?.wrong_answer_rate_given_answered;
    const a = r.wrong_answer_rate_given_answered;
    if (!b || b.rate === null || a.rate === null) continue;
    const rise = a.rate - b.rate;
    out.push({ schema: r.schema, before: b, after: a, rise, failed: rise > GATE_RISE });
  }
  return out;
}

function dbName(schema: string): string {
  return schema.startsWith("spider_") ? schema.slice("spider_".length) : schema;
}

function gateTable(caption: string, rows: GateLine[]): HTMLElement {
  return h(
    "div",
    { class: "scroll" },
    h(
      "table",
      { class: "gate" },
      h("caption", {}, caption),
      h(
        "thead",
        {},
        h("tr", {}, ...["Database", "Wrong before", "Wrong after", "Change, points", "Rule"].map((c) => h("th", { attrs: { scope: "col" } }, c))),
      ),
      h(
        "tbody",
        {},
        ...rows.map((g) =>
          h(
            "tr",
            { attrs: { "data-schema": g.schema, "data-failed": String(g.failed) } },
            h("th", { attrs: { scope: "row" } }, dbName(g.schema)),
            h("td", {}, `${pct(g.before.rate ?? 0)} (${g.before.n} of ${g.before.of})`),
            h("td", {}, `${pct(g.after.rate ?? 0)} (${g.after.n} of ${g.after.of})`),
            h("td", {}, points(g.rise)),
            h("td", { class: g.failed ? "failed" : "" }, g.failed ? "Failed" : "Passed"),
          ),
        ),
      ),
    ),
  );
}

function gateFold(
  now: Report | undefined,
  before: Report | undefined,
  gate: { spider: [Loaded, Loaded]; csv: [Loaded, Loaded] },
): HTMLDetailsElement {
  const spider = gate.spider.map((l) => l.report);
  const csv = gate.csv.map((l) => l.report);
  const spiderLines = gateLines(spider[0], spider[1], GATE.spider.system);
  const csvLines = gateLines(csv[0], csv[1], GATE.csv.system);
  const world = spiderLines.find((g) => g.schema === "spider_world_1");
  const ties = spider[1]?.misses.filter(
    (m) => m.schema === "spider_world_1" && m.outcome === "wrong" && m.tag === "gold_issue",
  ).length;
  const csvWorldBefore = row(csv[0], GATE.csv.system, "spider_world_1");
  const csvWorldAfter = row(csv[1], GATE.csv.system, "spider_world_1");
  const rightBefore = right(before, ASKWELL);
  const rightNow = right(now, ASKWELL);
  const perDb = spider[1]?.table.find((t) => t.system === GATE.spider.system)?.coverage.of;

  const reasons: string[] = [];
  if (rightBefore && rightNow)
    reasons.push(
      `the gain on the held-out questions is clear: ${rightBefore.n} to ${rightNow.n} of ${rightNow.of} right, with fewer wrong answers;`,
    );
  if (world && ties !== undefined)
    reasons.push(
      `${ties} of world_1's ${world.after.n} wrong answers are ties, where several rows are equally right and the gold answer keeps only one of them;`,
    );
  if (csvWorldBefore && csvWorldAfter)
    reasons.push(
      `uploaded as CSV files, world_1 went from answering ${csvWorldBefore.coverage.n} questions to answering ${csvWorldAfter.coverage.n}, ${csvWorldAfter.execution_accuracy.n} of them right.`,
    );

  return fold(
    "release-check",
    "The release check that failed, and why it shipped anyway",
    "Spider is a public set of test databases and questions written by other researchers; world_1 is one of them, about countries and the languages they speak.",
    h(
      "p",
      {},
      `Before v0.3 could ship, a rule set in advance said that on each new test database, the share of wrong answers among those given could rise by at most ${Math.round(GATE_RISE * 100)} points.${perDb ? ` Each database here was asked ${perDb} questions it had never seen, once.` : ""}`,
    ),
    spiderLines.length ? gateTable("Spider databases, read on the repeat run", spiderLines) : null,
    csvLines.length ? gateTable("The same databases uploaded as CSV files", csvLines) : null,
    unloaded([...gate.spider, ...gate.csv]),
    // The failure and the override are recorded in ADR-008, so they are shown whatever
    // loads; the reports only add the figures behind them.
    h(
      "div",
      { class: "notice override" },
      h(
        "p",
        {},
        h("strong", {}, "The rule said not to ship. "),
        `world_1 failed it, as a database and as CSV uploads. Cristian read the failures and approved the release anyway, on 2026-11-15. ${reasons.length ? "His reasons, recorded in ADR-008:" : "His reasons are recorded in ADR-008."}`,
      ),
      reasons.length ? h("ul", {}, ...reasons.map((r) => h("li", {}, r))) : null,
      h("p", {}, h("a", { attrs: { href: ADR_008 } }, "Read ADR-008, with the gate and the override in full")),
    ),
    h(
      "p",
      { class: "small" },
      "Reports: ",
      ...[GATE.spider.before, GATE.spider.after, GATE.csv.before, GATE.csv.after].flatMap((id, i) => [i ? ", " : "", jsonLink(id)]),
      ".",
    ),
  );
}


function rateCell(rate: Rate): HTMLElement {
  if (rate.rate === null || rate.ci95 === null) return h("td", { class: "muted" }, "n/a");
  const [low, high] = rate.ci95;
  return h(
    "td",
    {},
    h("strong", {}, pct(rate.rate)),
    h("div", { class: "muted" }, `${rate.n} of ${rate.of}`),
    h("div", { class: "muted" }, `range ${Math.round(low * 100)}–${Math.round(high * 100)}%`),
  );
}

function schemaTitle(schema: string): string {
  if (schema === "fieldservice") return "fieldservice (the synthetic demo business)";
  if (schema.startsWith("spider_")) return `Spider: ${schema.slice("spider_".length)}`;
  return schema;
}

function definitions(): HTMLElement {
  const list = h("dl", { class: "definitions" });
  for (const metric of METRICS) {
    append(list, h("dt", {}, `${metric.label} (${metric.better} is better)`), h("dd", {}, metric.definition));
  }
  append(
    list,
    h("dt", {}, "Gold answer"),
    h("dd", {}, "The rows a hand-written, checked SQL query returns for the question. The questions and gold answers were fixed before Askwell's code was written."),
    h("dt", {}, "Range"),
    h(
      "dd",
      {},
      "The 95% Wilson interval: given how few questions there are, the true rate is very likely inside it. Two systems whose ranges overlap may not really differ.",
    ),
    h("dt", {}, "Triage file"),
    h("dd", {}, "A hand-written note on every miss: what went wrong and why, tagged by cause."),
  );
  return h("div", { attrs: { id: "definitions" } }, h("h3", {}, "What the numbers mean"), list);
}

function floorBox(floor: Floor): HTMLElement {
  const verdict = floor.met ? "Floor met" : "Floor not met";
  return h(
    "div",
    { class: `notice ${floor.met ? "ok" : "error"} floor`, attrs: { "data-met": String(floor.met) } },
    h("strong", {}, `${verdict}${floor.status_note ? ` ${floor.status_note}` : ""}.`),
    h(
      "ul",
      {},
      ...floor.checks.map((check) => {
        const label = METRICS.find((m) => m.key === check.metric)?.label ?? check.metric;
        const value = check.rate.rate === null ? "n/a" : pct(check.rate.rate);
        return h("li", {}, `${label} must be ${check.rule}: it is ${value}, ${check.met ? "met" : "not met"}.`);
      }),
    ),
    floor.cause ? h("p", {}, `Why: ${floor.cause}`) : null,
    floor.next ? h("p", {}, `Next: ${floor.next}`) : null,
  );
}

function missList(misses: Miss[]): HTMLElement {
  const counts = new Map<string, number>();
  for (const miss of misses) counts.set(miss.tag, (counts.get(miss.tag) ?? 0) + 1);
  const tally = [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([tag, n]) => h("li", {}, `${n} × ${tag}: ${TAGS[tag] ?? tag}`));
  return h(
    "details",
    { class: "misses" },
    h("summary", {}, `${misses.length} Askwell ${misses.length === 1 ? "miss" : "misses"}, each with its cause`),
    h("ul", {}, ...tally),
    h(
      "div",
      { class: "scroll" },
      h(
        "table",
        {},
        h("thead", {}, h("tr", {}, ...["Question", "Result", "Cause", "Note"].map((c) => h("th", { attrs: { scope: "col" } }, c)))),
        h(
          "tbody",
          {},
          ...misses.map((m) =>
            h(
              "tr",
              {},
              h("td", {}, h("code", {}, m.item_id)),
              h("td", {}, m.system === "askwell_csv" ? `${m.outcome} (CSV upload)` : m.outcome),
              h("td", {}, m.tag),
              h("td", { class: "note" }, m.note),
            ),
          ),
        ),
      ),
    ),
  );
}

function schemaSection(report: Report, schema: string): HTMLElement {
  const rows = report.table.filter((r) => r.schema === schema);
  const table = h(
    "table",
    { class: "metrics" },
    h("thead", {}, h("tr", {}, h("th", { attrs: { scope: "col" } }, "System"), ...METRICS.map((m) => h("th", { attrs: { scope: "col" } }, m.label)))),
    h(
      "tbody",
      {},
      ...rows.map((r) =>
        h(
          "tr",
          { attrs: { "data-system": r.system, "data-model": r.model } },
          h("th", { attrs: { scope: "row" } }, SYSTEMS[r.system] ?? r.system, h("div", { class: "muted" }, r.model)),
          ...METRICS.map((m) => rateCell(r[m.key])),
        ),
      ),
    ),
  );
  const misses = report.misses.filter((m) => m.schema === schema);
  return h(
    "section",
    { class: "schema", attrs: { "data-schema": schema } },
    h("h4", {}, schemaTitle(schema)),
    ...report.floors.filter((f) => f.schema === schema).map(floorBox),
    h("div", { class: "scroll" }, table),
    misses.length ? missList(misses) : h("p", { class: "muted" }, "Askwell missed nothing here."),
    report.triage_files.includes(schema)
      ? h("p", {}, h("a", { class: "triage", attrs: { href: `/api/triage/${encodeURIComponent(schema)}` } }, `Triage file for ${schema}`))
      : null,
  );
}

function picker(reports: Summary[], current: string): HTMLElement | null {
  if (reports.length < 2) return null;
  const select = h("select", { attrs: { id: "report" } });
  for (const r of reports) {
    const option = h("option", { attrs: { value: r.id } }, `${r.id} (${r.schemas.length} ${r.schemas.length === 1 ? "schema" : "schemas"})`);
    option.selected = r.id === current;
    select.appendChild(option);
  }
  select.addEventListener("change", () => {
    location.href = `?report=${encodeURIComponent(select.value)}#reports`;
  });
  return h("p", { class: "picker" }, h("label", { attrs: { for: "report" } }, "Report"), select);
}

// An export run that has no answers yet carries no simulation mark either, so a missing
// mark means a real model only when the run finished.
function banner(report: Report): HTMLElement {
  if (report.simulation) {
    return h("div", { class: "notice info banner", attrs: { role: "note", id: "simulated" } }, h("strong", {}, "Simulated. "), report.simulation);
  }
  if (report.status === "complete") {
    return h("div", { class: "notice ok banner", attrs: { role: "note" } }, "Measured with a real model.");
  }
  return h(
    "div",
    { class: "notice error banner", attrs: { role: "note" } },
    h("strong", {}, "Not measured. "),
    `This run is ${report.status}, so its numbers cover only the questions answered so far.`,
  );
}

function reportBody(report: Report, reports: Summary[]): HTMLElement[] {
  const schemas = [...new Set(report.table.map((r) => r.schema))];
  return [
    picker(reports, report.run_id),
    banner(report),
    h("h3", { attrs: { id: "report-title" } }, `Benchmark results: ${report.run_id}`),
    h("p", { attrs: { id: "status" } }, `Status: ${report.status}.`),
    h("p", {}, "The whole report as JSON: ", jsonLink(report.run_id), "."),
    h(
      "p",
      {},
      "Each schema is a database with a fixed set of questions. Askwell is compared with a one-shot baseline: the same model writes the SQL itself, and it runs read-only with no check in between.",
    ),
    report.notes.length ? h("ul", { class: "notes" }, ...report.notes.map((n) => h("li", {}, n))) : null,
    definitions(),
    ...schemas.map((schema) => schemaSection(report, schema)),
  ].filter((e): e is HTMLElement => e !== null);
}

function reportsFold(...body: HTMLElement[]): HTMLDetailsElement {
  return fold(
    "reports",
    "Every report, database by database",
    "Execution accuracy is how often the answer matched a checked answer key; refusal recall is how often it turned down a question it should have; a triage file explains each miss.",
    ...body,
  );
}

function openFoldFor(hash: string): void {
  const target = hash ? document.getElementById(decodeURIComponent(hash.slice(1))) : null;
  const holder = target?.closest("details");
  if (holder) holder.open = true;
}

async function start(): Promise<void> {
  const details = h(
    "section",
    { class: "details", attrs: { "aria-labelledby": "details-title" } },
    h("h2", { attrs: { id: "details-title" } }, "The details"),
    h(
      "p",
      {},
      "The technical record behind every figure: where each one comes from, the one release check that failed, and every measurement report with each test database.",
    ),
  );
  let reports: Summary[];
  try {
    reports = await getJson<Summary[]>("/api/reports");
  } catch (err) {
    renderStatement(undefined, undefined);
    append(main, details);
    details.appendChild(
      h("div", { class: "notice error", attrs: { role: "alert" } }, err instanceof Error ? err.message : "The report could not be loaded."),
    );
    return;
  }
  const listed = new Set(reports.map((r) => r.id));
  const [headline, previous, spiderBefore, spiderAfter, csvBefore, csvAfter] = await Promise.all([
    loadIf(listed, HEADLINE),
    loadIf(listed, BEFORE),
    loadIf(listed, GATE.spider.before),
    loadIf(listed, GATE.spider.after),
    loadIf(listed, GATE.csv.before),
    loadIf(listed, GATE.csv.after),
  ]);
  const now = headline.report;
  const before = previous.report;
  renderStatement(now, before);
  append(
    main,
    comparison(now),
    details,
  );
  append(details, sourcesFold(now, before), gateFold(now, before, { spider: [spiderBefore, spiderAfter], csv: [csvBefore, csvAfter] }));

  const wanted = new URLSearchParams(location.search).get("report");
  if (!reports.length) {
    details.appendChild(reportsFold(h("p", {}, "No report has been committed yet.")));
    return;
  }
  const id = wanted ?? (listed.has(HEADLINE) ? HEADLINE : reports[0].id);
  let reportFold: HTMLDetailsElement;
  try {
    reportFold = reportsFold(...reportBody(await load(id), reports));
  } catch (err) {
    reportFold = reportsFold(
      h("div", { class: "notice error", attrs: { role: "alert" } }, err instanceof Error ? err.message : "The report could not be loaded."),
    );
  }
  // A link to one report names it in ?report=, so its fold opens on arrival.
  if (wanted) reportFold.open = true;
  details.appendChild(reportFold);
  openFoldFor(location.hash);
}

window.addEventListener("hashchange", () => openFoldFor(location.hash));
main.addEventListener("click", (event) => {
  const link = (event.target as Element | null)?.closest("a");
  const href = link?.getAttribute("href");
  if (href?.startsWith("#")) openFoldFor(href);
});

void start();
