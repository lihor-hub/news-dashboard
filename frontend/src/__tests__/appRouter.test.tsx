// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';

// Stub every page/shell so the route table can be exercised cheaply without
// pulling in real data fetching. Each stub renders an identifiable marker.
const { stub, authState } = vi.hoisted(() => ({
  stub: (label: string) => () => <div>{label}</div>,
  authState: {
    user: { id: 1, username: 'admin', is_admin: true },
  },
}));

vi.mock('../components/RequireAuth', () => ({
  RequireAuth: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('../components/AppShell', async () => {
  const { Outlet } = await import('react-router-dom');
  return { AppShell: () => <Outlet /> };
});
vi.mock('../contexts/auth', () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAuth: () => ({ user: authState.user, setUser: vi.fn() }),
}));
vi.mock('../contexts/focusedArticle', () => ({
  FocusedArticleProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('../pages/LoginPage', () => ({ LoginPage: stub('login-page') }));
vi.mock('../pages/BriefPage', () => ({ BriefPage: stub('brief-page') }));
vi.mock('../pages/InboxPage', () => ({ InboxPage: stub('inbox-page') }));
vi.mock('../pages/LaterPage', () => ({ LaterPage: stub('later-page') }));
vi.mock('../pages/StarredPage', () => ({ StarredPage: stub('starred-page') }));
vi.mock('../pages/SearchPage', () => ({ SearchPage: stub('search-page') }));
vi.mock('../pages/AskPage', () => ({ AskPage: stub('ask-page') }));
vi.mock('../pages/FeedsPage', async () => {
  const { Outlet } = await import('react-router-dom');
  return {
    FeedsPage: () => (
      <div>
        feeds-page
        <Outlet />
      </div>
    ),
  };
});
vi.mock('../pages/SourcesPage', () => ({ SourcesPage: stub('sources-page') }));
vi.mock('../pages/SchedulerPage', () => ({ SchedulerPage: stub('scheduler-page') }));
vi.mock('../pages/FeedsRunsPage', () => ({ FeedsRunsPage: stub('runs-page') }));
vi.mock('../pages/FeedsLogsPage', () => ({ FeedsLogsPage: stub('logs-page') }));
vi.mock('../pages/StatsPage', () => ({ StatsPage: stub('stats-page') }));
vi.mock('../pages/ArchivePage', () => ({ ArchivePage: stub('archive-page') }));
vi.mock('../pages/SettingsPage', () => ({ SettingsPage: stub('settings-page') }));
vi.mock('../pages/OfflineSavedPage', () => ({ OfflineSavedPage: stub('offline-saved-page') }));
vi.mock('../pages/ArticlePage', () => ({ ArticlePage: stub('article-page') }));
vi.mock('../pages/BriefingsHistoryPage', () => ({ BriefingsHistoryPage: stub('briefs-page') }));
vi.mock('../pages/BriefingDetailPage', () => ({ BriefingDetailPage: stub('brief-detail-page') }));

import { routes, NotFound, AppRouter } from '../AppRouter';

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(<RouterProvider router={router} />);
}

describe('AppRouter routes', () => {
  it('renders the login route', async () => {
    renderAt('/login');
    expect(await screen.findByText('login-page')).toBeTruthy();
  });

  it('renders the index brief page', async () => {
    renderAt('/');
    expect(await screen.findByText('brief-page')).toBeTruthy();
  });

  it('renders a nested feeds child route', async () => {
    renderAt('/feeds/runs');
    expect(await screen.findByText('runs-page')).toBeTruthy();
  });

  it('renders the offline saved route', async () => {
    renderAt('/offline-saved');
    expect(await screen.findByText('offline-saved-page')).toBeTruthy();
  });

  describe('admin-guarded feeds operational routes', () => {
    afterEach(() => {
      authState.user = { id: 1, username: 'admin', is_admin: true };
    });

    it.each([
      ['/feeds/schedule', 'scheduler-page'],
      ['/feeds/runs', 'runs-page'],
      ['/feeds/logs', 'logs-page'],
    ])('mounts %s for admin users', async (path, label) => {
      authState.user = { id: 1, username: 'admin', is_admin: true };
      renderAt(path);
      expect(await screen.findByText(label)).toBeTruthy();
    });

    it.each([
      ['/feeds/schedule', 'scheduler-page'],
      ['/feeds/runs', 'runs-page'],
      ['/feeds/logs', 'logs-page'],
    ])('does not mount %s for non-admin users', async (path, label) => {
      authState.user = { id: 2, username: 'user', is_admin: false };
      renderAt(path);
      expect(await screen.findByText('Admins only')).toBeTruthy();
      expect(screen.queryByText(label)).toBeNull();
    });
  });

  it('redirects legacy /inbox to /today', async () => {
    renderAt('/inbox');
    expect(await screen.findByText('inbox-page')).toBeTruthy();
  });

  it('redirects legacy /scheduler to the schedule tab', async () => {
    renderAt('/scheduler');
    expect(await screen.findByText('scheduler-page')).toBeTruthy();
  });

  it('renders the 404 page for unknown routes', async () => {
    renderAt('/no-such-page');
    expect(await screen.findByText('404')).toBeTruthy();
  });

  it('mounts the provider tree via AppRouter', async () => {
    render(<AppRouter />);
    await waitFor(() => expect(screen.getByText('brief-page')).toBeTruthy());
  });
});

describe('NotFound', () => {
  it('renders a home link', () => {
    const router = createMemoryRouter([{ path: '/', element: <NotFound /> }]);
    render(<RouterProvider router={router} />);
    expect(screen.getByText('Page not found')).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Go home' }).getAttribute('href')).toBe('/');
  });
});
