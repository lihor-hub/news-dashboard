import { createFileRoute } from "@tanstack/react-router";
import { useApp } from "@/lib/store";
import { formatDate, relativeTime } from "@/lib/format";
import { Play, Pause, RefreshCw } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { toast } from "sonner";
import { FEED_RUNS } from "@/lib/mock-data";

export const Route = createFileRoute("/feeds/schedule")({
  component: SchedulePage,
});

function SchedulePage() {
  const { ingestIntervalMin, ingestPaused, nextRunAt, setInterval, setPaused, refreshNow } = useApp();
  const lastRun = FEED_RUNS[0];

  return (
    <div className="p-4 md:p-5 space-y-5 max-w-2xl">
      <Card>
        <Label>Ingest interval</Label>
        <div className="mt-1 flex items-baseline gap-2">
          <span className="text-2xl font-semibold tabular-nums">{ingestIntervalMin}</span>
          <span className="text-sm text-muted-foreground">minutes</span>
        </div>
        <Slider
          value={[ingestIntervalMin]}
          min={5}
          max={120}
          step={5}
          onValueChange={(v) => setInterval(v[0])}
          className="mt-3"
        />
      </Card>

      <div className="grid grid-cols-2 gap-3">
        <Card>
          <Label>Next run</Label>
          <div className="mt-1 text-sm font-medium">
            {ingestPaused ? "Paused" : relativeTime(nextRunAt)}
          </div>
          <div className="text-[11px] text-subtle mt-0.5">{!ingestPaused && formatDate(nextRunAt)}</div>
        </Card>
        <Card>
          <Label>Last run</Label>
          <div className="mt-1 text-sm font-medium">{relativeTime(lastRun.startedAt)}</div>
          <div className="text-[11px] text-subtle mt-0.5">{lastRun.itemsInserted} inserted / {lastRun.itemsFound} found</div>
        </Card>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => { refreshNow(); toast("Fetch started"); }}
          className="inline-flex items-center gap-1.5 rounded-md bg-foreground text-background px-3 py-2 text-sm font-medium"
        >
          <RefreshCw className="size-4" /> Fetch now
        </button>
        <button
          onClick={() => { setPaused(!ingestPaused); toast(ingestPaused ? "Resumed" : "Paused"); }}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-2 text-sm font-medium hover:bg-surface-2"
        >
          {ingestPaused ? <><Play className="size-4" /> Resume</> : <><Pause className="size-4" /> Pause</>}
        </button>
      </div>
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border border-border bg-card p-4">{children}</div>;
}
function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-[10px] uppercase tracking-wider text-subtle font-medium">{children}</div>;
}
