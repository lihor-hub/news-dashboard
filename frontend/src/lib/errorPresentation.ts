import { HttpError } from '@/api';

export type GenerationErrorKind = 'no_ai' | 'failed';

export interface ErrorPresentation {
  title: string;
  message: string;
  detail?: string;
  action?: string;
}

export interface FriendlyError {
  kind: GenerationErrorKind;
  title: string;
  message: string;
  detail?: string;
}

function detailOf(err: unknown): string | undefined {
  return err instanceof Error ? err.message : undefined;
}

function hasDetail(detail: string | undefined): detail is string {
  return typeof detail === 'string' && detail.trim().length > 0;
}

function withDetail(
  presentation: Omit<ErrorPresentation, 'detail'>,
  detail: string | undefined
): ErrorPresentation {
  return hasDetail(detail) ? { ...presentation, detail } : presentation;
}

function isNetworkError(err: unknown): boolean {
  return err instanceof TypeError && /fetch|network|load failed|connection/i.test(err.message);
}

function isAiProviderConfigurationError(detail: string | undefined): boolean {
  return (
    hasDetail(detail) &&
    /\b(ai provider|openai|anthropic|api[_ -]?key|provider[_ -]?not[_ -]?configured|not configured)\b/i.test(
      detail
    )
  );
}

function presentHttpError(error: HttpError): ErrorPresentation {
  const detail = detailOf(error);
  if (isAiProviderConfigurationError(detail)) {
    return withDetail(
      {
        title: 'AI not configured',
        message:
          'Your administrator needs to configure an AI provider for this app before AI features can run.',
        action: 'Ask an administrator to configure an AI provider.',
      },
      detail
    );
  }

  if (error.status >= 500) {
    return withDetail(
      {
        title: 'Server problem',
        message: 'The server hit a problem. Try again shortly.',
        action: 'Try again shortly.',
      },
      detail
    );
  }

  const byStatus: Record<number, Omit<ErrorPresentation, 'detail'>> = {
    401: {
      title: 'Sign in required',
      message: 'Sign in again to continue.',
      action: 'Sign in again.',
    },
    403: {
      title: 'Permission needed',
      message: 'You do not have permission to do that.',
      action: 'Ask an administrator for access.',
    },
    404: {
      title: 'Not found',
      message: 'That item could not be found. It may have been removed.',
      action: 'Refresh and try again.',
    },
    409: {
      title: 'Already exists',
      message: 'This conflicts with something that already exists.',
      action: 'Use different details and try again.',
    },
    422: {
      title: 'Check the details',
      message: 'Some information is missing or invalid.',
      action: 'Review the highlighted fields and try again.',
    },
    429: {
      title: 'Too many requests',
      message: 'Wait a moment, then try again.',
      action: 'Retry after a short pause.',
    },
  };

  return withDetail(
    byStatus[error.status] ?? {
      title: 'Request failed',
      message: 'The request could not be completed. Try again.',
      action: 'Try again.',
    },
    detail
  );
}

export function presentError(err: unknown): ErrorPresentation {
  const detail = detailOf(err);
  if (err instanceof HttpError) {
    return presentHttpError(err);
  }
  if (isNetworkError(err)) {
    return withDetail(
      {
        title: 'Connection problem',
        message: 'Check your connection, then try again.',
        action: 'Reconnect and retry.',
      },
      detail
    );
  }
  if (isAiProviderConfigurationError(detail)) {
    return withDetail(
      {
        title: 'AI not configured',
        message:
          'Your administrator needs to configure an AI provider for this app before AI features can run.',
        action: 'Ask an administrator to configure an AI provider.',
      },
      detail
    );
  }
  return withDetail(
    {
      title: 'Something went wrong',
      message:
        'Try again. If the problem continues, share the technical details with an administrator.',
      action: 'Try again.',
    },
    detail
  );
}

/** Classifies a briefing/podcast generation failure into user-facing copy, without leaking provider/env details. */
export function classifyGenerationError(err: unknown): FriendlyError {
  if (err instanceof HttpError && err.status === 503) {
    return {
      kind: 'no_ai',
      title: 'AI not configured',
      message:
        'Your administrator needs to configure an AI provider for this app before briefings can be generated.',
    };
  }
  return {
    kind: 'failed',
    title: 'Generation failed',
    message: 'The AI service is unavailable or returned an unexpected response. Try again shortly.',
    detail: detailOf(err),
  };
}

/** Friendly copy for a briefing that was persisted with status "failed". */
export function presentFailedBriefing(error?: string | null): FriendlyError {
  return {
    kind: 'failed',
    title: 'Last briefing failed',
    message:
      'The previous briefing could not be generated. You can retry or review the raw feed instead.',
    detail: error ?? undefined,
  };
}

export type SourceActionKind = 'add' | 'toggle' | 'cleanup' | 'delete';

/** Friendly copy for source management failures, without leaking raw backend/server strings as the primary message. */
export function sourceActionErrorMessage(err: unknown, action: SourceActionKind): string {
  if (err instanceof HttpError && err.status === 409) {
    return 'That slug is already in use — choose a different slug or source.';
  }
  switch (action) {
    case 'add':
      return 'Could not add source. Check the feed URL and try again.';
    case 'toggle':
      return 'Could not update the source — it has been reverted to its previous state.';
    case 'cleanup':
      return "Cleanup couldn't be applied — the source list has been restored.";
    case 'delete':
      return "Couldn't delete the source — it has been restored.";
  }
}
