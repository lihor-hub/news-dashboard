import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useApp } from "@/lib/store";
import { ArticleRow } from "@/components/article/ArticleRow";
import { useArticleListNav } from "@/hooks/use-article-list-nav";
import { EmptyState } from "@/components/EmptyState";
import { Archive as ArchiveIcon } from "lucide-react";

export const Route = createFileRoute("/archive")({
  head: () => ({ meta: [{ title: "Archive — Radar" }] }),
  component: ArchivePage,
});

function ArchivePage() {
  const articles = useApp((s) => s.articles);
  const navigate = useNavigate();
  const list = articles
    .filter((a) => a.state === "archived")
    .sort((a, b) => +new Date(b.archived_at ?? 0) - +new Date(a.archived_at ?? 0));
  const { focused } = useArticleListNav(list, (a) => navigate({ to: "/a/$id", params: { id: a.id } }));

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3">
        <h2 className="text-[22px] font-semibold tracking-tight">Archive</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Hidden from daily surfaces · still searchable
        </p>
      </div>
      {list.length === 0 ? (
        <EmptyState icon={ArchiveIcon} title="Archive empty" />
      ) : (
        list.map((a, i) => <ArticleRow key={a.id} article={a} focused={i === focused} />)
      )}
    </div>
  );
}
