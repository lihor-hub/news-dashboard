import { useEffect } from 'react';

export function useArticleKeyboardShortcuts({
  hasArticle,
  articleUrl,
  goBack,
  goPrev,
  goNext,
  doAction,
  doStar,
}: {
  hasArticle: boolean;
  articleUrl: string | undefined;
  goBack: () => void;
  goPrev: () => void;
  goNext: () => void;
  doAction: (state: 'done' | 'later' | 'skipped' | 'archived', label: string) => void;
  doStar: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t?.tagName === 'INPUT' || t?.tagName === 'TEXTAREA' || t?.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === 'Escape') goBack();
      else if (e.key === 'ArrowLeft') goPrev();
      else if (e.key === 'ArrowRight') goNext();
      else if ((e.key === 'r' || e.key === 'd') && hasArticle) doAction('done', 'Done');
      else if (e.key === 'l' && hasArticle) doAction('later', 'Later');
      else if (e.key === 's' && hasArticle) doStar();
      else if (e.key === 'x' && hasArticle) doAction('skipped', 'Skipped');
      else if (e.key === 'e' && hasArticle) doAction('archived', 'Archived');
      else if (e.key === 'o' && hasArticle && articleUrl)
        window.open(articleUrl, '_blank', 'noopener,noreferrer');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [hasArticle, articleUrl, goBack, goPrev, goNext, doAction, doStar]);
}
