/**
 * Typed client for the admin history route (/api/v1/admin/history): the
 * append-only event log over a closed due-date range for one filter.
 */
import { apiFetch } from "./client";
import { readJson } from "./definitions";

export type HistoryFilter = "all" | "reversals" | "missed";

export type HistoryEventType = "completed" | "uncompleted" | "missed";

export interface HistoryRow {
  /** UTC ISO stamp; null for a derived missed row (there is no event). */
  occurred_at: string | null;
  event_type: HistoryEventType;
  child_name: string;
  child_id: number;
  quest_title: string;
  instance_id: number;
  window: string;
  /** "YYYY-MM-DD", the day the task was owed. */
  due_date: string;
  /** Local wall-clock "HH:MM", or null. */
  due_time: string | null;
  /** e.g. "panel (Declan)", "joshua (admin)", "nightly sweep". */
  actor: string;
  was_on_time: boolean | null;
}

export interface HistoryResponse {
  filter: HistoryFilter;
  start: string;
  end: string;
  count: number;
  rows: HistoryRow[];
}

export const HISTORY_PATH = "/api/v1/admin/history";

/** `start`/`end` are inclusive "YYYY-MM-DD" due dates. */
export async function fetchHistory(
  filter: HistoryFilter,
  start: string,
  end: string,
): Promise<HistoryResponse> {
  const params = new URLSearchParams({ start, end, filter });
  return readJson<HistoryResponse>(await apiFetch(`${HISTORY_PATH}?${params.toString()}`));
}
