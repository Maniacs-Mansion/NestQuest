import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { waitFor } from "@testing-library/react";
import { EVENTS_PATH, SseParser, openTransitionStream, type TransitionEvent } from "./events";
import { frame, testStream, type TestStream } from "./testStream";
import { storeTokens } from "../auth/oidc";

const COMPLETED = {
  child_id: 1,
  child_name: "Declan",
  instance_id: 12,
  quest_title: "Make bed",
  window: "morning",
  due_date: "2026-09-23",
  due_time: null,
  occurred_at: "2026-09-23T11:04:00Z",
};
const DAY_COMPLETE = {
  child_id: 2,
  child_name: "Maeve",
  quests_due: 4,
  quests_completed: 4,
  occurred_at: "2026-09-23T12:00:00Z",
};

describe("SseParser", () => {
  it("yields every frame from one chunk", () => {
    const parser = new SseParser();
    const events = parser.push(
      frame("nestquest_quest_completed", COMPLETED) +
        frame("nestquest_child_day_complete", DAY_COMPLETE),
    );
    expect(events).toEqual([
      { type: "nestquest_quest_completed", payload: COMPLETED },
      { type: "nestquest_child_day_complete", payload: DAY_COMPLETE },
    ]);
  });

  it("buffers a frame split across two chunks", () => {
    const parser = new SseParser();
    const text = frame("nestquest_quest_uncompleted", COMPLETED);
    const cut = text.indexOf("Make");
    expect(parser.push(text.slice(0, cut))).toEqual([]);
    expect(parser.push(text.slice(cut))).toEqual([
      { type: "nestquest_quest_uncompleted", payload: COMPLETED },
    ]);
  });

  it("buffers a split inside the event name and the blank-line terminator", () => {
    const parser = new SseParser();
    const text = frame("nestquest_quest_missed", COMPLETED);
    expect(parser.push(text.slice(0, 12))).toEqual([]);
    expect(parser.push(text.slice(12, -1))).toEqual([]);
    expect(parser.push(text.slice(-1))).toEqual([
      { type: "nestquest_quest_missed", payload: COMPLETED },
    ]);
  });

  it("treats a CRLF split across chunks as one line break", () => {
    const parser = new SseParser();
    const text = `event: nestquest_quest_completed\r\ndata: ${JSON.stringify(COMPLETED)}\r\n\r\n`;
    const cut = text.indexOf("\n"); // chunk ends on "\r"
    expect(parser.push(text.slice(0, cut))).toEqual([]);
    expect(parser.push(text.slice(cut))).toEqual([
      { type: "nestquest_quest_completed", payload: COMPLETED },
    ]);
  });

  it("drops malformed, unknown and comment frames without throwing", () => {
    const parser = new SseParser();
    const events = parser.push(
      "event: nestquest_quest_completed\ndata: not-json\n\n" +
        "event: nestquest_quest_completed\ndata: [1,2]\n\n" +
        "event: something_else\ndata: {}\n\n" +
        ": keep-alive\n\n" +
        "data: {}\n\n" +
        frame("nestquest_quest_completed", COMPLETED),
    );
    expect(events).toEqual([{ type: "nestquest_quest_completed", payload: COMPLETED }]);
  });
});

describe("openTransitionStream", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let streams: TestStream[];
  let stop: (() => void) | null;

  beforeEach(() => {
    sessionStorage.clear();
    storeTokens({ access_token: "at-123", expires_in: 600 });
    streams = [];
    stop = null;
    fetchMock = vi.fn(() => {
      const stream = testStream();
      streams.push(stream);
      return Promise.resolve(stream.response);
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    stop?.();
    vi.unstubAllGlobals();
  });

  it("sends the token in the Authorization header, never in the URL", async () => {
    stop = openTransitionStream({ onTransition: () => {} });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(new RegExp(`${EVENTS_PATH}$`));
    expect(String(url)).not.toContain("at-123");
    expect(init.headers.Authorization).toBe("Bearer at-123");
    expect(init.headers.Accept).toBe("text/event-stream");
  });

  it("delivers transitions from frames split across chunks", async () => {
    const seen: TransitionEvent[] = [];
    stop = openTransitionStream({ onTransition: (event) => seen.push(event) });
    await waitFor(() => expect(streams).toHaveLength(1));
    const text = frame("nestquest_quest_completed", COMPLETED);
    streams[0].push(text.slice(0, 20));
    streams[0].push(text.slice(20));
    await waitFor(() =>
      expect(seen).toEqual([{ type: "nestquest_quest_completed", payload: COMPLETED }]),
    );
  });

  it("stop aborts the request and cancels the body", async () => {
    stop = openTransitionStream({ onTransition: () => {} });
    await waitFor(() => expect(streams).toHaveLength(1));
    const signal = fetchMock.mock.calls[0][1].signal as AbortSignal;
    stop();
    expect(signal.aborted).toBe(true);
    await waitFor(() => expect(streams[0].cancelled()).toBe(true));
  });

  it("reconnects after the stream drops", async () => {
    const seen: TransitionEvent[] = [];
    stop = openTransitionStream({ onTransition: (event) => seen.push(event), minDelayMs: 5 });
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].close();
    await waitFor(() => expect(streams).toHaveLength(2));
    streams[1].push(frame("nestquest_quest_missed", COMPLETED));
    await waitFor(() => expect(seen).toHaveLength(1));
  });

  it("does not reconnect after stop, even with a reconnect pending", async () => {
    stop = openTransitionStream({ onTransition: () => {}, minDelayMs: 20 });
    await waitFor(() => expect(streams).toHaveLength(1));
    streams[0].close();
    stop();
    await new Promise((resolve) => setTimeout(resolve, 60));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("gives up on a 403 refusal instead of retrying", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(new Response("", { status: 403 })));
    stop = openTransitionStream({ onTransition: () => {}, minDelayMs: 5 });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
