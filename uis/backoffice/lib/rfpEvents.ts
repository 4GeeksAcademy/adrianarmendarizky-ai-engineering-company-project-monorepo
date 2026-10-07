// lib/rfpEvents.ts
//
// Live "new RFP ticket" notifications (Real-Time Systems, Part 1).
// Reads the stream from GET /rfp/events (services/api/routes/rfp_events.py).
//
// Why not the bare EventSource? It cannot send an Authorization header, and
// the stream is behind login. So this uses fetch (through authFetch, which
// adds the token and handles a 401) and reads the stream by hand.
//
// If the connection drops it tries again with a growing delay (1s, 2s, 4s ...
// up to 30s). Two things keep the dashboard correct after a drop:
//   1. It sends the id of the last notification it saw in the Last-Event-ID header,
//      and the server replays any newer ones from the database.
//   2. It tells the page (onReconnected) so the page can reload the ticket list.
// A notification that was already shown is never shown twice.

import { authFetch } from "./api";

export type RfpTicketCreated = {
  ticket_id: number;
  rfp_id: string | null;
  client_name: string | null;
  location: string | null;
  service_type: string | null;
  status: string;
  created_at: string;
};

export type StreamState = "connecting" | "live" | "reconnecting";

type Handlers = {
  onTicket: (ticket: RfpTicketCreated) => void;
  onState?: (state: StreamState) => void;
  onReconnected?: () => void;
};

const EVENT_NAME = "rfp_ticket_created";
const FIRST_DELAY_MS = 1000;
const MAX_DELAY_MS = 30000;

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

// Starts listening. Returns a function that stops it (call it when the page closes).
export function subscribeToRfpTickets(handlers: Handlers): () => void {
  const controller = new AbortController();
  let lastId: number | null = null;
  let attempt = 0;
  let recovering = false;

  // One message from the server looks like:
  //   id: 42
  //   event: rfp_ticket_created
  //   data: {"ticket_id": 42, ...}
  // Lines starting with ":" are keep-alive comments and are ignored.
  function handleMessage(block: string) {
    let eventName = "message";
    let eventId: number | null = null;
    let data = "";
    for (const line of block.split("\n")) {
      if (line === "" || line.startsWith(":")) continue;
      const colon = line.indexOf(":");
      const field = colon === -1 ? line : line.slice(0, colon);
      const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
      if (field === "event") eventName = value;
      if (field === "data") data += value;
      if (field === "id") {
        const number = Number(value);
        if (Number.isInteger(number)) eventId = number;
      }
    }
    if (eventName !== EVENT_NAME || data === "") return;

    let ticket: RfpTicketCreated;
    try {
      ticket = JSON.parse(data);
    } catch {
      return; // not valid JSON: ignore this message
    }
    if (eventId !== null) {
      if (lastId !== null && eventId <= lastId) return; // already shown
      lastId = eventId;
    }
    handlers.onTicket(ticket);
  }

  async function readStream(body: ReadableStream<Uint8Array>) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let end = buffer.indexOf("\n\n");
      while (end !== -1) {
        handleMessage(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
        end = buffer.indexOf("\n\n");
      }
    }
  }

  async function run() {
    while (!controller.signal.aborted) {
      handlers.onState?.(recovering ? "reconnecting" : "connecting");
      try {
        const headers: Record<string, string> = { Accept: "text/event-stream" };
        if (lastId !== null) headers["Last-Event-ID"] = String(lastId);
        const response = await authFetch("/rfp/events", {
          headers,
          signal: controller.signal,
        });
        if (response.status === 401) return; // authFetch is already sending the user to /login
        if (!response.ok || !response.body) {
          throw new Error(`The stream answered ${response.status}`);
        }
        attempt = 0;
        handlers.onState?.("live");
        if (recovering) {
          handlers.onReconnected?.();
          recovering = false;
        }
        await readStream(response.body);
      } catch {
        if (controller.signal.aborted) return;
      }
      if (controller.signal.aborted) return;
      recovering = true;
      handlers.onState?.("reconnecting");
      attempt += 1;
      const delay = Math.min(FIRST_DELAY_MS * 2 ** (attempt - 1), MAX_DELAY_MS);
      await sleep(delay + Math.random() * 500, controller.signal);
    }
  }

  void run();
  return () => controller.abort();
}
