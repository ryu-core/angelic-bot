import { Navigate, Outlet, useLocation } from "react-router";
import { useAuth } from "../hooks/useAuth.jsx";
import { signInPath } from "../lib/api.js";
import ApiState from "./ApiState.jsx";

export default function RequireAuth({ roles }) {
  const { user, loading, error, refresh } = useAuth();
  const location = useLocation();
  const returnTo = `${location.pathname}${location.search}${location.hash}`;

  if (loading) {
    return <div className="page-shell">
      <ApiState loading loadingLabel="Checking your Discord session…" />
    </div>;
  }
  if (error) {
    return <div className="page-shell">
      <ApiState error={error} onRetry={() => refresh()} />
    </div>;
  }
  if (!user) return <Navigate to={signInPath(returnTo)} replace />;
  if (roles && !roles.includes(user.role)) {
    return <div className="page-shell">
      <ApiState error={{ status: 403, message: "Your Discord account does not have the role required for this page." }} />
    </div>;
  }
  return <Outlet />;
}
