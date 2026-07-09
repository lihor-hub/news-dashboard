import { useEffect } from 'react';
import { fetchLesson, type Lesson } from '@/api';

export function useLessonPolling(
  lesson: Lesson | null,
  setLesson: (lesson: Lesson) => void,
  setRequestError: (message: string | null) => void,
  fallbackErrorMessage: string
) {
  useEffect(() => {
    if (lesson?.generation_status !== 'pending') return;

    const lessonId = lesson.id;
    let isActive = true;
    let timeoutId: number | null = null;

    const schedulePoll = () => {
      timeoutId = window.setTimeout(() => {
        void (async () => {
          try {
            const nextLesson = await fetchLesson(lessonId);
            if (!isActive) return;
            setRequestError(null);
            setLesson(nextLesson);
            if (nextLesson.id === lessonId && nextLesson.generation_status === 'pending') {
              schedulePoll();
            }
          } catch (error) {
            if (!isActive) return;
            setRequestError(error instanceof Error ? error.message : fallbackErrorMessage);
            schedulePoll();
          }
        })();
      }, 2000);
    };

    schedulePoll();

    return () => {
      isActive = false;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [lesson?.generation_status, lesson?.id, setLesson, setRequestError, fallbackErrorMessage]);
}
