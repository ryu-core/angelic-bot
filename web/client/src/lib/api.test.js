import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/server.js";
import {
  ApiRequestError,
  api,
  formatNumber,
  formatUptime,
  json,
  safeReturnTo,
  signInPath,
} from "./api.js";

describe("API contracts", () => {
  it("unwraps the API data envelope and includes credentials", async () => {
    server.use(http.get("/api/health", ({ request }) => {
      expect(request.credentials).toBe("include");
      return HttpResponse.json({ data: { ok: true } });
    }));

    await expect(api("/api/health")).resolves.toEqual({ ok: true });
  });

  it("preserves the 204 logout contract", async () => {
    server.use(http.post("/api/auth/logout", () => new HttpResponse(null, { status: 204 })));
    await expect(api("/api/auth/logout", { method: "POST", redirectOnUnauthorized: false })).resolves.toBeNull();
  });

  it("surfaces structured 403 errors without redirecting", async () => {
    server.use(http.get("/api/settings/123", () => HttpResponse.json({
      error: { code: "FORBIDDEN", message: "Manage Server is required.", details: { guildId: "123" } },
    }, { status: 403 })));

    await expect(api("/api/settings/123")).rejects.toMatchObject({
      name: "ApiRequestError",
      code: "FORBIDDEN",
      status: 403,
      details: { guildId: "123" },
    });
  });

  it("normalizes browser-specific network failures into actionable feedback", async () => {
    server.use(http.get("/api/offline", () => HttpResponse.error()));

    await expect(api("/api/offline")).rejects.toMatchObject({
      name: "ApiRequestError",
      code: "NETWORK_ERROR",
      status: 0,
      message: "The service could not be reached. Try again.",
    });
  });

  it("keeps write payloads JSON encoded without changing their shape", () => {
    expect(json("PATCH", { prefix: "!", antiNuke: { enabled: true } })).toEqual({
      method: "PATCH",
      body: JSON.stringify({ prefix: "!", antiNuke: { enabled: true } }),
    });
  });

  it("rejects unsafe return destinations", () => {
    expect(safeReturnTo("//evil.example")).toBe("/dashboard");
    expect(safeReturnTo("/\\evil.example")).toBe("/dashboard");
    expect(safeReturnTo("/%5cevil.example")).toBe("/dashboard");
    expect(safeReturnTo("/dashboard\u000a//evil.example")).toBe("/dashboard");
    expect(safeReturnTo("/dashboard%0d%0aLocation:%20https://evil.example")).toBe("/dashboard");
    expect(safeReturnTo("https://evil.example")).toBe("/dashboard");
    expect(safeReturnTo("/settings/123?tab=security")).toBe("/settings/123?tab=security");
    expect(signInPath("/economy/123")).toBe("/?signin=1&returnTo=%2Feconomy%2F123");
  });

  it.each([
    ["non-JSON", "not json"],
    ["a missing data envelope", JSON.stringify({ ok: true })],
    ["an empty body", ""],
  ])("rejects successful responses containing %s", async (_, body) => {
    server.use(http.get("/api/malformed", () => new HttpResponse(body, { status: 200 })));

    await expect(api("/api/malformed")).rejects.toMatchObject({
      name: "ApiRequestError",
      code: "INVALID_RESPONSE",
      status: 200,
    });
  });

  it("keeps public formatting deterministic", () => {
    expect(formatNumber(12500)).toBe("13K");
    expect(formatUptime(90061)).toBe("1d 1h");
    expect(new ApiRequestError("No", "NO", 400)).toBeInstanceOf(Error);
  });
});
