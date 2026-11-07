import { Check, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router";
import ApiState from "../components/ApiState.jsx";
import PageHeader from "../components/PageHeader.jsx";
import { useApi } from "../hooks/useApi.js";
import { api, json } from "../lib/api.js";

const MODULES = ["ban", "kick", "channel", "role", "webhook", "botadd"];
const PUNISHMENTS = ["ban", "kick", "strip", "timeout", "warn"];

function settingsPayload(form) {
  return {
    prefix: form.prefix,
    antiNuke: form.antiNuke,
    welcome: form.welcome,
    leave: form.leave,
    inviteLog: form.inviteLog,
    access: form.access,
  };
}

function Toggle({ value, onChange, label }) {
  return <button
    type="button"
    className={`toggle ${value ? "on" : ""}`}
    onClick={() => onChange(!value)}
    role="switch"
    aria-checked={value}
    aria-label={label}
  />;
}

function SectionHeading({ id, title, description }) {
  return <div className="settings-section-heading">
    <p className="eyebrow">Configuration</p>
    <h2 id={id}>{title}</h2>
    <p>{description}</p>
  </div>;
}

function MessagePanel({ id, title, description, value, onChange }) {
  return <section className="panel message-panel" aria-labelledby={`${id}-title`}>
    <div className="panel-title">
      <div>
        <h3 id={`${id}-title`}>{title}</h3>
        <p>{description}</p>
      </div>
      <Toggle
        label={`${value.enabled ? "Disable" : "Enable"} ${title.toLowerCase()}`}
        value={value.enabled}
        onChange={(enabled) => onChange({ ...value, enabled })}
      />
    </div>
    <div className="field">
      <label htmlFor={`${id}-channel`}>Channel ID</label>
      <input
        id={`${id}-channel`}
        className="input"
        value={value.channelId}
        onChange={(event) => onChange({ ...value, channelId: event.target.value })}
        pattern="[0-9]{16,22}"
        inputMode="numeric"
        placeholder="123456789012345678"
      />
    </div>
    <div className="field field-spaced">
      <label htmlFor={`${id}-message`}>Message</label>
      <textarea
        id={`${id}-message`}
        className="textarea"
        value={value.message}
        maxLength={1500}
        onChange={(event) => onChange({ ...value, message: event.target.value })}
        placeholder="Welcome {user} to {server}. You are member {count}."
      />
      <span className="field-hint">{value.message.length.toLocaleString()} / 1,500 characters</span>
    </div>
  </section>;
}

function SettingsPageContent({ guildId }) {
  const guildPath = encodeURIComponent(guildId);
  const state = useApi(`/api/settings/${guildPath}`);
  const [form, setForm] = useState(null);
  const [savedSignature, setSavedSignature] = useState("");
  const [notice, setNotice] = useState(null);
  const [saving, setSaving] = useState(false);
  const [alias, setAlias] = useState({ name: "", command: "" });
  const [aliasPending, setAliasPending] = useState(false);
  const [removingAlias, setRemovingAlias] = useState(null);

  useEffect(() => {
    if (!state.data) return;
    setForm(state.data);
    setSavedSignature(JSON.stringify(settingsPayload(state.data)));
  }, [state.data]);

  const currentSignature = useMemo(
    () => (form ? JSON.stringify(settingsPayload(form)) : ""),
    [form],
  );
  const isDirty = Boolean(form && savedSignature && currentSignature !== savedSignature);
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));

  useEffect(() => {
    if (!isDirty) return undefined;
    const warnBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [isDirty]);

  const save = async (event) => {
    event?.preventDefault();
    if (!form || saving) return;

    const payload = settingsPayload(form);
    setSaving(true);
    setNotice(null);
    try {
      const saved = await api(`/api/settings/${guildPath}`, json("PATCH", payload));
      setForm(saved);
      setSavedSignature(JSON.stringify(settingsPayload(saved)));
      setNotice({ ok: true, text: "Settings saved and queued for the bot runtime." });
    } catch (error) {
      setNotice({ ok: false, text: error.message });
    } finally {
      setSaving(false);
    }
  };

  const setAccess = (key, raw) => update("access", {
    ...form.access,
    [key]: raw.split(/[\s,]+/).map((id) => id.trim()).filter(Boolean),
  });

  const addAlias = async (event) => {
    event.preventDefault();
    if (aliasPending) return;

    setAliasPending(true);
    setNotice(null);
    try {
      const aliases = await api(`/api/settings/${guildPath}/aliases`, json("POST", alias));
      setForm((current) => ({ ...current, aliases }));
      setAlias({ name: "", command: "" });
      setNotice({ ok: true, text: "Alias added immediately." });
    } catch (error) {
      setNotice({ ok: false, text: error.message });
    } finally {
      setAliasPending(false);
    }
  };

  const removeAlias = async (name) => {
    if (removingAlias) return;

    setRemovingAlias(name);
    setNotice(null);
    try {
      const aliases = await api(
        `/api/settings/${guildPath}/aliases/${encodeURIComponent(name)}`,
        { method: "DELETE" },
      );
      setForm((current) => ({ ...current, aliases }));
      setNotice({ ok: true, text: `Alias ${form.prefix}${name} deleted.` });
    } catch (error) {
      setNotice({ ok: false, text: error.message });
    } finally {
      setRemovingAlias(null);
    }
  };

  return <div className="page-shell settings-page">
    <PageHeader
      eyebrow={`Server · ${guildId}`}
      title="Server settings"
      description="Configure command behavior, server protection, automated messages, and trusted access."
      actions={<button
        type="submit"
        form="settings-form"
        className="button"
        disabled={!form || saving}
      >
        <Save size={16} />{saving ? "Saving…" : "Save all"}
      </button>}
    />
    <ApiState
      loading={state.loading}
      refreshing={state.refreshing}
      stale={state.stale}
      error={state.error}
      onRetry={state.reload}
    >
      {form && <div className="settings-workspace">
        <div className={`settings-save-bar ${isDirty ? "is-dirty" : ""}`} aria-live="polite">
          <div className="save-status">
            {saving
              ? <><span className="save-status-dot" aria-hidden="true" />Saving changes…</>
              : isDirty
                ? <><span className="save-status-dot" aria-hidden="true" />Unsaved changes</>
                : <><Check size={16} aria-hidden="true" />All bulk settings saved</>}
          </div>
          <p>Aliases are applied immediately and do not require this save.</p>
          <button
            type="submit"
            form="settings-form"
            className="button compact"
            disabled={!isDirty || saving}
          >
            <Save size={15} />{saving ? "Saving…" : "Save changes"}
          </button>
        </div>

        {notice && <div
          className={`notice settings-notice ${notice.ok ? "" : "error"}`}
          role={notice.ok ? "status" : "alert"}
        >
          {notice.text}
        </div>}

        <form id="settings-form" className="settings-form" onSubmit={save}>
          <section className="settings-section" aria-labelledby="settings-basics-title">
            <SectionHeading
              id="settings-basics-title"
              title="Basics"
              description="Set the command prefix and the destination for security events."
            />
            <div className="two-column settings-section-content">
              <section className="panel">
                <div className="panel-title">
                  <div>
                    <h3>Command prefix</h3>
                    <p>Use one to five characters that members can type easily.</p>
                  </div>
                </div>
                <div className="field">
                  <label htmlFor="command-prefix">Prefix</label>
                  <input
                    id="command-prefix"
                    className="input"
                    value={form.prefix}
                    required
                    minLength={1}
                    maxLength={5}
                    onChange={(event) => update("prefix", event.target.value)}
                  />
                </div>
              </section>
              <section className="panel">
                <div className="panel-title">
                  <div>
                    <h3>AntiNuke master switch</h3>
                    <p>Module rules are enforced only while this switch is enabled.</p>
                  </div>
                  <Toggle
                    label={`${form.antiNuke.enabled ? "Disable" : "Enable"} AntiNuke`}
                    value={form.antiNuke.enabled}
                    onChange={(enabled) => update("antiNuke", { ...form.antiNuke, enabled })}
                  />
                </div>
                <div className="field">
                  <label htmlFor="security-log-channel">Security log channel ID</label>
                  <input
                    id="security-log-channel"
                    className="input"
                    value={form.antiNuke.logChannelId}
                    pattern="[0-9]{16,22}"
                    inputMode="numeric"
                    placeholder="Optional Discord channel ID"
                    onChange={(event) => update("antiNuke", {
                      ...form.antiNuke,
                      logChannelId: event.target.value,
                    })}
                  />
                </div>
              </section>
            </div>
          </section>

          <section className="settings-section" aria-labelledby="settings-protection-title">
            <SectionHeading
              id="settings-protection-title"
              title="Protection rules"
              description="Tune each high-risk action independently. Thresholds accept values from 1 through 20."
            />
            <div className="three-column settings-section-content protection-grid">
              {MODULES.map((name) => {
                const module = form.antiNuke.modules[name];
                const change = (next) => update("antiNuke", {
                  ...form.antiNuke,
                  modules: { ...form.antiNuke.modules, [name]: next },
                });
                const label = name === "botadd" ? "Bot add" : name;

                return <section key={name} className="panel protection-card">
                  <div className="toggle-row">
                    <strong className="text-capitalize">{label}</strong>
                    <Toggle
                      label={`${module.enabled ? "Disable" : "Enable"} ${label} protection`}
                      value={module.enabled}
                      onChange={(enabled) => change({ ...module, enabled })}
                    />
                  </div>
                  <div className="form-grid protection-fields">
                    <div className="field">
                      <label htmlFor={`${name}-threshold`}>Threshold</label>
                      <input
                        id={`${name}-threshold`}
                        className="input"
                        type="number"
                        min="1"
                        max="20"
                        required
                        value={module.threshold}
                        onChange={(event) => change({ ...module, threshold: Number(event.target.value) })}
                      />
                    </div>
                    <div className="field">
                      <label htmlFor={`${name}-punishment`}>Punishment</label>
                      <select
                        id={`${name}-punishment`}
                        className="select"
                        value={module.punishment}
                        onChange={(event) => change({ ...module, punishment: event.target.value })}
                      >
                        {PUNISHMENTS.map((punishment) =>
                          <option key={punishment} value={punishment}>{punishment}</option>)}
                      </select>
                    </div>
                  </div>
                </section>;
              })}
            </div>
          </section>

          <section className="settings-section" aria-labelledby="settings-messages-title">
            <SectionHeading
              id="settings-messages-title"
              title="Member messages and invite logs"
              description="Choose what xiel sends when members join or leave, and where invite activity is recorded."
            />
            <div className="two-column settings-section-content">
              <MessagePanel
                id="welcome"
                title="Welcome message"
                description="Sent when a member joins."
                value={form.welcome}
                onChange={(value) => update("welcome", value)}
              />
              <MessagePanel
                id="leave"
                title="Leave message"
                description="Sent when a member leaves."
                value={form.leave}
                onChange={(value) => update("leave", value)}
              />
            </div>
            <section className="panel invite-log-panel">
              <div className="panel-title">
                <div>
                  <h3>Invite logging</h3>
                  <p>Leave either destination blank to skip that log.</p>
                </div>
              </div>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="join-log-channel">Join log channel ID</label>
                  <input
                    id="join-log-channel"
                    className="input"
                    value={form.inviteLog.joinChannelId}
                    pattern="[0-9]{16,22}"
                    inputMode="numeric"
                    placeholder="Optional Discord channel ID"
                    onChange={(event) => update("inviteLog", {
                      ...form.inviteLog,
                      joinChannelId: event.target.value,
                    })}
                  />
                </div>
                <div className="field">
                  <label htmlFor="leave-log-channel">Leave log channel ID</label>
                  <input
                    id="leave-log-channel"
                    className="input"
                    value={form.inviteLog.leaveChannelId}
                    pattern="[0-9]{16,22}"
                    inputMode="numeric"
                    placeholder="Optional Discord channel ID"
                    onChange={(event) => update("inviteLog", {
                      ...form.inviteLog,
                      leaveChannelId: event.target.value,
                    })}
                  />
                </div>
              </div>
            </section>
          </section>

          <section className="settings-section" aria-labelledby="settings-access-title">
            <SectionHeading
              id="settings-access-title"
              title="Trusted access"
              description="Enter Discord user IDs separated by commas, spaces, or new lines."
            />
            <section className="panel settings-section-content">
              <div className="three-column">
                {[
                  ["admins", "AntiNuke admins", 100],
                  ["whitelist", "Whitelist", 250],
                  ["trust", "Trusted bot operators", 250],
                ].map(([key, label, limit]) => <div className="field" key={key}>
                  <label htmlFor={`access-${key}`}>{label}</label>
                  <textarea
                    id={`access-${key}`}
                    className="textarea access-list-input"
                    value={form.access[key].join(", ")}
                    onChange={(event) => setAccess(key, event.target.value)}
                    placeholder="123456789012345678"
                    aria-describedby={`access-${key}-hint`}
                  />
                  <span id={`access-${key}-hint`} className="field-hint">
                    {form.access[key].length} of {limit} IDs
                  </span>
                </div>)}
              </div>
            </section>
          </section>
        </form>

        <section className="settings-section" aria-labelledby="settings-aliases-title">
          <SectionHeading
            id="settings-aliases-title"
            title="Command aliases"
            description="Aliases are created and deleted immediately, independently of the bulk settings above."
          />
          <section className="panel settings-section-content aliases-panel">
            <form className="alias-form" onSubmit={addAlias}>
              <div className="field">
                <label htmlFor="alias-name">Alias</label>
                <input
                  id="alias-name"
                  className="input"
                  required
                  pattern="[a-z0-9_-]+"
                  minLength={1}
                  maxLength={32}
                  value={alias.name}
                  onChange={(event) => setAlias({ ...alias, name: event.target.value.toLowerCase() })}
                  placeholder="rules"
                />
              </div>
              <div className="field alias-command-field">
                <label htmlFor="alias-command">Existing command</label>
                <input
                  id="alias-command"
                  className="input"
                  required
                  minLength={1}
                  maxLength={160}
                  value={alias.command}
                  onChange={(event) => setAlias({ ...alias, command: event.target.value })}
                  placeholder="help moderation"
                />
              </div>
              <button className="button alias-submit" disabled={aliasPending}>
                <Plus size={16} />{aliasPending ? "Adding…" : "Add alias"}
              </button>
            </form>

            {form.aliases.length
              ? <div className="data-list alias-list">
                {form.aliases.map((item) => <div className="data-row alias-row" key={item.name}>
                  <div className="data-row-copy">
                    <strong>{form.prefix}{item.name}</strong>
                    <span>{item.command}</span>
                  </div>
                  <button
                    type="button"
                    className="button danger compact alias-delete"
                    onClick={() => removeAlias(item.name)}
                    disabled={Boolean(removingAlias)}
                    aria-label={`Delete alias ${form.prefix}${item.name}`}
                  >
                    <Trash2 size={15} />
                    {removingAlias === item.name ? "Deleting…" : "Delete"}
                  </button>
                </div>)}
              </div>
              : <div className="api-state aliases-empty">
                No aliases yet. Add one to create a shorter path to an existing command.
              </div>}
          </section>
        </section>
      </div>}
    </ApiState>
  </div>;
}

export default function SettingsPage() {
  const { guildId } = useParams();
  return <SettingsPageContent key={guildId} guildId={guildId} />;
}
