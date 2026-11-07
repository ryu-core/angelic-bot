import PageHeader from "../components/PageHeader.jsx";
import PublicApiState from "../components/PublicApiState.jsx";
import StatCard from "../components/StatCard.jsx";
import { useStatus } from "../hooks/useStatus.jsx";
import { formatNumber, formatUptime } from "../lib/api.js";

function telemetryTimestamp(value) {
  if (!value) return "No telemetry heartbeat has been recorded.";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Telemetry timestamp unavailable." : `Last telemetry: ${date.toLocaleString()}`;
}

export default function StatusPage() {
  const { status, error, refresh } = useStatus();
  const state = !status ? (error ? "unavailable" : "loading") : (status.online ? (error ? "reconnecting" : "operational") : "offline");
  const stateTitle = state === "operational"
    ? "All systems operational"
    : state === "reconnecting"
      ? "Bot online · telemetry reconnecting"
      : "Bot gateway offline";
  const stateLabel = state === "operational" ? "Operational" : state === "reconnecting" ? "Reconnecting" : "Offline";

  return <div className={`page-shell route-stage route-reveal status-command status-command--${state}`}>
    <PageHeader eyebrow="Live health" title="System status" description="REST establishes the initial state; Socket.IO keeps every signal current." />
    {!status && <PublicApiState loading={!error} error={error} onRetry={refresh} />}
    {status && <>
      <section className="status-hero" aria-labelledby="status-state-title">
        <div className="status-signal" aria-hidden="true"><div className={`status-orb ${status.online ? "online" : ""}`} /></div>
        <div className="status-summary">
          <span className={`status-state status-state--${state}`}>{stateLabel}</span>
          <h2 id="status-state-title">{stateTitle}</h2>
          <p>{telemetryTimestamp(status.updatedAt)}</p>
        </div>
      </section>
      {error && <div className="status-stream-note notice" role="status">{error} The latest confirmed snapshot remains visible.</div>}
      <div className="stats-grid">
        <StatCard label="Latency" value={status.latency != null ? `${status.latency} ms` : "Unavailable"} />
        <StatCard label="Servers" value={formatNumber(status.guilds)} />
        <StatCard label="Users" value={formatNumber(status.users)} />
        <StatCard label="Uptime" value={formatUptime(status.uptime)} />
      </div>
      <div className="two-column">
        <StatCard label="Registered commands" value={formatNumber(status.commandCount)} tone="flare" />
        <StatCard label="Recorded executions" value={formatNumber(status.commandsRun)} tone="flare" />
      </div>
    </>}
  </div>;
}
