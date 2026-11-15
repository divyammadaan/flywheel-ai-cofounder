/**
 * The shared access code a hosted deployment asks for.
 *
 * Kept in localStorage so it is typed once per browser. Every read is wrapped:
 * storage is missing during the server render and can throw in a private
 * window, and the app must behave exactly as before when no code is in use.
 */

const STORAGE_KEY = "flywheel-access-code";

/**
 * The same code, as a cookie. Plan pages are rendered on the server, which asks the
 * API for the plan itself; localStorage is invisible to it, but a cookie travels with
 * the page request. Without this, the server's request carried no code and every plan
 * page failed with "An access code is required".
 */
export const ACCESS_COOKIE = "flywheel-access-code";

function writeCookie(code: string): void {
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${ACCESS_COOKIE}=${encodeURIComponent(code)}; path=/; max-age=31536000; SameSite=Lax${secure}`;
}

function readCookie(): string {
  const match = document.cookie.split("; ").find((part) => part.startsWith(`${ACCESS_COOKIE}=`));
  return match ? decodeURIComponent(match.slice(ACCESS_COOKIE.length + 1)) : "";
}

/**
 * Make the cookie match the saved code. True if it had to be written -- the page that
 * is showing was rendered without it, so the caller reloads once.
 */
export function syncAccessCookie(): boolean {
  const code = getAccessCode();
  if (!code || readCookie() === code) return false;
  writeCookie(code);
  return true;
}

/** Fired when the API answers 401, so the gate can ask for the code again. */
export const ACCESS_REQUIRED_EVENT = "flywheel:access-required";

export function getAccessCode(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setAccessCode(code: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, code.trim());
  } catch {
    /* without storage the code is simply asked for again next visit */
  }
  writeCookie(code.trim());
}

/**
 * A URL with the code attached as a query parameter.
 *
 * For what cannot send a header: EventSource (the live progress stream), an
 * <img>, and a plain download link.
 */
export function withAccessCode(url: string): string {
  const code = getAccessCode();
  if (!code) return url;
  return `${url}${url.includes("?") ? "&" : "?"}access_code=${encodeURIComponent(code)}`;
}
