"use client";

// Manager support chat -- Real-Time Systems, Part 2 (WebSocket).
// Talks to the Manager support agent through lib/chatSocket.ts (the page never
// opens a connection itself, same rule as the other pages).
//
// - The answer appears word by word as the server sends token_chunk events.
// - While nothing has arrived yet the page says "Thinking..." (the model can
//   take several seconds before its first word).
// - Stop interrupts the answer. With text in the box it also asks that instead:
//   the half-finished answer stays on screen marked "interrupted" and the new
//   question starts a new answer.
// - The conversation id is kept in sessionStorage, so reloading the page or a
//   dropped connection rejoins the same chat and the server sends the whole
//   conversation back (session_snapshot).

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  connectChat,
  newSessionId,
  type ChatConnection,
  type ChatEvent,
  type ChatMessage,
  type ConnectionState,
} from "@/lib/chatSocket";

const SESSION_KEY = "support_chat_session_id";
const LOCATION_KEY = "support_chat_location_id";

type Phase = "idle" | "thinking" | "streaming";

function localMessage(role: "user" | "assistant", text: string): ChatMessage {
  return { message_id: `local_${Date.now()}`, role, text, status: "complete", created_at: "" };
}

export default function SupportChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [liveText, setLiveText] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [catchingUp, setCatchingUp] = useState(false);
  const [connState, setConnState] = useState<ConnectionState>("connecting");
  const [notice, setNotice] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [location, setLocation] = useState("");
  const [chatKey, setChatKey] = useState(0);

  // Refs hold the values the event handler needs to read while it is running
  // (it is created once per connection, so it cannot read fresh state).
  const connRef = useRef<ChatConnection | null>(null);
  const phaseRef = useRef<Phase>("idle");
  const liveRef = useRef("");
  const catchingRef = useRef(false);
  const refreshingRef = useRef(false);
  const redirectRef = useRef<string | null>(null);
  const interruptSentRef = useRef(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const changePhase = useCallback((next: Phase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);
  const setLive = useCallback((text: string) => {
    liveRef.current = text;
    setLiveText(text);
  }, []);
  const setCatching = useCallback((value: boolean) => {
    catchingRef.current = value;
    setCatchingUp(value);
  }, []);

  useEffect(() => {
    let id = window.sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = newSessionId();
      window.sessionStorage.setItem(SESSION_KEY, id);
    }
    const savedLocation = window.sessionStorage.getItem(LOCATION_KEY);

    function onEvent(event: ChatEvent) {
      switch (event.event) {
        case "session_snapshot": {
          // The saved conversation replaces what is on screen. This is also what
          // restores the thread after a dropped connection.
          setMessages(event.data.messages);
          setLive("");
          const wasAnswering = phaseRef.current !== "idle" && !refreshingRef.current;
          refreshingRef.current = false;
          if (event.data.generating) {
            // An answer is being written right now (we came back in the middle of it, or
            // joined from another tab). The words sent while we were away are gone, so wait
            // for it to finish and then reload it.
            setCatching(true);
            changePhase("thinking");
          } else {
            // Nothing is being written, so there is nothing to wait for.
            setCatching(false);
            changePhase("idle");
            const last = event.data.messages[event.data.messages.length - 1];
            if (wasAnswering && last?.role === "user") {
              setNotice("The connection dropped while the agent was answering, and that answer was not saved. Ask again.");
            }
          }
          break;
        }
        case "token_chunk":
          if (catchingRef.current) break;
          changePhase("streaming");
          setLive(liveRef.current + event.data.token);
          break;
        case "output_blocked":
          // The server stopped the answer and replaced it; show the replacement.
          if (!catchingRef.current) setLive(event.data.replacement);
          break;
        case "generation_completed": {
          if (catchingRef.current) {
            refreshingRef.current = true;
            connRef.current?.refresh();
            break;
          }
          const text = liveRef.current;
          setLive("");
          setMessages((m) => [
            ...m,
            { message_id: event.data.message_id, role: "assistant", text, status: "complete", created_at: "" },
          ]);
          changePhase("idle");
          break;
        }
        case "generation_interrupted": {
          interruptSentRef.current = false;
          if (catchingRef.current) {
            refreshingRef.current = true;
            connRef.current?.refresh();
            break;
          }
          const partial = liveRef.current;
          const redirect = redirectRef.current;
          redirectRef.current = null;
          setLive("");
          setMessages((m) => {
            const next = [...m];
            if (partial) {
              next.push({
                message_id: event.data.message_id, role: "assistant", text: partial,
                status: "interrupted", created_at: "",
              });
            }
            if (redirect) next.push(localMessage("user", redirect));
            return next;
          });
          changePhase(redirect ? "thinking" : "idle");
          break;
        }
        case "generation_failed":
          setLive("");
          setCatching(false);
          changePhase("idle");
          setNotice(event.data.message);
          break;
        case "error":
          setNotice(event.data.message);
          if (interruptSentRef.current) {
            // The stop found nothing running: give the typed text back to the user.
            interruptSentRef.current = false;
            if (redirectRef.current) {
              setInput(redirectRef.current);
              redirectRef.current = null;
            }
            changePhase("idle");
          }
          break;
      }
    }

    const conn = connectChat(id, savedLocation, { onEvent, onState: setConnState });
    connRef.current = conn;
    return () => {
      conn.close();
      connRef.current = null;
    };
  }, [chatKey, changePhase, setLive, setCatching]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, liveText, phase]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    const conn = connRef.current;
    if (!conn) return;
    setNotice(null);

    if (phase === "idle") {
      if (!text) return;
      if (!conn.sendUserMessage(text)) {
        setNotice("Not connected yet - try again in a moment.");
        return;
      }
      setMessages((m) => [...m, localMessage("user", text)]);
      setInput("");
      changePhase("thinking");
      return;
    }

    // An answer is in progress: stop it (and, with text, ask that instead).
    if (catchingUp) return;
    if (!conn.sendInterrupt(text)) {
      setNotice("Not connected - could not stop the answer.");
      return;
    }
    interruptSentRef.current = true;
    redirectRef.current = text || null;
    setInput("");
  }

  function startNewChat() {
    window.sessionStorage.removeItem(SESSION_KEY);
    const place = location.trim();
    if (place) window.sessionStorage.setItem(LOCATION_KEY, place);
    else window.sessionStorage.removeItem(LOCATION_KEY);
    setMessages([]);
    setLive("");
    setCatching(false);
    changePhase("idle");
    setNotice(null);
    setInput("");
    redirectRef.current = null;
    interruptSentRef.current = false;
    refreshingRef.current = false;
    setConnState("connecting");
    setChatKey((k) => k + 1);
  }

  const busy = phase !== "idle";
  const buttonLabel = !busy ? "Send" : input.trim() ? "Stop and send this instead" : "Stop";
  const cannotType = connState !== "open" || catchingUp;

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-stone-900">Manager Support Chat</h1>
        <p className="text-sm text-stone-500 mt-1">
          A live conversation with the Manager support agent. Answers appear word by word; press
          Stop to interrupt and redirect it.
        </p>
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="Location for a new chat (optional), e.g. medellin_downtown"
          className="flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm"
        />
        <button
          type="button"
          onClick={startNewChat}
          className="rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-700 hover:bg-stone-200"
        >
          New chat
        </button>
      </div>

      {connState === "reconnecting" && (
        <p className="text-sm text-amber-700">Connection lost - trying to reconnect...</p>
      )}
      {connState === "refused" && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Could not join this chat: your login may have expired, or the chat belongs to someone
          else. Log in again, or press New chat.
        </div>
      )}
      {notice && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {notice}
        </div>
      )}

      <div className="min-h-64 space-y-3 rounded-xl border border-stone-200 bg-white p-4">
        {messages.length === 0 && !busy && (
          <p className="text-sm text-stone-400">Ask a question to start the conversation.</p>
        )}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <div
              key={`${m.message_id}-${i}`}
              className="ml-auto max-w-lg whitespace-pre-wrap rounded-xl bg-stone-900 px-4 py-3 text-sm text-white"
            >
              {m.text}
            </div>
          ) : (
            <div
              key={`${m.message_id}-${i}`}
              className="max-w-lg whitespace-pre-wrap rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-900"
            >
              {m.text || "(stopped before it said anything)"}
              {m.status === "interrupted" && (
                <span className="mt-2 block text-xs font-semibold uppercase tracking-widest text-amber-700">
                  Interrupted
                </span>
              )}
            </div>
          )
        )}

        {phase === "thinking" && !catchingUp && (
          <div className="max-w-lg animate-pulse rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-500">
            Thinking...
          </div>
        )}
        {liveText && !catchingUp && (
          <div className="max-w-lg whitespace-pre-wrap rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-900">
            {liveText}
            <span className="text-stone-400">&#9613;</span>
          </div>
        )}
        {catchingUp && (
          <div className="max-w-lg rounded-xl border border-stone-200 bg-stone-50 px-4 py-3 text-sm text-stone-500">
            Reconnected - the rest of the answer will appear when it finishes.
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={cannotType}
          placeholder={busy ? "Type a new question to redirect the agent..." : "Ask the support agent..."}
          className="flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={cannotType}
          className="rounded-lg bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-800 disabled:opacity-50"
        >
          {buttonLabel}
        </button>
      </form>
    </div>
  );
}
