import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useStatus } from "../hooks/useStatus.jsx";
import InvitesPage from "./InvitesPage.jsx";

vi.mock("../hooks/useStatus.jsx", () => ({ useStatus: vi.fn() }));

describe("InvitesPage", () => {
  beforeEach(() => {
    useStatus.mockReturnValue({
      connectionState: "online",
      status: { online: true, guilds: 42, users: 12_500, latency: 37 },
    });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it("builds an allow-listed same-origin invite from the selected preset", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><InvitesPage /></MemoryRouter>);

    const administrator = screen.getByRole("button", { name: /Administrator/ });
    const recommended = screen.getByRole("button", { name: /Recommended/ });
    expect(administrator).toHaveAttribute("aria-pressed", "true");

    await user.click(recommended);

    const path = "/api/invite?permissions=268823648";
    expect(recommended).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Generated same-origin invite").value).toBe(new URL(path, window.location.origin).toString());
    expect(screen.getByRole("link", { name: /Open Invite/ })).toHaveAttribute("href", path);
  });

  it("copies the generated URL and announces accessible feedback", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    render(<MemoryRouter><InvitesPage /></MemoryRouter>);

    await user.click(screen.getByRole("button", { name: "Copy Link" }));

    expect(writeText).toHaveBeenCalledWith(
      new URL("/api/invite?permissions=8", window.location.origin).toString(),
    );
    expect(screen.getByRole("status")).toHaveTextContent("Invite link copied");
  });

  it("shows live footprint and the three continuation routes without accessibility violations", async () => {
    const { container } = render(<MemoryRouter><InvitesPage /></MemoryRouter>);

    expect(screen.getByText("42")).toBeVisible();
    expect(screen.getByText("13K")).toBeVisible();
    expect(screen.getByRole("link", { name: /Commands/ })).toHaveAttribute("href", "/commands");
    expect(screen.getByRole("link", { name: /Status/ })).toHaveAttribute("href", "/status");
    expect(screen.getByRole("link", { name: /Dashboard/ })).toHaveAttribute("href", "/dashboard");
    expect(await axe(container)).toHaveNoViolations();
  });
});
