import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import './globals.css';
import { initTheme } from './lib/theme';
import { queryClient } from './lib/queryClient';
import { AppRouter } from './AppRouter';

initTheme();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AppRouter />
      <Toaster position="bottom-center" toastOptions={{ className: '!text-sm' }} />
    </QueryClientProvider>
  </React.StrictMode>
);
