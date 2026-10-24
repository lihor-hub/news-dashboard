import { useState } from 'react';
import { Plus, X, Tag as TagIcon } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  addArticleTag,
  createTag,
  fetchArticleTags,
  fetchTags,
  removeArticleTag,
} from '@/api/tagsApi';
import { cn } from '@/lib/utils';

interface Props {
  articleId: string;
}

export function ArticleTags({ articleId }: Props) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [newTagName, setNewTagName] = useState('');

  const { data: articleTags = [] } = useQuery({
    queryKey: ['articleTags', articleId],
    queryFn: () => fetchArticleTags(articleId),
  });

  const { data: allTags = [] } = useQuery({
    queryKey: ['tags'],
    queryFn: fetchTags,
    enabled: open,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['articleTags', articleId] });
    void queryClient.invalidateQueries({ queryKey: ['tags'] });
  };

  const addMutation = useMutation({
    mutationFn: (tagId: number) => addArticleTag(articleId, tagId),
    onSuccess: invalidate,
  });

  const removeMutation = useMutation({
    mutationFn: (tagId: number) => removeArticleTag(articleId, tagId),
    onSuccess: invalidate,
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createTag(name),
    onSuccess: async (tag) => {
      invalidate();
      await addMutation.mutateAsync(tag.id);
      setNewTagName('');
    },
  });

  const appliedIds = new Set(articleTags.map((t) => t.id));
  const availableTags = allTags.filter((t) => !appliedIds.has(t.id));

  function handleCreate() {
    const name = newTagName.trim();
    if (!name) return;
    createMutation.mutate(name);
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5" data-testid="article-tags">
      {articleTags.map((tag) => (
        <span
          key={tag.id}
          className="inline-flex items-center gap-1 rounded-full border border-border bg-surface min-h-8 px-2.5 py-0.5 text-meta font-medium text-foreground md:min-h-0"
          data-testid="article-tag-chip"
        >
          <TagIcon
            className="size-4"
            strokeWidth={1.75}
            style={{ color: tag.color ?? undefined }}
          />
          {tag.name}
          <button
            type="button"
            aria-label={`Remove tag ${tag.name}`}
            onClick={() => removeMutation.mutate(tag.id)}
            className="-me-1.5 inline-flex size-8 items-center justify-center rounded-full text-muted-foreground hover:text-foreground md:size-5"
          >
            <X className="size-4" strokeWidth={1.75} />
          </button>
        </span>
      ))}

      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className={cn(
            'inline-flex min-h-8 items-center gap-1 rounded-full border border-dashed border-border px-2.5 py-0.5 text-meta font-medium text-muted-foreground hover:text-foreground hover:border-border-strong md:min-h-0'
          )}
        >
          <Plus className="size-4" strokeWidth={1.75} />
          Add tag
        </button>
        {open && (
          <div className="absolute z-20 mt-1 min-w-[180px] rounded-md border border-border bg-popover shadow-md p-1.5">
            <div className="flex items-center gap-1 mb-1.5">
              <input
                value={newTagName}
                onChange={(e) => setNewTagName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreate();
                }}
                placeholder="New tag…"
                className="h-9 flex-1 min-w-0 rounded border border-border bg-background px-2 text-sm md:h-7 md:text-xs outline-none focus:border-border-strong"
              />
              <button
                type="button"
                onClick={handleCreate}
                disabled={!newTagName.trim() || createMutation.isPending}
                className="h-9 px-3 rounded bg-foreground text-background text-sm md:h-7 md:px-2 md:text-xs disabled:opacity-50"
              >
                Add
              </button>
            </div>
            {availableTags.length > 0 && (
              <div className="max-h-40 overflow-y-auto">
                {availableTags.map((tag) => (
                  <button
                    key={tag.id}
                    type="button"
                    onClick={() => {
                      addMutation.mutate(tag.id);
                      setOpen(false);
                    }}
                    className="flex w-full items-center gap-1.5 min-h-touch rounded px-2 py-1 text-start text-sm hover:bg-surface md:min-h-0 md:text-xs"
                  >
                    <TagIcon
                      className="size-4 shrink-0"
                      strokeWidth={2}
                      style={{ color: tag.color ?? undefined }}
                    />
                    <span className="truncate">{tag.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
