import { Plus, Trash2, WalletCards } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router";
import ApiState from "../components/ApiState.jsx";
import PageHeader from "../components/PageHeader.jsx";
import PrivilegedConfirmation from "../components/PrivilegedConfirmation.jsx";
import StatCard from "../components/StatCard.jsx";
import { useApi } from "../hooks/useApi.js";
import { api, formatNumber, json } from "../lib/api.js";

const WALLET_FIELDS = [
  { key: "balance", label: "Wallet balance", max: 1_000_000_000 },
  { key: "bank", label: "Bank balance", max: 1_000_000_000 },
  { key: "streak", label: "Daily streak", max: 100_000 },
];

function EconomySectionHeading({ id, title, description }) {
  return <div className="economy-section-heading">
    <h2 id={id}>{title}</h2>
    <p>{description}</p>
  </div>;
}

function EconomyPageContent({ guildId }) {
  const guildPath = encodeURIComponent(guildId);
  const state = useApi(`/api/economy/${guildPath}/overview`);
  const [wallet, setWallet] = useState({ userId: "", balance: "", bank: "", streak: "" });
  const [item, setItem] = useState({
    sku: "",
    name: "",
    description: "",
    price: "",
    enabled: true,
  });
  const [notice, setNotice] = useState(null);
  const [walletPending, setWalletPending] = useState(false);
  const [itemPending, setItemPending] = useState(false);
  const [deletingItem, setDeletingItem] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);

  const saveWallet = async (event) => {
    event.preventDefault();
    if (walletPending) return;

    const body = Object.fromEntries(
      ["balance", "bank", "streak"]
        .filter((key) => wallet[key] !== "")
        .map((key) => [key, Number(wallet[key])]),
    );
    if (!Object.keys(body).length) {
      setNotice({ ok: false, text: "Enter at least one wallet value to change." });
      return;
    }

    setWalletPending(true);
    setNotice(null);
    try {
      await api(
        `/api/economy/${guildPath}/wallets/${encodeURIComponent(wallet.userId)}`,
        json("PATCH", body),
      );
      setNotice({ ok: true, text: "Wallet updated. Blank values were left unchanged." });
      state.reload();
    } catch (error) {
      setNotice({ ok: false, text: error.message });
    } finally {
      setWalletPending(false);
    }
  };

  const addItem = async (event) => {
    event.preventDefault();
    if (itemPending) return;

    setItemPending(true);
    setNotice(null);
    try {
      await api(
        `/api/economy/${guildPath}/shop`,
        json("POST", { ...item, price: Number(item.price) }),
      );
      setItem({ sku: "", name: "", description: "", price: "", enabled: true });
      setNotice({ ok: true, text: "Shop item created and added to the inventory." });
      state.reload();
    } catch (error) {
      setNotice({ ok: false, text: error.message });
    } finally {
      setItemPending(false);
    }
  };

  const deleteItem = async (id, name) => {
    if (deletingItem) return;

    setDeletingItem(id);
    setNotice(null);
    try {
      await api(`/api/economy/${guildPath}/shop/${encodeURIComponent(id)}`, { method: "DELETE" });
      setNotice({ ok: true, text: `${name} deleted from the shop.` });
      setPendingDelete(null);
      state.reload();
    } catch (error) {
      setNotice({ ok: false, text: error.message });
    } finally {
      setDeletingItem(null);
    }
  };

  const data = state.data;
  const stats = data?.stats ?? {};
  const leaderboard = Array.isArray(data?.leaderboard) ? data.leaderboard : [];
  const shop = Array.isArray(data?.shop) ? data.shop : [];

  return <div className="page-shell economy-page">
    <PageHeader
      eyebrow={`Economy · ${guildId}`}
      title="Economy operations"
      description="Review circulation, correct server-scoped wallets, and manage the purchasable shop inventory."
    />
    <ApiState
      loading={state.loading}
      refreshing={state.refreshing}
      stale={state.stale}
      error={state.error}
      onRetry={state.reload}
    >
      {data && <div className="economy-workspace">
        {notice && <div
          className={`notice economy-notice ${notice.ok ? "" : "error"}`}
          role={notice.ok ? "status" : "alert"}
        >
          {notice.text}
        </div>}

        <section className="economy-section economy-overview" aria-labelledby="economy-overview-title">
          <EconomySectionHeading
            id="economy-overview-title"
            title="Economy at a glance"
            description="Live totals from this server’s wallet and shop records."
          />
          <div className="stats-grid">
            <StatCard label="Wallets" value={formatNumber(stats.wallets)} />
            <StatCard label="Circulating" value={formatNumber(stats.circulating)} />
            <StatCard
              label="Average streak"
              value={Number(stats.averageStreak || 0).toFixed(1)}
            />
            <StatCard label="Shop items" value={formatNumber(shop.length)} tone="flare" />
          </div>
        </section>

        <section className="economy-section" aria-labelledby="economy-actions-title">
          <EconomySectionHeading
            id="economy-actions-title"
            title="Operations"
            description="Apply a targeted wallet correction or publish a new shop item."
          />
          <div className="two-column economy-operations">
            <section className="panel operation-panel">
              <div className="panel-title">
                <div>
                  <h3>Wallet correction</h3>
                  <p>Only entered values are changed. Every blank wallet field remains untouched.</p>
                </div>
                <WalletCards aria-hidden="true" />
              </div>
              <form className="stack" onSubmit={saveWallet}>
                <div className="field">
                  <label htmlFor="wallet-user-id">Discord user ID</label>
                  <input
                    id="wallet-user-id"
                    className="input"
                    required
                    pattern="[0-9]{16,22}"
                    inputMode="numeric"
                    value={wallet.userId}
                    onChange={(event) => setWallet({ ...wallet, userId: event.target.value })}
                    placeholder="123456789012345678"
                  />
                </div>
                <div className="form-grid wallet-fields">
                  {WALLET_FIELDS.map(({ key, label, max }) => <div className="field" key={key}>
                    <label htmlFor={`wallet-${key}`}>{label}</label>
                    <input
                      id={`wallet-${key}`}
                      className="input"
                      type="number"
                      min="0"
                      max={max}
                      step="1"
                      value={wallet[key]}
                      onChange={(event) => setWallet({ ...wallet, [key]: event.target.value })}
                      placeholder="No change"
                    />
                  </div>)}
                </div>
                <div className="operation-submit-row">
                  <span className="field-hint">Blank fields are omitted from the update.</span>
                  <button className="button" disabled={walletPending}>
                    {walletPending ? "Applying…" : "Apply correction"}
                  </button>
                </div>
              </form>
            </section>

            <section className="panel operation-panel">
              <div className="panel-title">
                <div>
                  <h3>Create shop item</h3>
                  <p>Adds a real purchasable record to this server’s inventory.</p>
                </div>
              </div>
              <form className="stack" onSubmit={addItem}>
                <div className="form-grid">
                  <div className="field">
                    <label htmlFor="shop-sku">SKU</label>
                    <input
                      id="shop-sku"
                      className="input"
                      required
                      pattern="[a-z0-9_-]+"
                      minLength={1}
                      maxLength={40}
                      value={item.sku}
                      onChange={(event) => setItem({ ...item, sku: event.target.value.toLowerCase() })}
                      placeholder="vip-pass"
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="shop-name">Name</label>
                    <input
                      id="shop-name"
                      className="input"
                      required
                      minLength={1}
                      maxLength={80}
                      value={item.name}
                      onChange={(event) => setItem({ ...item, name: event.target.value })}
                      placeholder="VIP Pass"
                    />
                  </div>
                </div>
                <div className="field">
                  <label htmlFor="shop-description">Description</label>
                  <input
                    id="shop-description"
                    className="input"
                    maxLength={240}
                    value={item.description}
                    onChange={(event) => setItem({ ...item, description: event.target.value })}
                    placeholder="What buyers receive"
                  />
                </div>
                <div className="form-grid shop-item-options">
                  <div className="field">
                    <label htmlFor="shop-price">Price</label>
                    <input
                      id="shop-price"
                      className="input"
                      required
                      type="number"
                      min="0"
                      max="1000000000"
                      step="1"
                      value={item.price}
                      onChange={(event) => setItem({ ...item, price: event.target.value })}
                    />
                  </div>
                  <div className="checkbox-field">
                    <input
                      id="shop-enabled"
                      type="checkbox"
                      aria-labelledby="shop-enabled-label"
                      checked={item.enabled}
                      onChange={(event) => setItem({ ...item, enabled: event.target.checked })}
                    />
                    <span>
                      <strong id="shop-enabled-label">Available for purchase</strong>
                      <small>Uncheck to create it disabled.</small>
                    </span>
                  </div>
                </div>
                <div className="operation-submit-row">
                  <span className="field-hint">{item.description.length} / 240 description characters</span>
                  <button className="button" disabled={itemPending}>
                    <Plus size={16} />{itemPending ? "Creating…" : "Create item"}
                  </button>
                </div>
              </form>
            </section>
          </div>
        </section>

        <section className="economy-section" aria-labelledby="economy-records-title">
          <EconomySectionHeading
            id="economy-records-title"
            title="Records"
            description="Inspect the highest-value wallets and every shop item in this server."
          />
          <div className="two-column economy-records">
            <section className="panel">
              <div className="panel-title">
                <div>
                  <h3>Wealth leaderboard</h3>
                  <p>Ranked by the stored wallet and bank balances.</p>
                </div>
                <span className="badge">{leaderboard.length} shown</span>
              </div>
              {leaderboard.length
                ? <ol className="data-list leaderboard-list">
                  {leaderboard.map((row, index) => <li className="data-row leaderboard-row" key={row._id}>
                    <span className="leaderboard-rank" aria-label={`Rank ${index + 1}`}>#{index + 1}</span>
                    <div className="data-row-copy">
                      <strong>{row.userId}</strong>
                      <span>{formatNumber(Number(row.balance || 0) + Number(row.bank || 0))} total</span>
                    </div>
                    <span className="streak-value">{formatNumber(row.streak)} streak</span>
                  </li>)}
                </ol>
                : <div className="api-state economy-list-empty">
                  No wallets have been created in this server.
                </div>}
            </section>

            <section className="panel">
              <div className="panel-title">
                <div>
                  <h3>Shop inventory</h3>
                  <p>Deleting an item permanently removes it from the purchasable catalog.</p>
                </div>
                <span className="badge">{shop.length} items</span>
              </div>
              {shop.length
                ? <>
                  <div className="data-list shop-list">
                    {shop.map((row) => <div className="data-row shop-row" key={row._id}>
                      <div className="data-row-copy">
                        <div className="shop-item-title">
                          <strong>{row.name}</strong>
                          <span className={`badge ${row.enabled ? "is-active" : "is-disabled"}`}>
                            {row.enabled ? "Active" : "Disabled"}
                          </span>
                        </div>
                        <span>{row.sku} · {formatNumber(row.price)}</span>
                        {row.description && <p>{row.description}</p>}
                      </div>
                      <button
                        type="button"
                        className="button danger compact shop-delete"
                        onClick={() => setPendingDelete({ id: row._id, name: row.name })}
                        disabled={Boolean(deletingItem)}
                        aria-label={`Permanently delete ${row.name} from the shop`}
                      >
                        <Trash2 size={15} />
                        {deletingItem === row._id ? "Deleting…" : "Delete"}
                      </button>
                    </div>)}
                  </div>
                  {pendingDelete && <PrivilegedConfirmation
                    title={`Delete ${pendingDelete.name}?`}
                    description="This permanently removes the item from the server shop and cannot be undone."
                    details={[
                      { label: "Item", value: pendingDelete.name },
                      { label: "Server", value: guildId },
                    ]}
                    confirmLabel="Delete item"
                    busy={deletingItem === pendingDelete.id}
                    onCancel={() => setPendingDelete(null)}
                    onConfirm={() => deleteItem(pendingDelete.id, pendingDelete.name)}
                  />}
                </>
                : <div className="api-state economy-list-empty">
                  No shop items have been created. Use the form above to add the first one.
                </div>}
            </section>
          </div>
        </section>
      </div>}
    </ApiState>
  </div>;
}

export default function EconomyPage() {
  const { guildId } = useParams();
  return <EconomyPageContent key={guildId} guildId={guildId} />;
}
