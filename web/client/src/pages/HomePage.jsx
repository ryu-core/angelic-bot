import {
  Activity,
  ArrowRight,
  BookOpenText,
  Coins,
  Command,
  Gauge,
  Radio,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Link, useLocation } from "react-router";
import SaturnScrollScene from "../components/SaturnScrollScene.jsx";
import { useStatus } from "../hooks/useStatus.jsx";
import { formatNumber } from "../lib/api.js";

const SYSTEM_SLIDES = [
  {
    number: "01",
    tone: "security",
    icon: ShieldCheck,
    kicker: "Protection / Moderation",
    title: "A perimeter that reacts before chaos spreads.",
    copy: "Tune AntiNuke thresholds, punishments, trusted users, admins, moderation flows, and audit destinations for every managed server.",
    capabilities: ["AntiNuke", "Moderation", "Staff tools", "Security logs"],
    to: "/dashboard",
    linkLabel: "Open the control plane",
    rail: "Detect / decide / contain",
  },
  {
    number: "02",
    tone: "automation",
    icon: Gauge,
    kicker: "Setup / Automation",
    title: "Server operations, organized into one exact surface.",
    copy: "Manage prefixes, aliases, welcome and leave messages, invite logging, role automation, boosters, tickets, and recurring community systems.",
    capabilities: ["Server setup", "Welcome", "Invites", "Roles & tickets"],
    to: "/dashboard",
    linkLabel: "Manage a server",
    rail: "Configure / validate / deploy",
  },
  {
    number: "03",
    tone: "economy",
    icon: Coins,
    kicker: "Economy / Games",
    title: "An economy with real operational controls.",
    copy: "Inspect balances and streaks, apply wallet corrections, operate a server-scoped shop, and give members games, crypto tools, collections, and rewards.",
    capabilities: ["Economy", "Games", "Crypto", "Catch system"],
    to: "/dashboard",
    linkLabel: "Enter the dashboard",
    rail: "Earn / trade / compete",
  },
  {
    number: "04",
    tone: "community",
    icon: Sparkles,
    kicker: "Community / Culture",
    title: "Every reason for a community to stay in orbit.",
    copy: "AI chat, voice, music, roleplay, confessions, marriage, giveaways, therapy, translation, search, and utility tools live in one bot.",
    capabilities: ["AI chat", "Music & voice", "Social systems", "Utilities"],
    to: "/commands",
    linkLabel: "Explore every category",
    rail: "Talk / play / connect",
  },
  {
    number: "05",
    tone: "atlas",
    icon: BookOpenText,
    kicker: "Command Atlas / Docs",
    title: "The complete surface, indexed from the live bot.",
    copy: "Search the current command registry by category, syntax, alias, source, or access marker, then use the operator guide to move from discovery to deployment.",
    capabilities: ["Live registry", "Syntax & aliases", "Access markers", "Operator docs"],
    to: "/commands",
    secondaryTo: "/docs",
    linkLabel: "Browse the command atlas",
    secondaryLabel: "Read operator docs",
    rail: "Search / inspect / execute",
  },
  {
    number: "06",
    tone: "telemetry",
    icon: Activity,
    kicker: "Runtime / Telemetry",
    title: "No simulated health. Only the current signal.",
    copy: "REST establishes the first confirmed snapshot while the live connection keeps latency, reach, uptime, command totals, and availability current.",
    capabilities: ["Live gateway", "Latency", "Uptime", "Execution totals"],
    to: "/status",
    linkLabel: "View system status",
    rail: "Observe / verify / respond",
  },
];

function TelemetryItem({ label, value }) {
  return <div className="xiel-telemetry__item">
    <dt className="xiel-telemetry__label"><span>{label}</span></dt>
    <dd className="xiel-telemetry__value"><strong>{value}</strong></dd>
  </div>;
}

function SystemSlide({ slide }) {
  const Icon = slide.icon;
  const titleId = `system-slide-${slide.number}`;

  return <article
    className={`system-slide system-slide--${slide.tone}`}
    aria-labelledby={titleId}
  >
    <div className="system-slide__index" aria-hidden="true">{slide.number}</div>
    <div className="system-slide__body">
      <div className="system-slide__heading">
        <span className="system-slide__icon" aria-hidden="true"><Icon size={19} /></span>
        <p className="system-slide__kicker">{slide.kicker}</p>
      </div>
      <h3 id={titleId} className="system-slide__title">{slide.title}</h3>
      <p className="system-slide__copy">{slide.copy}</p>
      <ul className="system-slide__capabilities" aria-label={`${slide.kicker} capabilities`}>
        {slide.capabilities.map((capability) => (
          <li className="system-slide__capability" key={capability}>{capability}</li>
        ))}
      </ul>
      <div className="system-slide__links">
        <Link className="system-slide__link" to={slide.to}>
          {slide.linkLabel}<ArrowRight size={16} aria-hidden="true" />
        </Link>
        {slide.secondaryTo && <Link
          className="system-slide__link system-slide__link--secondary"
          to={slide.secondaryTo}
        >
          {slide.secondaryLabel}<ArrowRight size={16} aria-hidden="true" />
        </Link>}
      </div>
    </div>
    <div className="system-slide__rail" aria-hidden="true">
      <span>{slide.rail}</span>
      <i />
    </div>
  </article>;
}

export default function HomePage() {
  const { status } = useStatus();
  const location = useLocation();
  const dashboardUnavailable = new URLSearchParams(location.search).get("error") === "dashboard_unavailable";

  return <div className="route-stage route-reveal home-route xiel-home">
    {dashboardUnavailable && <div className="notice error dashboard-config-notice" role="alert">
      The public site is online, but administrator sign-in is not configured yet. Set the dashboard MongoDB and Discord OAuth secrets, then restart xiel.
    </div>}
    <section className="xiel-hero" aria-labelledby="xiel-hero-title">
      <SaturnScrollScene>
        <div className="xiel-hero__layout">
          <div className="xiel-hero__copy">
            <p className="eyebrow xiel-hero__meta">Discord infrastructure / xiel</p>
            <h1
              id="xiel-hero-title"
              className="xiel-hero__title"
              data-route-heading
              tabIndex="-1"
            >
              Shape chaos<br />into <span className="xiel-hero__accent">clarity.</span>
            </h1>
            <p className="xiel-hero__lede">xiel unifies moderation, AntiNuke, economy, automation, and community tools in one exacting command system.</p>
            <div className="hero-actions xiel-hero__actions">
              <a className="button" href="/api/invite">
                Add to server <ArrowRight size={17} aria-hidden="true" />
              </a>
              <Link className="button secondary" to="/commands">
                <Command size={17} aria-hidden="true" />Browse commands
              </Link>
            </div>
            <p className="hero-note xiel-hero__note">
              <Radio size={14} aria-hidden="true" />
              Live telemetry · permission-aware controls · no simulated data
            </p>
          </div>
        </div>

        <dl
          className="stat-strip telemetry-ribbon xiel-telemetry"
          aria-label="Live bot statistics"
        >
          <TelemetryItem label="Servers" value={status ? formatNumber(status.guilds) : "—"} />
          <TelemetryItem label="Users reached" value={status ? formatNumber(status.users) : "—"} />
          <TelemetryItem label="Gateway latency" value={status?.latency != null ? `${status.latency}ms` : "—"} />
          <TelemetryItem label="Commands run" value={status ? formatNumber(status.commandsRun) : "—"} />
        </dl>
      </SaturnScrollScene>
    </section>

    <section className="section system-deck" aria-labelledby="system-deck-title">
      <header className="section-heading section-intro system-deck__intro">
        <div>
          <p className="eyebrow">System index / 01—06</p>
          <h2 id="system-deck-title">One core.<br />Every system.</h2>
        </div>
        <p>The dashboard exposes the same settings and records the bot consumes at runtime. Changes are permission-checked, validated, persisted, and reflected without a duplicate configuration layer.</p>
      </header>
      <div className="system-deck__slides">
        {SYSTEM_SLIDES.map((slide) => <SystemSlide key={slide.number} slide={slide} />)}
      </div>
    </section>

    <section className="section xiel-closing-cta" aria-labelledby="xiel-closing-title">
      <div className="xiel-closing-cta__signal" aria-hidden="true"><i /></div>
      <div className="xiel-closing-cta__copy">
        <p className="eyebrow">Ready for a cleaner orbit?</p>
        <h2 id="xiel-closing-title">Put every server system within reach.</h2>
        <p>Start with the complete command surface, then connect xiel to move from browsing to operating.</p>
      </div>
      <div className="xiel-closing-cta__actions">
        <a className="button" href="/api/invite">
          Add xiel to Discord <ArrowRight size={17} aria-hidden="true" />
        </a>
        <Link className="button secondary" to="/docs">
          <BookOpenText size={17} aria-hidden="true" />Read the docs
        </Link>
      </div>
    </section>
  </div>;
}
