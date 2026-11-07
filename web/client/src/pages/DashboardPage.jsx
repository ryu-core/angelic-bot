import { Command, RefreshCw, Search, Settings2, ShieldCheck, WalletCards } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import ApiState from "../components/ApiState.jsx";
import PageHeader from "../components/PageHeader.jsx";
import { useApi } from "../hooks/useApi.js";

function normalizeServer(server) {
  if (!server || typeof server !== "object") return null;
  const id = String(server.id ?? "").trim();
  if (!id) return null;

  const rawName = typeof server.name === "string" ? server.name.trim() : "";
  const parsedMemberCount = Number(server.memberCount);

  return {
    id,
    name: rawName || "Unnamed server",
    icon: typeof server.icon === "string" && server.icon.trim() ? server.icon.trim() : null,
    owner: Boolean(server.owner),
    memberCount: Number.isFinite(parsedMemberCount) && parsedMemberCount >= 0
      ? Math.floor(parsedMemberCount)
      : null,
  };
}

function GuildIcon({ server }) {
  const [failedUrl, setFailedUrl] = useState(null);

  if (!server.icon || failedUrl === server.icon) {
    return <div className="guild-fallback" aria-hidden="true">{server.name.charAt(0).toUpperCase() || "?"}</div>;
  }

  return <img
    className="guild-icon"
    src={server.icon}
    alt=""
    loading="lazy"
    onError={() => setFailedUrl(server.icon)}
  />;
}

function DashboardEmptyState({ onRefresh }) {
  return <section className="api-state dashboard-empty-state" aria-labelledby="managed-servers-empty-title">
    <div className="empty-state-content">
      <ShieldCheck className="empty-state-icon" aria-hidden="true" />
      <div>
        <h2 id="managed-servers-empty-title">No manageable servers found</h2>
        <p>xiel only lists servers where the bot is installed and your Discord account has Manage Server permission.</p>
      </div>
      <div className="empty-state-actions">
        <a href="/api/invite" className="button">Invite xiel to a server</a>
        <button type="button" className="button secondary" onClick={onRefresh}>
          <RefreshCw size={16} />Refresh access
        </button>
      </div>
      <details className="permission-help">
        <summary>Why is a server missing?</summary>
        <p>Ask a server owner to grant you Manage Server, confirm xiel is still a member, then refresh this page.</p>
      </details>
    </div>
  </section>;
}

export default function DashboardPage() {
  const { data: servers, loading, refreshing, stale, error, reload } = useApi("/api/servers");
  const [query, setQuery] = useState("");
  const normalizedServers = useMemo(
    () => (Array.isArray(servers) ? servers : []).map(normalizeServer).filter(Boolean),
    [servers],
  );
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredServers = useMemo(() => {
    if (!normalizedQuery) return normalizedServers;
    return normalizedServers.filter((server) =>
      `${server.name} ${server.id}`.toLocaleLowerCase().includes(normalizedQuery));
  }, [normalizedQuery, normalizedServers]);

  return <div className="page-shell dashboard-page">
    <PageHeader
      eyebrow="Your control plane"
      title="Managed servers"
      description="Choose a server to configure xiel. Only servers where xiel is present and you hold Manage Server permission appear here."
      actions={<a href="/api/invite" className="button">Add xiel</a>}
    />
    <ApiState loading={loading} refreshing={refreshing} stale={stale} error={error} onRetry={reload}>
      {normalizedServers.length ? <>
        <div className="toolbar server-toolbar" role="search">
          <label className="server-search">
            <span>Search managed servers</span>
            <span className="input-with-icon">
              <Search size={17} aria-hidden="true" />
              <input
                className="input"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search by server name or ID"
              />
            </span>
          </label>
          <p className="result-count" aria-live="polite">
            Showing {filteredServers.length} of {normalizedServers.length} {normalizedServers.length === 1 ? "server" : "servers"}
          </p>
          <button type="button" className="button secondary compact" onClick={reload}>
            <RefreshCw size={15} />Refresh
          </button>
        </div>
        {filteredServers.length
          ? <div className="guild-grid">{filteredServers.map((server) => <article className="guild-card" key={server.id}>
            <header>
              <GuildIcon server={server} />
              <div className="guild-card-identity">
                <div className="guild-name-row">
                  <h2>{server.name}</h2>
                  {server.owner && <span className="badge">Owner</span>}
                </div>
                <p>{server.memberCount == null
                  ? "Member count unavailable"
                  : `${server.memberCount.toLocaleString()} ${server.memberCount === 1 ? "member" : "members"}`}</p>
                <span className="guild-id">ID {server.id}</span>
              </div>
            </header>
            <div className="guild-actions">
              <Link
                className="button"
                to={`/settings/${encodeURIComponent(server.id)}`}
                aria-label={`Open settings for ${server.name}`}
              >
                <Settings2 size={15} />Settings
              </Link>
              <Link
                className="button secondary"
                to={`/economy/${encodeURIComponent(server.id)}`}
                aria-label={`Open economy for ${server.name}`}
              >
                <WalletCards size={15} />Economy
              </Link>
            </div>
          </article>)}</div>
          : <section className="api-state dashboard-search-empty" aria-live="polite">
            <div className="empty-state-content">
              <h2>No servers match “{query.trim()}”</h2>
              <p>Try a different server name or paste its Discord ID.</p>
              <button type="button" className="text-button" onClick={() => setQuery("")}>Clear search</button>
            </div>
          </section>}
      </> : <DashboardEmptyState onRefresh={reload} />}
    </ApiState>
    <nav className="dashboard-secondary-nav" aria-label="Command reference">
      <Link to="/commands" className="button secondary"><Command size={16} />Open command atlas</Link>
    </nav>
  </div>;
}
