import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider, Navigate, type RouteObject } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { FocusedArticleProvider } from './contexts/focusedArticle';
import { AuthProvider } from './contexts/auth';
import { RequireAuth } from './components/RequireAuth';
import { AppShell } from './components/AppShell';
import { LoginPage } from './pages/LoginPage';
import { BriefPage } from './pages/BriefPage';
import { InboxPage } from './pages/InboxPage';
import { SharedPage } from './pages/SharedPage';
import { SharedDetailPage } from './pages/SharedDetailPage';
import { LaterPage } from './pages/LaterPage';
import { StarredPage } from './pages/StarredPage';
import { FeedsPage } from './pages/FeedsPage';
import { SourcesPage } from './pages/SourcesPage';
import { ArchivePage } from './pages/ArchivePage';

const SearchPage = lazy(() =>
  import('./pages/SearchPage').then((m) => ({ default: m.SearchPage }))
);
const AskPage = lazy(() => import('./pages/AskPage').then((m) => ({ default: m.AskPage })));
const SchedulerPage = lazy(() =>
  import('./pages/SchedulerPage').then((m) => ({ default: m.SchedulerPage }))
);
const FeedsRunsPage = lazy(() =>
  import('./pages/FeedsRunsPage').then((m) => ({ default: m.FeedsRunsPage }))
);
const FeedsLogsPage = lazy(() =>
  import('./pages/FeedsLogsPage').then((m) => ({ default: m.FeedsLogsPage }))
);
const StatsPage = lazy(() => import('./pages/StatsPage').then((m) => ({ default: m.StatsPage })));
const ReadingDnaPage = lazy(() =>
  import('./pages/ReadingDnaPage').then((m) => ({ default: m.ReadingDnaPage }))
);
const SettingsPage = lazy(() =>
  import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage }))
);
const ArticlePage = lazy(() =>
  import('./pages/ArticlePage').then((m) => ({ default: m.ArticlePage }))
);
const AdminPage = lazy(() => import('./pages/AdminPage').then((m) => ({ default: m.AdminPage })));
const AnalyticsPage = lazy(() =>
  import('./pages/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage }))
);
const BriefingsHistoryPage = lazy(() =>
  import('./pages/BriefingsHistoryPage').then((m) => ({ default: m.BriefingsHistoryPage }))
);
const BriefingDetailPage = lazy(() =>
  import('./pages/BriefingDetailPage').then((m) => ({ default: m.BriefingDetailPage }))
);
const TopicMapPage = lazy(() =>
  import('./pages/TopicMapPage').then((m) => ({ default: m.TopicMapPage }))
);

function PageLoader() {
  return (
    <div className="flex min-h-[50vh] flex-1 items-center justify-center p-8">
      <Loader2 className="text-muted-foreground size-6 animate-spin" />
    </div>
  );
}

function withSuspense(Component: React.ComponentType) {
  return (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  );
}

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
    element: <RequireAuth>{withSuspense(ArticlePage)}</RequireAuth>,
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
      { path: 'shared/:shareId', element: <SharedDetailPage /> },
      { path: 'search', element: withSuspense(SearchPage) },
      { path: 'ask', element: withSuspense(AskPage) },
      {
        path: 'feeds',
        element: <FeedsPage />,
        children: [
          { index: true, element: <SourcesPage /> },
          { path: 'schedule', element: withSuspense(SchedulerPage) },
          { path: 'runs', element: withSuspense(FeedsRunsPage) },
          { path: 'logs', element: withSuspense(FeedsLogsPage) },
        ],
      },
      { path: 'briefs', element: withSuspense(BriefingsHistoryPage) },
      { path: 'briefs/:id', element: withSuspense(BriefingDetailPage) },
      { path: 'topic-map', element: withSuspense(TopicMapPage) },
      { path: 'stats', element: withSuspense(StatsPage) },
      { path: 'reading-dna', element: withSuspense(ReadingDnaPage) },
      { path: 'archive', element: <ArchivePage /> },
      { path: 'settings', element: withSuspense(SettingsPage) },
      { path: 'admin', element: withSuspense(AdminPage) },
      { path: 'analytics', element: withSuspense(AnalyticsPage) },

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
