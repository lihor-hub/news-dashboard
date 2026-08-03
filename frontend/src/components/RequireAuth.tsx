import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { fetchMe, HttpError, sessionExpiredEvent } from '@/api';
import { useAuth } from '@/contexts/auth';
import { AppLogo } from './AppLogo';

interface Props {
  children: ReactNode;
}

export function RequireAuth({ children }: Props) {
  const { status, sessionExpired, setUser, setStatus, resetAuth } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [startupError, setStartupError] = useState(false);
  const intendedRoute = `${location.pathname}${location.search}${location.hash}`;

  useEffect(() => {
    setStatus('checking');
    setStartupError(false);
    fetchMe()
      .then((user) => {
        setUser(user);
      })
      .catch((error: unknown) => {
        if (isUnauthorized(error)) {
          setStatus('anonymous');
          // Always route to the in-app login page. Even when Keycloak is enabled,
          // the login page offers email OTP as the primary option with Keycloak as
          // a secondary choice, so we no longer redirect straight to Keycloak.
          void navigate('/login', { state: { from: intendedRoute }, replace: true });
          return;
        }
        setStatus('recoverable-error');
        setStartupError(true);
      });
    // Run once on mount only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    function handleSessionExpired() {
      if (location.pathname === '/login') return;
      resetAuth('session-expired');
      void navigate('/login', {
        state: { from: intendedRoute, sessionExpired: true },
        replace: true,
      });
    }

    window.addEventListener(sessionExpiredEvent, handleSessionExpired);
    return () => window.removeEventListener(sessionExpiredEvent, handleSessionExpired);
  }, [intendedRoute, location.pathname, navigate, resetAuth]);

  if (status === 'checking') return <AuthStatusPanel title="Checking your session" />;
  if (startupError || status === 'recoverable-error') {
    return (
      <AuthStatusPanel
        title="We could not verify your session"
        detail="Check your connection and retry. Your sign-in was not changed."
        onRetry={() => window.location.reload()}
      />
    );
  }
  if (sessionExpired) return <AuthStatusPanel title="Your session expired" />;
  return <>{children}</>;
}

function isUnauthorized(error: unknown): boolean {
  return error instanceof HttpError && error.status === 401;
}

function AuthStatusPanel({
  title,
  detail,
  onRetry,
}: {
  title: string;
  detail?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 text-center shadow-sm">
        <AppLogo className="mx-auto size-10 rounded-xl" />
        <h1 className="mt-4 text-lg font-semibold text-foreground">{title}</h1>
        {detail ? <p className="mt-2 text-sm text-muted-foreground">{detail}</p> : null}
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-4 rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
          >
            Retry
          </button>
        ) : null}
      </div>
    </div>
  );
}
