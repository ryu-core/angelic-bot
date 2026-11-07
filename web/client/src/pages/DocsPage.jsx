import { useEffect, useMemo, useState } from "react";
import PageHeader from "../components/PageHeader.jsx";
import PublicApiState from "../components/PublicApiState.jsx";
import DocsContent from "../content/DocsContent.mdx";
import { useApi } from "../hooks/useApi.js";

const sections = [
  ["start", "Getting started"],
  ["antinuke", "AntiNuke"],
  ["join", "Join flow"],
  ["access", "Access & whitelist"],
  ["family", "Marriage & family"],
  ["economy", "Economy"],
  ["consoles", "Owner consoles"],
  ["registry", "Command registry"],
  ["troubleshooting", "Troubleshooting"],
];

export default function DocsPage() {
  const [active, setActive] = useState("start");
  const { data: commands, loading, refreshing, error, reload } = useApi("/api/commands");
  const hasRegistry = Array.isArray(commands);
  const commandList = useMemo(() => Array.isArray(commands) ? commands : [], [commands]);
  const counts = useMemo(
    () => hasRegistry
      ? Object.fromEntries([...new Set(commandList.map((command) => command.category))].map((category) => [category, commandList.filter((command) => command.category === category).length]))
      : null,
    [commandList, hasRegistry],
  );
  const categoryTotal = counts ? Object.keys(counts).length : null;

  useEffect(() => {
    const targets = sections.map(([id]) => document.getElementById(id)).filter(Boolean);
    const hash = window.location.hash.slice(1);
    if (targets.some((target) => target.id === hash)) setActive(hash);
    if (typeof IntersectionObserver === "undefined") return undefined;

    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible[0]) setActive(visible[0].target.id);
    }, { rootMargin: "-18% 0px -68% 0px", threshold: 0 });
    targets.forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, []);

  return <div className="page-shell route-stage route-reveal docs-shell">
    <PageHeader
      eyebrow="Operator manual"
      title="Documentation"
      description="Configure xiel with confidence, understand each control surface, and verify the commands currently available from the live bot."
    />
    <div className="docs-layout">
      <aside className="doc-nav docs-rail" aria-label="Documentation sections">
        <div className="docs-rail-heading"><span>Field manual</span><strong>{sections.length} sections</strong></div>
        <nav>{sections.map(([id, label], index) => <a key={id} href={`#${id}`} className={active === id ? "active" : ""} aria-current={active === id ? "location" : undefined} onClick={() => setActive(id)}><span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>{label}</a>)}</nav>
      </aside>
      <article className="prose-panel docs-content" aria-busy={loading || refreshing ? "true" : undefined}>
        {loading && <div className="api-state api-state--inline" role="status">Loading live command totals…</div>}
        {error && <PublicApiState error={error} onRetry={reload} />}
        {refreshing && <div className="api-state api-state--inline" role="status">Refreshing command totals…</div>}
        <DocsContent total={hasRegistry ? commandList.length : null} counts={counts} />
        <section id="registry">
          <h2>Live command registry</h2>
          <p>
            The <a href="/commands">command atlas</a> is generated from the commands currently loaded by xiel.
            Use it to search names, descriptions, aliases, syntax, categories, source types, and access markers
            without relying on a manually maintained list.
          </p>
          <p>
            Current public snapshot: <code>{hasRegistry
              ? `${commandList.length} commands across ${categoryTotal} categories`
              : "unavailable"}</code>. Restricted owner commands are not exposed to normal viewers.
          </p>
        </section>
        <section id="troubleshooting">
          <h2>Troubleshooting access</h2>
          <p>
            A server appears in the dashboard only when xiel is already present and the signed-in Discord account
            has Manage Server permission. Reload the dashboard after changing either condition so the server list
            can be requested again from Discord.
          </p>
          <p>
            If live command totals are unavailable, the rest of this manual remains usable. Retry the registry
            request from the notice above, then check System status if the error continues.
          </p>
        </section>
      </article>
    </div>
  </div>;
}
