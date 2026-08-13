// lib/auth.ts
//
// Everything to do with WHERE the token lives. Nothing here talks to
// the network -- that's lib/api.ts, which imports these functions.

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

// Decodes a JWT's payload WITHOUT checking its signature -- signature
// verification only means something on the server, which is the only
// place that holds the secret key. This is just enough to answer "has
// this obviously expired?" so the route guard can redirect before even
// attempting an API call, rather than waiting for a 401 to come back.
export function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    if (typeof payload.exp !== "number") return false;
    return Date.now() >= payload.exp * 1000;
  } catch {
    // Not a well-formed JWT at all -- treat that as expired/invalid too.
    return true;
  }
}

export function hasValidToken(): boolean {
  const token = getToken();
  return token !== null && !isTokenExpired(token);
}