import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useApi } from "../hooks/useApi.js";
import DocsPage from "./DocsPage.jsx";

vi.mock("../hooks/useApi.js", () => ({ useApi: vi.fn() }));

describe("DocsPage resilience", () => {
  it("renders the manual while live command totals are still loading", () => {
    useApi.mockReturnValue({
      data: null,
      loading: true,
      refreshing: false,
      error: null,
      reload: vi.fn(),
    });

    render(<DocsPage />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading live command totals");
    expect(screen.getByRole("heading", { name: "Getting started" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Live command registry" })).toBeVisible();
  });

  it("keeps the operator manual available when live command counts fail", () => {
    useApi.mockReturnValue({
      data: null,
      loading: false,
      error: new Error("Registry unavailable"),
      reload: vi.fn(),
    });

    render(<DocsPage />);

    expect(screen.getByRole("alert")).toHaveTextContent("Registry unavailable");
    expect(screen.getByRole("heading", { name: "Getting started" })).toBeVisible();
    expect(screen.getByRole("navigation")).toBeVisible();
    expect(screen.getAllByText("unavailable").length).toBeGreaterThan(0);
  });
});
