import { NavLink, Outlet } from "react-router-dom";

import { ConnectionBadge } from "@/components/ConnectionBadge";
import { cn } from "@/lib/utils";

// The six screens from the brief. This is an internal analyst tool, not a chat
// app: navigation is a fixed left rail, dense and identifier-forward.
interface NavItem {
  to: string;
  label: string;
  end?: boolean;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/circulars", label: "Circulars" },
  { to: "/assessments", label: "Impact Assessment" },
  { to: "/point-in-time", label: "Point-in-Time" },
  { to: "/evaluation", label: "Evaluation" },
  { to: "/search", label: "Search" },
];

export function AppShell() {
  return (
    <div className="grid min-h-screen grid-cols-[220px_1fr]">
      <aside className="flex flex-col border-r border-border bg-card">
        <div className="px-5 py-4">
          <div className="font-mono text-sm font-semibold tracking-tight">RegDelta</div>
          <div className="text-xs text-muted-foreground">SEBI change-impact engine</div>
        </div>
        <nav className="flex flex-col gap-0.5 px-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-accent font-medium text-accent-foreground"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-4 py-4">
          <ConnectionBadge />
        </div>
      </aside>

      <main className="min-w-0 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
