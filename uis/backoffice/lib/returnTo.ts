/**
 * returnTo.ts -- decides whether a "returnTo" address is safe to send a
 * login token to. Without this check, a crafted login link could send a
 * user's token to any website.
 *
 * Allowed: localhost (only when this page is also on localhost), a sibling
 * port of the same Codespace, and origins listed in
 * NEXT_PUBLIC_ALLOWED_RETURN_ORIGINS (comma separated, for production).
 * Anything else returns null.
 */
const EXTRA_ORIGINS: string[] = (process.env.NEXT_PUBLIC_ALLOWED_RETURN_ORIGINS ?? "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

const CODESPACE_HOST = /^(.+)-\d+\.app\.github\.dev$/;

function isLocal(url: URL): boolean {
  return url.hostname === "localhost" || url.hostname === "127.0.0.1";
}

export function safeReturnTo(
  value: string | null,
  currentHref: string,
  extraOrigins: string[] = EXTRA_ORIGINS
): string | null {
  if (!value) return null;
  let target: URL;
  let here: URL;
  try {
    target = new URL(value);
    here = new URL(currentHref);
  } catch {
    return null;
  }
  if (target.protocol !== "http:" && target.protocol !== "https:") return null;
  if (target.username || target.password) return null;

  const clean = target.origin + target.pathname + target.search;

  if (extraOrigins.includes(target.origin)) return clean;
  if (isLocal(here) && isLocal(target)) return clean;

  const hereSpace = CODESPACE_HOST.exec(here.hostname);
  const targetSpace = CODESPACE_HOST.exec(target.hostname);
  if (
    hereSpace &&
    targetSpace &&
    target.protocol === "https:" &&
    hereSpace[1] === targetSpace[1]
  ) {
    return clean;
  }
  return null;
}
