import { createFileRoute, Link, useNavigate, useRouter } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, ChevronLeft as PrevIcon, Star, Check, Clock, X as XIcon, Archive, ExternalLink, AlertCircle, Loader2 } from "lucide-react";
import { useApp } from "@/lib/store";
import { relativeTime, formatDate, signalLabel } from "@/lib/format";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/a/$id")({
  component: ReaderPage,
});

function ReaderPage() {
  const { id } = Route.useParams();
  const router = useRouter();
  const navigate = useNavigate();
  const articles = useApp((s) => s.articles);
  const { toggleStar, setState, sendLater, restore } = useApp.getState();

  // ordered list = today queue order for swiping, but include all
  const ordered = useMemo(() =>
    [...articles].sort((a, b) => +new Date(b.publishedAt) - +new Date(a.publishedAt)),
    [articles]);
  const idx = ordered.findIndex((a) => a.id === id);
  const article = ordered[idx];

  const [loading, setLoading] = useState(true);
  useEffect(() => {
    setLoading(true);
    const t = setTimeout(() => setLoading(false), 350);
    return () => clearTimeout(t);
  }, [id]);

  // swipe horizontal between articles
  const [dx, setDx] = useState(0);
  const start = useState<{ x: number; y: number } | null>(null);
  const [startPt, setStartPt] = useState<{ x: number; y: number } | null>(null);
  void start;

  if (!article) {
    return (
      <div className="min-h-screen p-6">
        <div className="text-sm">Article not found.</div>
      </div>
    );
  }

  const goPrev = () => {
    const prev = ordered[idx - 1];
    if (prev) navigate({ to: "/a/$id", params: { id: prev.id }, replace: true });
  };
  const goNext = () => {
    const next = ordered[idx + 1];
    if (next) navigate({ to: "/a/$id", params: { id: next.id }, replace: true });
  };

  // keyboard
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || t?.isContentEditable) return;
      if (e.key === "r" || e.key === "d") doAction("done");
      else if (e.key === "l") doLater();
      else if (e.key === "s") doStar();
      else if (e.key === "x") doAction("skipped");
      else if (e.key === "e") doAction("archived");
      else if (e.key === "o") window.open(article.url, "_blank");
      else if (e.key === "ArrowLeft") goPrev();
      else if (e.key === "ArrowRight") goNext();
      else if (e.key === "Escape") router.history.back();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const doStar = () => {
    const snap = toggleStar(article.id);
    toast(article.starred ? "Unstarred" : "Starred", { action: { label: "Undo", onClick: () => restore(snap) } });
  };
  const doAction = (state: "done" | "skipped" | "archived") => {
    if (state === "skipped" && article.starred) {
      toast.error("Starred articles can't be skipped");
      return;
    }
    const snap = setState(article.id, state);
    if (snap) {
      const label = state === "done" ? "Done" : state === "skipped" ? "Skipped" : "Archived";
      toast(label, { action: { label: "Undo", onClick: () => restore(snap) } });
      const next = ordered[idx + 1];
      if (next) navigate({ to: "/a/$id", params: { id: next.id }, replace: true });
      else router.history.back();
    }
  };
  const doLater = () => {
    const snap = sendLater(article.id);
    if (snap) {
      toast("Snoozed to tomorrow", { action: { label: "Undo", onClick: () => restore(snap) } });
      const next = ordered[idx + 1];
      if (next) navigate({ to: "/a/$id", params: { id: next.id }, replace: true });
      else router.history.back();
    }
  };

  const signalColor =
    article.signal === "high" ? "text-signal-high" : article.signal === "mid" ? "text-signal-mid" : "text-signal-low";

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto max-w-2xl flex h-12 items-center justify-between px-3">
          <button
            onClick={() => router.history.back()}
            className="inline-flex items-center gap-1 px-2 py-1 -ml-1 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-surface"
          >
            <ChevronLeft className="size-4" /> Back
          </button>
          <div className="flex items-center gap-1">
            <button
              onClick={goPrev}
              disabled={idx <= 0}
              className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface disabled:opacity-30"
            >
              <PrevIcon className="size-4" />
            </button>
            <button
              onClick={goNext}
              disabled={idx >= ordered.length - 1}
              className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface disabled:opacity-30"
            >
              <ChevronRight className="size-4" />
            </button>
            <a
              href={article.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-surface"
              aria-label="Open original"
            >
              <ExternalLink className="size-4" />
            </a>
          </div>
        </div>
      </header>

      <div
        className="flex-1 pb-32 overflow-x-hidden"
        onTouchStart={(e) => setStartPt({ x: e.touches[0].clientX, y: e.touches[0].clientY })}
        onTouchMove={(e) => {
          if (!startPt) return;
          const d = e.touches[0].clientX - startPt.x;
          const dy = Math.abs(e.touches[0].clientY - startPt.y);
          if (dy < 40) setDx(d);
        }}
        onTouchEnd={() => {
          if (dx < -80) goNext();
          else if (dx > 80) goPrev();
          setDx(0); setStartPt(null);
        }}
      >
        <article className="mx-auto max-w-2xl px-5 pt-6" style={{ transform: `translateX(${dx * 0.3}px)` }}>
          <div className="text-[11px] text-subtle flex items-center gap-1.5 flex-wrap">
            <span className="font-medium text-muted-foreground">{article.sourceName}</span>
            <span>·</span>
            <span>{article.category}</span>
            <span>·</span>
            <span>{formatDate(article.publishedAt)}</span>
            <span>·</span>
            <span className={cn("font-medium", signalColor)}>{signalLabel(article.signal)}</span>
          </div>
          <h1 className="mt-3 text-[26px] md:text-[30px] font-semibold tracking-tight leading-tight">
            {article.title}
          </h1>
          <div className="mt-4 rounded-lg border-l-2 border-accent bg-surface/60 px-4 py-3">
            <div className="text-[10px] font-medium uppercase tracking-wider text-subtle mb-1">Why this matters</div>
            <p className="text-[14px] leading-snug text-foreground">{article.reason}</p>
          </div>

          <div className="mt-8">
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground py-12">
                <Loader2 className="size-4 animate-spin" /> Loading article…
              </div>
            ) : article.bodyStatus === "error" || !article.body ? (
              <div className="rounded-lg border border-border bg-surface px-4 py-5">
                <div className="flex items-start gap-2 text-warn mb-2">
                  <AlertCircle className="size-4 mt-0.5" />
                  <div className="text-sm font-medium text-foreground">Couldn't extract article text</div>
                </div>
                <p className="text-sm text-muted-foreground mb-4">
                  {article.summary}
                </p>
                <a
                  href={article.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md bg-foreground text-background px-3 py-1.5 text-sm font-medium hover:opacity-90"
                >
                  Open original <ExternalLink className="size-3.5" />
                </a>
              </div>
            ) : (
              <div className="reader-prose" dangerouslySetInnerHTML={{ __html: renderBody(article.body) }} />
            )}
          </div>
        </article>
      </div>

      <div className="fixed bottom-0 inset-x-0 z-20 border-t border-border bg-background/95 backdrop-blur pb-[env(safe-area-inset-bottom)]">
        <div className="mx-auto max-w-2xl grid grid-cols-5 gap-1 p-2">
          <ActionBtn onClick={doStar} icon={Star} label={article.starred ? "Unstar" : "Star"} active={article.starred} />
          <ActionBtn onClick={() => doAction("done")} icon={Check} label="Done" />
          <ActionBtn onClick={doLater} icon={Clock} label="Later" />
          <ActionBtn onClick={() => doAction("skipped")} icon={XIcon} label="Skip" disabled={article.starred} />
          <ActionBtn onClick={() => doAction("archived")} icon={Archive} label="Archive" />
        </div>
      </div>
    </div>
  );
}

function ActionBtn({ onClick, icon: Icon, label, active, disabled }: { onClick: () => void; icon: any; label: string; active?: boolean; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex flex-col items-center justify-center gap-0.5 py-2 rounded-md text-[11px] font-medium transition-colors",
        active ? "text-star" : "text-muted-foreground hover:text-foreground hover:bg-surface",
        disabled && "opacity-30 cursor-not-allowed hover:bg-transparent",
      )}
    >
      <Icon className={cn("size-5", active && "fill-current")} strokeWidth={1.75} />
      {label}
    </button>
  );
}

// minimal markdown -> html (no external deps)
function renderBody(md: string): string {
  const escape = (s: string) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]!));
  const lines = md.split("\n");
  let html = "";
  let inCode = false;
  let inList = false;
  let para: string[] = [];
  const flushPara = () => { if (para.length) { html += `<p>${inline(para.join(" "))}</p>`; para = []; } };
  const inline = (s: string) =>
    s
      .replace(/`([^`]+)`/g, (_, t) => `<code>${escape(t)}</code>`)
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  for (const raw of lines) {
    const l = raw;
    if (l.startsWith("```")) {
      if (inCode) { html += "</code></pre>"; inCode = false; }
      else { flushPara(); html += "<pre><code>"; inCode = true; }
      continue;
    }
    if (inCode) { html += escape(l) + "\n"; continue; }
    if (l.startsWith("## ")) { flushPara(); if (inList) { html += "</ul>"; inList = false; } html += `<h2>${inline(escape(l.slice(3)))}</h2>`; continue; }
    if (l.startsWith("- ")) { flushPara(); if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(escape(l.slice(2)))}</li>`; continue; }
    if (l.trim() === "") { flushPara(); if (inList) { html += "</ul>"; inList = false; } continue; }
    para.push(escape(l));
  }
  flushPara();
  if (inList) html += "</ul>";
  if (inCode) html += "</code></pre>";
  return html;
}

// suppress unused
void Link;
