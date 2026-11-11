// Calls to the Ledgerline API. The workspace id goes in the X-Workspace-Id header only,
// never in a request URL, so it stays out of server logs.

export type State = "new" | "checked" | "confirmed";

export interface Problem {
  level: "error" | "warning";
  code: string;
  file: string;
  row: number | null;
  column: string | null;
  message: string;
  fix: string;
}

export interface FileReport {
  name: string;
  table: string | null;
  ok: boolean;
  rows: number;
  columns: number;
  errors: number;
  warnings: number;
  problems: Problem[];
  more: number;
  more_text: string | null;
}

export interface Status {
  id: string;
  state: State;
  time_zone: string;
  created_at: string;
  expires_at: string;
  files: { name: string; bytes: number }[];
  check: { ok: boolean; files: FileReport[] } | null;
}

export interface Field {
  key: string;
  name: string;
  header: string;
  type: string;
  hidden: boolean;
  auto_hidden: boolean;
  description: string;
  values: string[];
  share_values: boolean;
  link: string | null;
}

export interface FieldEdit {
  hidden?: boolean;
  description?: string;
  share_values?: boolean;
}

export interface Edits {
  fields: Record<string, FieldEdit>;
}

export interface Answer {
  question: string;
  intent: unknown;
  validation: { ok: boolean; attempts: { issues: { code: string; message: string }[] }[] };
  sql: string | null;
  params: Record<string, unknown> | null;
  columns: string[];
  rows: unknown[][];
  truncated: boolean;
  refusal: string | null;
  explanation: { message: string; suggestion: string } | null;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

let workspaceId: string | null = null;

export function useWorkspace(id: string | null): void {
  workspaceId = id;
}

async function call<T>(method: string, path: string, body?: BodyInit, json = true): Promise<T> {
  const headers: Record<string, string> = {};
  if (workspaceId) headers["X-Workspace-Id"] = workspaceId;
  if (body !== undefined && json) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { method, headers, body });
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    const message =
      typeof detail === "string" ? detail : "Something went wrong. Try again in a minute.";
    throw new ApiError(message, response.status);
  }
  return data as T;
}

export const api = {
  timeZones: () => call<string[]>("GET", "/api/time-zones"),
  create: (time_zone: string) =>
    call<Status>("POST", "/api/workspaces", JSON.stringify({ time_zone })),
  status: () => call<Status>("GET", "/api/workspace"),
  upload: (file: File) =>
    call<Status>("PUT", `/api/workspace/files?name=${encodeURIComponent(file.name)}`, file, false),
  remove: (name: string) =>
    call<Status>("DELETE", `/api/workspace/files?name=${encodeURIComponent(name)}`),
  check: () => call<Status>("POST", "/api/workspace/check"),
  fields: () => call<{ tables: { name: string; fields: Field[] }[]; edits: Edits }>(
    "GET",
    "/api/workspace/fields",
  ),
  preview: (edits: Edits) =>
    call<{ prompt: string; truncation: string[] }>(
      "POST",
      "/api/workspace/preview",
      JSON.stringify(edits),
    ),
  confirm: (edits: Edits) => call<Status>("POST", "/api/workspace/confirm", JSON.stringify(edits)),
  ask: (question: string) =>
    call<Answer>("POST", "/api/workspace/ask", JSON.stringify({ question })),
  remove_workspace: () => call<{ deleted: boolean }>("DELETE", "/api/workspace"),
};
