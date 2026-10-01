import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

// `phase` marks modules that are not built yet. They are shown disabled, never as dead links.
const NAV = [
  { label: "Dashboard", to: "/" },
  { label: "Design Security", to: "/designs", anyOf: ["design:view", "design:verify"] },
  { label: "Quality Control", to: "/quality", anyOf: ["quality:inspect", "quality:view"] },
  { label: "Supply Chain", to: "/supply-chain", anyOf: ["provenance:verify", "part:authenticate"] },
  { label: "Manufacturing", to: "/manufacturing", anyOf: ["printer:control", "gcode:analyze", "incident:view"] },
  { label: "Compliance", phase: 9 },
  { label: "Audit Logs", phase: 9 },
];

export default function Layout() {
  const { user, logout, can } = useAuth();
  return (
    <div className="flex min-h-screen">
      <aside className="w-60 shrink-0 border-r border-slate-800 bg-slate-900 p-4">
        <div className="mb-6">
          <div className="text-lg font-bold text-white">SecurePrint AI</div>
          <div className="text-xs text-slate-500">3D/4D printing security · academic MVP</div>
        </div>
        <nav aria-label="Main" className="space-y-1">
          {NAV.map((item) =>
            item.to && (!item.anyOf || item.anyOf.some((name) => can(name))) ? (
              <NavLink
                key={item.label}
                to={item.to}
                end
                className={({ isActive }) =>
                  `block rounded-lg px-3 py-2 text-sm ${isActive ? "bg-sky-500/15 text-sky-300" : "text-slate-300 hover:bg-slate-800"}`
                }
              >
                {item.label}
              </NavLink>
            ) : (
              <div
                key={item.label}
                title={item.to ? "Not available for your role" : `Implemented in Phase ${item.phase}`}
                aria-disabled="true"
                className="flex cursor-not-allowed items-center justify-between rounded-lg px-3 py-2 text-sm text-slate-600"
              >
                <span>{item.label}</span>
                {item.phase ? (
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-500">Phase {item.phase}</span>
                ) : null}
              </div>
            ),
          )}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end gap-4 border-b border-slate-800 bg-slate-900/60 px-6 py-3">
          <div className="text-right text-sm">
            <div className="font-medium text-slate-100">{user?.username}</div>
            <div className="text-xs text-slate-400">{user?.role}</div>
          </div>
          <button
            type="button"
            onClick={logout}
            className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800"
          >
            Log out
          </button>
        </header>
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
