import { AlertTriangle, LoaderCircle } from "lucide-react";

export default function PublicApiState({
  loading,
  refreshing = false,
  stale = false,
  error,
  empty,
  onRetry,
  children,
}) {
  const message = typeof error === "string" ? error : error?.message;

  if (loading) return <div className="api-state" role="status"><LoaderCircle className="animate-spin" aria-hidden="true" /> Loading live data…</div>;
  if (error && !stale) return <div className="api-state error" role="alert"><AlertTriangle aria-hidden="true" /> <span>{message || "The request could not be completed."}</span>{onRetry && <button type="button" className="text-button" onClick={onRetry}>Try again</button>}</div>;
  if (empty) return <div className="api-state">Nothing has been recorded here yet.</div>;
  if (stale || refreshing) return <div aria-busy={refreshing ? "true" : undefined}>
    <div className={`api-state api-state--inline${error ? " error" : ""}`} role={error ? "alert" : "status"}>
      {error
        ? <><AlertTriangle aria-hidden="true" /><span>{message || "Refresh failed. The last confirmed data remains visible."}</span></>
        : <><LoaderCircle className="animate-spin" aria-hidden="true" /><span>Refreshing live data…</span></>}
      {error && onRetry && <button type="button" className="text-button" onClick={onRetry}>Try again</button>}
    </div>
    {children}
  </div>;
  return children;
}
