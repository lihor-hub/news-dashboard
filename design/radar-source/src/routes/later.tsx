import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useApp } from "@/lib/store";
import { ArticleRow } from "@/components/article/ArticleRow";
import { useArticleListNav } from "@/hooks/use-article-list-nav";
import { EmptyState } from "@/components/EmptyState";
import { Clock } from "lucide-react";

export const Route = createFileRoute("/later")({
  head: () => ({ meta: [{ title: "Later — Radar" }] }),
  component: LaterPage,
});

function LaterPage() {
  const articles = useApp((s) => s.articles);
  const navigate = useNavigate();
  const list = articles
    .filter((a) => a.state === "later")
    .sort((a, b) => +new Date(a.later_until ?? 0) - +new Date(b.later_until ?? 0));
  const { focused } = useArticleListNav(list, (a) => navigate({ to: "/a/$id", params: { id: a.id } }));

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3">
        <h2 className="text-[22px] font-semibold tracking-tight">Later</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          {list.length} snoozed · returns to Today automatically
        </p>
      </div>
      {list.length === 0 ? (
        <EmptyState icon={Clock} title="Nothing snoozed" subtitle="Articles you send to Later will appear here with their return date." />
      ) : (
        list.map((a, i) => <ArticleRow key={a.id} article={a} focused={i === focused} showLaterUntil />)
      )}
    </div>
  );
}
