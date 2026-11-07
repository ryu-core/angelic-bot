import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ApiState from "./ApiState.jsx";

describe("ApiState", () => {
  it("announces loading without exposing the decorative spinner", () => {
    render(<ApiState loading><div>Content</div></ApiState>);
    expect(screen.getByRole("status")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText("Content")).not.toBeInTheDocument();
  });

  it("renders 403 as access denied without a retry action", () => {
    render(<ApiState error={{ status: 403, message: "Manage Server is required." }} onRetry={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Access denied");
    expect(screen.getByRole("link", { name: "Return to Dashboard" })).toHaveAttribute("href", "/dashboard");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("keeps stale children mounted while refreshing", () => {
    render(<ApiState refreshing><div>Existing records</div></ApiState>);
    expect(screen.getByText("Existing records")).toBeVisible();
    expect(screen.getByText(/Refreshing live data/)).toBeInTheDocument();
  });

  it("keeps stale children mounted with retry feedback after refresh failure", () => {
    render(
      <ApiState stale error={new Error("Refresh failed")} onRetry={vi.fn()}>
        <div>Existing records</div>
      </ApiState>,
    );
    expect(screen.getByText("Existing records")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("Refresh failed");
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  });
});
