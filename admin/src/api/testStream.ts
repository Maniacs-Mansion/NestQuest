/**
 * Test helper: a controllable text/event-stream Response whose body the test
 * feeds chunk by chunk (so a frame can be split across chunk boundaries).
 */
export interface TestStream {
  response: Response;
  push(text: string): void;
  close(): void;
  /** True once the reader cancelled the body (the stream was torn down). */
  cancelled(): boolean;
}

export function testStream(): TestStream {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  let cancelled = false;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
    cancel() {
      cancelled = true;
    },
  });
  return {
    response: new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    }),
    push: (text) => controller.enqueue(encoder.encode(text)),
    close: () => controller.close(),
    cancelled: () => cancelled,
  };
}

/** One SSE frame exactly as api/sse.py writes it. */
export function frame(type: string, payload: unknown): string {
  return `event: ${type}\ndata: ${JSON.stringify(payload)}\n\n`;
}
