import { useEffect, useState } from 'react';
import type { WorkflowArticle } from '../lib/workflowTypes';
import type { useTriageMutations } from './useTriageMutations';

type Mutations = ReturnType<typeof useTriageMutations>;

export function useArticleListNav(
  list: WorkflowArticle[],
  openArticle: (a: WorkflowArticle) => void,
  mutations: Mutations
) {
  const [focused, setFocused] = useState(0);

  useEffect(() => {
    if (focused >= list.length) setFocused(Math.max(0, list.length - 1));
  }, [list.length, focused]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t?.tagName === 'INPUT' || t?.tagName === 'TEXTAREA' || t?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const cur = list[focused];

      if (e.key === 'j') {
        setFocused((f) => Math.min(list.length - 1, f + 1));
        e.preventDefault();
      } else if (e.key === 'k') {
        setFocused((f) => Math.max(0, f - 1));
        e.preventDefault();
      } else if (e.key === 'Enter' && cur) {
        openArticle(cur);
        e.preventDefault();
      } else if ((e.key === 'r' || e.key === 'd') && cur) {
        mutations.setState(cur, 'done', 'Done');
      } else if (e.key === 'l' && cur) {
        mutations.sendLater(cur);
      } else if (e.key === 's' && cur) {
        mutations.toggleStar(cur);
      } else if (e.key === 'x' && cur && !cur.starred) {
        mutations.setState(cur, 'skipped', 'Skipped');
      } else if (e.key === 'e' && cur) {
        mutations.setState(cur, 'archived', 'Archived');
      } else if (e.key === 'o' && cur) {
        window.open(cur.url, '_blank', 'noopener,noreferrer');
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [list, focused, openArticle, mutations]);

  return { focused, setFocused };
}
