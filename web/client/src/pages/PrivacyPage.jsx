import PublicLegalPage from "../components/PublicLegalPage.jsx";

const sections = [
  {
    id: "scope",
    title: "Scope of this notice",
    body: "This notice covers the xiel Discord bot and web dashboard. It explains the information processed when a member runs a command, an administrator configures a server, or a user signs in with Discord.",
  },
  {
    id: "information-we-process",
    title: "Information xiel processes",
    body: "xiel processes Discord user, server, channel, and role identifiers; command usage; administrator-provided configuration and message content; server-scoped economy records; access grants; and the OAuth session data required to operate the dashboard. Network request information is also processed for rate limiting and failure diagnosis.",
  },
  {
    id: "sources",
    title: "Where information comes from",
    body: "Information comes from commands and configuration submitted to xiel, from activity the bot is permitted to observe in a server, and from Discord during OAuth sign-in and API requests. The dashboard requests only the Discord identity and server-list access needed to identify the user and determine which servers they may manage.",
  },
  {
    id: "why-it-is-used",
    title: "How information is used",
    body: "Information is used to deliver requested bot features, persist server configuration, enforce permissions and access controls, display current server and economy state, protect the service from abuse, and investigate operational failures. xiel does not sell personal data.",
  },
  {
    id: "discord-and-oauth",
    title: "Discord sign-in and sessions",
    body: "Dashboard sign-in is handled through Discord OAuth. OAuth credentials and bot tokens remain on the server; the browser receives a signed, HTTP-only session cookie. The server-side session can contain the signed-in user's Discord profile, manageable server list, and OAuth access token.",
  },
  {
    id: "retention-and-control",
    title: "Retention and control",
    body: "Web sessions expire after seven days, and signing out removes the active session. Server configuration, economy records, and feature data can remain while the service is in use. Where a dashboard control is available, an authorized administrator can update or delete the corresponding server data.",
  },
  {
    id: "sharing",
    title: "When information is shared",
    body: "xiel exchanges information with Discord when needed for authentication, permission checks, bot actions, and current server state. Information may also be processed by the infrastructure used to run the bot, dashboard, and database. It is not made public by xiel unless a requested feature is designed to post a result in Discord.",
  },
  {
    id: "security",
    title: "Security safeguards",
    body: "Write operations are permission-checked and validated by the server. Sessions use signed, HTTP-only cookies, sensitive credentials are kept out of browser code, and dashboard responses apply restrictive security headers. No online service can guarantee absolute security, so server administrators should grant privileged access carefully.",
  },
  {
    id: "changes",
    title: "Changes to this notice",
    body: "This notice may be updated when xiel's features, data flows, or operational requirements change. The date shown at the top identifies the current version.",
  },
];

export default function PrivacyPage() {
  return <PublicLegalPage
    title="Privacy"
    description="How xiel handles dashboard and bot data. Last updated 30 July 2026."
    sections={sections}
  />;
}
