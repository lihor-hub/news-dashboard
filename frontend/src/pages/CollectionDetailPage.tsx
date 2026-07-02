import { useParams } from 'react-router-dom';
import { Tag as TagIcon } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { ArticleListView } from '@/components/article/ArticleListView';
import { fetchArticlesByTag, fetchTags } from '@/api/tagsApi';

export function CollectionDetailPage() {
  const { tagId } = useParams<{ tagId: string }>();
  const id = Number(tagId);

  const { data: tags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: fetchTags,
  });
  const tag = tags.find((t) => t.id === id);

  if (!Number.isFinite(id)) return null;

  return (
    <ArticleListView
      title={tag?.name ?? 'Collection'}
      description={({ loadedCount, hasMore, isLoading }) =>
        isLoading ? '...' : `${loadedCount}${hasMore ? '+' : ''} tagged articles`
      }
      queryKey={['collection', id]}
      queryFn={(params) => fetchArticlesByTag(id, params)}
      empty={{
        icon: TagIcon,
        title: 'No articles yet',
        subtitle: 'Tag articles from the reader to add them to this collection.',
      }}
    />
  );
}
