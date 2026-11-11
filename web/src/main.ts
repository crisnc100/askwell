import "./style.css";
import {
  api,
  ApiError,
  type Answer,
  type Edits,
  type Field,
  type FieldEdit,
  type Status,
  useWorkspace,
} from "./api";
import { append, clear, h, type Child } from "./dom";

type Step = "prepare" | "upload" | "check" | "confirm" | "ask";

const STEPS: { id: Step; label: string }[] = [
  { id: "prepare", label: "Prepare" },
  { id: "upload", label: "Upload" },
  { id: "check", label: "Check" },
  { id: "confirm", label: "Confirm" },
  { id: "ask", label: "Ask" },
];

const DEFAULT_TIME_ZONE = "America/New_York";
const PRIVACY =
  "Don't upload personal data. Uploads are deleted after 7 days. Shared field values go to a third-party model.";

const app = document.getElementById("app") as HTMLElement;
let status: Status | null = null;
let step: Step = "prepare";
let edits: Edits = { fields: {} };
// Messages to show at the top of the next page drawn (an upload batch with a refusal).
let notices: string[] = [];

// The workspace link is "/#ws=<id>". A fragment never reaches the server, so the id is
// not in any access log, and Referrer-Policy keeps it from leaking to other sites.
function idFromHash(): string | null {
  const match = /(?:^#|&)ws=([0-9a-f]{32})(?:&|$)/.exec(location.hash);
  return match ? match[1] : null;
}

function workspaceLink(id: string): string {
  return `${location.origin}/#ws=${id}`;
}

function reachable(target: Step): boolean {
  if (target === "prepare") return true;
  if (!status) return false;
  if (target === "upload") return status.state !== "confirmed";
  if (target === "check") return status.state !== "confirmed" && status.files.length > 0;
  if (target === "confirm") return status.state !== "new";
  return status.state === "confirmed";
}

function stepFor(current: Status): Step {
  if (current.state === "confirmed") return "ask";
  if (current.state === "checked") return "confirm";
  return current.check ? "check" : "upload";
}

function go(target: Step): void {
  step = target;
  render();
}

function render(): void {
  clear(app);
  append(app, header(), nav());
  const main = h("main", { attrs: { "data-step": step } });
  app.appendChild(main);
  for (const message of notices) main.appendChild(notice("error", message));
  notices = [];
  const pages: Record<Step, () => Promise<void> | void> = {
    prepare: () => preparePage(main),
    upload: () => uploadPage(main),
    check: () => checkPage(main),
    confirm: () => confirmPage(main),
    ask: () => askPage(main),
  };
  void Promise.resolve(pages[step]()).catch((err: unknown) => showError(main, err));
}

function header(): HTMLElement {
  return h(
    "header",
    {},
    h("p", { class: "brand" }, "Ledgerline"),
    h("p", { class: "tagline" }, "Ask questions about your own data. See the SQL behind every answer."),
  );
}

function nav(): HTMLElement {
  const list = h("ol", { class: "steps" });
  for (const item of STEPS) {
    const button = h(
      "button",
      {
        attrs: { type: "button", "aria-current": item.id === step ? "step" : "false" },
        on: { click: () => go(item.id) },
      },
      item.label,
    );
    button.disabled = !reachable(item.id);
    list.appendChild(h("li", {}, button));
  }
  return h("nav", { attrs: { "aria-label": "Steps" } }, list);
}

function notice(kind: "error" | "info" | "ok", ...children: Child[]): HTMLElement {
  return h("div", { class: `notice ${kind}`, attrs: { role: kind === "error" ? "alert" : "status" } }, ...children);
}

function showError(where: HTMLElement, err: unknown): void {
  const message = err instanceof ApiError ? err.message : "Something went wrong. Try again in a minute.";
  where.prepend(notice("error", message));
}

function workspaceBox(): HTMLElement | null {
  if (!status) return null;
  const expires = new Date(status.expires_at).toLocaleString();
  const link = workspaceLink(status.id);
  const remove = h(
    "button",
    {
      class: "danger",
      attrs: { type: "button" },
      on: {
        click: async () => {
          if (!confirm("Delete this workspace and every file in it? This cannot be undone.")) return;
          try {
            await api.remove_workspace();
          } catch (err) {
            showError(app.querySelector("main") as HTMLElement, err);
            return;
          }
          status = null;
          useWorkspace(null);
          history.replaceState(null, "", "/");
          go("prepare");
        },
      },
    },
    "Delete my data",
  );
  return h(
    "section",
    { class: "workspace" },
    h("p", {}, "Bookmark this link to come back to your workspace. Anyone with it can see your data."),
    h("p", {}, h("code", { class: "link" }, link)),
    h("p", { class: "muted" }, `Your files are deleted on ${expires} unless you use the workspace again before then.`),
    remove,
  );
}

// Prepare ------------------------------------------------------------------------------

async function preparePage(main: HTMLElement): Promise<void> {
  append(
    main,
    h("h1", {}, "Prepare your data"),
    h(
      "p",
      {},
      "Ledgerline reads CSV files, one table per file. Check runs every rule below and tells you the row, the column and the fix for anything it cannot read.",
    ),
    h(
      "ul",
      { class: "rules" },
      h("li", {}, "One table per CSV file, with a header row of column names. The file name becomes the table name."),
      h("li", {}, "UTF-8 text, separated by commas (not semicolons). A value with a comma or a line break goes in quotes."),
      h("li", {}, "Each table has an ID column named id or <table>_id, with one unique value per row. A table that only links two others needs no ID."),
      h("li", {}, "A column named <table>_id links to that table (customer_id links to customers)."),
      h("li", {}, "Dates are YYYY-MM-DD (2025-03-04); times are YYYY-MM-DD HH:MM, with no time zone."),
      h("li", {}, "Numbers are plain: 1234.50, not 1,234.50, $1234.50 or 45%."),
      h("li", {}, "Blank, NULL, NA, N/A and - all mean no value."),
      h("li", {}, "At most 10 files of 10 MB each, 200 columns and 1,000,000 rows per file."),
    ),
    h("h2", {}, "A worked example"),
    h("p", {}, "orders.csv links each order to a customer through customer_id:"),
    exampleTable(["id", "customer_id", "order_date", "status", "shipping_cost"], [
      ["1001", "7", "2026-03-24", "paid", "9.5"],
      ["1002", "10", "2025-09-29", "shipped", "0"],
    ]),
    h("p", {}, "customers.csv has the id that customer_id points to:"),
    exampleTable(["id", "name", "city", "segment", "signup_date"], [
      ["7", "Northwind Bikes", "Riverton", "retail", "2025-02-11"],
      ["10", "Orchard Market", "Lakeside", "wholesale", "2025-06-30"],
    ]),
    h(
      "p",
      {},
      "Try it with the sample shop data: ",
      ...["customers.csv", "orders.csv", "order_items.csv", "products.csv"].flatMap((name, i) => [
        i ? ", " : "",
        h("a", { attrs: { href: `/sample/${name}`, download: name } }, name),
      ]),
      ".",
    ),
    h("p", { class: "privacy" }, PRIVACY),
  );
  if (status) {
    append(main, h("button", { attrs: { type: "button" }, on: { click: () => go(stepFor(status as Status)) } }, "Back to your workspace"));
    return;
  }
  const select = h("select", { attrs: { id: "time-zone" } });
  const start = h("button", { attrs: { type: "button" } }, "Start a workspace");
  append(
    main,
    h("h2", {}, "Start"),
    h("label", { attrs: { for: "time-zone" } }, "Your time zone (for questions like “last month”)"),
    select,
    start,
  );
  start.addEventListener("click", async () => {
    start.disabled = true;
    try {
      status = await api.create(select.value || DEFAULT_TIME_ZONE);
      useWorkspace(status.id);
      history.replaceState(null, "", `/#ws=${status.id}`);
      go("upload");
    } catch (err) {
      start.disabled = false;
      showError(main, err);
    }
  });
  const zones = await api.timeZones();
  for (const zone of zones) {
    const option = h("option", { attrs: { value: zone } }, zone);
    option.selected = zone === DEFAULT_TIME_ZONE;
    select.appendChild(option);
  }
}

function exampleTable(columns: string[], rows: string[][]): HTMLElement {
  return h(
    "table",
    { class: "example" },
    h("thead", {}, h("tr", {}, ...columns.map((c) => h("th", {}, c)))),
    h("tbody", {}, ...rows.map((r) => h("tr", {}, ...r.map((v) => h("td", {}, v))))),
  );
}

// Upload -------------------------------------------------------------------------------

function uploadPage(main: HTMLElement): void {
  const current = status as Status;
  const input = h("input", { attrs: { type: "file", id: "files", accept: ".csv,text/csv", multiple: "" } });
  const progress = h("div", { attrs: { "aria-live": "polite" } });
  input.addEventListener("change", async () => {
    const files = Array.from(input.files ?? []);
    clear(progress);
    // Every file is tried; the accepted ones are listed and the refused ones explained.
    for (const file of files) {
      append(progress, h("p", { class: "muted" }, `Uploading ${file.name}…`));
      try {
        status = await api.upload(file);
      } catch (err) {
        notices.push(`${file.name}: ${err instanceof ApiError ? err.message : "upload failed"}`);
      }
    }
    render();
  });
  const list = h("ul", { class: "files" });
  for (const file of current.files) {
    list.appendChild(
      h(
        "li",
        {},
        h("span", { class: "file-name" }, file.name),
        h("span", { class: "muted" }, ` ${formatBytes(file.bytes)} `),
        h(
          "button",
          {
            class: "link-button",
            attrs: { type: "button", "aria-label": `Remove ${file.name}` },
            on: {
              click: async () => {
                status = await api.remove(file.name);
                render();
              },
            },
          },
          "Remove",
        ),
      ),
    );
  }
  const check = h("button", { attrs: { type: "button" }, on: { click: () => runCheck(main, check) } }, "Check my files");
  check.disabled = current.files.length === 0;
  append(
    main,
    h("h1", {}, "Upload your files"),
    h("p", { class: "privacy" }, PRIVACY),
    h("label", { attrs: { for: "files" } }, "Choose CSV files (a file with the same name replaces the old one)"),
    input,
    progress,
    current.files.length ? list : h("p", { class: "muted" }, "No files yet."),
    check,
    workspaceBox(),
  );
}

async function runCheck(main: HTMLElement, button: HTMLButtonElement): Promise<void> {
  button.disabled = true;
  try {
    status = await api.check();
    go("check");
  } catch (err) {
    button.disabled = false;
    showError(main, err);
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// Check --------------------------------------------------------------------------------

function checkPage(main: HTMLElement): void {
  const current = status as Status;
  append(main, h("h1", {}, "Check"));
  if (!current.check) {
    const run = h("button", { attrs: { type: "button" }, on: { click: () => runCheck(main, run) } }, "Check my files");
    append(main, h("p", {}, "Check reads every file and lists anything that needs fixing."), run);
    return;
  }
  const report = current.check;
  if (report.ok) {
    append(
      main,
      notice("ok", "Every file passed and your data is loaded."),
      h("button", { attrs: { type: "button" }, on: { click: () => go("confirm") } }, "Next: confirm your fields"),
    );
  } else {
    const failing = report.files.filter((f) => !f.ok).length;
    append(
      main,
      notice(
        "error",
        `${failing} ${failing === 1 ? "file needs" : "files need"} fixing. Nothing was loaded. Fix the file, then upload it again with the same name.`,
      ),
      h("button", { attrs: { type: "button" }, on: { click: () => go("upload") } }, "Back to upload"),
    );
  }
  for (const file of report.files) {
    const card = h(
      "section",
      { class: `file-report ${file.ok ? "pass" : "fail"}`, attrs: { "data-file": file.name } },
      h(
        "h2",
        {},
        h("span", { class: "badge" }, file.ok ? "Passed" : "Needs fixing"),
        " ",
        file.name,
      ),
      h("p", { class: "muted" }, `Table ${file.table ?? "?"}: ${file.rows} rows, ${file.columns} columns.`),
    );
    if (file.problems.length) {
      const list = h("ul", { class: "problems" });
      for (const p of file.problems) {
        const where = [p.row !== null ? `Row ${p.row}` : null, p.column !== null ? `column ${p.column}` : null]
          .filter(Boolean)
          .join(", ");
        list.appendChild(
          h(
            "li",
            { class: p.level },
            h("strong", {}, p.level === "error" ? "Error" : "Warning"),
            where ? ` — ${where}: ` : " — ",
            p.message,
            ". ",
            h("span", { class: "fix" }, `Fix: ${p.fix}.`),
          ),
        );
      }
      card.appendChild(list);
      if (file.more_text) card.appendChild(h("p", { class: "muted" }, file.more_text));
    }
    main.appendChild(card);
  }
  append(main, workspaceBox());
}

// Confirm ------------------------------------------------------------------------------

async function confirmPage(main: HTMLElement): Promise<void> {
  const data = await api.fields();
  // The edits are the one source of truth: they start as the fields' current state, the
  // boxes are drawn from them, and the preview and Confirm send exactly them.
  edits = { fields: {} };
  for (const table of data.tables) {
    for (const field of table.fields) {
      edits.fields[field.key] = {
        hidden: field.hidden,
        description: field.description,
        share_values: field.share_values && !field.hidden,
      };
    }
  }
  const preview = h("pre", { class: "prompt", attrs: { id: "prompt-preview", "aria-live": "polite" } });
  let timer: number | undefined;
  let latest = 0;
  const refresh = (): void => {
    window.clearTimeout(timer);
    timer = window.setTimeout(async () => {
      const request = ++latest;
      try {
        const result = await api.preview(edits);
        // An older request that answers late never replaces a newer preview.
        if (request === latest) preview.textContent = result.prompt;
      } catch (err) {
        if (request === latest) showError(main, err);
      }
    }, 250);
  };
  const edit = (key: string, change: Partial<FieldEdit>): void => {
    edits.fields[key] = { ...(edits.fields[key] ?? {}), ...change };
    refresh();
  };
  append(
    main,
    h("h1", {}, "Confirm what the model may see"),
    h(
      "p",
      {},
      "Ledgerline drafted this from your files. The model sees table and column names, their types, links and your descriptions. It never sees your rows. Hidden fields are never shown to it.",
    ),
    notice(
      "info",
      "Category values are sent only for columns where you tick “Share these values with the model”. Shared values go to a third-party model.",
    ),
  );
  for (const table of data.tables) {
    const body = h("tbody");
    for (const field of table.fields) body.appendChild(fieldRow(field, edits.fields[field.key], edit));
    append(
      main,
      h("h2", {}, table.name),
      h(
        "table",
        { class: "fields", attrs: { "data-table": table.name } },
        h(
          "thead",
          {},
          h("tr", {}, ...["Field", "Type", "Hidden", "Description", "Values"].map((c) => h("th", {}, c))),
        ),
        body,
      ),
    );
  }
  const button = h("button", { attrs: { type: "button" } }, "Confirm and continue");
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      status = await api.confirm(edits);
      go("ask");
    } catch (err) {
      button.disabled = false;
      showError(main, err);
    }
  });
  append(main, h("h2", {}, "What the model will see"), preview, button, workspaceBox());
  refresh();
}

function fieldRow(
  field: Field,
  state: FieldEdit,
  edit: (key: string, change: Partial<FieldEdit>) => void,
): HTMLElement {
  const hidden = h("input", { attrs: { type: "checkbox", "aria-label": `Hide ${field.key}`, "data-key": field.key, "data-role": "hide" } });
  hidden.checked = Boolean(state.hidden);
  const description = h("input", {
    attrs: { type: "text", maxlength: "300", "aria-label": `Description of ${field.key}`, "data-key": field.key, "data-role": "description" },
  });
  description.value = state.description ?? "";
  description.addEventListener("input", () => edit(field.key, { description: description.value }));
  let share: HTMLInputElement | null = null;
  if (field.values.length) {
    share = h("input", { attrs: { type: "checkbox", "data-key": field.key, "data-role": "share" } });
    share.checked = Boolean(state.share_values);
    share.disabled = Boolean(state.hidden);
    const box = share;
    share.addEventListener("change", () => edit(field.key, { share_values: box.checked }));
  }
  hidden.addEventListener("change", () => {
    // A hidden field never shares its values, so hiding clears the box as well.
    if (share && hidden.checked) share.checked = false;
    edit(field.key, hidden.checked ? { hidden: true, share_values: false } : { hidden: false });
    if (share) share.disabled = hidden.checked;
  });
  const shown = field.values.slice(0, 8).join(", ") + (field.values.length > 8 ? ", …" : "");
  return h(
    "tr",
    {},
    h(
      "td",
      {},
      h("code", {}, field.name),
      field.header !== field.name ? h("div", { class: "muted" }, `from column “${field.header}”`) : null,
      field.link ? h("div", { class: "muted" }, `links to ${field.link}`) : null,
    ),
    h("td", {}, field.type),
    h("td", {}, hidden, field.auto_hidden ? h("div", { class: "muted" }, "hidden automatically") : null),
    h("td", {}, description),
    h(
      "td",
      {},
      share
        ? h("label", {}, share, " Share these values with the model", h("div", { class: "muted" }, shown))
        : h("span", { class: "muted" }, "—"),
    ),
  );
}

// Ask ----------------------------------------------------------------------------------

function askPage(main: HTMLElement): void {
  const input = h("input", { attrs: { type: "text", id: "question", maxlength: "2000", placeholder: "How many orders were paid last month?" } });
  const button = h("button", { attrs: { type: "submit" } }, "Ask");
  const result = h("div", { class: "result", attrs: { "aria-live": "polite" } });
  const form = h(
    "form",
    {
      class: "ask",
      on: {
        submit: async (event) => {
          event.preventDefault();
          const question = input.value.trim();
          if (!question) return;
          button.disabled = true;
          clear(result);
          append(result, h("p", { class: "muted" }, "Working…"));
          try {
            const answer = await api.ask(question);
            clear(result);
            showAnswer(result, answer);
          } catch (err) {
            clear(result);
            showError(result, err);
          } finally {
            button.disabled = false;
          }
        },
      },
    },
    h("label", { attrs: { for: "question" } }, "Your question"),
    input,
    button,
  );
  append(main, h("h1", {}, "Ask a question"), form, result, workspaceBox());
}

function showAnswer(where: HTMLElement, answer: Answer): void {
  if (answer.explanation) {
    append(
      where,
      notice("info", h("strong", {}, answer.explanation.message), " ", answer.explanation.suggestion),
    );
  } else {
    const table = h(
      "table",
      { class: "answer" },
      h("thead", {}, h("tr", {}, ...answer.columns.map((c) => h("th", {}, c)))),
      h("tbody", {}, ...answer.rows.map((row) => h("tr", {}, ...row.map((v) => h("td", {}, v === null ? "" : String(v)))))),
    );
    append(where, table);
    if (answer.truncated) append(where, h("p", { class: "muted" }, "Only the first rows are shown."));
  }
  const attempts = answer.validation.attempts;
  const issues = attempts.length ? attempts[attempts.length - 1].issues : [];
  append(
    where,
    h(
      "details",
      { class: "trace" },
      h("summary", {}, "How this answer was made"),
      h("h3", {}, "What the model understood"),
      h("pre", {}, JSON.stringify(answer.intent, null, 2)),
      h("h3", {}, "Safety check"),
      issues.length
        ? h("ul", {}, ...issues.map((i) => h("li", {}, `${i.message} (${i.code})`)))
        : h("p", {}, answer.validation.ok ? "Passed." : "No query was run."),
      h("h3", {}, "SQL"),
      h("pre", {}, answer.sql ?? "No SQL was run."),
      answer.params ? h("pre", {}, JSON.stringify(answer.params, null, 2)) : null,
    ),
  );
}

// Start --------------------------------------------------------------------------------

async function start(): Promise<void> {
  const id = idFromHash();
  if (id) {
    useWorkspace(id);
    try {
      status = await api.status();
      step = stepFor(status);
    } catch (err) {
      useWorkspace(null);
      history.replaceState(null, "", "/");
      render();
      showError(app.querySelector("main") as HTMLElement, err);
      return;
    }
  }
  render();
}

// Opening a different workspace link in the same tab starts over with that workspace,
// so nothing from the previous one (its id included) carries across.
window.addEventListener("hashchange", () => location.reload());

void start();
