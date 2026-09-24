/**
 * Typed client for the admin instance mutation route
 * (POST /api/v1/admin/instances/{id}/uncomplete).
 */
import { apiFetch } from "./client";
import { readJson } from "./definitions";

export interface UncompleteResult {
  instance_id: number;
  /** The derived state after the reversal: "open", or "missed" when past due. */
  state: string;
  /** False when the instance was already open (a no-op). */
  appended: boolean;
}

export function uncompletePath(instanceId: number): string {
  return `/api/v1/admin/instances/${instanceId}/uncomplete`;
}

/** Reverse one completion; raises ApiRequestError with the API's detail on failure. */
export async function uncompleteInstance(instanceId: number): Promise<UncompleteResult> {
  return readJson<UncompleteResult>(await apiFetch(uncompletePath(instanceId), { method: "POST" }));
}
