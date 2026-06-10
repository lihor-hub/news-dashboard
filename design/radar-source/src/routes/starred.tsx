import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useApp } from "@/lib/store";
import { ArticleRow } from "@/components/article/ArticleRow";
import { useArticleListNav } from "@/hooks/use-article-list-nav";
import { EmptyState } from "@/components/EmptyState";
import { Star } from "lucide-react";

export const Route = createFileRoute("/starred")({
  head: () => ({ meta: [{ title: "Starred — Radar" }] }),
  component: StarredPage,
});

function StarredPage() {
  const articles = useApp((s) => s.articles);
  const navigate = useNavigate();
  const list = articles
    .filter((a) => a.starred)
    .sort((a, b) => +new Date(b.starred_at ?? b.publishedAt) - +new Date(a.starred_at ?? a.publishedAt));
  const { focused } = useArticleListNav(list, (a) => navigate({ to: "/a/$id", params: { id: a.id } }));

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3">
        <h2 className="text-[22px] font-semibold tracking-tight">Starred</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          {list.length} reference articles · always available to Ask AI
        </p>
      </div>
      {list.length === 0 ? (
        <EmptyState icon={Star} title="No stars yet" subtitle="Star articles you want to keep as reference material." />
      ) : (
        list.map((a, i) => <ArticleRow key={a.id} article={a} focused={i === focused} />)
      )}
    </div>
  );
}
