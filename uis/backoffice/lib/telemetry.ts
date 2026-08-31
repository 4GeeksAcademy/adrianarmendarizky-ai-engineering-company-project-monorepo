// lib/telemetry.ts
//
// The single entry point for all backoffice telemetry. Every event —
// mandatory or identified — goes through track(). No component ever
// calls fetch/axios directly for tracking. See
// docs/telemetry/telemetry-plan.md for the full design rationale and
// docs/telemetry/event-schemas.json for the event_type/properties
// contract this file's callers must follow.
//
// Implements: an in-memory queue, batch+debounce (flush every 10s or
// at 20 events, whichever comes first), a reliable flush via
// sendBeacon on tab close/hide, and retry with exponential backoff
// before a batch is discarded. The endpoint the stub/real backend
// lives at is read from NEXT_PUBLIC_TELEMETRY_ENDPOINT — never
// hardcoded — so Phase 3's swap to real persistence needs zero
// frontend changes.

const TELEMETRY_ENDPOINT =
  process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT ??
  "http://localhost:8000/telemetry/events";

const FLUSH_INTERVAL_MS = 10_000;
const MAX_BATCH_SIZE = 20;
const MAX_RETRIES = 3;

// Bumped only if TelemetryEvent's envelope itself changes shape —
// independent of each individual event_type's own schemaVersion in
// event-schemas.json.
const SCHEMA_VERSION = 1;

const TOKEN_KEY = "brasaland_token";

export type TelemetryEvent = {
  eventId: string;
  timestamp: string;
  sessionId: string;
  userId: string | null;
  event_type: string;
  schemaVersion: number;
  requestId: string | null;
  properties: Record<string, unknown>;
};

// Generated once per app load, kept only in memory — deliberately NOT
// tied to login. user_login_failed fires before a session/token
// exists, and it still needs a sessionId to correlate a string of
// failed attempts followed by a success. See telemetry-plan.md §1.
let sessionId: string | null = null;

function getSessionId(): string {
  if (!sessionId) sessionId = crypto.randomUUID();
  return sessionId;
}

// userId comes straight out of the JWT's own `sub` claim (see
// services/api/security.py) rather than a second, separate source of
// truth for "who is logged in." Null before login succeeds.
function getUserId(): string | null {
  if (typeof window === "undefined") return null;
  const token = window.localStorage.getItem(TOKEN_KEY);
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return typeof payload.sub === "string" ? payload.sub : null;
  } catch {
    return null;
  }
}

let queue: TelemetryEvent[] = [];
let flushTimer: ReturnType<typeof setInterval> | null = null;

function ensureTimer(): void {
  if (flushTimer !== null || typeof window === "undefined") return;
  flushTimer = setInterval(() => {
    void sendQueued();
  }, FLUSH_INTERVAL_MS);
}

async function sendBatch(events: TelemetryEvent[], attempt = 0): Promise<void> {
  try {
    const res = await fetch(TELEMETRY_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events }),
    });
    if (!res.ok) throw new Error(`Telemetry endpoint returned ${res.status}`);
  } catch (err) {
    if (attempt >= MAX_RETRIES) {
      // Telemetry must never block the app — drop the batch and move
      // on, per the brief ("if it still fails after N attempts, it
      // discards the batch -- telemetry data is not critical and must
      // not block the application").
      console.warn("Telemetry batch discarded after retries:", err);
      return;
    }
    const delayMs = 2 ** attempt * 500; // 500ms, 1s, 2s
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    return sendBatch(events, attempt + 1);
  }
}

function sendQueued(): void {
  if (queue.length === 0) return;
  const batch = queue;
  queue = [];
  void sendBatch(batch);
}

// sendBeacon can't be retried — the page may already be gone by the
// time a retry would fire — and it doesn't report success/failure.
// That's the right trade-off specifically for "the tab is closing
// right now": best-effort delivery beats losing the batch entirely.
function flushWithBeacon(): void {
  if (queue.length === 0 || typeof navigator === "undefined") return;
  const batch = queue;
  queue = [];
  const payload = JSON.stringify({ events: batch });

  const sent = navigator.sendBeacon?.(
    TELEMETRY_ENDPOINT,
    new Blob([payload], { type: "application/json" })
  );
  if (!sent) {
    // sendBeacon can refuse (payload too large, browser policy) —
    // fall back to a best-effort fire-and-forget fetch with
    // keepalive, which survives the page unloading in most browsers.
    void fetch(TELEMETRY_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      keepalive: true,
    }).catch(() => {});
  }
}

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flushWithBeacon();
  });
}

/**
 * The only function backoffice components/hooks/services call to
 * record telemetry. eventType and properties must match an entry in
 * docs/telemetry/event-schemas.json — this function doesn't validate
 * that client-side (the backend does), so check the allowlist before
 * adding a new call site.
 *
 * requestId is optional: pass the id you generated for a specific
 * backend call when this event corresponds 1:1 to one (e.g. an order
 * creation); omit it for events with no single corresponding request
 * (e.g. section_visited).
 */
export function track(
  eventType: string,
  properties: Record<string, unknown> = {},
  requestId: string | null = null
): void {
  if (typeof window === "undefined") return;

  const event: TelemetryEvent = {
    eventId: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    sessionId: getSessionId(),
    userId: getUserId(),
    event_type: eventType,
    schemaVersion: SCHEMA_VERSION,
    requestId,
    properties,
  };

  queue.push(event);
  ensureTimer();
  if (queue.length >= MAX_BATCH_SIZE) sendQueued();
}
