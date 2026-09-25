/**
 * Typed client for the admin presence routes: a child's repeating patterns
 * (/api/v1/admin/children/{id}/presence-patterns, /presence-patterns/{id})
 * and the household's date-range overrides (/api/v1/admin/presence-overrides).
 */
import { apiFetch } from "./client";
import { CHILDREN_PATH, readJson } from "./definitions";

/** A pattern claims its covered days as the child being home or away. */
export type PatternKind = "home" | "away";

/**
 * Cycle week index ("0".."n-1", JSON object keys) -> covered weekdays
 * (0 = Monday .. 6 = Sunday). An empty list covers nothing that week.
 */
export type PatternWeeks = Record<string, number[]>;

/** The anchor-based cycle every pattern repeats on. */
export interface PatternCycle {
  cycle_length_weeks: number;
  /** "YYYY-MM-DD"; pins cycle week 0. */
  anchor_date: string;
  pattern: PatternWeeks;
}

export interface PresencePatternBody extends PatternCycle {
  name: string;
  kind: PatternKind;
}

export interface PresencePattern extends PresencePatternBody {
  id: number;
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
export const PRESENCE_PATTERNS_PATH = "/api/v1/admin/presence-patterns";

export function childPatternsPath(childId: number): string {
  return `${CHILDREN_PATH}/${childId}/presence-patterns`;
}

function sendJson(path: string, method: "POST" | "PATCH", body: unknown): Promise<Response> {
  return apiFetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** The child's patterns in id order; empty when it has none (present every day). */
export async function fetchPresencePatterns(childId: number): Promise<PresencePattern[]> {
  const body = await readJson<{ patterns: PresencePattern[] }>(
    await apiFetch(childPatternsPath(childId)),
  );
  return body.patterns;
}

export async function createPresencePattern(
  childId: number,
  body: PresencePatternBody,
): Promise<PresencePattern> {
  return readJson<PresencePattern>(await sendJson(childPatternsPath(childId), "POST", body));
}

/** Change only the supplied fields; resolves to the pattern as stored. */
export async function updatePresencePattern(
  patternId: number,
  body: Partial<PresencePatternBody>,
): Promise<PresencePattern> {
  return readJson<PresencePattern>(
    await sendJson(`${PRESENCE_PATTERNS_PATH}/${patternId}`, "PATCH", body),
  );
}

export async function deletePresencePattern(patternId: number): Promise<void> {
  await readJson<{ status: string }>(
    await apiFetch(`${PRESENCE_PATTERNS_PATH}/${patternId}`, { method: "DELETE" }),
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

export interface PresenceOverrideRange {
  child_id: number;
  /** "YYYY-MM-DD", inclusive. */
  start_date: string;
  /** "YYYY-MM-DD", inclusive; never before start_date. */
  end_date: string;
  is_present: boolean;
}

export interface PresenceOverrideBody extends PresenceOverrideRange {
  note?: string;
}

export const PRESENCE_OVERRIDE_CONSEQUENCE_PATH = `${PRESENCE_OVERRIDES_PATH}/consequence`;

/**
 * How many open upcoming tasks saving this override would remove. Computed
 * by the API before anything is saved; completed instances never count.
 */
export async function previewOverrideConsequence(range: PresenceOverrideRange): Promise<number> {
  const body = await readJson<{ removed: number }>(
    await sendJson(PRESENCE_OVERRIDE_CONSEQUENCE_PATH, "POST", range),
  );
  return body.removed;
}

export async function createPresenceOverride(body: PresenceOverrideBody): Promise<PresenceOverride> {
  return readJson<PresenceOverride>(await sendJson(PRESENCE_OVERRIDES_PATH, "POST", body));
}

export async function deletePresenceOverride(overrideId: number): Promise<void> {
  await readJson<{ status: string }>(
    await apiFetch(`${PRESENCE_OVERRIDES_PATH}/${overrideId}`, { method: "DELETE" }),
  );
}
