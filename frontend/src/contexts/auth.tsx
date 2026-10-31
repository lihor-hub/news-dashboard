import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  useEffect,
  useRef,
  type ReactNode,
} from 'react';
import { queryClient } from '@/lib/queryClient';
import type { User } from '@/types';
import { changePrivateSession, privateSessionChanged } from '@/lib/privateSession';

export type AuthStatus = 'checking' | 'authenticated' | 'anonymous' | 'recoverable-error';

interface AuthState {
  user: User | null;
  status: AuthStatus;
  sessionExpired: boolean;
  setUser: (u: User | null) => Promise<void>;
  setStatus: (status: AuthStatus) => void;
  resetAuth: (reason?: 'session-expired' | 'sign-out') => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>('checking');
  const [sessionExpired, setSessionExpired] = useState(false);

  const authVersion = useRef(0);

  const clearMemory = useCallback(() => {
    authVersion.current += 1;
    setUser(null);
    setStatus('anonymous');
    void queryClient.cancelQueries();
    queryClient.clear();
  }, []);

  const handleSetUser = useCallback((nextUser: User | null) => {
    const version = ++authVersion.current;
    if (!nextUser) {
      setUser(null);
      setStatus('anonymous');
    } else {
      setStatus('checking');
    }
    void queryClient.cancelQueries();
    queryClient.clear();
    const transition = changePrivateSession(nextUser?.id ?? null);
    const publish = () => {
      if (version !== authVersion.current) return;
      setUser(nextUser);
      setStatus(nextUser ? 'authenticated' : 'anonymous');
      if (nextUser) setSessionExpired(false);
    };
    if (!('serviceWorker' in navigator) || !import.meta.env.PROD) publish();
    return transition.then(publish);
  }, []);

  const resetAuth = useCallback(
    (reason?: 'session-expired' | 'sign-out') => {
      clearMemory();
      setSessionExpired(reason === 'session-expired');
      void changePrivateSession(null).catch(() => {
        // Local state stays revoked even if an old/offline worker cannot acknowledge.
      });
    },
    [clearMemory]
  );

  useEffect(() => {
    window.addEventListener(privateSessionChanged, clearMemory);
    return () => window.removeEventListener(privateSessionChanged, clearMemory);
  }, [clearMemory]);

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
