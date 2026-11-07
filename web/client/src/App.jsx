import { lazy, Suspense, useEffect, useRef } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";
import Layout from "./components/Layout.jsx";
import RequireAuth from "./components/RequireAuth.jsx";
import { useCapabilities } from "./hooks/useCapabilities.js";
import HomePage from "./pages/HomePage.jsx";

const CommandsPage = lazy(() => import("./pages/CommandsPage.jsx"));
const CoOwnerPage = lazy(() => import("./pages/CoOwnerPage.jsx"));
const DashboardPage = lazy(() => import("./pages/DashboardPage.jsx"));
const DocsPage = lazy(() => import("./pages/DocsPage.jsx"));
const EconomyPage = lazy(() => import("./pages/EconomyPage.jsx"));
const InvitesPage = lazy(() => import("./pages/InvitesPage.jsx"));
const OwnerPage = lazy(() => import("./pages/OwnerPage.jsx"));
const PrivacyPage = lazy(() => import("./pages/PrivacyPage.jsx"));
const SettingsPage = lazy(() => import("./pages/SettingsPage.jsx"));
const StatusPage = lazy(() => import("./pages/StatusPage.jsx"));
const TermsPage = lazy(() => import("./pages/TermsPage.jsx"));

const ROUTE_TITLES = {
  "/": "Discord infrastructure",
  "/commands": "Commands",
  "/docs": "Documentation",
  "/invites": "Invite control",
  "/status": "System status",
  "/privacy": "Privacy",
  "/terms": "Terms of service",
  "/dashboard": "Managed servers",
  "/owner": "Owner console",
  "/coowner": "Co-owner console",
};

function titleForPath(pathname) {
  const normalized = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  if (normalized.startsWith("/settings/")) return "Server settings";
  if (normalized.startsWith("/economy/")) return "Economy operations";
  return ROUTE_TITLES[normalized] || "Discord infrastructure";
}

function RouteEffects() {
  const location = useLocation();
  const { reducedMotion } = useCapabilities();
  const reducedMotionRef = useRef(reducedMotion);

  useEffect(() => {
    reducedMotionRef.current = reducedMotion;
  }, [reducedMotion]);

  useEffect(() => {
    document.title = `${titleForPath(location.pathname)} · xiel`;
    window.scrollTo({ top: 0, left: 0, behavior: reducedMotionRef.current ? "auto" : "smooth" });
    let observer;
    let fallbackTimer;

    const focusHeading = () => {
      const main = document.getElementById("main-content");
      if (!main) return false;
      const heading = main.querySelector("[data-route-heading]");
      if (!heading) return false;
      try {
        heading.focus({ preventScroll: true });
      } catch {
        heading.focus();
      }
      return true;
    };

    const frame = window.requestAnimationFrame(() => {
      const main = document.getElementById("main-content");
      if (!main) return;
      if (focusHeading()) return;
      observer = new MutationObserver(() => {
        if (focusHeading()) observer?.disconnect();
      });
      observer.observe(main, { childList: true, subtree: true });
      fallbackTimer = window.setTimeout(() => {
        observer?.disconnect();
        if (!focusHeading()) main.focus({ preventScroll: true });
      }, 1_000);
    });
    return () => {
      window.cancelAnimationFrame(frame);
      window.clearTimeout(fallbackTimer);
      observer?.disconnect();
    };
  }, [location.key, location.pathname]);

  return null;
}

export default function App() {
  return <Layout>
    <RouteEffects />
    <Suspense fallback={<div className="page-shell"><div className="api-state" role="status">Loading interface…</div></div>}>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/commands" element={<CommandsPage />} />
        <Route path="/docs" element={<DocsPage />} />
        <Route path="/invites" element={<InvitesPage />} />
        <Route path="/status" element={<StatusPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/settings/:guildId" element={<SettingsPage />} />
          <Route path="/economy/:guildId" element={<EconomyPage />} />
        </Route>
        <Route element={<RequireAuth roles={["owner"]} />}>
          <Route path="/owner" element={<OwnerPage />} />
        </Route>
        <Route element={<RequireAuth roles={["owner", "coowner"]} />}>
          <Route path="/coowner" element={<CoOwnerPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  </Layout>;
}
