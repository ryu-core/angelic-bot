import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import RequireAuth from "../components/RequireAuth.jsx";
import { server } from "../test/server.js";
import { AuthProvider, useAuth } from "./useAuth.jsx";

function AuthSnapshot() {
  const { user, loading, error } = useAuth();
  return <div>
    <span>{loading ? "loading" : "settled"}</span>
    <span>{user === null ? "unauthenticated" : user?.username || "unknown"}</span>
    {error && <span role="alert">{error.message}</span>}
  </div>;
}

describe("AuthProvider", () => {
  it("marks an explicit 401 as unauthenticated without an auth error", async () => {
    server.use(http.get("/api/auth/me", () => HttpResponse.json({
      error: { code: "UNAUTHENTICATED", message: "Sign in required." },
    }, { status: 401 })));

    render(<MemoryRouter><AuthProvider><AuthSnapshot /></AuthProvider></MemoryRouter>);
    await screen.findByText("unauthenticated");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps a 5xx failure out of the OAuth redirect path and exposes a working retry", async () => {
    let requests = 0;
    server.use(http.get("/api/auth/me", () => {
      requests += 1;
      if (requests === 1) {
        return HttpResponse.json({ error: { code: "UNAVAILABLE", message: "Auth service unavailable." } }, { status: 503 });
      }
      return HttpResponse.json({ data: { id: "1", username: "Operator", role: "user" } });
    }));

    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <AuthProvider>
          <Routes>
            <Route element={<RequireAuth />}>
              <Route path="/dashboard" element={<h1>Protected dashboard</h1>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Auth service unavailable.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Protected dashboard" })).toBeVisible());
  });

  it.each([
    ["403", () => HttpResponse.json({
      error: { code: "FORBIDDEN", message: "Session verification was forbidden." },
    }, { status: 403 }), "Session verification was forbidden."],
    ["network failure", () => HttpResponse.error(), "The service could not be reached. Try again."],
  ])("treats %s as an auth error instead of unauthenticated", async (_, response, message) => {
    server.use(http.get("/api/auth/me", response));

    render(<MemoryRouter><AuthProvider><AuthSnapshot /></AuthProvider></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByText("unknown")).toBeVisible();
    expect(screen.queryByText("unauthenticated")).not.toBeInTheDocument();
  });
});
