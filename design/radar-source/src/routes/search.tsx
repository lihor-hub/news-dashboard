import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useApp } from "@/lib/store";
import { Search as SearchIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { CATEGORIES, STATE_LABELS, type WorkflowState, type Category } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ArticleRow } from "@/components/article/ArticleRow";
import { useArticleListNav } from "@/hooks/use-article-list-nav";

export const Route = createFileRoute("/search")({
  validateSearch: (s: Record<string, unknown>) => ({
    q: typeof s.q === "string" ? s.q : "",
  }),
  head: () => ({ meta: [{ title: "Search — Radar" }] }),
  component: SearchPage,
});

function SearchPage() {
  const { q: initQ } = Route.useSearch();
  const navigate = useNavigate();
  const articles = useApp((s) => s.articles);
  const sources = useApp((s) => s.sources);

  const [q, setQ] = useState(initQ ?? "");
  const [states, setStates] = useState<WorkflowState[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [srcs, setSrcs] = useState<string[]>([]);
  const [starredOnly, setStarredOnly] = useState(false);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [range, setRange] = useState<"all" | "today" | "week" | "month">("all");

  const results = useMemo(() => {
    const lq = q.trim().toLowerCase();
    return articles.filter((a) => {
      if (!includeArchived && a.state === "archived") return false;
      if (states.length && !states.includes(a.state)) return false;
      if (cats.length && !cats.includes(a.category)) return false;
      if (srcs.length && !srcs.includes(a.sourceId)) return false;
      if (starredOnly && !a.starred) return false;
      if (range !== "all") {
        const age = Date.now() - +new Date(a.publishedAt);
        const limit = range === "today" ? 86400e3 : range === "week" ? 7 * 86400e3 : 30 * 86400e3;
        if (age > limit) return false;
      }
      if (!lq) return true;
      return (
        a.title.toLowerCase().includes(lq) ||
        a.summary.toLowerCase().includes(lq) ||
        a.reason.toLowerCase().includes(lq) ||
        a.tags.some((t) => t.toLowerCase().includes(lq)) ||
        a.sourceName.toLowerCase().includes(lq) ||
        (a.body?.toLowerCase().includes(lq) ?? false)
      );
    });
  }, [articles, q, states, cats, srcs, starredOnly, includeArchived, range]);

  const { focused } = useArticleListNav(results, (a) => navigate({ to: "/a/$id", params: { id: a.id } }));

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-2">
        <h2 className="text-[22px] font-semibold tracking-tight mb-3">Search</h2>
        <div className="relative">
          <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <input
            autoFocus
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              navigate({ to: "/search", search: { q: e.target.value }, replace: true });
            }}
            placeholder="Search titles, summaries, tags, full text…"
            className="w-full h-10 pl-9 pr-3 rounded-md border border-border bg-surface text-sm outline-none focus:border-border-strong focus:bg-background"
          />
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          <Chip active={starredOnly} onClick={() => setStarredOnly((v) => !v)}>Starred</Chip>
          <Chip active={includeArchived} onClick={() => setIncludeArchived((v) => !v)}>Include archived</Chip>
          <FilterGroup label="State" all={Object.keys(STATE_LABELS) as WorkflowState[]} selected={states} onChange={setStates} render={(s) => STATE_LABELS[s as WorkflowState]} />
          <FilterGroup label="Category" all={CATEGORIES} selected={cats} onChange={setCats} render={(c) => c} />
          <FilterGroup label="Source" all={sources.map((s) => s.id)} selected={srcs} onChange={setSrcs} render={(id) => sources.find((s) => s.id === id)?.name ?? id} />
          <FilterGroup
            label="Date"
            all={["all", "today", "week", "month"]}
            selected={[range]}
            onChange={(v) => setRange((v[0] as any) ?? "all")}
            render={(v) => v === "all" ? "Any time" : v === "today" ? "Today" : v === "week" ? "Past week" : "Past month"}
            single
          />
        </div>
      </div>
      <div className="px-4 md:px-5 py-2 text-[11px] text-subtle border-b border-border">
        {results.length} {results.length === 1 ? "result" : "results"}
      </div>
      {results.map((a, i) => <ArticleRow key={a.id} article={a} focused={i === focused} />)}
    </div>
  );
}

function Chip({ active, onClick, children }: { active?: boolean; onClick?: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "h-7 px-2.5 rounded-full border text-[11px] font-medium transition-colors",
        active
          ? "bg-foreground text-background border-foreground"
          : "bg-surface border-border text-muted-foreground hover:text-foreground hover:border-border-strong",
      )}
    >
      {children}
    </button>
  );
}

function FilterGroup<T extends string>({
  label, all, selected, onChange, render, single,
}: {
  label: string;
  all: T[];
  selected: T[];
  onChange: (next: T[]) => void;
  render: (v: T) => string;
  single?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "h-7 px-2.5 rounded-full border text-[11px] font-medium transition-colors",
          selected.length && (!single || selected[0] !== "all")
            ? "bg-foreground text-background border-foreground"
            : "bg-surface border-border text-muted-foreground hover:text-foreground hover:border-border-strong",
        )}
      >
        {label}{selected.length > 0 && !single ? ` · ${selected.length}` : single && selected[0] && selected[0] !== "all" ? ` · ${render(selected[0])}` : ""}
      </button>
      {open && (
        <div className="absolute z-20 mt-1 min-w-[180px] max-h-72 overflow-y-auto rounded-md border border-border bg-popover shadow-md p-1">
          {all.map((v) => {
            const on = selected.includes(v);
            return (
              <button
                key={v}
                onClick={() => {
                  if (single) onChange([v]);
                  else onChange(on ? selected.filter((x) => x !== v) : [...selected, v]);
                }}
                className={cn("flex w-full items-center justify-between gap-2 px-2.5 py-1.5 rounded text-xs hover:bg-surface", on && "font-medium text-foreground")}
              >
                <span className="truncate text-left">{render(v)}</span>
                {on && <span className="text-accent">✓</span>}
              </button>
            );
          })}
          <div className="border-t border-border mt-1 pt-1 flex justify-end gap-1">
            <button onClick={() => onChange([])} className="px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground">Clear</button>
            <button onClick={() => setOpen(false)} className="px-2 py-1 text-[11px] text-foreground">Done</button>
          </div>
        </div>
      )}
    </div>
  );
}
