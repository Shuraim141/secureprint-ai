import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, tokenStore } from "./api";

function mockFetch(status, body, headers = {}) {
  const fn = vi.fn(async () => ({
    status,
    ok: status >= 200 && status < 300,
    headers: { get: (name) => headers[name.toLowerCase()] ?? null },
    text: async () => (body === undefined || body instanceof Blob ? "" : JSON.stringify(body)),
    blob: async () => body,
  }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("design API calls", () => {
  beforeEach(() => {
    tokenStore.set("tok");
    vi.unstubAllGlobals();
  });

  it("registerDesign sends multipart form data, not JSON", async () => {
    const spy = mockFetch(201, { id: 1 });
    await api.registerDesign(new File(["x"], "a.stl"), "My Part");
    const init = spy.mock.calls[0][1];
    expect(init.headers["Content-Type"]).toBeUndefined(); // browser sets multipart boundary itself
    expect(init.body).toBeInstanceOf(FormData);
    expect(init.body.get("name")).toBe("My Part");
  });

  it("verifyDesign omits design_id when none is given", async () => {
    const spy = mockFetch(200, { verdict: "UNREGISTERED" });
    await api.verifyDesign(new File(["x"], "a.stl"), null);
    expect(spy.mock.calls[0][1].body.has("design_id")).toBe(false);
    await api.verifyDesign(new File(["x"], "a.stl"), 7);
    expect(spy.mock.calls[1][1].body.get("design_id")).toBe("7");
  });

  it("downloadVersion returns a blob and reads the filename from Content-Disposition", async () => {
    const blob = new Blob(["binary"]);
    mockFetch(200, blob, { "content-disposition": 'attachment; filename="bracket.stl"' });
    const result = await api.downloadVersion(1, 1);
    expect(result.filename).toBe("bracket.stl");
    expect(result.blob).toBe(blob);
  });

  it("save4dProfile sends JSON to the PUT endpoint", async () => {
    const spy = mockFetch(200, { security_fingerprint: "abc" });
    await api.save4dProfile(3, { material_id: "X" });
    expect(spy.mock.calls[0][0]).toBe("/api/designs/3/4d");
    expect(spy.mock.calls[0][1].method).toBe("PUT");
    expect(JSON.parse(spy.mock.calls[0][1].body).material_id).toBe("X");
  });
});
