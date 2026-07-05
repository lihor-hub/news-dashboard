import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import './globals.css';
import { ErrorBoundary } from './components/ErrorBoundary';
import { initErrorTracking } from './lib/errorTracking';
import { initTheme } from './lib/theme';
import { queryClient } from './lib/queryClient';
import { AppRouter } from './AppRouter';
import i18n from '@/lib/i18n';
import { initLanguageDirection } from '@/lib/languages';

initTheme();
initLanguageDirection(i18n);
void initErrorTracking();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AppRouter />
        <Toaster position="bottom-center" toastOptions={{ className: '!text-sm' }} />
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>
);
