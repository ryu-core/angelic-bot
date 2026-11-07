import { Search } from "lucide-react";
import { useId, useMemo, useState } from "react";

const PAGE_SIZE = 30;

export default function PrivilegedRegistry({
  items = [],
  label,
  noun = "records",
  searchPlaceholder,
  getSearchText,
  renderItem,
  emptyMessage,
  className = "",
}) {
  const searchId = useId();
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredItems = useMemo(() => {
    if (!normalizedQuery) return items;
    return items.filter((item) =>
      getSearchText(item).toLocaleLowerCase().includes(normalizedQuery),
    );
  }, [getSearchText, items, normalizedQuery]);
  const visibleItems = filteredItems.slice(0, visibleCount);
  const remaining = filteredItems.length - visibleItems.length;

  const updateQuery = (event) => {
    setQuery(event.target.value);
    setVisibleCount(PAGE_SIZE);
  };

  return (
    <div className={`citadel-registry ${className}`.trim()}>
      <div className="citadel-registry__toolbar">
        <div className="field citadel-registry__search">
          <label htmlFor={searchId}>{label}</label>
          <div className="citadel-registry__search-control">
            <Search size={16} aria-hidden="true" />
            <input
              id={searchId}
              className="input"
              type="search"
              value={query}
              onChange={updateQuery}
              placeholder={searchPlaceholder}
              autoComplete="off"
            />
          </div>
        </div>
        <p className="citadel-registry__count" aria-live="polite">
          {normalizedQuery
            ? `${filteredItems.length} of ${items.length} ${noun}`
            : `${items.length} ${noun}`}
        </p>
      </div>

      {visibleItems.length > 0 ? (
        <div className="data-list citadel-registry__list">
          {visibleItems.map(renderItem)}
        </div>
      ) : (
        <div className="citadel-registry__empty" role="status">
          {normalizedQuery ? `No ${noun} match “${query.trim()}”.` : emptyMessage}
        </div>
      )}

      {remaining > 0 && (
        <div className="citadel-registry__more">
          <button
            type="button"
            className="button secondary compact"
            onClick={() => setVisibleCount((current) => current + PAGE_SIZE)}
          >
            Show {Math.min(PAGE_SIZE, remaining)} more
          </button>
          <span>{remaining} still hidden</span>
        </div>
      )}
    </div>
  );
}
