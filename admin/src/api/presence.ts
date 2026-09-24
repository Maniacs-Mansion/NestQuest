/**
 * Typed client for the admin presence routes: a child's repeating schedule
 * (/api/v1/admin/children/{id}/presence-schedule) and the household's
 * date-range overrides (/api/v1/admin/presence-overrides).
 */
import { apiFetch } from "./client";
import { CHILDREN_PATH, readJson } from "./definitions";

/**
 * Cycle week index ("0".."n-1", JSON object keys) -> present weekdays
 * (0 = Monday .. 6 = Sunday). An empty list is away that whole week.
 */
export type PresencePattern = Record<string, number[]>;

export interface PresenceScheduleBody {
  cycle_length_weeks: number;
  /** "YYYY-MM-DD"; pins cycle week 0. */
  anchor_date: string;
  pattern: PresencePattern;
}

export interface PresenceSchedule extends PresenceScheduleBody {
  child_id: number;
}

export interface PresenceOverride {
  id: number;
  child_id: number;
  start_date: string;
  end_date: string;
  is_present: boolean;
  note: string | null;
}

export interface PresenceOverrideFilter {
  childId?: number;
  /** "YYYY-MM-DD"; keeps overrides overlapping [start, end]. */
  start?: string;
  end?: string;
}

export const PRESENCE_OVERRIDES_PATH = "/api/v1/admin/presence-overrides";

export function presenceSchedulePath(childId: number): string {
  return `${CHILDREN_PATH}/${childId}/presence-schedule`;
}

/** The child's schedule, or null when it has none (present every day). */
export async function fetchPresenceSchedule(childId: number): Promise<PresenceSchedule | null> {
  const body = await readJson<{ schedule: PresenceSchedule | null }>(
    await apiFetch(presenceSchedulePath(childId)),
  );
  return body.schedule;
}

/** Set (upsert) the child's schedule; resolves to the schedule as stored. */
export async function savePresenceSchedule(
  childId: number,
  body: PresenceScheduleBody,
): Promise<PresenceSchedule> {
  return readJson<PresenceSchedule>(
    await apiFetch(presenceSchedulePath(childId), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function fetchPresenceOverrides(
  filter: PresenceOverrideFilter = {},
): Promise<PresenceOverride[]> {
  const params = new URLSearchParams();
  if (filter.childId !== undefined) params.set("child_id", String(filter.childId));
  if (filter.start !== undefined) params.set("start", filter.start);
  if (filter.end !== undefined) params.set("end", filter.end);
  const query = params.toString();
  const body = await readJson<{ overrides: PresenceOverride[] }>(
    await apiFetch(query ? `${PRESENCE_OVERRIDES_PATH}?${query}` : PRESENCE_OVERRIDES_PATH),
  );
  return body.overrides;
}
