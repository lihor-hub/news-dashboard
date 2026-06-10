import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Clock } from 'lucide-react';
import { ArticleRow } from '@/components/article/ArticleRow';
import { EmptyState } from '@/components/EmptyState';
import { useArticleListNav } from '@/hooks/useArticleListNav';
import { useTriageMutations } from '@/hooks/useTriageMutations';
import { fetchTriageArticles } from '@/api/workflowApi';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';

export function LaterPage() {
  const navigate = useNavigate();

  const { data: articles = [] } = useQuery({
    queryKey: [ARTICLES_KEY, 'later'],
    queryFn: () => fetchTriageArticles('later'),
  });

  // Sort by return date, soonest first
  const list = [...articles].sort(
    (a, b) => +new Date(a.later_until ?? 0) - +new Date(b.later_until ?? 0)
  );

  const mutations = useTriageMutations();
  const { focused } = useArticleListNav(list, (a) => navigate(`/a/${a.id}`), mutations);

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3">
        <h2 className="text-[22px] font-semibold tracking-tight">Later</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          {list.length} snoozed · returns to Today automatically
        </p>
      </div>
      {list.length === 0 ? (
        <EmptyState
          icon={Clock}
          title="Nothing snoozed"
          subtitle="Articles you send to Later will appear here with their return date. (Requires #87 for persistence)"
        />
      ) : (
        list.map((a, i) => (
          <ArticleRow key={a.id} article={a} focused={i === focused} showLaterUntil />
        ))
      )}
    </div>
  );
}
