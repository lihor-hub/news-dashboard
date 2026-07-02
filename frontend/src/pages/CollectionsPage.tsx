import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Tag as TagIcon, Trash2 } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createTag, deleteTag, fetchTags } from '@/api/tagsApi';
import { EmptyState } from '@/components/EmptyState';

export function CollectionsPage() {
  const queryClient = useQueryClient();
  const [newTagName, setNewTagName] = useState('');

  const { data: tags = [], isLoading } = useQuery({
    queryKey: ['tags'],
    queryFn: fetchTags,
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createTag(name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tags'] });
      setNewTagName('');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (tagId: number) => deleteTag(tagId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['tags'] }),
  });

  function handleCreate() {
    const name = newTagName.trim();
    if (!name) return;
    createMutation.mutate(name);
  }

  return (
    <div>
      <div className="px-4 md:px-5 pt-4 pb-3">
        <h2 className="text-[22px] font-semibold tracking-tight">Collections</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Group articles into your own tags, independent of workflow state.
        </p>
      </div>

      <div className="px-4 md:px-5 pb-4 flex items-center gap-2">
        <input
          value={newTagName}
          onChange={(e) => setNewTagName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleCreate();
          }}
          placeholder="New collection name…"
          className="h-9 flex-1 max-w-xs rounded-md border border-border bg-surface px-3 text-sm outline-none focus:border-border-strong"
        />
        <button
          type="button"
          onClick={handleCreate}
          disabled={!newTagName.trim() || createMutation.isPending}
          className="h-9 px-3 rounded-md bg-foreground text-background text-sm font-medium disabled:opacity-50"
        >
          Create
        </button>
      </div>

      {isLoading ? null : tags.length === 0 ? (
        <EmptyState
          icon={TagIcon}
          title="No collections yet"
          subtitle="Create a tag to start organizing articles into your own collections."
        />
      ) : (
        <div className="divide-y divide-border border-t border-border">
          {tags.map((tag) => (
            <div
              key={tag.id}
              className="flex items-center justify-between gap-3 px-4 md:px-5 py-3 hover:bg-surface"
            >
              <Link to={`/collections/${tag.id}`} className="flex items-center gap-2 min-w-0">
                <TagIcon
                  className="size-4 shrink-0"
                  strokeWidth={1.75}
                  style={{ color: tag.color ?? undefined }}
                />
                <span className="text-sm font-medium truncate">{tag.name}</span>
                <span className="text-xs text-muted-foreground shrink-0">
                  {tag.article_count ?? 0} {tag.article_count === 1 ? 'article' : 'articles'}
                </span>
              </Link>
              <button
                type="button"
                aria-label={`Delete ${tag.name}`}
                onClick={() => deleteMutation.mutate(tag.id)}
                className="text-muted-foreground hover:text-destructive shrink-0"
              >
                <Trash2 className="size-4" strokeWidth={1.75} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
