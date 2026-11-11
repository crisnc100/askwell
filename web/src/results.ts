import "./style.css";
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
  table: Row[];
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
  ledgerline: "Ledgerline",
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

const app = document.getElementById("app") as HTMLElement;

function pct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
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

function header(): HTMLElement {
  return h(
    "header",
    {},
    h("p", { class: "brand" }, "Ledgerline"),
    h("p", { class: "tagline" }, "How often it answers, how often it is right, and how often it refuses."),
    h("p", {}, h("a", { attrs: { href: "/" } }, "Ask about your own data")),
  );
}

function definitions(): HTMLElement {
  const list = h("dl", { class: "definitions" });
  for (const metric of METRICS) {
    append(
      list,
      h("dt", {}, `${metric.label} (${metric.better} is better)`),
      h("dd", {}, metric.definition),
    );
  }
  append(
    list,
    h("dt", {}, "Gold answer"),
    h("dd", {}, "The rows a hand-written, checked SQL query returns for the question. The questions and gold answers were fixed before Ledgerline's code was written."),
    h("dt", {}, "Range"),
    h(
      "dd",
      {},
      "The 95% Wilson interval: given how few questions there are, the true rate is very likely inside it. Two systems whose ranges overlap may not really differ.",
    ),
  );
  return h("section", { attrs: { id: "definitions" } }, h("h2", {}, "What the numbers mean"), list);
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
    h("summary", {}, `${misses.length} Ledgerline ${misses.length === 1 ? "miss" : "misses"}, each with its cause`),
    h("ul", {}, ...tally),
    h(
      "table",
      {},
      h("thead", {}, h("tr", {}, ...["Question", "Result", "Cause", "Note"].map((c) => h("th", {}, c)))),
      h(
        "tbody",
        {},
        ...misses.map((m) =>
          h("tr", {}, h("td", {}, h("code", {}, m.item_id)), h("td", {}, m.outcome), h("td", {}, m.tag), h("td", {}, m.note)),
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
    h(
      "thead",
      {},
      h("tr", {}, h("th", {}, "System"), ...METRICS.map((m) => h("th", {}, m.label))),
    ),
    h(
      "tbody",
      {},
      ...rows.map((row) =>
        h(
          "tr",
          { attrs: { "data-system": row.system } },
          h("th", { attrs: { scope: "row" } }, SYSTEMS[row.system] ?? row.system, h("div", { class: "muted" }, row.model)),
          ...METRICS.map((m) => rateCell(row[m.key])),
        ),
      ),
    ),
  );
  const misses = report.misses.filter((m) => m.schema === schema);
  return h(
    "section",
    { class: "schema", attrs: { "data-schema": schema } },
    h("h2", {}, schemaTitle(schema)),
    ...report.floors.filter((f) => f.schema === schema).map(floorBox),
    h("div", { class: "scroll" }, table),
    misses.length ? missList(misses) : h("p", { class: "muted" }, "Ledgerline missed nothing here."),
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
    location.search = `?report=${encodeURIComponent(select.value)}`;
  });
  return h("p", {}, h("label", { attrs: { for: "report" } }, "Report"), select);
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(response.status === 404 ? "No report has that name." : "The report could not be loaded.");
  return (await response.json()) as T;
}

async function start(): Promise<void> {
  clear(app);
  append(app, header());
  const main = h("main");
  app.appendChild(main);
  try {
    const reports = await getJson<Summary[]>("/api/reports");
    if (!reports.length) {
      append(main, h("h1", {}, "Benchmark results"), h("p", {}, "No report has been committed yet."));
      return;
    }
    const wanted = new URLSearchParams(location.search).get("report");
    const id = wanted ?? reports[0].id;
    const report = await getJson<Report>(`/api/reports/${encodeURIComponent(id)}`);
    append(
      main,
      report.simulation
        ? h("div", { class: "notice info banner", attrs: { role: "note", id: "simulated" } }, h("strong", {}, "Simulated. "), report.simulation)
        : h("div", { class: "notice ok banner", attrs: { role: "note" } }, "Measured with a real model."),
      h("h1", {}, `Benchmark results: ${report.run_id}`),
      picker(reports, report.run_id),
      h(
        "p",
        {},
        "Each schema is a database with a fixed set of questions. Ledgerline is compared with a one-shot baseline: the same model writes the SQL itself, and it runs read-only with no check in between.",
      ),
      report.notes.length ? h("ul", { class: "notes" }, ...report.notes.map((n) => h("li", {}, n))) : null,
      definitions(),
    );
    const schemas = [...new Set(report.table.map((r) => r.schema))];
    for (const schema of schemas) main.appendChild(schemaSection(report, schema));
  } catch (err) {
    main.prepend(h("div", { class: "notice error", attrs: { role: "alert" } }, err instanceof Error ? err.message : "The report could not be loaded."));
  }
}

void start();
