import { Menu, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { RouteErrorBoundary } from "@/components/RouteErrorBoundary";
import { useHealth } from "@/hooks/queries";
import { cn } from "@/lib/utils";

const ROUTES = [
  { to: "/", label: "Overview", end: true },
  { to: "/circulars", label: "Circulars" },
  { to: "/search", label: "Search" },
  { to: "/assessments", label: "Assessments" },
  { to: "/point-in-time", label: "Point in time" },
  { to: "/evaluation", label: "Evaluation" },
];

/**
 * Database and assessment-provider readiness, stated in words. Trouble is
 * marked by weight and an icon, not by colour, which stays inside plates.
 */
export function SystemStatus({ className }: { className?: string }) {
  const health = useHealth();
  let text: string;
  let trouble = false;
  if (health.isPending) {
    text = "Checking the API";
  } else if (health.isError) {
    text = "API not reachable";
    trouble = true;
  } else if (health.data.database === "down") {
    text = "Database unavailable";
    trouble = true;
  } else if (!health.data.provider.ready) {
    text = "Assessments unavailable: provider not configured";
    trouble = true;
  } else {
    text = health.data.provider.deterministic
      ? "Database up · rule-based judge (demo)"
      : `Database up · ${health.data.provider.name} ready`;
  }
  return (
    <p
      className={cn(
        "inline-flex items-center gap-1.5 text-xs",
        trouble ? "font-semibold text-[#FFFDF6]" : "text-[#C9C3B4]",
        className,
      )}
      title={health.data?.provider.reason ?? undefined}
    >
      {trouble ? <TriangleAlert aria-hidden className="size-3.5 shrink-0" /> : null}
      {text}
    </p>
  );
}

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const location = useLocation();

  // Navigating closes the phone menu; focus returns to the button that opened it.
  useEffect(() => {
    setMenuOpen((open) => {
      if (open) menuButton.current?.focus();
      return false;
    });
  }, [location.pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only z-50 bg-raised px-3 py-2 font-semibold text-ink focus:not-sr-only focus:absolute focus:left-3 focus:top-3"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-40 bg-ink text-[#E9E5DA]">
        <div className="mx-auto flex h-14 max-w-[1680px] items-center gap-6 px-4 sm:px-6">
          <NavLink to="/" className="font-serif text-lg font-bold text-[#FFFDF6] no-underline">
            RegDelta
          </NavLink>
          <nav aria-label="Main" className="hidden h-full md:flex md:items-stretch md:gap-1">
            {ROUTES.map((route) => (
              <NavLink
                key={route.to}
                to={route.to}
                end={route.end}
                className={({ isActive }) =>
                  cn(
                    "flex items-center px-3 text-base font-medium no-underline transition-colors duration-150",
                    isActive
                      ? "text-[#FFFDF6] shadow-[inset_0_-3px_0_#FFFDF6]"
                      : "text-[#C9C3B4] hover:text-[#FFFDF6]",
                  )
                }
              >
                {route.label}
              </NavLink>
            ))}
          </nav>
          <SystemStatus className="ml-auto hidden text-right lg:inline-flex" />
          <button
            ref={menuButton}
            type="button"
            aria-expanded={menuOpen}
            aria-controls="phone-nav"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            onClick={() => setMenuOpen((open) => !open)}
            className="ml-auto inline-flex size-10 items-center justify-center rounded-control text-[#FFFDF6] md:hidden"
          >
            {menuOpen ? <X aria-hidden className="size-5" /> : <Menu aria-hidden className="size-5" />}
          </button>
        </div>
        {menuOpen ? (
          <nav id="phone-nav" aria-label="Main" className="border-t border-[#2c3445] px-4 pb-4 md:hidden">
            <ul className="flex flex-col">
              {ROUTES.map((route) => (
                <li key={route.to}>
                  <NavLink
                    to={route.to}
                    end={route.end}
                    className={({ isActive }) =>
                      cn(
                        "block py-3 text-md font-medium no-underline",
                        isActive ? "text-[#FFFDF6]" : "text-[#C9C3B4]",
                      )
                    }
                  >
                    {route.label}
                  </NavLink>
                </li>
              ))}
            </ul>
            <SystemStatus className="pt-2" />
          </nav>
        ) : null}
      </header>
      <main
        id="main"
        tabIndex={-1}
        className="mx-auto w-full max-w-[1680px] flex-1 px-4 py-6 outline-none sm:px-6 lg:py-8"
      >
        <RouteErrorBoundary key={location.pathname}>
          <Outlet />
        </RouteErrorBoundary>
      </main>
    </div>
  );
}
