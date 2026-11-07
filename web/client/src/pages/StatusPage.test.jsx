import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { useStatus } from "../hooks/useStatus.jsx";
import StatusPage from "./StatusPage.jsx";

vi.mock("../hooks/useStatus.jsx", () => ({ useStatus: vi.fn() }));

describe("StatusPage resilience", () => {
  it("offers an actionable retry when initial telemetry fails", async () => {
    const user = userEvent.setup();
    const refresh = vi.fn();
    useStatus.mockReturnValue({
      status: null,
      error: "Telemetry unavailable",
      refresh,
    });

    render(<StatusPage />);
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(refresh).toHaveBeenCalledOnce();
  });
});
