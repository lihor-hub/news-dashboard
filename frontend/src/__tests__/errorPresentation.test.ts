import { describe, expect, it } from 'vitest';
import { HttpError } from '../api';
import { presentError } from '../lib/errorPresentation';

describe('presentError', () => {
  it.each([
    [
      new HttpError(401, 'token expired'),
      {
        title: 'Sign in required',
        message: 'Sign in again to continue.',
        detail: 'token expired',
      },
    ],
    [
      new HttpError(403, 'admin role required'),
      {
        title: 'Permission needed',
        message: 'You do not have permission to do that.',
        detail: 'admin role required',
      },
    ],
    [
      new HttpError(404, 'source not found'),
      {
        title: 'Not found',
        message: 'That item could not be found. It may have been removed.',
        detail: 'source not found',
      },
    ],
    [
      new HttpError(409, 'slug already exists'),
      {
        title: 'Already exists',
        message: 'This conflicts with something that already exists.',
        detail: 'slug already exists',
      },
    ],
    [
      new HttpError(422, 'field required'),
      {
        title: 'Check the details',
        message: 'Some information is missing or invalid.',
        detail: 'field required',
      },
    ],
    [
      new HttpError(429, 'rate limit exceeded'),
      {
        title: 'Too many requests',
        message: 'Wait a moment, then try again.',
        detail: 'rate limit exceeded',
      },
    ],
    [
      new HttpError(500, 'Internal Server Error'),
      {
        title: 'Server problem',
        message: 'The server hit a problem. Try again shortly.',
        detail: 'Internal Server Error',
      },
    ],
  ])('maps known HTTP errors to friendly copy while preserving detail', (error, expected) => {
    expect(presentError(error)).toMatchObject(expected);
  });

  it('maps network failures to offline-friendly copy', () => {
    expect(presentError(new TypeError('Failed to fetch'))).toMatchObject({
      title: 'Connection problem',
      message: 'Check your connection, then try again.',
      detail: 'Failed to fetch',
    });
  });

  it('maps AI provider configuration errors without exposing raw configuration text as primary copy', () => {
    expect(presentError(new Error('OPENAI_API_KEY is not configured'))).toMatchObject({
      title: 'AI not configured',
      message:
        'Your administrator needs to configure an AI provider for this app before AI features can run.',
      detail: 'OPENAI_API_KEY is not configured',
    });
  });

  it('falls back to generic copy for unknown errors and keeps technical detail', () => {
    expect(presentError(new Error('unexpected parser branch'))).toMatchObject({
      title: 'Something went wrong',
      message:
        'Try again. If the problem continues, share the technical details with an administrator.',
      detail: 'unexpected parser branch',
    });
  });
});
