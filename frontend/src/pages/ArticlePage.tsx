import { useCallback } from 'react';
import { useParams, useNavigate } from 'react-router';
import { getReaderList } from '@/lib/readerList';
import { ArticleReader } from '@/components/article/ArticleReader';

/** Full-screen reader route for `/a/:id` and `/shared/:shareId/article`. */
export function ArticlePage() {
  const { id, shareId } = useParams<{ id?: string; shareId?: string }>();
  const navigate = useNavigate();

  // Prev/next navigation from sessionStorage list
  const readerList = getReaderList();
  const idx = readerList && id ? readerList.ids.indexOf(String(id)) : -1;
  const prevId = idx > 0 ? readerList!.ids[idx - 1] : null;
  const nextId =
    idx >= 0 && idx < (readerList?.ids.length ?? 0) - 1 ? readerList!.ids[idx + 1] : null;

  const goBack = useCallback(() => void navigate(-1), [navigate]);
  const goPrev = useCallback(() => {
    if (prevId) void navigate(`/a/${prevId}`, { replace: true });
  }, [navigate, prevId]);
  const goNext = useCallback(() => {
    if (nextId) void navigate(`/a/${nextId}`, { replace: true });
  }, [navigate, nextId]);

  return (
    <ArticleReader
      articleId={id}
      shareId={shareId}
      variant="page"
      onBack={goBack}
      onPrev={goPrev}
      onNext={goNext}
      prevId={prevId}
      nextId={nextId}
    />
  );
}
