import { useEffect, useRef, useState } from 'react';
import type { WorkflowArticle } from '../lib/workflowTypes';
import type { useTriageMutations } from './useTriageMutations';

type Mutations = ReturnType<typeof useTriageMutations>;

// Enter on these keeps its native meaning (press the button, follow the link);
// article row links are the exception and open the focused article.
const NATIVE_ENTER_TARGET =
  'button, summary, select, [role="button"], [role="menuitem"], [role="tab"], a:not([data-article-row])';

export interface ArticleListNavOptions {
  /**
   * Controlled focus: when `onFocusChange` is set the host owns the focused
   * index (e.g. a URL-synced reading-pane selection; -1 = nothing selected).
   */
  focused?: number;
  onFocusChange?: (index: number) => void;
  /** Bound to Esc when set. */
  onEscape?: () => void;
}

export function useArticleListNav(
  list: WorkflowArticle[],
  openArticle: (a: WorkflowArticle) => void,
  mutations: Mutations,
  { focused: controlledFocused, onFocusChange, onEscape }: ArticleListNavOptions = {}
) {
  const [internalFocused, setInternalFocused] = useState(0);
  const controlled = onFocusChange != null;
  const focused = controlled ? (controlledFocused ?? -1) : internalFocused;
  // Controlled steps land on the next render; chain fast repeats off the last
  // requested index instead of the not-yet-updated prop.
  const pendingFocus = useRef<number | null>(null);

  useEffect(() => {
    pendingFocus.current = null;
  }, [focused]);

  useEffect(() => {
    if (controlled) return;
    if (internalFocused >= list.length) setInternalFocused(Math.max(0, list.length - 1));
  }, [controlled, list.length, internalFocused]);

  useEffect(() => {
    const move = (delta: number) => {
      if (list.length === 0) return;
      const clamp = (index: number) => Math.min(list.length - 1, Math.max(0, index));
      if (onFocusChange) {
        const next = clamp((pendingFocus.current ?? focused) + delta);
        pendingFocus.current = next;
        onFocusChange(next);
      } else setInternalFocused((f) => clamp(f + delta));
    };

    const handler = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t?.tagName === 'INPUT' || t?.tagName === 'TEXTAREA' || t?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const cur = list[focused];
      const key = e.key.toLowerCase();

      if (key === 'j') {
        move(1);
        e.preventDefault();
      } else if (key === 'k') {
        move(-1);
        e.preventDefault();
      } else if (key === 'escape' && onEscape) {
        // Radix layers (dialogs, menus) prevent the Esc they consume.
        if (!e.defaultPrevented) onEscape();
      } else if (key === 'enter' && cur && !t?.closest?.(NATIVE_ENTER_TARGET)) {
        openArticle(cur);
        e.preventDefault();
      } else if ((key === 'r' || key === 'd') && cur) {
        mutations.setState(cur, 'done', 'Done');
      } else if (key === 'l' && cur) {
        mutations.sendLater(cur);
      } else if (key === 's' && cur) {
        mutations.toggleStar(cur);
      } else if (key === 'x' && cur && !cur.starred) {
        mutations.setState(cur, 'skipped', 'Skipped');
      } else if (key === 'e' && cur) {
        mutations.setState(cur, 'archived', 'Archived');
      } else if (key === 'o' && cur) {
        window.open(cur.url, '_blank', 'noopener,noreferrer');
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [list, focused, openArticle, mutations, onFocusChange, onEscape]);

  return { focused, setFocused: setInternalFocused };
}
