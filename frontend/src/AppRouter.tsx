import { createBrowserRouter, RouterProvider, Navigate, type RouteObject } from 'react-router-dom';
import { FocusedArticleProvider } from './contexts/focusedArticle';
import { AuthProvider } from './contexts/auth';
import { RequireAuth } from './components/RequireAuth';
import { AppShell } from './components/AppShell';
import { LoginPage } from './pages/LoginPage';
import { BriefPage } from './pages/BriefPage';
import { InboxPage } from './pages/InboxPage';
import { SharedPage } from './pages/SharedPage';
import { LaterPage } from './pages/LaterPage';
import { StarredPage } from './pages/StarredPage';
import { SearchPage } from './pages/SearchPage';
import { AskPage } from './pages/AskPage';
import { FeedsPage } from './pages/FeedsPage';
import { SourcesPage } from './pages/SourcesPage';
import { SchedulerPage } from './pages/SchedulerPage';
import { FeedsRunsPage } from './pages/FeedsRunsPage';
import { FeedsLogsPage } from './pages/FeedsLogsPage';
import { StatsPage } from './pages/StatsPage';
import { ArchivePage } from './pages/ArchivePage';
import { SettingsPage } from './pages/SettingsPage';
import { ArticlePage } from './pages/ArticlePage';
import { AdminPage } from './pages/AdminPage';
import { AnalyticsPage } from './pages/AnalyticsPage';
import { BriefingsHistoryPage } from './pages/BriefingsHistoryPage';
import { BriefingDetailPage } from './pages/BriefingDetailPage';

export function NotFound() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-foreground">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-foreground">Page not found</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export const routes: RouteObject[] = [
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/a/:id',
    element: (
      <RequireAuth>
        <ArticlePage />
      </RequireAuth>
    ),
  },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <BriefPage /> },
      { path: 'today', element: <InboxPage /> },
      { path: 'later', element: <LaterPage /> },
      { path: 'starred', element: <StarredPage /> },
      { path: 'shared', element: <SharedPage /> },
      { path: 'search', element: <SearchPage /> },
      { path: 'ask', element: <AskPage /> },
      {
        path: 'feeds',
        element: <FeedsPage />,
        children: [
          { index: true, element: <SourcesPage /> },
          { path: 'schedule', element: <SchedulerPage /> },
          { path: 'runs', element: <FeedsRunsPage /> },
          { path: 'logs', element: <FeedsLogsPage /> },
        ],
      },
      { path: 'briefs', element: <BriefingsHistoryPage /> },
      { path: 'briefs/:id', element: <BriefingDetailPage /> },
      { path: 'stats', element: <StatsPage /> },
      { path: 'archive', element: <ArchivePage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: 'admin', element: <AdminPage /> },
      { path: 'analytics', element: <AnalyticsPage /> },

      /* Legacy route redirects — remove when each migration slice lands */
      { path: 'inbox', element: <Navigate to="/today" replace /> },
      { path: 'saved', element: <Navigate to="/starred" replace /> },
      { path: 'read', element: <Navigate to="/archive" replace /> },
      { path: 'skipped', element: <Navigate to="/archive" replace /> },
      { path: 'archived', element: <Navigate to="/archive" replace /> },
      { path: 'sources', element: <Navigate to="/feeds" replace /> },
      { path: 'scheduler', element: <Navigate to="/feeds/schedule" replace /> },

      { path: '*', element: <NotFound /> },
    ],
  },
];

const router = createBrowserRouter(routes);

export function AppRouter() {
  return (
    <AuthProvider>
      <FocusedArticleProvider>
        <RouterProvider router={router} />
      </FocusedArticleProvider>
    </AuthProvider>
  );
}
