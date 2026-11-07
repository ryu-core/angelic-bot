import { AlertTriangle, LoaderCircle } from "lucide-react";

export default function ApiState({
  loading,
  refreshing = false,
  stale = false,
  error,
  empty,
  onRetry,
  loadingLabel = "Loading live data…",
  emptyLabel = "Nothing has been recorded here yet.",
  children,
}) {
  const message = typeof error === "string" ? error : error?.message;
  const forbidden = error?.status === 403;

  if (loading) {
    return <div className="api-state" role="status" aria-live="polite" aria-busy="true">
      <LoaderCircle className="animate-spin" aria-hidden="true" /> {loadingLabel}
    </div>;
  }
  if (error && !stale) {
    return <div className="api-state error" role="alert">
      <AlertTriangle aria-hidden="true" />
      <span>{forbidden ? <><strong>Access denied.</strong> {message}</> : message || "The request could not be completed."}</span>
      {forbidden && <a className="text-button" href="/dashboard">Return to Dashboard</a>}
      {onRetry && !forbidden && <button type="button" className="text-button" onClick={onRetry}>Try again</button>}
    </div>;
  }
  if (empty) return <div className="api-state" role="status">{emptyLabel}</div>;
  if (stale || refreshing) {
    return <div aria-busy={refreshing ? "true" : undefined}>
      <div className={`api-state api-state--inline${error ? " error" : ""}`} role={error ? "alert" : "status"}>
        {error
          ? <><AlertTriangle aria-hidden="true" /><span>{message || "Refresh failed. The last confirmed data remains visible."}</span></>
          : <><LoaderCircle className="animate-spin" aria-hidden="true" /><span>Refreshing live data…</span></>}
        {error && onRetry && <button type="button" className="text-button" onClick={onRetry}>Try again</button>}
      </div>
      {children}
    </div>;
  }
  return children;
}
