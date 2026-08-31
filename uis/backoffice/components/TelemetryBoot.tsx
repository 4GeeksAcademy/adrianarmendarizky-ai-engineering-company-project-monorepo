"use client";

// TelemetryBoot -- mounted once in the root layout so it covers every
// route, including /login and /register (outside the (protected)
// group where authFetch's instrumentation doesn't reach). Wires up
// the two remaining cross-cutting technical-baseline events the
// telemetry unit requires: section_visited on every route change, and
// frontend_error_occurred from uncaught errors and unhandled promise
// rejections. Renders nothing -- side effects only.
//
// Kept as its own component (not inlined into layout.tsx) because
// layout.tsx exports `metadata`, which requires a Server Component --
// usePathname() and window-level listeners both require "use client".

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { track } from "@/lib/telemetry";

// Error messages can carry fragments of user input (a value that
// failed to serialize, a stack trace referencing form state) --
// truncating is a simple, conservative cap, not full sanitization.
// See telemetry-plan.md §5's PII note: no email/password ever reaches
// this path, since neither auth function throws the raw form values.
const MAX_ERROR_MESSAGE_LENGTH = 200;

function sanitizeErrorMessage(raw: string): string {
  return raw.slice(0, MAX_ERROR_MESSAGE_LENGTH);
}

// Dedupe identical errors (same message + page) firing repeatedly --
// e.g. a render-loop bug -- so one bug doesn't flood the batch. Per
// telemetry-plan.md §4's throttle/debounce note.
const recentErrorKeys = new Set<string>();
const ERROR_DEDUPE_WINDOW_MS = 5_000;

function trackErrorOnce(message: string, pagePath: string): void {
  const key = `${message}::${pagePath}`;
  if (recentErrorKeys.has(key)) return;
  recentErrorKeys.add(key);
  setTimeout(() => recentErrorKeys.delete(key), ERROR_DEDUPE_WINDOW_MS);

  track("frontend_error_occurred", {
    error_message: sanitizeErrorMessage(message),
    page_path: pagePath,
  });
}

export default function TelemetryBoot() {
  const pathname = usePathname();

  // section_visited -- fires on every route change, including first
  // render. requestId is omitted: no single backend call corresponds
  // to "the user looked at this page."
  useEffect(() => {
    track("section_visited", { route: pathname });
  }, [pathname]);

  // frontend_error_occurred -- wired once at the window level for the
  // whole app, rather than per-component, per the brief's explicit
  // requirement to cover both uncaught errors and unhandled rejections.
  useEffect(() => {
    function handleError(event: ErrorEvent) {
      trackErrorOnce(event.message, window.location.pathname);
    }
    function handleRejection(event: PromiseRejectionEvent) {
      const message =
        event.reason instanceof Error ? event.reason.message : String(event.reason);
      trackErrorOnce(message, window.location.pathname);
    }

    window.addEventListener("error", handleError);
    window.addEventListener("unhandledrejection", handleRejection);
    return () => {
      window.removeEventListener("error", handleError);
      window.removeEventListener("unhandledrejection", handleRejection);
    };
  }, []);

  return null;
}
