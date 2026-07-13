// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ErrorBoundary } from '../components/ErrorBoundary';
import * as errorTracking from '../lib/errorTracking';

function Bomb(): never {
  throw new Error('test');
}

function ChunkBomb(): never {
  throw new Error('error loading dynamically imported module: /assets/page.js');
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

  it('renders inline instead of filling the viewport when compact is set', () => {
    const { container } = render(
      <ErrorBoundary compact>
        <Bomb />
      </ErrorBoundary>
    );

    expect(container.querySelector('.min-h-screen')).toBeNull();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('shows chunk-load-specific copy and hides Try again for stale chunk failures', () => {
    render(
      <ErrorBoundary>
        <ChunkBomb />
      </ErrorBoundary>
    );

    expect(screen.getByText('A new version is available')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
  });

  it('recovers without a full reload when Try again is clicked', async () => {
    function Flaky({ shouldThrow }: { shouldThrow: boolean }) {
      if (shouldThrow) throw new Error('flaky');
      return <div>recovered</div>;
    }

    const { rerender } = render(
      <ErrorBoundary>
        <Flaky shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    rerender(
      <ErrorBoundary>
        <Flaky shouldThrow={false} />
      </ErrorBoundary>
    );

    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(screen.getByText('recovered')).toBeInTheDocument();
  });

  it('resets automatically when resetKey changes', () => {
    const { rerender } = render(
      <ErrorBoundary resetKey="/a">
        <Bomb />
      </ErrorBoundary>
    );

    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    rerender(
      <ErrorBoundary resetKey="/b">
        <div>fresh route</div>
      </ErrorBoundary>
    );

    expect(screen.getByText('fresh route')).toBeInTheDocument();
  });

  it('renders nothing when silent is set, but still reports the error', () => {
    const { container } = render(
      <ErrorBoundary silent>
        <Bomb />
      </ErrorBoundary>
    );

    expect(container).toBeEmptyDOMElement();
    expect(errorTracking.reportError).toHaveBeenCalled();
  });
});
