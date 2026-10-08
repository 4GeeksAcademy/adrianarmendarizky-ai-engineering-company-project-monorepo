// lib/chatSocket.ts
//
// WebSocket client for the Manager support chat (Real-Time Systems, Part 2).
// Talks to WS /ws/chat/{session_id} (services/api/routes/chat_ws.py).
//
// - Login: the same JWT as the rest of the backoffice, sent as ?token= (a
//   browser's WebSocket cannot set an Authorization header).
// - Reconnecting: if the connection drops it tries again with a growing delay
//   (1s, 2s, 4s ... up to 30s) using the SAME session_id. The server answers
//   every connect with a session_snapshot (the whole conversation), which the
//   page uses to replace what is on screen, so the thread is restored, not
//   started again.
// - Close code 1008 means the server refused us (bad or expired login, or a
//   session that is not ours). Retrying cannot fix that, so we stop and say so.

import { clearToken, getToken, isTokenExpired } from "./auth";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

const FIRST_DELAY_MS = 1000;
const MAX_DELAY_MS = 30000;
const REFUSED = 1008;

export type ChatMessageStatus = "complete" | "interrupted";

export type ChatMessage = {
  message_id: string;
  role: "user" | "assistant";
  text: string;
  status: ChatMessageStatus;
  created_at: string;
};

// Events the server sends (names and payloads follow the Part 2 CONTEXT).
export type ChatEvent =
  | { event: "session_snapshot"; data: { session_id: string; status: string; generating: boolean; messages: ChatMessage[] } }
  | { event: "token_chunk"; data: { session_id: string; token: string; sequence: number } }
  | { event: "generation_completed"; data: { session_id: string; message_id: string } }
  | { event: "generation_interrupted"; data: { session_id: string; message_id: string; status: string } }
  | { event: "output_blocked"; data: { session_id: string; replacement: string } }
  | { event: "generation_failed"; data: { session_id: string; message: string } }
  | { event: "error"; data: { message: string } };

export type ConnectionState = "connecting" | "open" | "reconnecting" | "refused";

type Handlers = {
  onEvent: (event: ChatEvent) => void;
  onState: (state: ConnectionState) => void;
};

export type ChatConnection = {
  sendUserMessage: (text: string) => boolean;
  sendInterrupt: (newInput: string) => boolean;
  refresh: () => void;
  close: () => void;
};

// A new conversation id (the server accepts 8-64 letters, digits, - or _).
export function newSessionId(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

export function connectChat(
  sessionId: string,
  locationId: string | null,
  handlers: Handlers
): ChatConnection {
  let socket: WebSocket | null = null;
  let stopped = false;
  let attempt = 0;
  let retryTimer: ReturnType<typeof setTimeout> | null = null;

  function open() {
    const token = getToken();
    if (!token || isTokenExpired(token)) {
      // Same as every other page: an expired login means go back to /login.
      clearToken();
      if (typeof window !== "undefined") window.location.href = "/login";
      handlers.onState("refused");
      return;
    }
    handlers.onState(attempt === 0 ? "connecting" : "reconnecting");

    const query = new URLSearchParams({ token });
    if (locationId) query.set("location_id", locationId);
    const ws = new WebSocket(`${WS_BASE}/ws/chat/${encodeURIComponent(sessionId)}?${query}`);
    socket = ws;

    ws.onmessage = (message) => {
      let event: ChatEvent;
      try {
        event = JSON.parse(message.data);
      } catch {
        return; // not JSON: ignore
      }
      if (event.event === "session_snapshot") {
        attempt = 0; // the server accepted us and sent the conversation: we are connected
        handlers.onState("open");
      }
      handlers.onEvent(event);
    };

    ws.onclose = (closeEvent) => {
      if (stopped) return;
      if (closeEvent.code === REFUSED) {
        handlers.onState("refused");
        return;
      }
      handlers.onState("reconnecting");
      attempt += 1;
      const delay = Math.min(FIRST_DELAY_MS * 2 ** (attempt - 1), MAX_DELAY_MS);
      retryTimer = setTimeout(open, delay + Math.random() * 500);
    };
  }

  function send(event: string, data: Record<string, string>): boolean {
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify({ event, data }));
    return true;
  }

  open();

  return {
    sendUserMessage: (text) => send("user_message", { text }),
    sendInterrupt: (newInput) => send("interrupt_requested", { new_input: newInput }),
    // Drops the socket on purpose: it reconnects and the server sends a fresh snapshot.
    refresh: () => {
      socket?.close();
    },
    close: () => {
      stopped = true;
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
    },
  };
}
