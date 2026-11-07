import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useApi } from "../hooks/useApi.js";
import { api } from "../lib/api.js";
import SettingsPage from "./SettingsPage.jsx";

vi.mock("../hooks/useApi.js", () => ({ useApi: vi.fn() }));
vi.mock("../lib/api.js", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, api: vi.fn() };
});

const moduleRule = { enabled: true, threshold: 3, punishment: "ban" };
const settings = {
  prefix: "!",
  antiNuke: {
    enabled: true,
    logChannelId: "",
    modules: {
      ban: { ...moduleRule },
      kick: { ...moduleRule },
      channel: { ...moduleRule },
      role: { ...moduleRule },
      webhook: { ...moduleRule },
      botadd: { ...moduleRule },
    },
  },
  welcome: { enabled: false, channelId: "", message: "" },
  leave: { enabled: false, channelId: "", message: "" },
  inviteLog: { joinChannelId: "", leaveChannelId: "" },
  access: { admins: [], whitelist: [], trust: [] },
  aliases: [{ name: "rules", command: "help moderation" }],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/settings/123"]}>
      <Routes>
        <Route path="/settings/:guildId" element={<SettingsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SettingsPage write contracts", () => {
  beforeEach(() => {
    useApi.mockReturnValue({
      data: settings,
      loading: false,
      error: null,
      reload: vi.fn(),
    });
    api.mockReset();
  });

  it("PATCHes only the bulk settings contract", async () => {
    const user = userEvent.setup();
    api.mockResolvedValue({ ...settings, prefix: "?" });
    renderPage();

    const prefix = await screen.findByLabelText("Prefix");
    await user.clear(prefix);
    await user.type(prefix, "?");
    await user.click(screen.getByRole("button", { name: "Save all" }));

    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/api/settings/123",
      {
        method: "PATCH",
        body: JSON.stringify({
          prefix: "?",
          antiNuke: settings.antiNuke,
          welcome: settings.welcome,
          leave: settings.leave,
          inviteLog: settings.inviteLog,
          access: settings.access,
        }),
      },
    ));
  });

  it("applies alias creation immediately with the existing POST payload", async () => {
    const user = userEvent.setup();
    api.mockResolvedValue([{ name: "guide", command: "help docs" }]);
    renderPage();

    await user.type(await screen.findByLabelText("Alias"), "Guide");
    await user.type(screen.getByLabelText("Existing command"), "help docs");
    await user.click(screen.getByRole("button", { name: "Add alias" }));

    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/api/settings/123/aliases",
      { method: "POST", body: JSON.stringify({ name: "guide", command: "help docs" }) },
    ));
  });

  it("deletes an alias through its encoded DELETE endpoint", async () => {
    const user = userEvent.setup();
    api.mockResolvedValue([]);
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Delete alias !rules" }));

    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/api/settings/123/aliases/rules",
      { method: "DELETE" },
    ));
  });
});
