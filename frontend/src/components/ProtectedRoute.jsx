import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

/** Redirects anonymous users to /login. With `permission`, shows a 403 panel for other roles.
 *  This is a convenience for the UI only: the backend enforces every permission itself. */
export default function ProtectedRoute({ children, permission = null }) {
  const { status, can } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <div className="p-10 text-center text-slate-400">Checking session…</div>;
  }
  if (status !== "authenticated") {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  if (permission && !can(permission)) {
    return (
      <div role="alert" className="m-10 rounded-xl border border-amber-500/30 bg-amber-500/10 p-6 text-amber-200">
        <h2 className="text-lg font-semibold">Access denied</h2>
        <p className="mt-1 text-sm">Your role does not include the “{permission}” permission.</p>
      </div>
    );
  }
  return children;
}
