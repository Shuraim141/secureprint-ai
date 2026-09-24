import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, describeError, setUnauthorizedHandler, tokenStore } from "./api";

function mockFetch(status, body) {
  const fn = vi.fn(async () => ({
    status,
    ok: status >= 200 && status < 300,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("api client", () => {
  beforeEach(() => {
    tokenStore.clear();
    setUnauthorizedHandler(null);
    vi.unstubAllGlobals();
  });

  it("sends the bearer token on authenticated calls only", async () => {
    tokenStore.set("abc");
    const spy = mockFetch(200, { id: 1 });
    await api.me();
    expect(spy.mock.calls[0][1].headers.Authorization).toBe("Bearer abc");
    await api.health();
    expect(spy.mock.calls[1][1].headers.Authorization).toBeUndefined();
  });

  it("clears the session and notifies the app on 401 with a held token", async () => {
    tokenStore.set("expired");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(401, { detail: "Not authenticated" });
    await expect(api.me()).rejects.toMatchObject({ status: 401, message: "Not authenticated" });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not treat a failed login as an expired session", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(401, { detail: "Invalid username or password" });
    await expect(api.login("u", "bad")).rejects.toBeInstanceOf(ApiError);
    expect(handler).not.toHaveBeenCalled();
  });

  it("reports an unreachable backend clearly", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network down"); }));
    await expect(api.health()).rejects.toMatchObject({ status: 0 });
  });

  it("formats validation errors and skips empty query values", async () => {
    expect(describeError({ detail: [{ loc: ["body", "password"], msg: "too short" }] }, 422)).toBe("password: too short");
    const spy = mockFetch(200, { items: [] });
    await api.auditLogs({ limit: 8, user: "", action: undefined });
    expect(spy.mock.calls[0][0]).toBe("/api/audit/logs?limit=8");
  });
});
