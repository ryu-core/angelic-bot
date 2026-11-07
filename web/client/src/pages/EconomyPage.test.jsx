import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useApi } from "../hooks/useApi.js";
import { api } from "../lib/api.js";
import EconomyPage from "./EconomyPage.jsx";

vi.mock("../hooks/useApi.js", () => ({ useApi: vi.fn() }));
vi.mock("../lib/api.js", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, api: vi.fn() };
});

const reload = vi.fn();
const overview = {
  stats: { wallets: 1, circulating: 30, averageStreak: 2 },
  leaderboard: [],
  shop: [{
    _id: "item-1",
    sku: "vip-pass",
    name: "VIP Pass",
    description: "Premium access",
    price: 500,
    enabled: true,
  }],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/economy/123"]}>
      <Routes>
        <Route path="/economy/:guildId" element={<EconomyPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("EconomyPage write contracts", () => {
  beforeEach(() => {
    reload.mockReset();
    api.mockReset();
    useApi.mockReturnValue({
      data: overview,
      loading: false,
      error: null,
      reload,
    });
  });

  it("omits blank wallet values from the PATCH payload", async () => {
    const user = userEvent.setup();
    api.mockResolvedValue({});
    renderPage();

    await user.type(screen.getByLabelText("Discord user ID"), "123456789012345678");
    await user.type(screen.getByLabelText("Wallet balance"), "25");
    await user.click(screen.getByRole("button", { name: "Apply correction" }));

    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/api/economy/123/wallets/123456789012345678",
      { method: "PATCH", body: JSON.stringify({ balance: 25 }) },
    ));
  });

  it("POSTs the exact normalized shop item payload", async () => {
    const user = userEvent.setup();
    api.mockResolvedValue({});
    renderPage();

    await user.type(screen.getByLabelText("SKU"), "VIP-Pass");
    await user.type(screen.getByLabelText("Name"), "VIP Pass");
    await user.type(screen.getByLabelText("Description"), "Premium access");
    await user.type(screen.getByLabelText("Price"), "500");
    await user.click(screen.getByLabelText("Available for purchase"));
    await user.click(screen.getByRole("button", { name: "Create item" }));

    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/api/economy/123/shop",
      {
        method: "POST",
        body: JSON.stringify({
          sku: "vip-pass",
          name: "VIP Pass",
          description: "Premium access",
          price: 500,
          enabled: false,
        }),
      },
    ));
  });

  it("requires explicit confirmation before the destructive DELETE", async () => {
    const user = userEvent.setup();
    api.mockResolvedValue({});
    renderPage();

    await user.click(screen.getByRole("button", { name: "Permanently delete VIP Pass from the shop" }));
    expect(api).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog")).toHaveTextContent("Delete VIP Pass?");

    await user.click(screen.getByRole("button", { name: "Delete item" }));
    await waitFor(() => expect(api).toHaveBeenCalledWith(
      "/api/economy/123/shop/item-1",
      { method: "DELETE" },
    ));
  });
});
