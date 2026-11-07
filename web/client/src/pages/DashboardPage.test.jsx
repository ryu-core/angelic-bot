import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useApi } from "../hooks/useApi.js";
import DashboardPage from "./DashboardPage.jsx";

vi.mock("../hooks/useApi.js", () => ({
  useApi: vi.fn(),
}));

describe("DashboardPage", () => {
  beforeEach(() => {
    useApi.mockReturnValue({
      data: [],
      loading: false,
      refreshing: false,
      error: null,
      reload: vi.fn(),
    });
  });

  it("offers actionable guidance when no manageable servers exist", () => {
    render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "No manageable servers found" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Invite xiel to a server" })).toHaveAttribute("href", "/api/invite");
    expect(screen.getByRole("button", { name: /Refresh access/ })).toBeEnabled();
  });

  it("normalizes malformed fields and gives repeated actions guild context", async () => {
    useApi.mockReturnValue({
      data: [
        null,
        { id: "", name: "Invalid" },
        { id: "123", name: "", icon: null, memberCount: undefined, owner: true },
        { id: "456", name: "Citadel Prime", icon: null, memberCount: 42 },
      ],
      loading: false,
      refreshing: false,
      error: null,
      reload: vi.fn(),
    });

    const { container } = render(<MemoryRouter><DashboardPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Unnamed server" })).toBeVisible();
    expect(screen.getByText("Member count unavailable")).toBeVisible();
    expect(screen.getByRole("link", { name: "Open settings for Citadel Prime" })).toHaveAttribute("href", "/settings/456");
    expect(screen.getByRole("link", { name: "Open economy for Citadel Prime" })).toHaveAttribute("href", "/economy/456");
    expect(await axe(container)).toHaveNoViolations();
  });
});
