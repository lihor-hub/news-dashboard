import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Archive as ArchiveIcon } from 'lucide-react';
import { ArticleRow } from '@/components/article/ArticleRow';
import { EmptyState } from '@/components/EmptyState';
import { CategoryFilter } from '@/components/CategoryFilter';
import { useArticleListNav } from '@/hooks/useArticleListNav';
import { useTriageMutations } from '@/hooks/useTriageMutations';
import { fetchTriageArticles } from '@/api/workflowApi';
import { ARTICLES_KEY } from '@/hooks/useTriageMutations';

export function ArchivePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const category = searchParams.get('category') ?? undefined;

  const { data: articles = [], isLoading } = useQuery({
    queryKey: [ARTICLES_KEY, 'archived', category],
    queryFn: () => fetchTriageArticles('archived', category),
  });

  const list = [...articles].sort(
    (a, b) => +new Date(b.archived_at ?? 0) - +new Date(a.archived_at ?? 0)
  );

  const mutations = useTriageMutations();
  const { focused } = useArticleListNav(list, (a) => navigate(`/a/${a.id}`), mutations);

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3">
        <h2 className="text-[22px] font-semibold tracking-tight">Archive</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Hidden from daily surfaces · still searchable
        </p>
      </div>
      <CategoryFilter />
      {isLoading ? null : list.length === 0 ? (
        <EmptyState icon={ArchiveIcon} title="Archive empty" />
      ) : (
        list.map((a, i) => <ArticleRow key={a.id} article={a} focused={i === focused} />)
      )}
    </div>
  );
}
