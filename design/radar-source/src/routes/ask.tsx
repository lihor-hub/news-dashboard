import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useApp } from "@/lib/store";
import { Sparkles, Loader2, FileText } from "lucide-react";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/ask")({
  head: () => ({ meta: [{ title: "Ask AI — Radar" }] }),
  component: AskPage,
});

function AskPage() {
  const articles = useApp((s) => s.articles);
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<{ text: string; citations: typeof articles } | null>(null);
  const [includeAll, setIncludeAll] = useState(false);

  const pool = articles.filter((a) =>
    includeAll ? a.state !== "archived" : a.starred || a.state === "done",
  );

  const ask = (e: React.FormEvent) => {
    e.preventDefault();
    if (!q.trim()) return;
    if (pool.length < 3) {
      setAnswer({ text: "", citations: [] });
      return;
    }
    setLoading(true);
    setTimeout(() => {
      const lq = q.toLowerCase();
      const matches = pool
        .map((a) => ({
          a,
          score:
            (a.title.toLowerCase().includes(lq) ? 3 : 0) +
            (a.reason.toLowerCase().includes(lq) ? 2 : 0) +
            (a.tags.some((t) => lq.includes(t.toLowerCase())) ? 2 : 0) +
            (a.summary.toLowerCase().includes(lq) ? 1 : 0),
        }))
        .filter((x) => x.score > 0)
        .sort((x, y) => y.score - x.score)
        .slice(0, 4)
        .map((x) => x.a);

      if (matches.length === 0) {
        const recent = pool.slice(0, 3);
        setAnswer({
          text: `I don't have any saved articles that directly address "${q}". Based on your recent reading, the most related material is ${recent.map((r) => `"${r.title}"`).join(", ")} — but none of these directly answer the question.`,
          citations: recent,
        });
      } else {
        const themes = matches.flatMap((m) => m.tags).slice(0, 5);
        const text = `Based on ${matches.length} ${matches.length === 1 ? "article" : "articles"} you've saved or finished, the common thread around "${q}" centers on ${themes.join(", ") || "the topic"}. Key takeaways: ${matches
          .map((m, i) => `(${i + 1}) ${m.reason}`)
          .join(" ")}`;
        setAnswer({ text, citations: matches });
      }
      setLoading(false);
    }, 700);
  };

  return (
    <div className="px-4 md:px-5 pt-4 pb-12 max-w-2xl mx-auto">
      <div className="flex items-center gap-2 mb-1">
        <Sparkles className="size-5 text-accent" />
        <h2 className="text-[22px] font-semibold tracking-tight">Ask AI</h2>
      </div>
      <p className="text-xs text-muted-foreground mb-4">
        Answers over your Starred and Done articles. Today, Skipped, and Archived are excluded by default.
      </p>

      <form onSubmit={ask} className="space-y-2">
        <textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="What did I read about Postgres LISTEN/NOTIFY?"
          rows={3}
          className="w-full p-3 rounded-md border border-border bg-surface text-sm outline-none focus:border-border-strong focus:bg-background resize-none"
        />
        <div className="flex items-center justify-between gap-2">
          <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <input type="checkbox" checked={includeAll} onChange={(e) => setIncludeAll(e.target.checked)} className="accent-accent" />
            Include all non-archived articles
          </label>
          <button
            type="submit"
            disabled={loading || !q.trim()}
            className="inline-flex items-center gap-1.5 rounded-md bg-foreground text-background px-3 py-1.5 text-sm font-medium disabled:opacity-50"
          >
            {loading && <Loader2 className="size-3.5 animate-spin" />}
            Ask
          </button>
        </div>
      </form>

      {pool.length < 3 && (
        <div className="mt-6 rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground">
          Save or finish more articles to ask questions. You currently have <span className="font-medium text-foreground">{pool.length}</span> in the answer pool.
        </div>
      )}

      {answer && (
        <div className="mt-6 space-y-4">
          {answer.text && (
            <div className="reader-prose text-[15px]">{answer.text}</div>
          )}
          {answer.citations.length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-subtle font-medium mb-2">Citations</div>
              <div className="space-y-2">
                {answer.citations.map((c, i) => (
                  <button
                    key={c.id}
                    onClick={() => navigate({ to: "/a/$id", params: { id: c.id } })}
                    className={cn(
                      "w-full text-left rounded-md border border-border bg-card p-3 hover:bg-surface transition-colors",
                    )}
                  >
                    <div className="flex items-baseline justify-between gap-2 mb-0.5">
                      <span className="text-[10px] text-subtle">[{i + 1}]</span>
                      <span className="text-[10px] text-subtle">{relativeTime(c.publishedAt)}</span>
                    </div>
                    <div className="text-sm font-medium leading-snug">{c.title}</div>
                    <div className="text-[11px] text-muted-foreground mt-0.5">{c.sourceName} · {c.category}</div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      {/* keep imports used */}
      <Link to="/starred" className="hidden"><FileText /></Link>
    </div>
  );
}
