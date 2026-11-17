import "./tokens.css";
import "./value.css";
import { append, h } from "./dom";
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
  p50_latency_ms: number | null;
  coverage: Rate;
  wrong_answer_rate_given_answered: Rate;
}

interface Report {
  run_id: string;
  simulation: string | null;
  status: string;
  trials?: number;
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
  p50LatencyMs: number | null;
  trials: number;
}

const main = document.getElementById("app") as HTMLElement;
const wait = document.getElementById("sheet-wait") as HTMLElement;

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
    p50LatencyMs: Number.isFinite(row.p50_latency_ms) ? row.p50_latency_ms : null,
    trials: report.trials ?? 1,
  };
}


function fold(id: string, title: string, definition: string, ...body: (HTMLElement | null)[]): HTMLDetailsElement {
  return h(
    "details",
    { class: "fold", attrs: { id } },
    h("summary", {}, title),
    h("div", { class: "fold-body" }, h("p", { class: "fold-def" }, definition), ...body),
  );
}

function measuredFold(seen: Figures, holdout: Figures): HTMLDetailsElement {
  const from = (tag: "span" | "dd", id: string, f: Figures, ...children: (string | HTMLElement)[]) =>
    h(tag, { attrs: { id, "data-source": f.reportId } }, ...children);
  // The counts are answers over every run, so a report run 3 times counts each question 3 times.
  const rate = (r: Rate, value: number, f: Figures) =>
    `${pct(value)} (${r.n} of ${r.of}${f.trials > 1 ? `, over ${f.trials} runs` : ""})`;
  const interval = (f: Figures) => `95% range ${pct(f.wrongInterval[0])} to ${pct(f.wrongInterval[1])}`;
  return fold(
    "measured",
    "Where the measured rates come from",
    "A report is one saved measurement run, kept with the code. Questions it never saw were written blind, so it could not be tuned to them; questions it was tuned on were used while it was built. A 95% range is where the true rate very likely falls, given how few questions there were.",
    h(
      "p",
      {},
      "AI model ",
      from("span", "seen-model", seen, seen.model),
      ". What the AI costs per question: ",
      h("strong", {}, from("span", "cost-per-question", seen, `$${seen.costPerQuestion.toFixed(6)}`)),
      ", from report ",
      from("span", "seen-run-id", seen, seen.reportId),
      ", run on ",
      from("span", "seen-run-date", seen, SOURCE.date),
      ".",
    ),
    holdout.p50LatencyMs === null
      ? null
      : h(
          "p",
          { attrs: { id: "answer-time", "data-source": holdout.reportId } },
          `Answer time: about ${(holdout.p50LatencyMs / 1000).toFixed(1)} seconds, compared with hours or days in someone's queue.`,
          h("span", { class: "muted" }, ` (median over ${holdout.reportId})`),
        ),
    h("h3", {}, "How often it answers, used in the estimate"),
    h(
      "dl",
      { class: "definitions" },
      h("dt", {}, "On questions it never saw (report ", from("span", "holdout-run-id", holdout, holdout.reportId), ", written blind)"),
      from("dd", "holdout-answered", holdout, rate(holdout.answered, holdout.answeredShare, holdout)),
      h("dt", {}, `On questions it was tuned on (report ${seen.reportId})`),
      from("dd", "seen-answered", seen, rate(seen.answered, seen.answeredShare, seen)),
    ),
    h("h3", {}, "Answers it gave that were wrong, shown but not used in the estimate"),
    h(
      "dl",
      { class: "definitions", attrs: { id: "accuracy" } },
      h("dt", {}, "On questions it never saw"),
      from("dd", "holdout-wrong", holdout, `${rate(holdout.wrong, holdout.wrongRate, holdout)}, ${interval(holdout)}`),
      h("dt", {}, "On questions it was tuned on"),
      from("dd", "seen-wrong", seen, `${rate(seen.wrong, seen.wrongRate, seen)}, ${interval(seen)}`),
    ),
    h("p", { class: "muted" }, "These do not feed the formula. Every answer shows its query; the check time is counted."),
    h(
      "ul",
      { class: "muted" },
      h("li", {}, "Model cost is the provider's list price."),
      h("li", {}, "The rates come from one test database (a made-up field-service business), not from your data."),
    ),
  );
}

function formulaFold(): HTMLDetailsElement {
  return fold(
    "formula",
    "How the estimate is worked out",
    "Net value is what the time saved is worth, plus any savings you expect from findings, minus what it costs to run.",
    h(
      "ul",
      {},
      h("li", {}, "Running cost: every question costs the model price, plus hosting."),
      h("li", {}, "Answered: the questions Askwell answers instead of refusing."),
      h("li", {}, "Time saved: for each answered question, the time to answer it by hand minus the time to check Askwell's answer."),
      h("li", {}, "Value of time: the time saved at the person's cost per hour."),
      h("li", {}, "Findings: what you estimate you save each month from things you find and act on. It adds straight to net value; at $0 it changes nothing."),
      h("li", {}, "Net value a month: value of time, plus findings, minus running cost."),
      h("li", {}, "A wrong answer has no separate cost here. Every answer shows its query; the check time is counted."),
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
        "net value     = value of time + findings − running cost",
      ].join("\n"),
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
    spec.note ? h("p", { class: "line-note" }, spec.note) : null,
    h("p", { class: "line-note" }, `Example, replace with your own: ${example}. From ${spec.min} to ${spec.max}.`),
    h("div", { class: "value-controls" }, slider, box),
  );
}

function assumptions(seen: Figures, holdout: Figures): HTMLElement {
  return h(
    "div",
    { class: "assumed", attrs: { "aria-labelledby": "assumed-title", role: "group" } },
    h("h3", { class: "label", attrs: { id: "assumed-title" } }, "Assumed"),
    h(
      "ul",
      {},
      h("li", {}, "The AI costs ", h("strong", { class: "rate" }, `$${seen.costPerQuestion.toFixed(6)}`), " a question, at the provider's list price."),
      h(
        "li",
        {},
        "It answers ",
        h("strong", { class: "rate" }, pct(holdout.answeredShare)),
        " of the questions your data can answer, as measured on questions it had never seen. The rest go back to a person and save nothing.",
      ),
      h("li", {}, "A wrong answer costs nothing extra: every answer shows its query, and your minutes to check each one are counted."),
      h("li", {}, "Both rates were measured on one made-up business's database, not on yours."),
    ),
    h(
      "p",
      { class: "assumed-foot" },
      h("a", { attrs: { href: "#formula" } }, "How the estimate is worked out"),
      h("a", { attrs: { href: "#measured" } }, "Where the rates come from"),
    ),
  );
}

function render(seen: Figures, holdout: Figures): void {
  const state = Object.fromEntries(INPUTS.map((s) => [s.key, s.example])) as unknown as ReaderInputs;
  const results = h("section", { class: "sheet-figures", attrs: { id: "results", "aria-live": "polite", "aria-labelledby": "results-title" } });

  const line = (label: string, id: string) => {
    const cell = h("td", { attrs: { id } });
    return { cell, row: h("tr", {}, h("th", { attrs: { scope: "row" } }, label), cell) };
  };
  const running = line("Running cost", "out-running-cost");
  const answered = line("Questions answered", "out-answered");
  const hoursSaved = line("Hours saved", "out-hours-saved");
  const valueOfTime = line("Value of the time saved", "out-value-of-time");
  const findings = line("Savings from findings (your estimate)", "out-findings");
  const net = h("td", { attrs: { id: "out-net" } });
  const atUnseenText = h("strong", { attrs: { id: "out-range-unseen" } });
  const atTunedText = h("strong", { attrs: { id: "out-range-tuned" } });
  // Built once and only its figures rewritten, so a screen reader hears the figures that
  // changed rather than the whole region on every keystroke.
  append(
    results,
    h(
      "table",
      { class: "sheet-ledger" },
      h(
        "tbody",
        {},
        running.row,
        answered.row,
        hoursSaved.row,
        valueOfTime.row,
        findings.row,
        h("tr", { class: "total" }, h("th", { attrs: { scope: "row" } }, "Net value each month"), net),
      ),
    ),
    h(
      "p",
      { class: "sheet-range", attrs: { id: "out-range" } },
      "Net value a month is ",
      atUnseenText,
      ` on questions it never saw (it answered ${pct(holdout.answeredShare)}) and `,
      atTunedText,
      ` on questions it was tuned on (it answered ${pct(seen.answeredShare)}).`,
    ),
  );

  const update = () => {
    const out = monthly(state, { costPerQuestion: seen.costPerQuestion, answeredShare: holdout.answeredShare });
    const [atUnseen, atTuned] = range(state, {
      costPerQuestion: seen.costPerQuestion,
      answeredShares: [holdout.answeredShare, seen.answeredShare],
    });
    running.cell.textContent = money(out.runningCost);
    // Whole questions on screen; the formula keeps the fraction.
    answered.cell.textContent = number(Math.round(out.answered), 0);
    hoursSaved.cell.textContent = number(out.hoursSaved);
    valueOfTime.cell.textContent = money(out.valueOfTime);
    findings.cell.textContent = money(out.findings);
    net.textContent = money(out.net);
    atUnseenText.textContent = money(atUnseen);
    atTunedText.textContent = money(atTuned);
  };

  const worksheet = h(
    "div",
    { class: "worksheet" },
    h(
      "section",
      { class: "sheet-inputs", attrs: { id: "inputs", "aria-labelledby": "inputs-title" } },
      h("div", { class: "sheet-head" }, h("h2", { class: "label", attrs: { id: "inputs-title" } }, "Your numbers")),
      h("p", { class: "sheet-note" }, "Every number here is an example. Replace each with your own."),
      ...INPUTS.map((spec) => inputControl(spec, state, update)),
    ),
    h(
      "div",
      { class: "sheet-side" },
      h(
        "div",
        { class: "sheet-statement" },
        h("div", { class: "sheet-head red" }, h("h2", { class: "label", attrs: { id: "results-title" } }, "Each month, at your numbers"), h("span", { class: "label sheet-mark" }, "Estimate")),
        results,
        assumptions(seen, holdout),
      ),
    ),
  );
  const details = h(
    "section",
    { class: "details", attrs: { "aria-labelledby": "details-title" } },
    h("h2", { attrs: { id: "details-title" } }, "The details"),
    h("p", {}, "The working behind the estimate, and the record each measured rate is read from."),
    formulaFold(),
    measuredFold(seen, holdout),
  );
  wait.replaceWith(worksheet);
  append(main, details);
  update();
}

function openFoldFor(hash: string): void {
  const target = hash ? document.getElementById(decodeURIComponent(hash.slice(1))) : null;
  const holder = target?.closest("details");
  if (holder) holder.open = true;
}

async function start(): Promise<void> {
  try {
    const [seen, holdout] = await Promise.all([getReport(SOURCE.seen), getReport(SOURCE.holdout)]);
    render(figures(seen), figures(holdout));
    openFoldFor(location.hash);
  } catch (err) {
    wait.replaceWith(
      h("div", { class: "notice error", attrs: { role: "alert" } }, err instanceof Error ? err.message : "The reports could not be loaded."),
    );
  }
}

window.addEventListener("hashchange", () => openFoldFor(location.hash));
main.addEventListener("click", (event) => {
  const link = (event.target as Element | null)?.closest("a");
  const href = link?.getAttribute("href");
  if (href?.startsWith("#")) openFoldFor(href);
});

void start();
