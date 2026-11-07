import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PublicApiState from "./PublicApiState.jsx";

describe("PublicApiState", () => {
  it("renders request Error objects as a resilient message", () => {
    render(<PublicApiState error={new Error("Network unavailable")} onRetry={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent("Network unavailable");
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  });
});
