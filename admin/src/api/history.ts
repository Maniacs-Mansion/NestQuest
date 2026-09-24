/**
 * Typed client for the admin history route (/api/v1/admin/history): the
 * append-only event log over a closed due-date range for one filter.
 */
import { apiFetch } from "./client";
import { ApiRequestError, readJson } from "./definitions";

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

export const HISTORY_CSV_PATH = "/api/v1/admin/history.csv";

export interface HistoryCsv {
  blob: Blob;
  filename: string;
}

/** The `filename` from a Content-Disposition header, or null. */
export function csvFilename(disposition: string | null): string | null {
  const match = disposition?.match(/filename="?([^";]+)"?/i);
  return match ? match[1].trim() : null;
}

/**
 * The CSV export of the same range and filter as `fetchHistory`. Goes through
 * apiFetch so the admin token travels in the Authorization header.
 */
export async function exportHistoryCsv(
  filter: HistoryFilter,
  start: string,
  end: string,
): Promise<HistoryCsv> {
  const params = new URLSearchParams({ start, end, filter });
  const response = await apiFetch(`${HISTORY_CSV_PATH}?${params.toString()}`);
  if (!response.ok) {
    // readJson raises ApiRequestError with the API's `detail` for a non-OK response.
    await readJson<never>(response);
    throw new ApiRequestError(response.status, null);
  }
  return {
    blob: await response.blob(),
    filename:
      csvFilename(response.headers.get("Content-Disposition")) ??
      `nestquest-history-${start}-to-${end}.csv`,
  };
}
