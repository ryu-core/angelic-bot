import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useApi } from "../hooks/useApi.js";
import { api } from "../lib/api.js";
import PrivilegedConsole from "./PrivilegedConsole.jsx";

vi.mock("../hooks/useApi.js", () => ({
  useApi: vi.fn(),
}));
vi.mock("../lib/api.js", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, api: vi.fn() };
});

const overview = {
  servers: [{ id: "123", name: "Citadel Prime", memberCount: 10 }],
  premium: [],
  profiles: [],
};

describe("PrivilegedConsole capability boundary", () => {
  beforeEach(() => {
    api.mockReset();
    useApi.mockImplementation((path) => ({
      data: path.endsWith("/bans") ? [] : overview,
      loading: false,
      error: null,
      reload: vi.fn(),
    }));
  });

  it("never mounts owner requests or controls for a co-owner", async () => {
    const { container } = render(<PrivilegedConsole capability="coowner" />);

    expect(useApi).toHaveBeenCalledTimes(1);
    expect(useApi).toHaveBeenCalledWith("/api/coowner/overview");
    expect(screen.queryByText("Global ban citadel")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Leave server/ })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("mounts owner-only data and actions only for owners", () => {
    render(<PrivilegedConsole capability="owner" />);

    expect(useApi).toHaveBeenCalledWith("/api/owner/overview");
    expect(useApi).toHaveBeenCalledWith("/api/owner/bans");
    expect(screen.getByText("Global ban citadel")).toBeVisible();
    expect(screen.getByRole("button", { name: /Make the bot leave Citadel Prime/ })).toBeEnabled();
  });

  it("uses the co-owner premium grant endpoint and exact payload", async () => {
    const user = userEvent.setup();
    api.mockResolvedValue({});
    render(<PrivilegedConsole capability="coowner" />);

    const panel = screen.getByRole("heading", { name: "Grant premium access" }).closest("section");
    await user.type(within(panel).getByLabelText("Discord user ID"), "123456789012345678");
    await user.type(within(panel).getByLabelText("Discord server ID"), "987654321098765432");
    await user.clear(within(panel).getByLabelText("Command scope"));
    await user.type(within(panel).getByLabelText("Command scope"), "antinuke");
    await user.click(within(panel).getByRole("button", { name: "Grant premium" }));

    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/api/coowner/premium",
      {
        method: "POST",
        body: JSON.stringify({
          userId: "123456789012345678",
          guildId: "987654321098765432",
          commandName: "antinuke",
        }),
      },
    ));
  });

  it("requires confirmation before posting an owner global ban", async () => {
    const user = userEvent.setup();
    api.mockResolvedValue({});
    render(<PrivilegedConsole capability="owner" />);

    const panel = screen.getByRole("heading", { name: "Global ban citadel" }).closest("section");
    await user.type(within(panel).getByLabelText("Discord user ID"), "123456789012345678");
    await user.type(within(panel).getByLabelText("Ban reason"), "Coordinated abuse");
    await user.click(within(panel).getByRole("button", { name: "Review global ban" }));
    expect(api).not.toHaveBeenCalled();

    await user.click(within(panel).getByRole("button", { name: "Apply global ban" }));
    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/api/owner/bans",
      {
        method: "POST",
        body: JSON.stringify({
          userId: "123456789012345678",
          reason: "Coordinated abuse",
        }),
      },
    ));
  });
});
