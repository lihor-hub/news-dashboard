import { AlertCircle, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

interface RetryableErrorStateProps {
  title: string;
  message: string;
  onRetry: () => void;
  retryLabel?: string;
  isRetrying?: boolean;
  icon?: LucideIcon;
}

export function RetryableErrorState({
  title,
  message,
  onRetry,
  retryLabel = 'Retry',
  isRetrying = false,
  icon: Icon = AlertCircle,
}: RetryableErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center px-6 py-16 text-center text-muted-foreground"
    >
      <Icon className="mb-3 size-10 text-destructive" strokeWidth={1.25} />
      <div className="text-sm font-medium text-foreground">{title}</div>
      <div className="mt-1 max-w-sm text-xs">{message}</div>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="mt-4"
        onClick={onRetry}
        disabled={isRetrying}
      >
        {isRetrying ? 'Retrying...' : retryLabel}
      </Button>
    </div>
  );
}

/** Placeholder row shaped like an article row: thumbnail + meta line + title line. */
export function RowSkeleton() {
  return (
    <div className="flex items-start gap-3 px-4 py-3 md:px-5">
      <Skeleton className="size-12 shrink-0 rounded-lg bg-muted" />
      <div className="min-w-0 flex-1 space-y-2 pt-0.5">
        <Skeleton className="h-3 w-32 rounded-full bg-muted" />
        <Skeleton className="h-4 w-4/5 rounded-full bg-muted" />
      </div>
    </div>
  );
}

/** Placeholder card shaped like a story card: avatar + title + one line of meta. */
export function CardSkeleton() {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border p-3">
      <Skeleton className="size-10 shrink-0 rounded-full bg-muted" />
      <div className="min-w-0 flex-1 space-y-2 pt-0.5">
        <Skeleton className="h-4 w-3/4 rounded-full bg-muted" />
        <Skeleton className="h-3 w-1/2 rounded-full bg-muted" />
      </div>
    </div>
  );
}

export function ListSkeleton({
  rows = 5,
  variant = 'row',
}: {
  rows?: number;
  variant?: 'row' | 'card';
}) {
  const { t } = useTranslation();
  const Item = variant === 'card' ? CardSkeleton : RowSkeleton;
  return (
    <div
      role="status"
      aria-busy="true"
      data-testid="list-skeleton"
      className={variant === 'card' ? 'grid gap-2' : 'divide-y divide-border'}
    >
      <span className="sr-only">{t('states.loading')}</span>
      {Array.from({ length: rows }).map((_, index) => (
        <Item key={index} />
      ))}
    </div>
  );
}

export function InlineError({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-3 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive"
    >
      <span>{message}</span>
      {action}
    </div>
  );
}
