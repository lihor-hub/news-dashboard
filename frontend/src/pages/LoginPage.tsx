import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { fetchAuthConfig, loginUser, type AuthConfig } from '@/api';
import { useAuth } from '@/contexts/auth';

export function LoginPage() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/';

  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void fetchAuthConfig()
      .then(setAuthConfig)
      .catch(() =>
        setAuthConfig({
          provider: 'password',
          keycloak_enabled: false,
          login_url: null,
          logout_url: '/api/auth/logout',
        })
      );
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await loginUser(username, password);
      setUser(user);
      navigate(from, { replace: true });
    } catch {
      setError('Invalid username or password.');
    } finally {
      setLoading(false);
    }
  }

  const keycloakLoginUrl =
    authConfig?.provider === 'keycloak' ? (authConfig.login_url ?? '/auth/login') : null;

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-sm">
        <div className="mb-6 text-center space-y-2">
          <div className="mx-auto size-10 rounded-xl bg-foreground/90 grid place-items-center text-background text-sm font-bold tracking-tight">
            RD
          </div>
          <div>
            <h1 className="text-xl font-semibold text-foreground">Sign in</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Private radar dashboard for news.example.com
            </p>
          </div>
        </div>

        {keycloakLoginUrl ? (
          <a
            href={keycloakLoginUrl}
            className="flex w-full items-center justify-center rounded-md bg-foreground px-4 py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-90"
          >
            Sign in with Keycloak
          </a>
        ) : (
          <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
            <div className="space-y-1">
              <label htmlFor="username" className="block text-xs font-medium text-muted-foreground">
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-subtle focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            <div className="space-y-1">
              <label htmlFor="password" className="block text-xs font-medium text-muted-foreground">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-subtle focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {error && (
              <p role="alert" className="text-xs text-[color:var(--err)]">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity disabled:opacity-50"
            >
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
