// REST client for the SecurePrint API. Every call goes to the real backend; nothing is mocked.
//
// Token storage decision (MVP): the JWT lives in sessionStorage, so it survives a page reload but
// is cleared when the tab closes. Trade-off: readable by any script running in the page (XSS).
// Production: httpOnly + SameSite cookies set by the backend, plus a strict Content-Security-Policy.

const BASE = import.meta.env?.VITE_API_BASE ?? "";
const TOKEN_KEY = "secureprint.token";

export class ApiError extends Error {
  constructor(status, message, detail = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export const tokenStore = {
  get() {
    try {
      return sessionStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token) {
    try {
      sessionStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable: user will simply have to log in again after reload */
    }
  },
  clear() {
    try {
      sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  },
};

let unauthorizedHandler = null;
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

export function describeError(data, status) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join("; ");
  }
  if (status === 403) return "You do not have permission to do that.";
  if (status === 404) return "Not found.";
  return `Request failed (HTTP ${status}).`;
}

async function request(path, { method = "GET", body, auth = true, signal } = {}) {
  const headers = { Accept: "application/json" };
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  const token = tokenStore.get();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error?.name === "AbortError") throw error;
    throw new ApiError(0, "Cannot reach the SecurePrint API. Is the backend running on port 8000?");
  }

  if (response.status === 204) return null;
  let data = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    // A 401 while we hold a token means it expired or was revoked: drop it and return to login.
    if (response.status === 401 && auth && token && unauthorizedHandler) unauthorizedHandler();
    throw new ApiError(response.status, describeError(data, response.status), data);
  }
  return data;
}

function withQuery(path, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}

export const api = {
  login: (username, password) =>
    request("/api/auth/login", { method: "POST", body: { username, password }, auth: false }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  me: (signal) => request("/api/auth/me", { signal }),
  health: (signal) => request("/health", { auth: false, signal }),
  dashboardSummary: (signal) => request("/api/dashboard/summary", { signal }),
  auditLogs: (params, signal) => request(withQuery("/api/audit/logs", params), { signal }),
  verifyAuditChain: (signal) => request("/api/audit/verify", { signal }),
};
