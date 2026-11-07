import { ShieldAlert } from "lucide-react";
import { useEffect, useId, useRef } from "react";

export default function PrivilegedConfirmation({
  title,
  description,
  details = [],
  confirmLabel,
  onConfirm,
  onCancel,
  busy = false,
  danger = true,
}) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef(null);
  const cancelRef = useRef(null);
  const confirmRef = useRef(null);
  const triggerRef = useRef(typeof document === "undefined" ? null : document.activeElement);

  useEffect(() => {
    const dialog = dialogRef.current;
    const trigger = triggerRef.current;
    if (!dialog) return undefined;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    confirmRef.current?.focus();

    return () => {
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus();
    };
  }, []);

  const cancel = () => {
    if (!busy) onCancel();
  };

  const containFocus = (event) => {
    if (event.key !== "Tab") return;
    const first = cancelRef.current;
    const last = confirmRef.current;
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    // Native modal semantics provide document inertness; click handling below only detects the backdrop.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={dialogRef}
      className={`citadel-confirmation${danger ? " citadel-confirmation--danger" : ""}`}
      role="alertdialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        event.preventDefault();
        cancel();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) cancel();
      }}
      onKeyDown={containFocus}
    >
      <div className="citadel-confirmation__icon" aria-hidden="true">
        <ShieldAlert size={22} />
      </div>
      <div className="citadel-confirmation__content">
        <p className="citadel-confirmation__eyebrow">Confirmation required</p>
        <h3 id={titleId}>{title}</h3>
        <p id={descriptionId}>{description}</p>
        {details.length > 0 && (
          <dl className="citadel-confirmation__details">
            {details.map(({ label, value }) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        )}
        <div className="citadel-confirmation__actions">
          <button
            ref={cancelRef}
            type="button"
            className="button secondary compact"
            onClick={cancel}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            ref={confirmRef}
            type="button"
            className={`button compact${danger ? " danger" : ""}`}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  );
}
