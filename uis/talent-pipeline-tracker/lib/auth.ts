// lib/auth.ts
//
// Reads and checks the session token. This app never sets one itself
// -- there's no /login here by design (AUTH-02's decision: Backoffice
// hosts the shared login/register/account views, other apps only read
// and check the token, and send the person to Backoffice when it's
// missing or invalid).

const TOKEN_KEY = "brasaland_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

// Decodes a JWT's payload WITHOUT checking its signature -- that only
// means something on the server, which holds the secret key. Just
// enough to answer "has this obviously expired?"
export function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    if (typeof payload.exp !== "number") return false;
    return Date.now() >= payload.exp * 1000;
  } catch {
    return true;
  }
}

export function hasValidToken(): boolean {
  const token = getToken();
  return token !== null && !isTokenExpired(token);
}

// Backoffice's dev port is fixed at 3000 (see its package.json "dev"
// script), so Backoffice's URL can be derived from this app's own
// current URL. Handles both plain localhost dev and GitHub Codespaces
// forwarded URLs ("<codespace-name>-<port>.app.github.dev") -- a
// hardcoded "localhost:3000" would silently point at your own machine
// instead of the Codespace when you're on a forwarded preview URL.
const BACKOFFICE_PORT = "3000";

export function getBackofficeLoginUrl(returnTo?: string): string {
  if (typeof window === "undefined") return "/";
  const { protocol, hostname } = window.location;

  let backofficeHost: string;
  if (hostname.endsWith(".app.github.dev")) {
    backofficeHost = hostname.replace(
      /-\d+\.app\.github\.dev$/,
      `-${BACKOFFICE_PORT}.app.github.dev`
    );
  } else {
    backofficeHost = `localhost:${BACKOFFICE_PORT}`;
  }

  const loginUrl = `${protocol}//${backofficeHost}/login`;
  return returnTo ? `${loginUrl}?returnTo=${encodeURIComponent(returnTo)}` : loginUrl;
}
