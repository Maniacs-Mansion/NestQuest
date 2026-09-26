/**
 * Typed client for the admin quest-definition routes and the children list
 * the assignee picker reads (/api/v1/admin/quest-definitions, /children).
 */
import { apiFetch } from "./client";

export type WindowName = "morning" | "afternoon" | "evening";

/** Model rule names, as the admin plane serializes ScheduleRule.to_dict. */
export type RuleType =
  | "daily"
  | "weekly"
  | "monthly_day"
  | "monthly_weekday"
  | "yearly"
  | "custom_days";

export interface DefinitionRule {
  rule_type: RuleType;
  interval: number;
  /** 0 = Monday .. 6 = Sunday. */
  weekday_set: number[] | null;
  day_of_month: number | null;
  nth_weekday: number | null;
  nth_weekday_weekday: number | null;
  month: number | null;
  start_date: string;
  end_date: string | null;
}

export interface DefinitionAssignee {
  id: number;
  display_name: string;
}

export interface DefinitionWindow {
  window: WindowName;
  /** Local wall-clock "HH:MM", or null. */
  due_time: string | null;
}

export interface QuestDefinition {
  id: number;
  title: string;
  description: string | null;
  icon: string | null;
  is_active: boolean;
  skip_on_away: boolean;
  rule: DefinitionRule;
  assignees: DefinitionAssignee[];
  windows: DefinitionWindow[];
}

export interface AdminChild {
  id: number;
  display_name: string;
  colour: string | null;
  avatar_ref: string | null;
  sort_order: number;
  is_active: boolean;
}

/** A window declaration as the create/edit bodies accept it. */
export type WindowEntry = WindowName | [WindowName, string | null];

export interface DefinitionCreateBody {
  title: string;
  rule: DefinitionRule;
  assignee_child_ids: number[];
  windows: WindowEntry[];
  description?: string | null;
  icon?: string | null;
  skip_on_away?: boolean;
}

export type DefinitionEditBody = Partial<DefinitionCreateBody>;

export const DEFINITIONS_PATH = "/api/v1/admin/quest-definitions";
export const CHILDREN_PATH = "/api/v1/admin/children";

/** A non-2xx save response; `detail` is the API's message when it sent one. */
export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string | null,
  ) {
    super(detail ?? `Request failed (HTTP ${status}).`);
    this.name = "ApiRequestError";
  }
}

/** FastAPI sends `detail` as a string (core errors) or a list of {msg} (body validation). */
function readDetail(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const { detail } = body as { detail: unknown };
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item === "object" ? (item as { msg?: unknown }).msg : null))
      .filter((msg): msg is string => typeof msg === "string");
    return messages.length > 0 ? messages.join("; ") : null;
  }
  return null;
}

export async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      // Non-JSON error body: report the status alone.
    }
    throw new ApiRequestError(response.status, readDetail(body));
  }
  return (await response.json()) as T;
}

export async function fetchDefinitions(): Promise<QuestDefinition[]> {
  const body = await readJson<{ definitions: QuestDefinition[] }>(
    await apiFetch(DEFINITIONS_PATH),
  );
  return body.definitions;
}

export async function fetchChildren(): Promise<AdminChild[]> {
  const body = await readJson<{ children: AdminChild[] }>(await apiFetch(CHILDREN_PATH));
  return body.children;
}

function sendJson(path: string, method: "POST" | "PATCH", body: unknown): Promise<Response> {
  return apiFetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function createDefinition(body: DefinitionCreateBody): Promise<QuestDefinition> {
  return readJson<QuestDefinition>(await sendJson(DEFINITIONS_PATH, "POST", body));
}

export async function updateDefinition(
  id: number,
  body: DefinitionEditBody,
): Promise<QuestDefinition> {
  return readJson<QuestDefinition>(await sendJson(`${DEFINITIONS_PATH}/${id}`, "PATCH", body));
}

export const OCCURRENCES_PREVIEW_PATH = `${DEFINITIONS_PATH}/occurrences-preview`;

export interface OccurrencesPreviewOptions {
  /**
   * "YYYY-MM-DD"; the API defaults to the household-local today in the
   * configured `timezone` (the API host's local time when that is empty).
   */
  startDate?: string;
  /** 1..50; the API defaults to 10. */
  count?: number;
}

/**
 * The next occurrence dates ("YYYY-MM-DD", ascending) for `rule`, computed by
 * the same backend recurrence engine the materializer uses.
 */
export async function previewOccurrences(
  rule: DefinitionRule,
  options: OccurrencesPreviewOptions = {},
): Promise<string[]> {
  const body: { rule: DefinitionRule; start_date?: string; count?: number } = { rule };
  if (options.startDate !== undefined) body.start_date = options.startDate;
  if (options.count !== undefined) body.count = options.count;
  const response = await readJson<{ dates: string[] }>(
    await sendJson(OCCURRENCES_PREVIEW_PATH, "POST", body),
  );
  return response.dates;
}
