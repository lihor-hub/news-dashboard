// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ErrorBoundary } from '../components/ErrorBoundary';
import * as errorTracking from '../lib/errorTracking';

function Bomb(): never {
  throw new Error('test');
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(errorTracking, 'reportError').mockImplementation(() => undefined);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('shows a friendly error UI instead of a blank screen when a child throws', () => {
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  });

  it('calls reportError when a child throws', () => {
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>
    );

    expect(errorTracking.reportError).toHaveBeenCalled();
    const [errorArg, contextArg] = vi.mocked(errorTracking.reportError).mock.calls[0];
    expect(errorArg).toBeInstanceOf(Error);
    expect(typeof contextArg?.componentStack).toBe('string');
  });

  it('renders children normally when there is no error', () => {
    render(
      <ErrorBoundary>
        <div>All good</div>
      </ErrorBoundary>
    );

    expect(screen.getByText('All good')).toBeInTheDocument();
  });

  it('reloads the page when the Reload button is clicked', async () => {
    const reload = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, reload },
    });

    try {
      render(
        <ErrorBoundary>
          <Bomb />
        </ErrorBoundary>
      );

      await userEvent.click(screen.getByRole('button', { name: 'Reload' }));
      expect(reload).toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: originalLocation,
      });
    }
  });
});
