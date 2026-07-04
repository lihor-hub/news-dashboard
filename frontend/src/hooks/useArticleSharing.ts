import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { createArticleHighlight, deleteArticleHighlight, fetchArticleHighlights } from '@/api';
import type { WorkflowArticle } from '@/lib/workflowTypes';

export function useArticleSharing({
  id,
  shareId,
  article,
}: {
  id: string | undefined;
  shareId: string | undefined;
  article: WorkflowArticle | null;
}) {
  const queryClient = useQueryClient();
  const [shareOpen, setShareOpen] = useState(false);
  const [selectedShareText, setSelectedShareText] = useState('');
  const [pendingShareHighlight, setPendingShareHighlight] = useState<{ text: string } | null>(null);

  const highlightsQuery = useQuery({
    queryKey: ['article-highlights', id],
    queryFn: () => fetchArticleHighlights(id!),
    enabled: Boolean(id) && !shareId,
  });

  const createHighlightMutation = useMutation({
    mutationFn: ({ text, note }: { text: string; note: string | null }) =>
      createArticleHighlight(id!, {
        highlighted_text: text,
        offset_chars: article?.body?.indexOf(text) ?? 0,
        note,
      }),
    onSuccess: () => {
      setSelectedShareText('');
      window.getSelection()?.removeAllRanges();
      void queryClient.invalidateQueries({ queryKey: ['article-highlights', id] });
      toast('Highlight saved');
    },
    onError: () => toast.error('Could not save highlight'),
  });

  const deleteHighlightMutation = useMutation({
    mutationFn: (highlightId: number) => deleteArticleHighlight(id!, highlightId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['article-highlights', id] });
      toast('Highlight deleted');
    },
    onError: () => toast.error('Could not delete highlight'),
  });

  function handleShare() {
    if (!article) return;
    setPendingShareHighlight(null);
    setShareOpen(true);
  }

  function selectedTextWithinReader(): string {
    const selection = window.getSelection();
    const text = selection?.toString().trim() ?? '';
    if (!selection || !text || selection.rangeCount === 0) return '';
    const reader = document.querySelector('.reader-prose');
    const container = selection.getRangeAt(0).commonAncestorContainer;
    if (!reader?.contains(container)) return '';
    return text;
  }

  function updateSelectedShareText() {
    setSelectedShareText(selectedTextWithinReader());
  }

  function handleShareSelected() {
    if (!article || !selectedShareText) return;
    setPendingShareHighlight({ text: selectedShareText });
    setShareOpen(true);
  }

  function handleHighlightSelected() {
    if (!article || !selectedShareText || shareId) return;
    const note = window.prompt('Add a private note to this highlight?')?.trim() ?? null;
    createHighlightMutation.mutate({ text: selectedShareText, note });
  }

  return {
    shareOpen,
    setShareOpen,
    selectedShareText,
    pendingShareHighlight,
    highlights: highlightsQuery.data ?? [],
    deleteHighlight: (highlightId: number) => deleteHighlightMutation.mutate(highlightId),
    handleShare,
    updateSelectedShareText,
    handleShareSelected,
    handleHighlightSelected,
  };
}
