import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';
import { AlertCircle, ArrowLeft, Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { LessonDetailView } from '@/components/LessonDetailView';
import { useLessonPolling } from '@/hooks/useLessonPolling';
import { fetchLesson, type Lesson } from '@/api';

export function LessonDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const lessonId = Number(id);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isActive = true;
    setIsLoading(true);
    setLoadError(null);
    fetchLesson(lessonId)
      .then((result) => {
        if (isActive) setLesson(result);
      })
      .catch((error: unknown) => {
        if (!isActive) return;
        setLoadError(error instanceof Error ? error.message : t('learn.refresh_error'));
      })
      .finally(() => {
        if (isActive) setIsLoading(false);
      });
    return () => {
      isActive = false;
    };
    // t is intentionally omitted: react-i18next's t identity can change every
    // render, and this effect must only refire when the lesson id changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lessonId]);

  useLessonPolling(lesson, setLesson, setLoadError, t('learn.refresh_error'));

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <Link
        to="/learn/library"
        className="mb-6 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground hover:underline"
      >
        <ArrowLeft className="size-3.5" />
        {t('learn.library.back_to_library', 'Back to library')}
      </Link>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
        </div>
      ) : lesson ? (
        <LessonDetailView lesson={lesson} onLessonUpdate={setLesson} />
      ) : (
        <div className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <div className="text-sm text-foreground">
            {loadError ?? t('learn.library.not_found', 'Lesson not found.')}
          </div>
        </div>
      )}
    </div>
  );
}
