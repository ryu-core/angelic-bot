import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import PrivilegedConfirmation from "./PrivilegedConfirmation.jsx";

function ConfirmationHarness({ onConfirm = vi.fn() }) {
  const [open, setOpen] = useState(false);
  return <>
    <button type="button" onClick={() => setOpen(true)}>Open confirmation</button>
    {open && <PrivilegedConfirmation
      title="Delete record?"
      description="This cannot be undone."
      confirmLabel="Delete record"
      onConfirm={onConfirm}
      onCancel={() => setOpen(false)}
    />}
  </>;
}

describe("PrivilegedConfirmation", () => {
  it("is modal, contains keyboard focus, closes with Escape, and restores trigger focus", async () => {
    const user = userEvent.setup();
    render(<ConfirmationHarness />);

    const trigger = screen.getByRole("button", { name: "Open confirmation" });
    await user.click(trigger);
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveAttribute("open");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Delete record" }));

    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel" }));
    fireEvent(dialog, new Event("cancel", { cancelable: true }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(trigger);
  });

  it("treats a click on the native dialog backdrop as cancellation", async () => {
    const user = userEvent.setup();
    render(<ConfirmationHarness />);
    await user.click(screen.getByRole("button", { name: "Open confirmation" }));

    fireEvent.click(screen.getByRole("alertdialog"));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
});
