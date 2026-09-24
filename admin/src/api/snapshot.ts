/**
 * Typed client for GET /api/v1/admin/snapshot — today's household snapshot
 * that drives the admin Today tab.
 */
import { apiFetch } from "./client";

export type InstanceWindow = "morning" | "afternoon" | "evening";
export type InstanceState = "open" | "completed" | "missed";

export interface SnapshotInstance {
  id: number;
  definition_id: number;
  child_id: number;
  title: string;
  icon: string | null;
  window: InstanceWindow;
  /** Local wall-clock "HH:MM", or null when the definition has no due time. */
  due_time: string | null;
  state: InstanceState;
  overdue: boolean;
  /** UTC ISO timestamp of the completion event, when completed. */
  completed_at: string | null;
  on_time: boolean | null;
}

export interface SnapshotChild {
  child_id: number;
  child_name: string;
  present: boolean;
  /** "YYYY-MM-DD" of the next present day, or null. */
  next_present: string | null;
  due_today: number;
  completed_today: number;
  remaining_today: number;
  completion_pct: number;
  instances: SnapshotInstance[];
}

export interface AdminSnapshot {
  /** "YYYY-MM-DD" in the household's local zone. */
  today_iso: string;
  /** 1-based day in the custody cycle. */
  cycle_day: number;
  children: SnapshotChild[];
}

export const SNAPSHOT_PATH = "/api/v1/admin/snapshot";

export async function fetchSnapshot(): Promise<AdminSnapshot> {
  const response = await apiFetch(SNAPSHOT_PATH);
  if (!response.ok) {
    throw new Error(`Snapshot request failed (HTTP ${response.status}).`);
  }
  return (await response.json()) as AdminSnapshot;
}
