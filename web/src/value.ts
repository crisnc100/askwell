import "./style.css";
import { append, clear, h } from "./dom";
import { clamp, INPUTS, type InputSpec, monthly, range, type ReaderInputs } from "./value-formula";
import { SOURCE } from "./value-source";

interface Rate {
  n: number;
  of: number;
  rate: number | null;
  ci95: [number, number] | null;
}

interface Row {
  system: string;
  model: string;
  mean_cost_usd: number;
  coverage: Rate;
  wrong_answer_rate_given_answered: Rate;
}

interface Report {
  run_id: string;
  simulation: string | null;
  status: string;
  table: Row[];
}

interface Figures {
  reportId: string;
  model: string;
  costPerQuestion: number;
  answeredShare: number;
  answered: Rate;
  wrongRate: number;
  wrongInterval: [number, number];
  wrong: Rate;
}

const app = document.getElementById("app") as HTMLElement;

// Every figure goes through these, so a bad value shows as "n/a", never NaN or Infinity.
function money(value: number): string {
  if (!Number.isFinite(value)) return "n/a";
  const text = Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${value < 0 ? "−" : ""}$${text}`;
}

function number(value: number, digits = 1): string {
  if (!Number.isFinite(value)) return "n/a";
  return value.toLocaleString("en-US", { maximumFractionDigits: digits });
}

function pct(value: number): string {
  return Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "n/a";
}

async function getReport(id: string): Promise<Report> {
  const response = await fetch(`/api/reports/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error(`The report ${id} could not be loaded.`);
  return (await response.json()) as Report;
}

function figures(report: Report): Figures {
  const row = report.table.find((r) => r.system === "ledgerline" && r.model === SOURCE.model);
  const answered = row?.coverage;
  const wrong = row?.wrong_answer_rate_given_answered;
  if (
    report.simulation !== null ||
    !row ||
    !Number.isFinite(row.mean_cost_usd) ||
    answered?.rate == null ||
    wrong?.rate == null ||
    wrong.ci95 === null
  ) {
    throw new Error(`The report ${report.run_id} has no measured Askwell row for ${SOURCE.model}.`);
  }
  return {
    reportId: report.run_id,
    model: row.model,
    costPerQuestion: row.mean_cost_usd,
    answeredShare: answered.rate,
    answered,
    wrongRate: wrong.rate,
    wrongInterval: wrong.ci95,
    wrong,
  };
}

function header(): HTMLElement {
  return h(
    "header",
    {},
    h("p", { class: "brand" }, "Askwell"),
    h("p", { class: "tagline" }, "What it would cost to run, and what it could be worth to you."),
    h("p", {}, h("a", { attrs: { href: "/" } }, "Ask about your own data"), " · ", h("a", { attrs: { href: "/results/" } }, "Benchmark results")),
  );
}

function measuredSection(seen: Figures, holdout: Figures): HTMLElement {
  const cell = (id: string, source: string, ...children: (string | HTMLElement)[]) =>
    h("td", { attrs: { id, "data-source": source } }, ...children);
  const rateCell = (id: string, f: Figures, rate: Rate, value: number, interval?: [number, number]) =>
    cell(
      id,
      f.reportId,
      h("strong", {}, pct(value)),
      h("div", { class: "muted" }, `${rate.n} of ${rate.of}`),
      interval ? h("div", { class: "muted" }, `95% range ${pct(interval[0])} to ${pct(interval[1])}`) : "",
    );
  return h(
    "section",
    { attrs: { id: "measured" } },
    h("h2", {}, "Measured, from a committed report"),
    h(
      "p",
      {},
      `Model ${seen.model}. The main figures are measured on the seen questions (report ${seen.reportId}, run date ${SOURCE.date}). `,
      `The held-out questions (report ${holdout.reportId}) were written blind and never seen while Askwell was built, so their rates are the stricter figure.`,
    ),
    h(
      "div",
      { class: "scroll" },
      h(
        "table",
        {},
        h(
          "thead",
          {},
          h("tr", {}, h("th", {}, ""), h("th", { attrs: { scope: "col" } }, "Seen questions"), h("th", { attrs: { scope: "col" } }, "Held-out questions (stricter)")),
        ),
        h(
          "tbody",
          {},
          h("tr", {}, h("th", { attrs: { scope: "row" } }, "Report"), cell("seen-run-id", seen.reportId, seen.reportId), cell("holdout-run-id", holdout.reportId, holdout.reportId)),
          h("tr", {}, h("th", { attrs: { scope: "row" } }, "Model"), cell("seen-model", seen.reportId, seen.model), cell("holdout-model", holdout.reportId, holdout.model)),
          h("tr", {}, h("th", { attrs: { scope: "row" } }, "Run date"), cell("seen-run-date", seen.reportId, SOURCE.date), cell("holdout-run-date", holdout.reportId, SOURCE.date)),
          h(
            "tr",
            {},
            h("th", { attrs: { scope: "row" } }, "Model cost per question"),
            cell("cost-per-question", seen.reportId, `$${seen.costPerQuestion.toFixed(6)}`),
            cell("holdout-cost-per-question", holdout.reportId, `$${holdout.costPerQuestion.toFixed(6)}`, h("div", { class: "muted" }, "shown only; the calculator uses the seen cost")),
          ),
          h(
            "tr",
            {},
            h("th", { attrs: { scope: "row" } }, "Answered share (of answerable questions)"),
            rateCell("seen-answered", seen, seen.answered, seen.answeredShare),
            rateCell("holdout-answered", holdout, holdout.answered, holdout.answeredShare),
          ),
          h(
            "tr",
            {},
            h("th", { attrs: { scope: "row" } }, "Wrong answers among answered"),
            rateCell("seen-wrong", seen, seen.wrong, seen.wrongRate, seen.wrongInterval),
            rateCell("holdout-wrong", holdout, holdout.wrong, holdout.wrongRate, holdout.wrongInterval),
          ),
        ),
      ),
    ),
    h(
      "ul",
      { class: "muted" },
      h("li", {}, "The cost is the model's list price. Cristian's API credits are not counted."),
      h("li", {}, "The rates come from one benchmark schema (a synthetic field-service business), not from your data."),
    ),
  );
}

function inputControl(spec: InputSpec, state: ReaderInputs, onChange: () => void): HTMLElement {
  const sliderId = `${spec.key}-slider`;
  const boxId = `${spec.key}-number`;
  const unit = spec.unit === "usd" ? " (US dollars)" : spec.unit === "minutes" ? " (minutes)" : "";
  const example = spec.unit === "usd" ? `$${spec.example}` : String(spec.example);
  const attrs = { min: String(spec.min), max: String(spec.max), step: String(spec.step), value: String(state[spec.key]) };
  const slider = h("input", { attrs: { ...attrs, type: "range", id: sliderId, "data-key": spec.key } });
  const box = h("input", {
    attrs: { ...attrs, type: "number", id: boxId, inputmode: "decimal", "aria-label": `${spec.label}${unit}, as a number`, "data-key": spec.key },
  });
  slider.addEventListener("input", () => {
    state[spec.key] = clamp(Number(slider.value), spec.min, spec.max);
    box.value = String(state[spec.key]);
    onChange();
  });
  box.addEventListener("input", () => {
    const typed = Number(box.value);
    if (box.value.trim() === "" || Number.isNaN(typed)) return;
    state[spec.key] = clamp(typed, spec.min, spec.max);
    slider.value = String(state[spec.key]);
    onChange();
  });
  // An empty, unreadable or out-of-range entry is put back to the value in use.
  box.addEventListener("change", () => {
    box.value = String(state[spec.key]);
  });
  return h(
    "div",
    { class: "value-input" },
    h("label", { attrs: { for: sliderId } }, `${spec.label}${unit}`),
    h("p", { class: "muted example" }, `Example, replace with your own: ${example}. From ${spec.min} to ${spec.max}.`),
    h("div", { class: "value-controls" }, slider, box),
  );
}

function formulaSection(): HTMLElement {
  return h(
    "section",
    { attrs: { id: "formula" } },
    h("h2", {}, "The formula"),
    h(
      "ul",
      {},
      h("li", {}, "Running cost: every question costs the model price, plus hosting."),
      h("li", {}, "Answered: the questions Askwell answers instead of refusing."),
      h("li", {}, "Time saved: for each answered question, the time to answer it by hand minus the time to check Askwell's answer."),
      h("li", {}, "Value of time: the time saved at the person's cost per hour."),
      h("li", {}, "Risk: the answered questions that are wrong, each costing what a wrong answer costs."),
      h("li", {}, "Net value a month: value of time, minus risk, minus running cost."),
      h("li", {}, "A refused question goes back to a person, so it saves nothing. Its model cost is already in cost per question."),
    ),
    h(
      "pre",
      {},
      [
        "running cost  = questions × cost per question + hosting",
        "answered      = questions × answered share",
        "time saved    = answered × (minutes by hand − minutes to check) ÷ 60",
        "value of time = time saved × cost per hour",
        "risk          = answered × wrong-answer rate × cost of a wrong answer",
        "net value     = value of time − risk − running cost",
      ].join("\n"),
    ),
  );
}

function render(seen: Figures, holdout: Figures): void {
  const state = Object.fromEntries(INPUTS.map((s) => [s.key, s.example])) as unknown as ReaderInputs;
  const results = h("section", { attrs: { id: "results", "aria-live": "polite" } });

  const update = () => {
    const out = monthly(state, seen);
    const [atLow, atHigh] = range(state, {
      costPerQuestion: seen.costPerQuestion,
      answeredShare: holdout.answeredShare,
      wrongInterval: holdout.wrongInterval,
    });
    const line = (label: string, id: string, value: string) =>
      h("tr", {}, h("th", { attrs: { scope: "row" } }, label), h("td", { attrs: { id } }, value));
    clear(results);
    append(
      results,
      h("h2", {}, "Each month"),
      h("p", { class: "muted" }, `At the rates measured on the seen questions (${seen.reportId}).`),
      h(
        "table",
        {},
        h(
          "tbody",
          {},
          line("Running cost", "out-running-cost", money(out.runningCost)),
          line("Questions answered", "out-answered", number(out.answered)),
          line("Hours saved", "out-hours-saved", number(out.hoursSaved)),
          line("Value of the time saved", "out-value-of-time", money(out.valueOfTime)),
          line("Risk from wrong answers", "out-risk", money(out.risk)),
          line("Net value", "out-net", money(out.net)),
        ),
      ),
      h("h2", {}, "On the held-out questions"),
      h(
        "p",
        { attrs: { id: "out-range" } },
        `With the held-out answered share (${pct(holdout.answeredShare)}) and its wrong-answer rate anywhere in its 95% range, net value a month is between `,
        h("strong", { attrs: { id: "out-range-high" } }, money(atHigh)),
        ` (wrong-answer rate ${pct(holdout.wrongInterval[1])}) and `,
        h("strong", { attrs: { id: "out-range-low" } }, money(atLow)),
        ` (${pct(holdout.wrongInterval[0])}).`,
      ),
      h(
        "p",
        { class: "muted" },
        "This is the stricter figure. Askwell answers fewer of the held-out questions and gets more of them wrong, so it can sit well below the seen figure above.",
      ),
    );
  };

  const inputs = h(
    "section",
    { attrs: { id: "inputs" } },
    h("h2", {}, "Your numbers"),
    h("p", { class: "muted" }, "Every number here is an example. Replace each with your own."),
    ...INPUTS.map((spec) => inputControl(spec, state, update)),
  );
  append(app.querySelector("main") as HTMLElement, measuredSection(seen, holdout), inputs, results, formulaSection());
  update();
}

async function start(): Promise<void> {
  clear(app);
  const main = h("main", {}, h("h1", {}, "What Askwell could be worth to you"));
  append(app, header(), main);
  try {
    const [seen, holdout] = await Promise.all([getReport(SOURCE.seen), getReport(SOURCE.holdout)]);
    render(figures(seen), figures(holdout));
  } catch (err) {
    append(
      main,
      h("div", { class: "notice error", attrs: { role: "alert" } }, err instanceof Error ? err.message : "The reports could not be loaded."),
    );
  }
}

void start();
