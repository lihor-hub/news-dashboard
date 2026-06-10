import { createFileRoute } from "@tanstack/react-router";
import { useApp } from "@/lib/store";
import { useEffect, useRef, useState } from "react";
import { Play, Square } from "lucide-react";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/feeds/logs")({
  component: LogsPage,
});

interface Line {
  ts: string;
  level: "info" | "ok" | "warn" | "error";
  text: string;
}

const SAMPLE: Omit<Line, "ts">[] = [
  { level: "info", text: "Starting ingest run #1284" },
  { level: "info", text: "[Real Python] GET https://realpython.com/atom.xml" },
  { level: "ok", text: "[Real Python] 200 OK · 8 items · 3 inserted (124ms)" },
  { level: "info", text: "[PyCoder's Weekly] GET https://pycoders.com/issues/feed" },
  { level: "ok", text: "[PyCoder's Weekly] 200 OK · 12 items · 5 inserted (181ms)" },
  { level: "info", text: "[Simon Willison's Weblog] GET https://simonwillison.net/atom/everything/" },
  { level: "ok", text: "[Simon Willison's Weblog] 200 OK · 5 items · 2 inserted (98ms)" },
  { level: "info", text: "[Anthropic News] GET https://www.anthropic.com/news/rss.xml" },
  { level: "ok", text: "[Anthropic News] 200 OK · 2 items · 1 inserted (143ms)" },
  { level: "warn", text: "[OpenAI Blog] 304 Not Modified — skipping body parse" },
  { level: "info", text: "[Cloudflare Blog] GET https://blog.cloudflare.com/rss/" },
  { level: "ok", text: "[Cloudflare Blog] 200 OK · 4 items · 2 inserted (211ms)" },
  { level: "info", text: "[Hacker News Front Page] fetch top 30" },
  { level: "ok", text: "[Hacker News Front Page] · 30 items · 7 inserted (612ms)" },
  { level: "info", text: "[Cloudflare Workers Updates] GET https://developers.cloudflare.com/workers/changelog/" },
  { level: "error", text: "[Cloudflare Workers Updates] HTTP 503 from upstream (3 consecutive failures)" },
  { level: "info", text: "[GitHub Trending (Python)] scraping https://github.com/trending/python" },
  { level: "ok", text: "[GitHub Trending (Python)] 25 items · 6 inserted (498ms)" },
  { level: "ok", text: "Run #1284 complete — 38 inserted / 126 found · 18.4s" },
];

function LogsPage() {
  const ingestPaused = useApp((s) => s.ingestPaused);
  const [running, setRunning] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [errored, setErrored] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [lines]);

  const start = () => {
    setRunning(true);
    setErrored(false);
    setLines([]);
    let i = 0;
    const tick = () => {
      if (i >= SAMPLE.length) {
        setRunning(false);
        return;
      }
      const next = SAMPLE[i];
      setLines((l) => [...l, { ...next, ts: new Date().toISOString() }]);
      if (next.level === "error") setErrored(true);
      i++;
      setTimeout(tick, 280 + Math.random() * 320);
    };
    tick();
  };
  const stop = () => setRunning(false);

  return (
    <div className="p-4 md:p-5">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-sm font-medium">{running ? "Fetching…" : "Idle"}</div>
          <div className="text-[11px] text-subtle">{ingestPaused && "Scheduler is paused — manual runs only"}</div>
        </div>
        {running ? (
          <button onClick={stop} className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-sm">
            <Square className="size-3.5" /> Stop
          </button>
        ) : (
          <button onClick={start} className="inline-flex items-center gap-1.5 rounded-md bg-foreground text-background px-3 py-1.5 text-sm font-medium">
            <Play className="size-3.5" /> Run fetch
          </button>
        )}
      </div>

      <div
        ref={scrollRef}
        className={cn(
          "rounded-md border h-[60vh] overflow-y-auto p-3 bg-surface-2/60 term-log",
          errored && !running ? "border-err/40" : "border-border",
        )}
      >
        {lines.length === 0 && !running && (
          <div className="text-muted-foreground">No fetch running. Press Run fetch to start.</div>
        )}
        {lines.map((l, i) => (
          <div key={i} className="flex gap-2">
            <span className="text-subtle shrink-0">{new Date(l.ts).toLocaleTimeString()}</span>
            <span
              className={cn(
                "shrink-0 w-12 font-medium",
                l.level === "info" && "text-muted-foreground",
                l.level === "ok" && "text-ok",
                l.level === "warn" && "text-warn",
                l.level === "error" && "text-err",
              )}
            >
              {l.level.toUpperCase()}
            </span>
            <span className="text-foreground/90">{l.text}</span>
          </div>
        ))}
        {running && <div className="text-subtle animate-pulse">…</div>}
      </div>
    </div>
  );
}
