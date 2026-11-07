import {
  ArrowUpRight,
  Check,
  CheckCircle2,
  Clipboard,
  Command,
  Gauge,
  Radio,
  Server,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import PageHeader from "../components/PageHeader.jsx";
import StatCard from "../components/StatCard.jsx";
import { useStatus } from "../hooks/useStatus.jsx";
import { formatNumber } from "../lib/api.js";

const INVITE_PRESETS = [
  {
    id: "administrator",
    name: "Administrator",
    permissions: "8",
    summary: "Everything enabled",
    description: "Best when xiel will operate the full moderation, security, economy, and automation stack.",
  },
  {
    id: "recommended",
    name: "Recommended",
    permissions: "268823648",
    summary: "Balanced server access",
    description: "Balanced access including Manage Server, which is required for accurate invite tracking.",
  },
  {
    id: "slash-only",
    name: "Slash-only",
    permissions: "274877906944",
    summary: "Commands and responses",
    description: "A minimal command-oriented install. Invite tracking is unavailable with this profile.",
  },
];

function sameOriginInviteUrl(path) {
  if (typeof window === "undefined") return path;
  return new URL(path, window.location.origin).toString();
}

export default function InvitesPage() {
  const [selectedPermissions, setSelectedPermissions] = useState("8");
  const [copyFeedback, setCopyFeedback] = useState("");
  const { status, connectionState } = useStatus();
  const invitePath = `/api/invite?permissions=${selectedPermissions}`;
  const inviteUrl = sameOriginInviteUrl(invitePath);
  const selectedPreset = INVITE_PRESETS.find((preset) => preset.permissions === selectedPermissions);

  const choosePreset = (permissions) => {
    setSelectedPermissions(permissions);
    setCopyFeedback("");
  };

  const copyInvite = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard API unavailable");
      await navigator.clipboard.writeText(inviteUrl);
      setCopyFeedback("Invite link copied to your clipboard.");
    } catch {
      setCopyFeedback("Copy failed. Select the generated link and copy it manually.");
    }
  };

  const footprintState = status?.online
    ? connectionState === "reconnecting" ? "Reconnecting" : "Online"
    : connectionState === "checking" ? "Checking" : "Offline";

  return <div className="page-shell route-stage route-reveal invites-command">
    <PageHeader
      eyebrow="Installation control"
      title="Invite xiel, deliberately."
      description="Choose a reviewed permission profile, inspect the exact same-origin invite endpoint, and finish setup with live bot context."
    />

    <section className="panel invite-generator" aria-labelledby="invite-generator-title">
      <div className="panel-title">
        <div>
          <h2 id="invite-generator-title">Permission profile</h2>
          <p>Only these three reviewed presets can reach Discord through the dashboard.</p>
        </div>
        <ShieldCheck aria-hidden="true" />
      </div>

      <div className="feature-grid invite-preset-slides" role="group" aria-label="Invite permission presets">
        {INVITE_PRESETS.map((preset, index) => {
          const selected = preset.permissions === selectedPermissions;
          return <button
            key={preset.id}
            type="button"
            className={`feature-card invite-preset-slide${selected ? " is-selected" : ""}`}
            aria-pressed={selected}
            onClick={() => choosePreset(preset.permissions)}
          >
            <span className="feature-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
            <span className="invite-preset-slide__status">
              {selected ? <Check size={16} aria-hidden="true" /> : <Radio size={16} aria-hidden="true" />}
              {selected ? "Selected" : "Select preset"}
            </span>
            <strong>{preset.name}</strong>
            <span>{preset.summary}</span>
            <code>{preset.permissions}</code>
            <small>{preset.description}</small>
          </button>;
        })}
      </div>

      <div className="two-column invite-output-grid">
        <label className="field invite-url-field" htmlFor="invite-url">
          <span>Generated same-origin invite</span>
          <input
            id="invite-url"
            className="input"
            aria-label="Generated same-origin invite"
            value={inviteUrl}
            readOnly
            onFocus={(event) => event.currentTarget.select()}
          />
          <small>{selectedPreset?.name} · permission integer {selectedPermissions}</small>
        </label>
        <div className="toolbar invite-actions">
          <a className="button" href={invitePath} target="_blank" rel="noopener noreferrer">
            Open Invite <ArrowUpRight size={17} aria-hidden="true" />
          </a>
          <button type="button" className="button secondary" onClick={copyInvite}>
            <Clipboard size={17} aria-hidden="true" />Copy Link
          </button>
          <p
            className={`invite-feedback${copyFeedback.startsWith("Copy failed") ? " notice error" : copyFeedback ? " notice" : ""}`}
            role="status"
            aria-live="polite"
          >
            {copyFeedback || "The preview updates without sending you away from xiel."}
          </p>
        </div>
      </div>
    </section>

    <div className="two-column invite-support-grid">
      <section className="panel" aria-labelledby="invite-checklist-title">
        <div className="panel-title">
          <div>
            <h2 id="invite-checklist-title">Setup checklist</h2>
            <p>Three checks before you hand xiel the keys.</p>
          </div>
          <CheckCircle2 aria-hidden="true" />
        </div>
        <ol className="data-list invite-checklist">
          <li className="data-row">
            <CheckCircle2 size={18} aria-hidden="true" />
            <span>Use Recommended for public servers unless your configuration needs administrator access.</span>
          </li>
          <li className="data-row">
            <CheckCircle2 size={18} aria-hidden="true" />
            <span>Keep Manage Server available when you configure invite tracking and server settings.</span>
          </li>
          <li className="data-row">
            <CheckCircle2 size={18} aria-hidden="true" />
            <span>Confirm slash commands have synced after xiel joins, then review the command atlas.</span>
          </li>
        </ol>
      </section>

      <section className="panel invite-footprint" aria-labelledby="invite-footprint-title">
        <div className="panel-title">
          <div>
            <h2 id="invite-footprint-title">Live bot footprint</h2>
            <p>Current telemetry from the same status stream used across the dashboard.</p>
          </div>
          <Server aria-hidden="true" />
        </div>
        <div className="two-column invite-footprint__stats">
          <StatCard
            label="Gateway"
            value={footprintState}
            detail={status?.online ? "Ready for a new server" : "Check status before installing"}
          />
          <StatCard label="Servers" value={status ? formatNumber(status.guilds) : "—"} />
          <StatCard label="Users reached" value={status ? formatNumber(status.users) : "—"} />
          <StatCard label="Latency" value={status?.latency != null ? `${status.latency} ms` : "—"} />
        </div>
      </section>
    </div>

    <nav className="three-column invite-quick-actions" aria-label="Continue xiel setup">
      <Link className="feature-card" to="/commands">
        <Command aria-hidden="true" />
        <h2>Commands</h2>
        <p>Check syntax, aliases, access markers, and every available category.</p>
      </Link>
      <Link className="feature-card" to="/status">
        <Radio aria-hidden="true" />
        <h2>Status</h2>
        <p>Inspect gateway health, latency, uptime, and the latest telemetry heartbeat.</p>
      </Link>
      <Link className="feature-card" to="/dashboard">
        <Gauge aria-hidden="true" />
        <h2>Dashboard</h2>
        <p>Sign in to configure the servers where you already manage xiel.</p>
      </Link>
    </nav>
  </div>;
}
