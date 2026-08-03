// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';
import { RouteErrorRecovery } from '../components/RouteErrorRecovery';
import * as errorTracking from '../lib/errorTracking';

function Bomb(): never {
  throw new Error('route boom');
}

function ChunkBomb(): never {
  throw new Error('Failed to fetch dynamically imported module: /assets/page.js');
}

function renderRouterWithThrower(Thrower: React.ComponentType, initialPath = '/broken') {
  const router = createMemoryRouter(
    [
      { path: '/', element: <div>home-page</div> },
      { path: '/broken', element: <Thrower />, errorElement: <RouteErrorRecovery /> },
    ],
    { initialEntries: [initialPath] }
  );
  return render(<RouterProvider router={router} />);
}

describe('RouteErrorRecovery', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(errorTracking, 'reportError').mockImplementation(() => undefined);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('renders a branded recovery state instead of the default router error UI', async () => {
    renderRouterWithThrower(Bomb);
    expect(await screen.findByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Go home' })).toHaveAttribute('href', '/');
  });

  it('reports the error for non-response errors', async () => {
    renderRouterWithThrower(Bomb);
    await screen.findByText('Something went wrong');
    expect(errorTracking.reportError).toHaveBeenCalled();
  });

  it('offers a Try again action that revalidates instead of reloading', async () => {
    renderRouterWithThrower(Bomb);
    await screen.findByText('Something went wrong');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reload' })).not.toBeInTheDocument();
  });

  it('invokes the router revalidator when Try again is clicked', async () => {
    renderRouterWithThrower(Bomb);
    await screen.findByText('Something went wrong');

    // Clicking must not throw and must not fall back to a full page reload.
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Something went wrong')).toBeInTheDocument();
  });

  it('shows not-found copy for a matched 404 route response', async () => {
    const router = createMemoryRouter(
      [
        { path: '/', element: <div>home-page</div> },
        {
          path: '/broken',
          element: <div>never rendered</div>,
          errorElement: <RouteErrorRecovery />,
          loader: () => {
            throw new Response('Not Found', { status: 404 });
          },
        },
      ],
      { initialEntries: ['/broken'] }
    );
    render(<RouterProvider router={router} />);

    expect(await screen.findByText('Page not found')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Reload' })).not.toBeInTheDocument();
    expect(errorTracking.reportError).not.toHaveBeenCalled();
  });

  it('shows chunk-load-specific copy and a Reload action for stale chunk failures', async () => {
    renderRouterWithThrower(ChunkBomb);
    expect(await screen.findByText('A new version is available')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  it('reloads the page when Reload is clicked on a chunk error', async () => {
    const reload = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, reload },
    });

    try {
      renderRouterWithThrower(ChunkBomb);
      await screen.findByText('A new version is available');
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
