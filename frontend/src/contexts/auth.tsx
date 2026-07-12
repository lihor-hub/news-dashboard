import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { queryClient } from '@/lib/queryClient';
import type { User } from '@/types';

export type AuthStatus = 'checking' | 'authenticated' | 'anonymous' | 'recoverable-error';

interface AuthState {
  user: User | null;
  status: AuthStatus;
  sessionExpired: boolean;
  setUser: (u: User | null) => void;
  setStatus: (status: AuthStatus) => void;
  resetAuth: (reason?: 'session-expired' | 'sign-out') => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>('checking');
  const [sessionExpired, setSessionExpired] = useState(false);

  const handleSetUser = useCallback((nextUser: User | null) => {
    setUser(nextUser);
    setStatus(nextUser ? 'authenticated' : 'anonymous');
    if (nextUser) setSessionExpired(false);
  }, []);

  const resetAuth = useCallback((reason?: 'session-expired' | 'sign-out') => {
    setUser(null);
    setStatus('anonymous');
    setSessionExpired(reason === 'session-expired');
    queryClient.clear();
  }, []);

  const value = useMemo(
    () => ({
      user,
      status,
      sessionExpired,
      setUser: handleSetUser,
      setStatus,
      resetAuth,
    }),
    [handleSetUser, resetAuth, sessionExpired, status, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
