/**
 * Live transition stream: GET /api/v1/admin/events (text/event-stream).
 *
 * The admin JWT travels in the Authorization header (via apiFetch), so the
 * stream is read with fetch + a ReadableStream reader — EventSource cannot
 * set headers, and the token must never go into a URL.
 */
import { ApiForbiddenError, ApiUnauthorizedError, apiFetch } from "./client";

export const EVENTS_PATH = "/api/v1/admin/events";

/** The four documented transitions, as the API names them on the wire. */
export const TRANSITION_TYPES = [
  "nestquest_quest_completed",
  "nestquest_quest_uncompleted",
  "nestquest_quest_missed",
  "nestquest_child_day_complete",
] as const;

export type TransitionType = (typeof TRANSITION_TYPES)[number];

/** Quest transitions carry the instance; a day-complete carries the child's counts. */
export interface QuestTransitionPayload {
  child_id: number;
  child_name: string | null;
  instance_id: number;
  quest_title: string | null;
  window: string;
  due_date: string;
  due_time: string | null;
  occurred_at: string;
}

export interface ChildDayCompletePayload {
  child_id: number;
  child_name: string | null;
  quests_due: number;
  quests_completed: number;
  occurred_at: string;
}

export type TransitionEvent =
  | {
      type:
        | "nestquest_quest_completed"
        | "nestquest_quest_uncompleted"
        | "nestquest_quest_missed";
      payload: QuestTransitionPayload;
    }
  | { type: "nestquest_child_day_complete"; payload: ChildDayCompletePayload };

function isTransitionType(value: string): value is TransitionType {
  return (TRANSITION_TYPES as readonly string[]).includes(value);
}

/**
 * Incremental SSE frame parser. Feed it decoded text in whatever chunks the
 * network delivers; it buffers a partial line or frame until it completes.
 * Comments (keep-alives), unknown event types and frames whose data is not a
 * JSON object are dropped, never thrown.
 */
export class SseParser {
  private buffer = "";
  private eventType = "";
  private data: string[] = [];
  /** A chunk ended on "\r": a leading "\n" in the next chunk is the same line break. */
  private pendingCr = false;

  push(text: string): TransitionEvent[] {
    if (this.pendingCr && text.startsWith("\n")) text = text.slice(1);
    this.pendingCr = text.endsWith("\r");
    this.buffer += text;
    const lines = this.buffer.split(/\r\n|\r|\n/);
    this.buffer = lines.pop() ?? "";
    const events: TransitionEvent[] = [];
    for (const line of lines) {
      const event = this.line(line);
      if (event) events.push(event);
    }
    return events;
  }

  private line(line: string): TransitionEvent | null {
    if (line === "") return this.dispatch();
    if (line.startsWith(":")) return null;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.eventType = value;
    else if (field === "data") this.data.push(value);
    return null;
  }

  private dispatch(): TransitionEvent | null {
    const type = this.eventType;
    const data = this.data.join("\n");
    this.eventType = "";
    this.data = [];
    if (!isTransitionType(type)) return null;
    let payload: unknown;
    try {
      payload = JSON.parse(data);
    } catch {
      return null;
    }
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return null;
    return { type, payload } as TransitionEvent;
  }
}

export interface TransitionStreamOptions {
  onTransition: (event: TransitionEvent) => void;
  /** Reconnect delay after a drop: starts at `minDelayMs`, doubles up to `maxDelayMs`. */
  minDelayMs?: number;
  maxDelayMs?: number;
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(done, ms);
    signal.addEventListener("abort", done, { once: true });
    function done() {
      clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    }
  });
}

/** Read one connection until the body ends (or the signal aborts). */
async function readOnce(
  signal: AbortSignal,
  onTransition: (event: TransitionEvent) => void,
): Promise<void> {
  const response = await apiFetch(EVENTS_PATH, {
    signal,
    headers: { Accept: "text/event-stream" },
  });
  if (!response.ok || !response.body) {
    throw new Error(`Event stream request failed (HTTP ${response.status}).`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  const cancel = () => void reader.cancel().catch(() => {});
  signal.addEventListener("abort", cancel, { once: true });
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done || signal.aborted) break;
      for (const event of parser.push(decoder.decode(value, { stream: true }))) {
        if (signal.aborted) break;
        onTransition(event);
      }
    }
  } finally {
    signal.removeEventListener("abort", cancel);
    reader.releaseLock();
  }
}

/**
 * Subscribe to the admin transition stream, reconnecting with a bounded
 * backoff after a drop. Returns a stop function that aborts the open request
 * and any pending reconnect. A 401/403 stops the stream for good: apiFetch
 * has already started a login (401) or the account is refused (403).
 */
export function openTransitionStream({
  onTransition,
  minDelayMs = 1_000,
  maxDelayMs = 30_000,
}: TransitionStreamOptions): () => void {
  const controller = new AbortController();
  const { signal } = controller;

  void (async () => {
    let delay = minDelayMs;
    while (!signal.aborted) {
      try {
        await readOnce(signal, onTransition);
        // A connection that was accepted and then ended starts the backoff over.
        delay = minDelayMs;
      } catch (error: unknown) {
        if (signal.aborted) return;
        if (error instanceof ApiUnauthorizedError || error instanceof ApiForbiddenError) return;
        // Dropped or refused connection: fall through to the backoff.
      }
      if (signal.aborted) return;
      await wait(delay, signal);
      delay = Math.min(delay * 2, maxDelayMs);
    }
  })();

  return () => controller.abort();
}
