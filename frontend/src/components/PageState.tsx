import { AlertCircle, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { Button } from '@/components/ui/button';

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

export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="divide-y divide-border border-t border-border">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="px-4 py-3 md:px-5">
          <div className="mb-2 h-3 w-28 animate-pulse rounded bg-muted" />
          <div className="mb-2 h-4 w-2/3 animate-pulse rounded bg-muted" />
          <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
        </div>
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
