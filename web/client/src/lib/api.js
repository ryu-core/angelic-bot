export class ApiRequestError extends Error {
  constructor(message, code, status, details) {
    super(message);
    this.name = "ApiRequestError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

const RETURN_TO_KEY = "xiel:returnTo";

function hasUnsafeReturnCharacter(value) {
  return value.includes("\\") || [...value].some((character) => {
    const code = character.charCodeAt(0);
    return code <= 31 || code === 127;
  });
}

export function safeReturnTo(value, fallback = "/dashboard") {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) return fallback;
  if (hasUnsafeReturnCharacter(value)) return fallback;

  let decoded;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    return fallback;
  }
  if (hasUnsafeReturnCharacter(decoded) || decoded.startsWith("//")) return fallback;

  try {
    const origin = typeof window === "undefined" ? "http://localhost" : window.location.origin;
    const destination = new URL(value, origin);
    if (destination.origin !== origin || destination.username || destination.password) return fallback;
    return `${destination.pathname}${destination.search}${destination.hash}`;
  } catch {
    return fallback;
  }
}

export function currentReturnTo() {
  if (typeof window === "undefined") return "/dashboard";
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

export function rememberReturnTo(value) {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(RETURN_TO_KEY, safeReturnTo(value));
  } catch {
    // Login still works when storage is unavailable; only the post-login return is lost.
  }
}

export function consumeReturnTo() {
  if (typeof window === "undefined") return null;
  try {
    const value = window.sessionStorage.getItem(RETURN_TO_KEY);
    window.sessionStorage.removeItem(RETURN_TO_KEY);
    return value ? safeReturnTo(value) : null;
  } catch {
    return null;
  }
}

export function clearReturnTo() {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(RETURN_TO_KEY);
  } catch {
    // Storage may be disabled.
  }
}

export function signInPath(returnTo = currentReturnTo()) {
  return `/?signin=1&returnTo=${encodeURIComponent(safeReturnTo(returnTo))}`;
}

export function redirectToSignIn(returnTo = currentReturnTo()) {
  if (typeof window === "undefined") return;
  const destination = safeReturnTo(returnTo);
  rememberReturnTo(destination);
  const current = `${window.location.pathname}${window.location.search}`;
  const signIn = signInPath(destination);
  if (current !== signIn) window.location.assign(signIn);
}

export async function api(path, options = {}) {
  const { redirectOnUnauthorized = true, ...fetchOptions } = options;
  let response;
  try {
    response = await fetch(path, {
      credentials: "include",
      ...fetchOptions,
      headers: { ...(fetchOptions.body ? { "Content-Type": "application/json" } : {}), ...fetchOptions.headers },
    });
  } catch (cause) {
    if (cause?.name === "AbortError") throw cause;
    const offline = typeof navigator !== "undefined" && navigator.onLine === false;
    throw new ApiRequestError(
      offline ? "You appear to be offline. Reconnect and try again." : "The service could not be reached. Try again.",
      "NETWORK_ERROR",
      0,
      { cause: cause?.message },
    );
  }
  if (response.status === 204) return null;
  let payload;
  try {
    payload = JSON.parse(await response.text());
  } catch {
    if (response.ok) {
      throw new ApiRequestError(
        "The service returned an invalid response. Try again.",
        "INVALID_RESPONSE",
        response.status,
      );
    }
    payload = {};
  }
  if (!response.ok) {
    const error = new ApiRequestError(
      payload?.error?.message || (response.status === 403 ? "You do not have access to this resource." : "Request failed."),
      payload?.error?.code,
      response.status,
      payload?.error?.details,
    );
    if (response.status === 401 && redirectOnUnauthorized) redirectToSignIn();
    throw error;
  }
  if (!payload || typeof payload !== "object" || !Object.prototype.hasOwnProperty.call(payload, "data")) {
    throw new ApiRequestError(
      "The service returned an invalid response. Try again.",
      "INVALID_RESPONSE",
      response.status,
    );
  }
  return payload.data;
}

export function json(method, body) {
  return { method, body: JSON.stringify(body) };
}

export function formatNumber(value) {
  return new Intl.NumberFormat("en", { notation: Number(value) > 9999 ? "compact" : "standard" }).format(value || 0);
}

export function formatUptime(seconds = 0) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return days ? `${days}d ${hours}h` : hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}
