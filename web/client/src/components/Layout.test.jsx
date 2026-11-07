import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuth } from "../hooks/useAuth.jsx";
import { useCapabilities } from "../hooks/useCapabilities.js";
import { useStatus } from "../hooks/useStatus.jsx";
import Layout from "./Layout.jsx";

vi.mock("../hooks/useAuth.jsx", () => ({ useAuth: vi.fn() }));
vi.mock("../hooks/useCapabilities.js", () => ({ useCapabilities: vi.fn() }));
vi.mock("../hooks/useStatus.jsx", () => ({ useStatus: vi.fn() }));

describe("Layout shells", () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ user: null, loading: false, login: vi.fn(), logout: vi.fn() });
    useCapabilities.mockReturnValue({ compactNavigation: false });
    useStatus.mockReturnValue({ connectionState: "checking" });
  });

  it("keeps public navigation and footer on public routes", async () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/commands"]}>
        <Layout><h1>Commands</h1></Layout>
      </MemoryRouter>,
    );

    expect(screen.getByRole("contentinfo")).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("Checking");
    expect(container.querySelector(".public-shell")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("uses operational chrome without the marketing footer", () => {
    useAuth.mockReturnValue({
      user: { id: "1", username: "Owner", avatar: null, role: "owner" },
      loading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    const { container } = render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Layout><h1>Managed servers</h1></Layout>
      </MemoryRouter>,
    );

    expect(container.querySelector(".authenticated-shell")).toBeInTheDocument();
    expect(screen.queryByRole("contentinfo")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Owner" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Co-owner" })).toBeVisible();
  });

  it("opens and closes the compact native-dialog navigation", async () => {
    const user = userEvent.setup();
    useCapabilities.mockReturnValue({ compactNavigation: true });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <Layout><h1>Home</h1></Layout>
      </MemoryRouter>,
    );

    const trigger = screen.getByRole("button", { name: "Open navigation" });
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const close = screen.getByRole("button", { name: "Close navigation" });
    await user.click(close);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});
