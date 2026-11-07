import {
  Ban,
  Plus,
  Server,
  ShieldCheck,
  Trash2,
  UserRoundCheck,
} from "lucide-react";
import { useState } from "react";
import ApiState from "./ApiState.jsx";
import PageHeader from "./PageHeader.jsx";
import PrivilegedConfirmation from "./PrivilegedConfirmation.jsx";
import PrivilegedRegistry from "./PrivilegedRegistry.jsx";
import StatCard from "./StatCard.jsx";
import { useApi } from "../hooks/useApi.js";
import { api, formatNumber, json } from "../lib/api.js";

const DISCORD_ID_PATTERN = "\\d{16,22}";

const premiumSearchText = (row) =>
  `${row.userId} ${row.guildId} ${row.commandName}`;
const profileSearchText = (row) => `${row.userId} ${row.guildId}`;
const banSearchText = (row) => `${row.userId} ${row.reason}`;
const serverSearchText = (row) => `${row.name} ${row.id} ${row.memberCount}`;

function PremiumGrantForm({ onSubmit, busy }) {
  const [grant, setGrant] = useState({
    userId: "",
    guildId: "",
    commandName: "all",
  });

  const submitGrant = async (event) => {
    const saved = await onSubmit(event, grant);
    if (saved) {
      setGrant({ userId: "", guildId: "", commandName: "all" });
    }
  };

  return (
    <section className="panel citadel-panel citadel-panel--grant">
      <div className="panel-title citadel-panel__heading">
        <div>
          <p className="citadel-panel__kicker">Command entitlement</p>
          <h2>Grant premium access</h2>
          <p>Authorize one user in one server for a command or every command.</p>
        </div>
        <ShieldCheck size={22} aria-hidden="true" />
      </div>
      <form className="stack citadel-form" onSubmit={submitGrant}>
        <div className="form-grid">
          <div className="field citadel-field">
            <label htmlFor="premium-user-id">Discord user ID</label>
            <input
              id="premium-user-id"
              className="input"
              required
              pattern={DISCORD_ID_PATTERN}
              inputMode="numeric"
              autoComplete="off"
              placeholder="123456789012345678"
              value={grant.userId}
              onChange={(event) =>
                setGrant({ ...grant, userId: event.target.value })
              }
            />
          </div>
          <div className="field citadel-field">
            <label htmlFor="premium-server-id">Discord server ID</label>
            <input
              id="premium-server-id"
              className="input"
              required
              pattern={DISCORD_ID_PATTERN}
              inputMode="numeric"
              autoComplete="off"
              placeholder="123456789012345678"
              value={grant.guildId}
              onChange={(event) =>
                setGrant({ ...grant, guildId: event.target.value })
              }
            />
          </div>
        </div>
        <div className="field citadel-field">
          <label htmlFor="premium-command">Command scope</label>
          <input
            id="premium-command"
            className="input"
            required
            autoComplete="off"
            placeholder="all or a premium command name"
            value={grant.commandName}
            onChange={(event) =>
              setGrant({ ...grant, commandName: event.target.value })
            }
          />
        </div>
        <div className="citadel-form__actions">
          <button className="button" type="submit" disabled={busy}>
            <Plus size={15} aria-hidden="true" />
            {busy ? "Granting…" : "Grant premium"}
          </button>
        </div>
      </form>
    </section>
  );
}

function ProfileGrantForm({ onSubmit, busy }) {
  const [profile, setProfile] = useState({ userId: "", guildId: "" });

  const submitGrant = async (event) => {
    const saved = await onSubmit(event, profile);
    if (saved) {
      setProfile({ userId: "", guildId: "" });
    }
  };

  return (
    <section className="panel citadel-panel citadel-panel--grant">
      <div className="panel-title citadel-panel__heading">
        <div>
          <p className="citadel-panel__kicker">Profile entitlement</p>
          <h2>Grant profile access</h2>
          <p>Manage bot profile access separately from premium commands.</p>
        </div>
        <UserRoundCheck size={22} aria-hidden="true" />
      </div>
      <form className="stack citadel-form" onSubmit={submitGrant}>
        <div className="field citadel-field">
          <label htmlFor="profile-user-id">Discord user ID</label>
          <input
            id="profile-user-id"
            className="input"
            required
            pattern={DISCORD_ID_PATTERN}
            inputMode="numeric"
            autoComplete="off"
            placeholder="123456789012345678"
            value={profile.userId}
            onChange={(event) =>
              setProfile({ ...profile, userId: event.target.value })
            }
          />
        </div>
        <div className="field citadel-field">
          <label htmlFor="profile-server-id">Discord server ID</label>
          <input
            id="profile-server-id"
            className="input"
            required
            pattern={DISCORD_ID_PATTERN}
            inputMode="numeric"
            autoComplete="off"
            placeholder="123456789012345678"
            value={profile.guildId}
            onChange={(event) =>
              setProfile({ ...profile, guildId: event.target.value })
            }
          />
        </div>
        <div className="citadel-form__actions">
          <button className="button" type="submit" disabled={busy}>
            <Plus size={15} aria-hidden="true" />
            {busy ? "Granting…" : "Grant profile"}
          </button>
        </div>
      </form>
    </section>
  );
}

function GrantRegistry({
  kind,
  rows,
  pendingRevoke,
  onRequestRevoke,
  onCancelRevoke,
  onConfirmRevoke,
  busy,
}) {
  const premium = kind === "premium";
  const title = premium ? "Premium grant ledger" : "Profile grant ledger";
  const noun = premium ? "premium grants" : "profile grants";

  return (
    <section className="panel citadel-panel citadel-panel--ledger">
      <div className="panel-title citadel-panel__heading">
        <div>
          <p className="citadel-panel__kicker">Revocation ledger</p>
          <h2>{title}</h2>
          <p>Search the active records, then explicitly confirm any revocation.</p>
        </div>
      </div>
      {pendingRevoke?.kind === kind && (
        <PrivilegedConfirmation
          danger={false}
          title={`Revoke ${premium ? "premium" : "profile"} access?`}
          description="This removes the selected entitlement immediately."
          details={[
            { label: "User ID", value: pendingRevoke.row.userId },
            { label: "Server ID", value: pendingRevoke.row.guildId },
            ...(premium
              ? [{ label: "Command", value: pendingRevoke.row.commandName }]
              : []),
          ]}
          confirmLabel="Confirm revoke"
          onCancel={onCancelRevoke}
          onConfirm={onConfirmRevoke}
          busy={busy}
        />
      )}
      <PrivilegedRegistry
        items={rows}
        label={`Search ${noun}`}
        noun={noun}
        searchPlaceholder={
          premium
            ? "User ID, server ID, or command"
            : "User ID or server ID"
        }
        getSearchText={premium ? premiumSearchText : profileSearchText}
        emptyMessage={`No ${noun} have been created.`}
        renderItem={(row) => (
          <article
            className="data-row citadel-record"
            key={row._id}
            aria-label={`${premium ? "Premium" : "Profile"} grant for user ${row.userId}`}
          >
            <div className="citadel-record__identity">
              <strong>{row.userId}</strong>
              <span>Server {row.guildId}</span>
            </div>
            <div className="citadel-record__meta">
              {premium && (
                <span className="badge citadel-record__scope">
                  {row.commandName}
                </span>
              )}
              <button
                className="icon-button danger"
                type="button"
                aria-label={`Revoke ${premium ? "premium" : "profile"} access for user ${row.userId} in server ${row.guildId}`}
                onClick={() => onRequestRevoke(kind, row)}
              >
                <Trash2 size={15} aria-hidden="true" />
              </button>
            </div>
          </article>
        )}
      />
    </section>
  );
}

function OwnerBanPanel({ onNotice }) {
  const bans = useApi("/api/owner/bans");
  const [ban, setBan] = useState({ userId: "", reason: "" });
  const [pendingBan, setPendingBan] = useState(null);
  const [pendingUnban, setPendingUnban] = useState(null);
  const [busy, setBusy] = useState(false);

  const requestBan = (event) => {
    event.preventDefault();
    setPendingUnban(null);
    setPendingBan({ ...ban });
  };

  const confirmBan = async () => {
    if (!pendingBan) return;
    setBusy(true);
    try {
      await api("/api/owner/bans", json("POST", pendingBan));
      setBan({ userId: "", reason: "" });
      setPendingBan(null);
      onNotice({
        ok: true,
        text: `Global ban created for user ${pendingBan.userId}.`,
      });
      await bans.reload();
    } catch (error) {
      onNotice({ ok: false, text: error.message });
    } finally {
      setBusy(false);
    }
  };

  const confirmUnban = async () => {
    if (!pendingUnban) return;
    setBusy(true);
    try {
      await api(`/api/owner/bans/${pendingUnban.userId}`, {
        method: "DELETE",
      });
      setPendingUnban(null);
      onNotice({
        ok: true,
        text: `Global ban removed for user ${pendingUnban.userId}.`,
      });
      await bans.reload();
    } catch (error) {
      onNotice({ ok: false, text: error.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel citadel-panel citadel-panel--danger">
      <div className="panel-title citadel-panel__heading">
        <div>
          <p className="citadel-panel__kicker">Owner-only enforcement</p>
          <h2>Global ban citadel</h2>
          <p>
            A confirmed record is enforced when the user joins any connected
            server.
          </p>
        </div>
        <Ban size={23} aria-hidden="true" />
      </div>

      <form className="form-grid citadel-form" onSubmit={requestBan}>
        <div className="field citadel-field">
          <label htmlFor="global-ban-user-id">Discord user ID</label>
          <input
            id="global-ban-user-id"
            className="input"
            required
            pattern={DISCORD_ID_PATTERN}
            inputMode="numeric"
            autoComplete="off"
            placeholder="123456789012345678"
            value={ban.userId}
            onChange={(event) =>
              setBan({ ...ban, userId: event.target.value })
            }
          />
        </div>
        <div className="field citadel-field">
          <label htmlFor="global-ban-reason">Ban reason</label>
          <input
            id="global-ban-reason"
            className="input"
            required
            minLength="3"
            autoComplete="off"
            placeholder="Reason shown in the enforcement record"
            value={ban.reason}
            onChange={(event) =>
              setBan({ ...ban, reason: event.target.value })
            }
          />
        </div>
        <div className="citadel-form__actions citadel-form__actions--wide">
          <button className="button danger" type="submit" disabled={busy}>
            Review global ban
          </button>
        </div>
      </form>

      {pendingBan && (
        <PrivilegedConfirmation
          title="Apply this global ban across connected servers?"
          description="This is a global enforcement action. The user may be banned from every connected server where the bot has permission."
          details={[
            { label: "User ID", value: pendingBan.userId },
            { label: "Reason", value: pendingBan.reason },
          ]}
          confirmLabel="Apply global ban"
          onCancel={() => setPendingBan(null)}
          onConfirm={confirmBan}
          busy={busy}
        />
      )}

      {pendingUnban && (
        <PrivilegedConfirmation
          title="Remove this global ban record?"
          description="The global-ban record will be revoked. This does not automatically restore prior server membership."
          details={[
            { label: "User ID", value: pendingUnban.userId },
            { label: "Reason", value: pendingUnban.reason },
          ]}
          confirmLabel="Remove global ban"
          onCancel={() => setPendingUnban(null)}
          onConfirm={confirmUnban}
          busy={busy}
        />
      )}

      <div className="citadel-panel__registry">
        <ApiState
          loading={bans.loading}
          refreshing={bans.refreshing}
          stale={bans.stale}
          error={bans.error}
          onRetry={bans.reload}
        >
          <PrivilegedRegistry
            items={Array.isArray(bans.data) ? bans.data : []}
            label="Search global bans"
            noun="global bans"
            searchPlaceholder="User ID or reason"
            getSearchText={banSearchText}
            emptyMessage="No global bans are active."
            className="citadel-registry--danger"
            renderItem={(row) => (
              <article
                className="data-row citadel-record citadel-record--danger"
                key={row.userId}
                aria-label={`Global ban for user ${row.userId}`}
              >
                <div className="citadel-record__identity">
                  <strong>{row.userId}</strong>
                  <span>{row.reason}</span>
                </div>
                <button
                  className="icon-button danger"
                  type="button"
                  aria-label={`Remove global ban for user ${row.userId}`}
                  onClick={() => {
                    setPendingBan(null);
                    setPendingUnban(row);
                  }}
                >
                  <Trash2 size={15} aria-hidden="true" />
                </button>
              </article>
            )}
          />
        </ApiState>
      </div>
    </section>
  );
}

function ServerRegistry({ servers, owner, onNotice, onReload }) {
  const [pendingLeave, setPendingLeave] = useState(null);
  const [busy, setBusy] = useState(false);

  const confirmLeave = async () => {
    if (!owner || !pendingLeave) return;
    setBusy(true);
    try {
      await api(`/api/owner/servers/${pendingLeave.id}`, { method: "DELETE" });
      onNotice({
        ok: true,
        text: `The bot left ${pendingLeave.name}.`,
      });
      setPendingLeave(null);
      await onReload();
    } catch (error) {
      onNotice({ ok: false, text: error.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel citadel-panel citadel-panel--servers">
      <div className="panel-title citadel-panel__heading">
        <div>
          <p className="citadel-panel__kicker">Connected territory</p>
          <h2>Server load registry</h2>
          <p>Search the current guild cache, ranked by member count.</p>
        </div>
        <Server size={22} aria-hidden="true" />
      </div>

      {owner && pendingLeave && (
        <PrivilegedConfirmation
          title={`Make the bot leave ${pendingLeave.name}?`}
          description="This immediately removes the bot from the selected server. Rejoining will require a new Discord invite."
          details={[
            { label: "Server", value: pendingLeave.name },
            { label: "Server ID", value: pendingLeave.id },
            {
              label: "Cached members",
              value: formatNumber(pendingLeave.memberCount),
            },
          ]}
          confirmLabel="Leave this server"
          onCancel={() => setPendingLeave(null)}
          onConfirm={confirmLeave}
          busy={busy}
        />
      )}

      <PrivilegedRegistry
        items={servers}
        label="Search connected servers"
        noun="servers"
        searchPlaceholder="Server name or ID"
        getSearchText={serverSearchText}
        emptyMessage="No connected servers are currently cached."
        renderItem={(server, index) => (
          <article
            className="data-row citadel-record citadel-server-record"
            key={server.id}
            aria-label={`${server.name}, server ${server.id}`}
          >
            <div className="citadel-server-record__rank" aria-hidden="true">
              {String(index + 1).padStart(2, "0")}
            </div>
            <div className="citadel-record__identity">
              <strong>{server.name}</strong>
              <span>
                {server.id} · {formatNumber(server.memberCount)} members
              </span>
            </div>
            {owner && (
              <button
                className="button danger compact"
                type="button"
                aria-label={`Make the bot leave ${server.name}, server ${server.id}`}
                onClick={() => setPendingLeave(server)}
              >
                Leave server
              </button>
            )}
          </article>
        )}
      />
    </section>
  );
}

export default function PrivilegedConsole({ capability = "coowner" }) {
  const owner = capability === "owner";
  const base = owner ? "/api/owner" : "/api/coowner";
  const state = useApi(`${base}/overview`);
  const [notice, setNotice] = useState(null);
  const [busyAction, setBusyAction] = useState(null);
  const [pendingRevoke, setPendingRevoke] = useState(null);

  const submitGrant = (path, successMessage) => async (event, body) => {
    event.preventDefault();
    setBusyAction(path);
    setNotice(null);
    try {
      await api(`${base}${path}`, json("POST", body));
      setNotice({ ok: true, text: successMessage });
      await state.reload();
      return true;
    } catch (error) {
      setNotice({ ok: false, text: error.message });
      return false;
    } finally {
      setBusyAction(null);
    }
  };

  const requestRevoke = (kind, row) => {
    setPendingRevoke({ kind, row });
  };

  const confirmRevoke = async () => {
    if (!pendingRevoke) return;
    const { kind, row } = pendingRevoke;
    setBusyAction(`revoke-${kind}`);
    setNotice(null);
    try {
      await api(`${base}/${kind}/${row._id}`, { method: "DELETE" });
      setNotice({
        ok: true,
        text: `${kind === "premium" ? "Premium" : "Profile"} access revoked for user ${row.userId}.`,
      });
      setPendingRevoke(null);
      await state.reload();
    } catch (error) {
      setNotice({ ok: false, text: error.message });
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div
      className={`page-shell citadel-console citadel-console--${owner ? "owner" : "coowner"}`}
    >
      <div className="citadel-console__masthead">
        <PageHeader
          eyebrow={owner ? "Owner authority" : "Co-owner authority"}
          title={owner ? "Owner console" : "Co-owner console"}
          description={
            owner
              ? "Global enforcement, access grants, and destructive server operations. Every capability is checked again by the server."
              : "Premium and profile access management with a server-enforced co-owner capability boundary."
          }
        />
      </div>

      <ApiState
        loading={state.loading}
        refreshing={state.refreshing}
        stale={state.stale}
        error={state.error}
        onRetry={state.reload}
      >
        {state.data && (
          <div className="stack citadel-console__body">
            {notice && (
              <div
                className={`notice citadel-console__notice${notice.ok ? "" : " error"}`}
                role={notice.ok ? "status" : "alert"}
              >
                {notice.text}
              </div>
            )}

            <section
              className="stats-grid citadel-console__stats"
              aria-label="Privileged console overview"
            >
              <StatCard
                label="Connected servers"
                value={state.data.servers.length}
              />
              <StatCard
                label="Combined members"
                value={formatNumber(
                  state.data.servers.reduce(
                    (sum, row) => sum + row.memberCount,
                    0,
                  ),
                )}
              />
              <StatCard
                label="Premium grants"
                value={state.data.premium.length}
              />
              <StatCard
                label="Profile grants"
                value={state.data.profiles.length}
                tone="flare"
              />
            </section>

            <div className="two-column citadel-console__grant-deck">
              <PremiumGrantForm
                onSubmit={submitGrant(
                  "/premium",
                  "Premium access granted successfully.",
                )}
                busy={busyAction === "/premium"}
              />
              <ProfileGrantForm
                onSubmit={submitGrant(
                  "/profiles",
                  "Profile access granted successfully.",
                )}
                busy={busyAction === "/profiles"}
              />
            </div>

            {owner && <OwnerBanPanel onNotice={setNotice} />}

            <div className="two-column citadel-console__ledgers">
              <GrantRegistry
                kind="premium"
                rows={state.data.premium}
                pendingRevoke={pendingRevoke}
                onRequestRevoke={requestRevoke}
                onCancelRevoke={() => setPendingRevoke(null)}
                onConfirmRevoke={confirmRevoke}
                busy={busyAction === "revoke-premium"}
              />
              <GrantRegistry
                kind="profiles"
                rows={state.data.profiles}
                pendingRevoke={pendingRevoke}
                onRequestRevoke={(kind, row) =>
                  requestRevoke(kind === "profiles" ? "profiles" : kind, row)
                }
                onCancelRevoke={() => setPendingRevoke(null)}
                onConfirmRevoke={confirmRevoke}
                busy={busyAction === "revoke-profiles"}
              />
            </div>

            <ServerRegistry
              servers={state.data.servers}
              owner={owner}
              onNotice={setNotice}
              onReload={state.reload}
            />
          </div>
        )}
      </ApiState>
    </div>
  );
}
