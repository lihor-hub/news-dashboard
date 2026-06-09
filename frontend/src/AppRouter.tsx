import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { InboxPage } from './pages/InboxPage';
import { SavedPage } from './pages/SavedPage';
import { ReadPage } from './pages/ReadPage';
import { SkippedPage } from './pages/SkippedPage';
import { ArchivedPage } from './pages/ArchivedPage';
import { SourcesPage } from './pages/SourcesPage';
import { SchedulerPage } from './pages/SchedulerPage';
import { StatsPage } from './pages/StatsPage';
import { AskPage } from './pages/AskPage';

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/inbox" replace /> },
      { path: 'inbox', element: <InboxPage /> },
      { path: 'saved', element: <SavedPage /> },
      { path: 'read', element: <ReadPage /> },
      { path: 'skipped', element: <SkippedPage /> },
      { path: 'archived', element: <ArchivedPage /> },
      { path: 'sources', element: <SourcesPage /> },
      { path: 'scheduler', element: <SchedulerPage /> },
      { path: 'stats', element: <StatsPage /> },
      { path: 'ask', element: <AskPage /> },
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
