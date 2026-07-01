import { HttpError } from '@/api';

export type GenerationErrorKind = 'no_ai' | 'failed';

export interface FriendlyError {
  kind: GenerationErrorKind;
  title: string;
  message: string;
  detail?: string;
}

function detailOf(err: unknown): string | undefined {
  return err instanceof Error ? err.message : undefined;
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
