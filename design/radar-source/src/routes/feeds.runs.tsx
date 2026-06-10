import { createFileRoute } from "@tanstack/react-router";
import { FEED_RUNS } from "@/lib/mock-data";
import { formatDate } from "@/lib/format";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/feeds/runs")({
  component: RunsPage,
});

function RunsPage() {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div>
      {FEED_RUNS.map((r) => {
        const isOpen = open === r.id;
        return (
          <div key={r.id} className="border-b border-border">
            <button
              onClick={() => setOpen(isOpen ? null : r.id)}
              className="w-full text-left px-4 md:px-5 py-3 hover:bg-surface/60 transition-colors"
            >
              <div className="flex items-center gap-2">
                {isOpen ? <ChevronDown className="size-4 text-muted-foreground" /> : <ChevronRight className="size-4 text-muted-foreground" />}
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{formatDate(r.startedAt)}</div>
                  <div className="text-[11px] text-subtle mt-0.5">
                    {(r.durationMs / 1000).toFixed(1)}s · {r.itemsInserted} inserted / {r.itemsFound} found
                  </div>
                </div>
                <StatusPill status={r.status} />
              </div>
            </button>
            {isOpen && (
              <div className="px-4 md:px-5 pb-3 -mt-1">
                <div className="rounded-md border border-border bg-surface/60 overflow-hidden">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-[10px] uppercase tracking-wider text-subtle border-b border-border">
                        <th className="px-3 py-1.5 font-medium">Source</th>
                        <th className="px-3 py-1.5 font-medium text-right">Found</th>
                        <th className="px-3 py-1.5 font-medium text-right">Inserted</th>
                        <th className="px-3 py-1.5 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.perSource.map((s) => (
                        <tr key={s.sourceId} className="border-b border-border last:border-b-0">
                          <td className="px-3 py-1.5">{s.sourceName}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">{s.found}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">{s.inserted}</td>
                          <td className="px-3 py-1.5">
                            {s.status === "ok" ? <span className="text-ok">ok</span> : <span className="text-err">{s.error ?? "error"}</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function StatusPill({ status }: { status: "ok" | "partial" | "error" }) {
  return (
    <span
      className={cn(
        "text-[10px] font-medium uppercase tracking-wider px-1.5 py-0.5 rounded",
        status === "ok" && "bg-ok/15 text-ok",
        status === "partial" && "bg-warn/15 text-warn",
        status === "error" && "bg-err/15 text-err",
      )}
    >
      {status}
    </span>
  );
}
