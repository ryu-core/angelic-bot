import { act, renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, delay, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/server.js";
import { useApi } from "./useApi.js";

describe("useApi", () => {
  it("loads data and retains it during a background refresh", async () => {
    let request = 0;
    server.use(http.get("/api/servers", async () => {
      request += 1;
      if (request > 1) await delay(80);
      return HttpResponse.json({ data: [{ id: String(request) }] });
    }));

    const { result } = renderHook(() => useApi("/api/servers"));
    await waitFor(() => expect(result.current.data).toEqual([{ id: "1" }]));

    act(() => {
      void result.current.reload();
    });

    expect(result.current.data).toEqual([{ id: "1" }]);
    expect(result.current.refreshing).toBe(true);
    expect(result.current.stale).toBe(true);
    await waitFor(() => expect(result.current.data).toEqual([{ id: "2" }]));
  });

  it("exposes 403 as a forbidden inline state", async () => {
    server.use(http.get("/api/settings/123", () => HttpResponse.json({
      error: { code: "FORBIDDEN", message: "No access." },
    }, { status: 403 })));

    const { result } = renderHook(() => useApi("/api/settings/123"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.forbidden).toBe(true);
    expect(result.current.error).toMatchObject({ status: 403, message: "No access." });
  });

  it("lets the newest reload win", async () => {
    let request = 0;
    server.use(http.get("/api/status", async () => {
      request += 1;
      const current = request;
      await delay(current === 2 ? 80 : current === 3 ? 10 : 0);
      return HttpResponse.json({ data: { request: current } });
    }));

    const { result } = renderHook(() => useApi("/api/status"));
    await waitFor(() => expect(result.current.data).toEqual({ request: 1 }));

    act(() => {
      void result.current.reload();
      void result.current.reload();
    });

    await waitFor(() => expect(result.current.data).toEqual({ request: 3 }));
    await delay(100);
    expect(result.current.data).toEqual({ request: 3 });
  });

  it("never exposes data from the previous path while a new guild loads", async () => {
    server.use(
      http.get("/api/settings/one", () => HttpResponse.json({ data: { prefix: "!" } })),
      http.get("/api/settings/two", async () => {
        await delay(50);
        return HttpResponse.json({ data: { prefix: "?" } });
      }),
    );

    const { result, rerender } = renderHook(
      ({ guild }) => useApi(`/api/settings/${guild}`),
      { initialProps: { guild: "one" } },
    );
    await waitFor(() => expect(result.current.data).toEqual({ prefix: "!" }));

    rerender({ guild: "two" });
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.data).toEqual({ prefix: "?" }));
  });
});
