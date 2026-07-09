import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Sparkles, Star, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  createLessonFromLink,
  dismissLessonSuggestion,
  listLessonSuggestions,
  type Lesson,
  type LessonSuggestion,
} from '@/api';
import { patchArticleStar } from '@/api/workflowApi';

const SUGGESTIONS_QUERY_KEY = ['learn-suggestions'];

export function LessonSuggestions({ onGenerated }: { onGenerated: (lesson: Lesson) => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [pendingAction, setPendingAction] = useState<{
    articleId: number;
    action: 'generate' | 'save' | 'dismiss';
  } | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: SUGGESTIONS_QUERY_KEY,
    queryFn: listLessonSuggestions,
  });

  const dismissMutation = useMutation({
    mutationFn: (articleId: number) => dismissLessonSuggestion(articleId),
    onSuccess: (_result, articleId) => {
      queryClient.setQueryData<LessonSuggestion[]>(SUGGESTIONS_QUERY_KEY, (current) =>
        (current ?? []).filter((item) => item.article_id !== articleId)
      );
    },
  });

  const saveMutation = useMutation({
    mutationFn: (articleId: number) => patchArticleStar(String(articleId), true),
    onSuccess: (_result, articleId) => {
      queryClient.setQueryData<LessonSuggestion[]>(SUGGESTIONS_QUERY_KEY, (current) =>
        (current ?? []).filter((item) => item.article_id !== articleId)
      );
    },
  });

  const generateMutation = useMutation({
    mutationFn: (suggestion: LessonSuggestion) => createLessonFromLink(suggestion.url),
    onSuccess: (lesson, suggestion) => {
      onGenerated(lesson);
      queryClient.setQueryData<LessonSuggestion[]>(SUGGESTIONS_QUERY_KEY, (current) =>
        (current ?? []).filter((item) => item.article_id !== suggestion.article_id)
      );
    },
  });

  const suggestions = data ?? [];

  if (isLoading || isError || suggestions.length === 0) return null;

  return (
    <section className="mb-6 rounded-lg border border-border bg-surface p-4">
      <div className="mb-3 flex items-center gap-2">
        <Sparkles className="size-4 text-muted-foreground" />
        <h2 className="text-sm font-semibold text-foreground">
          {t('learn.suggestions.title', 'Worth turning into a lesson')}
        </h2>
      </div>
      <ul className="space-y-3">
        {suggestions.map((suggestion) => {
          const isBusy = pendingAction?.articleId === suggestion.article_id;
          return (
            <li
              key={suggestion.article_id}
              className="flex flex-col gap-2 rounded-md border border-border p-3 sm:flex-row sm:items-start sm:justify-between"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">{suggestion.title}</p>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                  {suggestion.source_name ? <span>{suggestion.source_name}</span> : null}
                  {suggestion.reasons.map((reason) => (
                    <Badge key={reason} variant="outline" className="font-normal">
                      {reason}
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={t('learn.suggestions.dismiss', 'Dismiss')}
                  disabled={isBusy}
                  onClick={() => {
                    setPendingAction({ articleId: suggestion.article_id, action: 'dismiss' });
                    dismissMutation.mutate(suggestion.article_id, {
                      onSettled: () => setPendingAction(null),
                    });
                  }}
                >
                  {isBusy && pendingAction?.action === 'dismiss' ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <X className="size-3.5" />
                  )}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={t('learn.suggestions.save', 'Save')}
                  disabled={isBusy}
                  onClick={() => {
                    setPendingAction({ articleId: suggestion.article_id, action: 'save' });
                    saveMutation.mutate(suggestion.article_id, {
                      onSettled: () => setPendingAction(null),
                    });
                  }}
                >
                  {isBusy && pendingAction?.action === 'save' ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Star className="size-3.5" />
                  )}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  disabled={isBusy}
                  onClick={() => {
                    setPendingAction({ articleId: suggestion.article_id, action: 'generate' });
                    generateMutation.mutate(suggestion, {
                      onSettled: () => setPendingAction(null),
                    });
                  }}
                >
                  {isBusy && pendingAction?.action === 'generate' ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : null}
                  {t('learn.suggestions.generate', 'Generate lesson')}
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
