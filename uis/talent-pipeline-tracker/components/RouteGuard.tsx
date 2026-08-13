"use client";

import { useEffect, useState } from "react";
import { getBackofficeLoginUrl, hasValidToken, setToken } from "@/lib/auth";

// This whole app is internal, so there's no public/protected split to
// manage -- this guard wraps every page once, in the root layout.
export default function RouteGuard({
  children,
}: {
  children: React.ReactNode;
}) {
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    // If we just got sent back here after logging in on Backoffice,
    // the token rides along as a URL fragment (#token=...) rather than
    // a query param -- fragments are never sent to the server, so this
    // never touches a log file or a Referer header, only this app's
    // own JS. Claim it into our own localStorage, then scrub it from
    // the visible URL with replaceState so it doesn't linger in
    // history.
    if (window.location.hash.startsWith("#token=")) {
      const token = decodeURIComponent(
        window.location.hash.slice("#token=".length)
      );
      setToken(token);
      window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search
      );
    }

    if (!hasValidToken()) {
      // Pass our own current URL as returnTo, so Backoffice's login
      // knows where to hand the token back to once it's issued.
      window.location.href = getBackofficeLoginUrl(window.location.href);
      return;
    }
    setChecking(false);
  }, []);

  if (checking) return null;

  return <>{children}</>;
}