import { useEffect, useState } from 'react';
import { ThumbsDown, ThumbsUp } from 'lucide-react';
import {
  deleteAiFeedback,
  fetchAiFeedback,
  postAiFeedback,
  type AiFeedbackSubjectType,
  type AiFeedbackVerdict,
} from '@/api';

/** Thumbs up/down feedback control for a briefing or recommendation. */
export function AiFeedbackThumbs({
  subjectType,
  subjectId,
  articleId,
  className,
}: {
  subjectType: AiFeedbackSubjectType;
  subjectId: number;
  articleId?: number;
  className?: string;
}) {
  const [verdict, setVerdict] = useState<AiFeedbackVerdict | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchAiFeedback(subjectType, [subjectId])
      .then((items) => {
        if (cancelled) return;
        const key = `${subjectId}:${articleId ?? ''}`;
        setVerdict(items[key] ?? null);
      })
      .catch(() => {
        // Non-critical: thumbs simply render unselected if the lookup fails.
      });
    return () => {
      cancelled = true;
    };
  }, [subjectType, subjectId, articleId]);

  async function handleClick(next: AiFeedbackVerdict) {
    if (pending) return;
    setPending(true);
    const previous = verdict;
    const nextVerdict = previous === next ? null : next;
    setVerdict(nextVerdict);
    try {
      if (nextVerdict === null) {
        await deleteAiFeedback(subjectType, subjectId, { articleId });
      } else {
        await postAiFeedback(subjectType, subjectId, nextVerdict, { articleId });
      }
    } catch {
      setVerdict(previous);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className={`inline-flex items-center gap-1 ${className ?? ''}`}>
      <button
        type="button"
        aria-label="Thumbs up"
        aria-pressed={verdict === 1}
        disabled={pending}
        onClick={() => void handleClick(1)}
        className={`rounded-md p-1 transition-colors ${
          verdict === 1
            ? 'text-primary bg-primary/10'
            : 'text-muted-foreground hover:text-foreground hover:bg-accent'
        }`}
      >
        <ThumbsUp className="size-3.5" strokeWidth={1.75} />
      </button>
      <button
        type="button"
        aria-label="Thumbs down"
        aria-pressed={verdict === -1}
        disabled={pending}
        onClick={() => void handleClick(-1)}
        className={`rounded-md p-1 transition-colors ${
          verdict === -1
            ? 'text-destructive bg-destructive/10'
            : 'text-muted-foreground hover:text-foreground hover:bg-accent'
        }`}
      >
        <ThumbsDown className="size-3.5" strokeWidth={1.75} />
      </button>
    </div>
  );
}
