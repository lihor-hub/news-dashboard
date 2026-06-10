import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useApp } from "@/lib/store";
import { ArticleRow } from "@/components/article/ArticleRow";
import { useArticleListNav } from "@/hooks/use-article-list-nav";
import { EmptyState } from "@/components/EmptyState";
import { Inbox } from "lucide-react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Today — Radar" },
      { name: "description", content: "Your daily technical triage queue." },
    ],
  }),
  component: TodayPage,
});

function TodayPage() {
  const articles = useApp((s) => s.articles);
  const navigate = useNavigate();
  const list = articles
    .filter((a) => a.state === "today")
    .sort((a, b) => +new Date(b.publishedAt) - +new Date(a.publishedAt));

  const { focused } = useArticleListNav(list, (a) => navigate({ to: "/a/$id", params: { id: a.id } }));

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3 flex items-baseline justify-between">
        <div>
          <h2 className="text-[22px] font-semibold tracking-tight">Today</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {list.length} unhandled · scan, decide, move on
          </p>
        </div>
      </div>
      {list.length === 0 ? (
        <EmptyState icon={Inbox} title="Queue clear" subtitle="Nothing left to triage today." />
      ) : (
        <div>
          {list.map((a, i) => (
            <ArticleRow key={a.id} article={a} focused={i === focused} />
          ))}
        </div>
      )}
    </div>
  );
}
