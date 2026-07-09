import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider, Navigate, type RouteObject } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { FocusedArticleProvider } from './contexts/focusedArticle';
import { AuthProvider } from './contexts/auth';
import { ListenQueueProvider } from './contexts/listenQueue';
import { RequireAuth } from './components/RequireAuth';
import { AppShell } from './components/AppShell';
import { LoginPage } from './pages/LoginPage';
import { BriefPage } from './pages/BriefPage';
import { FeedsPage } from './pages/FeedsPage';
import { useAuth } from './contexts/auth';
import { ShieldAlert } from 'lucide-react';

const InboxPage = lazy(() => import('./pages/InboxPage').then((m) => ({ default: m.InboxPage })));
const SharedPage = lazy(() =>
  import('./pages/SharedPage').then((m) => ({ default: m.SharedPage }))
);
const SharedDetailPage = lazy(() =>
  import('./pages/SharedDetailPage').then((m) => ({ default: m.SharedDetailPage }))
);
const LaterPage = lazy(() => import('./pages/LaterPage').then((m) => ({ default: m.LaterPage })));
const StarredPage = lazy(() =>
  import('./pages/StarredPage').then((m) => ({ default: m.StarredPage }))
);
const SourcesPage = lazy(() =>
  import('./pages/SourcesPage').then((m) => ({ default: m.SourcesPage }))
);
const ArchivePage = lazy(() =>
  import('./pages/ArchivePage').then((m) => ({ default: m.ArchivePage }))
);
const CollectionsPage = lazy(() =>
  import('./pages/CollectionsPage').then((m) => ({ default: m.CollectionsPage }))
);
const CollectionDetailPage = lazy(() =>
  import('./pages/CollectionDetailPage').then((m) => ({ default: m.CollectionDetailPage }))
);
const ShareTargetPage = lazy(() =>
  import('./pages/ShareTargetPage').then((m) => ({ default: m.ShareTargetPage }))
);
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
const ReadingListPage = lazy(() =>
  import('./pages/ReadingListPage').then((m) => ({ default: m.ReadingListPage }))
);
const OfflineSavedPage = lazy(() =>
  import('./pages/OfflineSavedPage').then((m) => ({ default: m.OfflineSavedPage }))
);
const LearnPage = lazy(() => import('./pages/LearnPage').then((m) => ({ default: m.LearnPage })));
const LessonLibraryPage = lazy(() =>
  import('./pages/LessonLibraryPage').then((m) => ({ default: m.LessonLibraryPage }))
);
const LessonDetailPage = lazy(() =>
  import('./pages/LessonDetailPage').then((m) => ({ default: m.LessonDetailPage }))
);
const WeeklyRecapPage = lazy(() =>
  import('./pages/WeeklyRecapPage').then((m) => ({ default: m.WeeklyRecapPage }))
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
const AiStatsPage = lazy(() =>
  import('./pages/AiStatsPage').then((m) => ({ default: m.AiStatsPage }))
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

export function AdminOnlyGuard({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (!user?.is_admin) {
    return (
      <div className="mx-auto flex min-h-[50vh] max-w-md flex-col items-center justify-center gap-3 text-center">
        <ShieldAlert className="size-8 text-muted-foreground" />
        <h1 className="text-lg font-semibold text-foreground">Admins only</h1>
        <p className="text-sm text-muted-foreground">
          You need an administrator account to access this page.
        </p>
      </div>
    );
  }
  return <>{children}</>;
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
    path: '/shared/:shareId/article',
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
      { path: 'today', element: withSuspense(InboxPage) },
      { path: 'later', element: withSuspense(LaterPage) },
      { path: 'starred', element: withSuspense(StarredPage) },
      { path: 'shared', element: withSuspense(SharedPage) },
      { path: 'shared/:shareId', element: withSuspense(SharedDetailPage) },
      { path: 'search', element: withSuspense(SearchPage) },
      { path: 'ask', element: withSuspense(AskPage) },
      {
        path: 'feeds',
        element: <FeedsPage />,
        children: [
          { index: true, element: withSuspense(SourcesPage) },
          {
            path: 'schedule',
            element: (
              <AdminOnlyGuard>
                <Suspense fallback={<PageLoader />}>
                  <SchedulerPage />
                </Suspense>
              </AdminOnlyGuard>
            ),
          },
          {
            path: 'runs',
            element: (
              <AdminOnlyGuard>
                <Suspense fallback={<PageLoader />}>
                  <FeedsRunsPage />
                </Suspense>
              </AdminOnlyGuard>
            ),
          },
          {
            path: 'logs',
            element: (
              <AdminOnlyGuard>
                <Suspense fallback={<PageLoader />}>
                  <FeedsLogsPage />
                </Suspense>
              </AdminOnlyGuard>
            ),
          },
        ],
      },
      { path: 'briefs', element: withSuspense(BriefingsHistoryPage) },
      { path: 'briefs/:id', element: withSuspense(BriefingDetailPage) },
      { path: 'topic-map', element: withSuspense(TopicMapPage) },
      { path: 'ai-stats', element: withSuspense(AiStatsPage) },
      {
        path: 'stats',
        element: (
          <AdminOnlyGuard>
            <Suspense fallback={<PageLoader />}>
              <StatsPage />
            </Suspense>
          </AdminOnlyGuard>
        ),
      },
      { path: 'reading-dna', element: withSuspense(ReadingDnaPage) },
      { path: 'reading-list', element: withSuspense(ReadingListPage) },
      { path: 'learn', element: withSuspense(LearnPage) },
      { path: 'learn/library', element: withSuspense(LessonLibraryPage) },
      { path: 'learn/:id', element: withSuspense(LessonDetailPage) },
      { path: 'offline-saved', element: withSuspense(OfflineSavedPage) },
      { path: 'recap', element: withSuspense(WeeklyRecapPage) },
      { path: 'archive', element: withSuspense(ArchivePage) },
      { path: 'collections', element: withSuspense(CollectionsPage) },
      { path: 'collections/:tagId', element: withSuspense(CollectionDetailPage) },
      { path: 'settings', element: withSuspense(SettingsPage) },
      { path: 'share-target', element: withSuspense(ShareTargetPage) },
      { path: 'admin', element: withSuspense(AdminPage) },
      {
        path: 'analytics',
        element: (
          <AdminOnlyGuard>
            <Suspense fallback={<PageLoader />}>
              <AnalyticsPage />
            </Suspense>
          </AdminOnlyGuard>
        ),
      },

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
        <ListenQueueProvider>
          <RouterProvider router={router} />
        </ListenQueueProvider>
      </FocusedArticleProvider>
    </AuthProvider>
  );
}
