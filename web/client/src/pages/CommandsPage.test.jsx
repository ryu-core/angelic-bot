import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useApi } from "../hooks/useApi.js";
import CommandsPage from "./CommandsPage.jsx";

vi.mock("../hooks/useApi.js", () => ({
  useApi: vi.fn(),
}));

const commands = [
  {
    id: "prefix:ban",
    name: "ban",
    aliases: ["hammer", "remove"],
    syntax: ",ban <member> [reason]",
    category: "Moderation",
    description: "Remove a member and record the moderation reason.",
    source: "cogs/moderation.py",
    kind: "prefix",
    premium: false,
    restricted: false,
  },
  {
    id: "slash:imagine",
    name: "imagine",
    aliases: ["dream"],
    syntax: "/imagine <prompt>",
    category: "AI Chat",
    description: "Create an image from a prompt.",
    source: "cogs/ai_chat.py",
    kind: "slash",
    premium: true,
    restricted: true,
  },
  {
    id: "prefix:sync",
    name: "sync",
    aliases: [],
    syntax: ",sync",
    category: "Owner",
    description: "Synchronize application commands.",
    source: "cogs/owner.py",
    kind: "prefix",
    premium: false,
    restricted: true,
  },
];

describe("CommandsPage", () => {
  beforeEach(() => {
    useApi.mockReturnValue({
      data: commands,
      loading: false,
      refreshing: false,
      stale: false,
      error: null,
      reload: vi.fn(),
    });
  });

  it("builds metrics and category slides entirely from the backend registry", () => {
    render(<CommandsPage />);
    const summary = screen.getByRole("region", { name: "Command summary" });

    expect(within(within(summary).getByText("Total commands").parentElement).getByText("3")).toBeVisible();
    expect(within(within(summary).getByText("Categories").parentElement).getByText("3")).toBeVisible();
    expect(within(within(summary).getByText("Aliases").parentElement).getByText("3")).toBeVisible();
    expect(screen.getByRole("button", { name: /AI Chat.*1 entry/ })).toBeVisible();
    expect(screen.getByRole("button", { name: /Moderation.*1 entry/ })).toBeVisible();
    expect(screen.getByRole("button", { name: /Owner.*1 entry/ })).toBeVisible();

    // Owner commands returned by the API remain visible; authorization belongs to the backend.
    expect(screen.getByRole("heading", { name: "sync" })).toBeVisible();
    expect(screen.getByText("prefix:sync")).toBeVisible();
    expect(screen.getByText("cogs/owner.py")).toBeVisible();
  });

  it("combines category slides with indexed search and can reset an empty result", async () => {
    const user = userEvent.setup();
    render(<CommandsPage />);

    await user.click(screen.getByRole("button", { name: /Moderation.*1 entry/ }));
    expect(screen.getByRole("heading", { name: "ban" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "imagine" })).not.toBeInTheDocument();

    await user.type(screen.getByRole("searchbox", { name: "Search commands" }), "dream");
    expect(screen.getByRole("heading", { name: "No commands fit those filters." })).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Show all commands" }));
    expect(screen.getByRole("heading", { name: "imagine" })).toBeVisible();
    expect(screen.getByRole("searchbox", { name: "Search commands" })).toHaveValue("");
  });

  it("copies exact command syntax and announces success accessibly", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(<CommandsPage />);

    fireEvent.click(screen.getByRole("button", { name: "Copy syntax for imagine" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("/imagine <prompt>"));
    expect(screen.getByRole("button", { name: "Copied syntax for imagine" })).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("imagine syntax copied to the clipboard.");
  });

  it("keeps stale commands available when a refresh fails", () => {
    useApi.mockReturnValue({
      data: commands,
      loading: false,
      refreshing: false,
      stale: true,
      error: new Error("Refresh unavailable"),
      reload: vi.fn(),
    });

    render(<CommandsPage />);

    expect(screen.getByRole("alert")).toHaveTextContent("Refresh unavailable");
    expect(screen.getByRole("heading", { name: "ban" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  });
});
