import {
  ArrowRight,
  Check,
  Clipboard,
  Search,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import PageHeader from "../components/PageHeader.jsx";
import PublicApiState from "../components/PublicApiState.jsx";
import { useApi } from "../hooks/useApi.js";

const ALL_CATEGORIES = "__all_categories__";
const categoryCollator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

function textValue(value, fallback = "") {
  if (typeof value === "string") return value.trim() || fallback;
  if (typeof value === "number") return String(value);
  return fallback;
}

function commandCategory(command) {
  return textValue(command.category, "Uncategorized");
}

function commandAliases(command) {
  if (!Array.isArray(command.aliases)) return [];
  return command.aliases
    .map((alias) => textValue(alias))
    .filter(Boolean);
}

function commandSearchText(command, category, aliases) {
  return [
    command.id,
    command.name,
    command.description,
    command.syntax,
    category,
    command.kind,
    command.source,
    ...aliases,
  ].filter((value) => value !== null && value !== undefined)
    .join(" ")
    .toLocaleLowerCase();
}

function commandKey(command, index) {
  return textValue(command.id)
    || [command.kind, command.name, command.syntax].filter(Boolean).join(":")
    || `command-${index}`;
}

async function writeClipboard(text) {
  let clipboardError;
  const previousFocus = document.activeElement;

  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (error) {
      clipboardError = error;
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  textarea.style.pointerEvents = "none";
  document.body.append(textarea);

  let copied = false;
  try {
    textarea.focus();
    textarea.select();
    copied = typeof document.execCommand === "function" && document.execCommand("copy");
  } finally {
    textarea.remove();
    if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
      try {
        previousFocus.focus({ preventScroll: true });
      } catch {
        previousFocus.focus();
      }
    }
  }

  if (!copied) throw clipboardError || new Error("Clipboard access is unavailable.");
}

function formatMetric(value) {
  return new Intl.NumberFormat().format(value);
}

export default function CommandsPage() {
  const { data: commands, loading, refreshing, stale, error, reload } = useApi("/api/commands");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(ALL_CATEGORIES);
  const [copiedCommand, setCopiedCommand] = useState("");
  const [copyFeedback, setCopyFeedback] = useState({ id: 0, message: "" });
  const copyResetTimer = useRef();

  useEffect(() => () => window.clearTimeout(copyResetTimer.current), []);

  const commandList = useMemo(
    () => Array.isArray(commands)
      ? commands.filter((command) => command && typeof command === "object")
      : [],
    [commands],
  );

  const atlas = useMemo(() => {
    const categoryCounts = new Map();

    const indexedCommands = commandList.map((command, index) => {
      const commandCategoryName = commandCategory(command);
      const aliases = commandAliases(command);
      categoryCounts.set(commandCategoryName, (categoryCounts.get(commandCategoryName) || 0) + 1);

      return {
        command,
        aliases,
        category: commandCategoryName,
        key: commandKey(command, index),
        searchText: commandSearchText(command, commandCategoryName, aliases),
      };
    });
    const aliasCount = indexedCommands.reduce((total, item) => total + item.aliases.length, 0);

    const categories = [...categoryCounts.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => categoryCollator.compare(a.name, b.name));

    return { aliasCount, categories, indexedCommands };
  }, [commandList]);

  const effectiveCategory = category === ALL_CATEGORIES
    || atlas.categories.some((item) => item.name === category)
    ? category
    : ALL_CATEGORIES;
  const normalizedQuery = query.trim().toLocaleLowerCase();

  const filtered = useMemo(
    () => atlas.indexedCommands.filter((item) => (
      (effectiveCategory === ALL_CATEGORIES || item.category === effectiveCategory)
      && (!normalizedQuery || item.searchText.includes(normalizedQuery))
    )),
    [atlas.indexedCommands, effectiveCategory, normalizedQuery],
  );

  const hasActiveFilters = Boolean(normalizedQuery) || effectiveCategory !== ALL_CATEGORIES;

  function clearFilters() {
    setQuery("");
    setCategory(ALL_CATEGORIES);
  }

  async function copySyntax(item) {
    const syntax = textValue(item.command.syntax);
    const name = textValue(item.command.name, "command");
    if (!syntax) return;

    window.clearTimeout(copyResetTimer.current);
    try {
      await writeClipboard(syntax);
      setCopiedCommand(item.key);
      setCopyFeedback((current) => ({
        id: current.id + 1,
        message: `${name} syntax copied to the clipboard.`,
      }));
      copyResetTimer.current = window.setTimeout(() => setCopiedCommand(""), 2000);
    } catch {
      setCopiedCommand("");
      setCopyFeedback((current) => ({
        id: current.id + 1,
        message: `Could not copy ${name} syntax. Select the syntax and copy it manually.`,
      }));
    }
  }

  return <div className="page-shell route-stage route-reveal atlas-shell commands-page">
    <PageHeader
      eyebrow="Command atlas"
      title="Every command. Searchable."
      description="A live index generated from xiel's command registry—organized by category, access level, and invocation type."
    />

    <section className="atlas-overview" aria-label="Command summary">
      <dl className="atlas-metrics">
        <div className="atlas-metric">
          <dt>Total commands</dt>
          <dd>{formatMetric(commandList.length)}</dd>
        </div>
        <div className="atlas-metric">
          <dt>Categories</dt>
          <dd>{formatMetric(atlas.categories.length)}</dd>
        </div>
        <div className="atlas-metric">
          <dt>Aliases</dt>
          <dd>{formatMetric(atlas.aliasCount)}</dd>
        </div>
        <div className="atlas-metric atlas-metric--visible">
          <dt>Visible now</dt>
          <dd>{formatMetric(filtered.length)}</dd>
        </div>
      </dl>
    </section>

    <section className="atlas-categories" aria-labelledby="command-category-title">
      <div className="atlas-section-heading">
        <div>
          <span className="atlas-kicker">Explore the registry</span>
          <h2 id="command-category-title">Command categories</h2>
        </div>
        <p>Choose a category slide to narrow the live command index.</p>
      </div>
      <div
        className="atlas-category-rail"
        role="group"
        aria-label="Filter commands by category"
      >
        <button
          type="button"
          className={`atlas-category-slide${effectiveCategory === ALL_CATEGORIES ? " is-active" : ""}`}
          aria-pressed={effectiveCategory === ALL_CATEGORIES}
          aria-controls="command-results"
          onClick={() => setCategory(ALL_CATEGORIES)}
        >
          <span className="atlas-category-slide__index" aria-hidden="true">00</span>
          <span className="atlas-category-slide__name">All commands</span>
          <span className="atlas-category-slide__footer">
            <span>{formatMetric(commandList.length)} entries</span>
            <ArrowRight size={16} aria-hidden="true" />
          </span>
        </button>
        {atlas.categories.map((item, index) => (
          <button
            type="button"
            className={`atlas-category-slide${effectiveCategory === item.name ? " is-active" : ""}`}
            aria-pressed={effectiveCategory === item.name}
            aria-controls="command-results"
            onClick={() => setCategory(item.name)}
            key={item.name}
          >
            <span className="atlas-category-slide__index" aria-hidden="true">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="atlas-category-slide__name">{item.name}</span>
            <span className="atlas-category-slide__footer">
              <span>{formatMetric(item.count)} {item.count === 1 ? "entry" : "entries"}</span>
              <ArrowRight size={16} aria-hidden="true" />
            </span>
          </button>
        ))}
      </div>
    </section>

    <div className="toolbar atlas-toolbar" role="search" aria-label="Search the command atlas">
      <div className="field atlas-search">
        <label htmlFor="command-search" className="sr-only">Search commands</label>
        <div className="atlas-search__control">
          <Search size={17} aria-hidden="true" />
          <input
            id="command-search"
            className="input"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search name, alias, syntax, or capability…"
            autoComplete="off"
            spellCheck="false"
          />
          {query && <button
            type="button"
            className="atlas-search__clear"
            aria-label="Clear command search"
            onClick={() => setQuery("")}
          >
            <X size={15} aria-hidden="true" />
          </button>}
        </div>
      </div>
      <span className="result-count" aria-live="polite" aria-atomic="true">
        {formatMetric(filtered.length)} of {formatMetric(commandList.length)} commands
      </span>
      {hasActiveFilters && <button type="button" className="text-button atlas-reset" onClick={clearFilters}>
        Reset filters
      </button>}
    </div>

    <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
      <span key={copyFeedback.id}>{copyFeedback.message}</span>
    </div>

    <PublicApiState
      loading={loading}
      refreshing={refreshing}
      stale={stale}
      error={error}
      onRetry={reload}
      empty={!commandList.length && !stale}
    >
      <section id="command-results" className="atlas-results" aria-labelledby="command-results-title">
        <div className="atlas-section-heading atlas-results__heading">
          <div>
            <span className="atlas-kicker">Live command index</span>
            <h2 id="command-results-title">
              {effectiveCategory === ALL_CATEGORIES ? "All commands" : effectiveCategory}
            </h2>
          </div>
          <p>{filtered.length === 1 ? "1 command matches" : `${formatMetric(filtered.length)} commands match`} the current view.</p>
        </div>

        {filtered.length
          ? <div className="command-grid">{filtered.map((item, index) => {
            const { command, aliases } = item;
            const name = textValue(command.name, "Unnamed command");
            const syntax = textValue(command.syntax);
            const description = textValue(command.description, "No description is available for this command.");
            const kind = textValue(command.kind);
            const source = textValue(command.source);
            const registryId = textValue(command.id);
            const isCopied = copiedCommand === item.key;

            return <article
              className={`command-card atlas-command-card${command.restricted ? " restricted" : ""}`}
              key={item.key}
            >
              <header className="atlas-command-card__header">
                <span className="atlas-command-card__index" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className={`badge command-category${command.premium ? " premium" : ""}`}>
                  {item.category}
                </span>
              </header>

              <h3>{name}</h3>
              <p>{description}</p>

              <div className="atlas-command-card__syntax">
                <code className="syntax">{syntax || "Syntax unavailable"}</code>
                <button
                  type="button"
                  className={`copy-syntax-button${isCopied ? " is-copied" : ""}`}
                  onClick={() => copySyntax(item)}
                  disabled={!syntax}
                  aria-label={isCopied ? `Copied syntax for ${name}` : `Copy syntax for ${name}`}
                >
                  {isCopied ? <Check size={15} aria-hidden="true" /> : <Clipboard size={15} aria-hidden="true" />}
                  <span>{isCopied ? "Copied" : "Copy"}</span>
                </button>
              </div>

              <div className="command-meta" aria-label={`Access and invocation details for ${name}`}>
                {kind && <span className={`badge command-kind ${kind}`}>{kind}</span>}
                {command.premium && <span className="badge premium">Premium</span>}
                {command.restricted && <span className="badge restricted">Restricted</span>}
                {!command.restricted && <span className="badge command-access">Public</span>}
              </div>

              {!!aliases.length && <div className="aliases">
                <span>Aliases</span>
                <div className="alias-list">
                  {aliases.map((alias, aliasIndex) => <code key={`${alias}-${aliasIndex}`}>{alias}</code>)}
                </div>
              </div>}

              {(source || registryId) && <footer className="atlas-command-card__registry">
                {source && <span>
                  <span>Source</span>
                  <code className="command-source" title={source}>{source}</code>
                </span>}
                {registryId && <span>
                  <span>Registry ID</span>
                  <code className="command-id" title={registryId}>{registryId}</code>
                </span>}
              </footer>}
            </article>;
          })}</div>
          : <div className="atlas-no-results" role="status">
            <span className="atlas-kicker">No match found</span>
            <h3>No commands fit those filters.</h3>
            <p>Try a shorter search or return to the complete registry.</p>
            <button type="button" className="button secondary" onClick={clearFilters}>Show all commands</button>
          </div>}
      </section>
    </PublicApiState>
  </div>;
}
