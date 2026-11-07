import { useEffect, useRef, useState } from "react";
import {
  Activity,
  BookOpen,
  Bot,
  Boxes,
  Command,
  Gauge,
  LogIn,
  LogOut,
  Menu,
  Send,
  Settings,
  Shield,
  X,
} from "lucide-react";
import { Link, NavLink, useLocation } from "react-router";
import { useAuth } from "../hooks/useAuth.jsx";
import { useCapabilities } from "../hooks/useCapabilities.js";
import { useStatus } from "../hooks/useStatus.jsx";

const PUBLIC_LINKS = [
  ["/", "Home", Boxes],
  ["/invites", "Invites", Send],
  ["/commands", "Commands", Command],
  ["/docs", "Docs", BookOpen],
  ["/status", "Status", Activity],
  ["/dashboard", "Dashboard", Gauge],
];

const OPERATIONAL_LINKS = [
  ["/dashboard", "Dashboard", Gauge],
  ["/invites", "Invites", Send],
  ["/commands", "Commands", Command],
  ["/docs", "Docs", BookOpen],
  ["/status", "Status", Activity],
];

const OPERATIONAL_PATHS = ["/dashboard", "/settings/", "/economy/", "/owner", "/coowner"];

function isOperationalPath(pathname) {
  const normalized = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  return OPERATIONAL_PATHS.some((path) => normalized === path || (path.endsWith("/") && normalized.startsWith(path)));
}

function SkipLink() {
  const [focused, setFocused] = useState(false);
  return <a
    href="#main-content"
    onFocus={() => setFocused(true)}
    onBlur={() => setFocused(false)}
    style={{
      position: "fixed",
      zIndex: 1000,
      left: 12,
      top: 12,
      padding: "10px 14px",
      borderRadius: 0,
      background: "#e1bc91",
      color: "#120d08",
      fontWeight: 800,
      transform: focused ? "translateY(0)" : "translateY(-160%)",
    }}
  >
    Skip to main content
  </a>;
}

function NavigationLinks({ links, user, onNavigate }) {
  return <>
    {links.map(([href, label, Icon]) => <NavLink
      key={href}
      to={href}
      end={href === "/"}
      onClick={onNavigate}
    >
      <Icon size={16} aria-hidden="true" />{label}
    </NavLink>)}
    {user?.role === "owner" && <NavLink to="/owner" onClick={onNavigate}>
      <Shield size={16} aria-hidden="true" />Owner
    </NavLink>}
    {(user?.role === "owner" || user?.role === "coowner") && <NavLink to="/coowner" onClick={onNavigate}>
      <Settings size={16} aria-hidden="true" />Co-owner
    </NavLink>}
  </>;
}

function MobileNavigation({ open, setOpen, triggerRef, links, user, operational }) {
  const dialogRef = useRef(null);
  const closeButtonRef = useRef(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
      window.requestAnimationFrame(() => closeButtonRef.current?.focus());
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
  }, [open]);

  const restoreFocus = () => {
    setOpen(false);
    window.requestAnimationFrame(() => triggerRef.current?.focus());
  };

  return <>
    {/* Native Escape handling and the close button cover keyboard use; this handler only detects backdrop clicks. */}
    {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
    <dialog
    ref={dialogRef}
    className={`nav${operational ? " auth-rail" : ""}${open ? " open" : ""}`}
    aria-label="Primary navigation"
    onCancel={(event) => {
      event.preventDefault();
      restoreFocus();
    }}
    onKeyDown={(event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      restoreFocus();
    }}
    onClose={restoreFocus}
    onClick={(event) => {
      if (event.target === event.currentTarget) restoreFocus();
    }}
    style={{
      margin: 0,
      width: "100%",
      maxWidth: "none",
      color: "inherit",
      borderTop: 0,
      borderLeft: 0,
      borderRight: 0,
    }}
  >
    <button
      ref={closeButtonRef}
      type="button"
      className="icon-button"
      aria-label="Close navigation"
      onClick={restoreFocus}
    >
      <X size={18} aria-hidden="true" />
    </button>
    <NavigationLinks links={links} user={user} onNavigate={restoreFocus} />
    </dialog>
  </>;
}

export default function Layout({ children }) {
  const [navigationOpen, setNavigationOpen] = useState(false);
  const menuButtonRef = useRef(null);
  const location = useLocation();
  const { compactNavigation } = useCapabilities();
  const { user, loading, login, logout } = useAuth();
  const { connectionState } = useStatus();
  const operational = isOperationalPath(location.pathname);
  const links = operational ? OPERATIONAL_LINKS : PUBLIC_LINKS;
  const brandTarget = operational ? "/dashboard" : "/";

  useEffect(() => {
    setNavigationOpen(false);
  }, [compactNavigation, location.pathname]);

  const statusLabel = {
    checking: "Checking",
    online: "Online",
    offline: "Offline",
    reconnecting: "Reconnecting",
  }[connectionState] || "Checking";

  return <div className={`app-frame ${operational ? "authenticated-shell" : "public-shell"}`}>
    <SkipLink />
    <header className={`topbar ${operational ? "auth-topbar" : "public-topbar"}`}>
      <Link to={brandTarget} className="brand" aria-label={`xiel ${operational ? "dashboard" : "home"}`}>
        <span className="brand-mark" aria-hidden="true">XI</span><span>xiel</span>
      </Link>
      <button
        ref={menuButtonRef}
        type="button"
        className="menu-button"
        onClick={() => setNavigationOpen(true)}
        aria-label="Open navigation"
        aria-haspopup="dialog"
        aria-expanded={navigationOpen}
      >
        <Menu aria-hidden="true" />
      </button>
      {compactNavigation
        ? <MobileNavigation
          open={navigationOpen}
          setOpen={setNavigationOpen}
          triggerRef={menuButtonRef}
          links={links}
          user={user}
          operational={operational}
        />
        : <nav className={`nav${operational ? " auth-rail" : ""}`} aria-label="Primary navigation">
          <NavigationLinks links={links} user={user} />
        </nav>}
      <div className="topbar-actions">
        <span
          className={`live-pill ${connectionState}`}
          role="status"
          aria-live="polite"
        >
          <i aria-hidden="true" />{statusLabel}
        </span>
        {user
          ? <button type="button" className="account-button" onClick={logout}>
            {user.avatar ? <img src={user.avatar} alt="" /> : <Bot aria-hidden="true" />}
            <span>{user.username}</span><LogOut size={15} aria-hidden="true" />
          </button>
          : <button
            type="button"
            className="button compact"
            onClick={() => login(operational
              ? `${location.pathname}${location.search}${location.hash}`
              : "/dashboard")}
            disabled={loading}
          >
            <LogIn size={16} aria-hidden="true" />{loading ? "Checking…" : "Sign in"}
          </button>}
      </div>
    </header>
    <main
      id="main-content"
      className={`content-frame ${operational ? "authenticated-content" : "public-content"}`}
      tabIndex="-1"
    >
      {children}
    </main>
    {!operational && <footer>
      <div className="brand"><span className="brand-mark" aria-hidden="true">XI</span><span>xiel</span></div>
      <p>Precision tools for ambitious Discord communities.</p>
      <div><Link to="/privacy">Privacy</Link><Link to="/terms">Terms</Link></div>
    </footer>}
  </div>;
}
