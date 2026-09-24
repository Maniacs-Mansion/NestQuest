/**
 * Typed client for the admin child-profile write routes
 * (/api/v1/admin/children). The list read is `fetchChildren` in ./definitions.
 */
import { apiFetch } from "./client";
import { CHILDREN_PATH, readJson, type AdminChild } from "./definitions";

export interface ChildCreateBody {
  display_name: string;
  colour?: string;
  avatar_ref?: string;
  sort_order?: number;
}

/**
 * Omitted fields stay unchanged. The API rejects an explicit null, so a set
 * colour or avatar cannot be cleared through this route.
 */
export type ChildEditBody = Partial<ChildCreateBody>;

export const CHILDREN_REORDER_PATH = `${CHILDREN_PATH}/reorder`;

function sendJson(path: string, method: "POST" | "PATCH", body: unknown): Promise<Response> {
  return apiFetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function createChild(body: ChildCreateBody): Promise<AdminChild> {
  return readJson<AdminChild>(await sendJson(CHILDREN_PATH, "POST", body));
}

export async function updateChild(id: number, body: ChildEditBody): Promise<AdminChild> {
  return readJson<AdminChild>(await sendJson(`${CHILDREN_PATH}/${id}`, "PATCH", body));
}

export async function setChildActive(id: number, isActive: boolean): Promise<AdminChild> {
  return readJson<AdminChild>(
    await sendJson(`${CHILDREN_PATH}/${id}/active`, "PATCH", { is_active: isActive }),
  );
}

/** `orderedIds` must be every child id in the household, in the new order. */
export async function reorderChildren(orderedIds: number[]): Promise<void> {
  await readJson<{ status: string }>(
    await sendJson(CHILDREN_REORDER_PATH, "POST", { ordered_ids: orderedIds }),
  );
}
