import { createFileRoute, Link, Outlet, useRouterState } from "@tanstack/react-router";
import { cn } from "@/lib/utils";

const tabs = [
  { to: "/feeds", label: "Sources", exact: true },
  { to: "/feeds/schedule", label: "Schedule" },
  { to: "/feeds/runs", label: "Runs" },
  { to: "/feeds/logs", label: "Logs" },
];

export const Route = createFileRoute("/feeds")({
  head: () => ({ meta: [{ title: "Feeds — Radar" }] }),
  component: FeedsLayout,
});

function FeedsLayout() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  return (
    <div>
      <div className="px-4 md:px-5 pt-4">
        <h2 className="text-[22px] font-semibold tracking-tight">Feeds</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Sources, schedule, and ingest history</p>
      </div>
      <div className="px-4 md:px-5 mt-3 border-b border-border overflow-x-auto no-scrollbar">
        <div className="flex gap-1">
          {tabs.map((t) => {
            const active = t.exact ? pathname === t.to : pathname === t.to;
            return (
              <Link
                key={t.to}
                to={t.to as any}
                className={cn(
                  "px-3 py-2 text-[13px] font-medium border-b-2 -mb-px whitespace-nowrap transition-colors",
                  active ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {t.label}
              </Link>
            );
          })}
        </div>
      </div>
      <div>
        <Outlet />
      </div>
    </div>
  );
}
