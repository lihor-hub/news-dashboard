import { createFileRoute } from "@tanstack/react-router";
import { useApp } from "@/lib/store";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CheckCircle2, AlertTriangle, AlertCircle } from "lucide-react";
import { Switch } from "@/components/ui/switch";

export const Route = createFileRoute("/feeds/")({
  component: SourcesPage,
});

function SourcesPage() {
  const sources = useApp((s) => s.sources);
  const toggle = useApp((s) => s.toggleSource);

  return (
    <div>
      {/* desktop table */}
      <div className="hidden md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wider text-subtle border-b border-border">
              <th className="px-5 py-2 font-medium">Source</th>
              <th className="px-3 py-2 font-medium">Kind</th>
              <th className="px-3 py-2 font-medium">Category</th>
              <th className="px-3 py-2 font-medium">Health</th>
              <th className="px-3 py-2 font-medium">Last checked</th>
              <th className="px-3 py-2 font-medium">Last success</th>
              <th className="px-3 py-2 font-medium text-right">Items (run)</th>
              <th className="px-3 py-2 font-medium text-right">On</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => (
              <tr key={s.id} className="border-b border-border hover:bg-surface/50">
                <td className="px-5 py-3">
                  <div className="font-medium">{s.name}</div>
                  {s.errorMessage && <div className="text-[11px] text-err mt-0.5">{s.errorMessage}</div>}
                </td>
                <td className="px-3 py-3 text-muted-foreground capitalize">{s.kind}</td>
                <td className="px-3 py-3 text-muted-foreground">{s.category}</td>
                <td className="px-3 py-3"><HealthBadge h={s.health} /></td>
                <td className="px-3 py-3 text-muted-foreground">{relativeTime(s.lastChecked)}</td>
                <td className="px-3 py-3 text-muted-foreground">{relativeTime(s.lastSuccess)}</td>
                <td className="px-3 py-3 text-right tabular-nums">{s.itemsInserted}/{s.itemsFetched}</td>
                <td className="px-3 py-3 text-right"><Switch checked={s.enabled} onCheckedChange={() => toggle(s.id)} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* mobile cards */}
      <div className="md:hidden">
        {sources.map((s) => (
          <div key={s.id} className="px-4 py-3 border-b border-border">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-medium truncate">{s.name}</div>
                <div className="text-[11px] text-subtle mt-0.5">{s.kind.toUpperCase()} · {s.category}</div>
              </div>
              <Switch checked={s.enabled} onCheckedChange={() => toggle(s.id)} />
            </div>
            <div className="mt-2 flex items-center justify-between text-[11px]">
              <HealthBadge h={s.health} />
              <span className="text-subtle">
                {relativeTime(s.lastChecked)} · {s.itemsInserted}/{s.itemsFetched}
              </span>
            </div>
            {s.errorMessage && <div className="mt-1 text-[11px] text-err">{s.errorMessage}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

function HealthBadge({ h }: { h: "ok" | "stale" | "error" }) {
  const cfg = {
    ok: { Icon: CheckCircle2, label: "ok", cls: "text-ok" },
    stale: { Icon: AlertTriangle, label: "stale", cls: "text-warn" },
    error: { Icon: AlertCircle, label: "error", cls: "text-err" },
  }[h];
  const Icon = cfg.Icon;
  return (
    <span className={cn("inline-flex items-center gap-1 text-[11px] font-medium", cfg.cls)}>
      <Icon className="size-3.5" /> {cfg.label}
    </span>
  );
}
