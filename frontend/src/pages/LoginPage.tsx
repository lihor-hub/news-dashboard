import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { fetchAuthConfig, loginUser, requestOtp, loginWithOtp, type AuthConfig } from '@/api';
import { useAuth } from '@/contexts/auth';
import { AppLogo } from '@/components/AppLogo';

type OtpStep = 'email' | 'code';
type LoginMode = 'password' | 'otp';

export function LoginPage() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/';

  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
  const [mode, setMode] = useState<LoginMode>('password');
  const [otpStep, setOtpStep] = useState<OtpStep>('email');

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [otpEmail, setOtpEmail] = useState('');
  const [otpCode, setOtpCode] = useState('');
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

  async function handlePasswordSubmit(e: FormEvent) {
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

  async function handleOtpEmailSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await requestOtp(otpEmail);
      setOtpStep('code');
    } catch {
      setError('Failed to send code. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  async function handleOtpCodeSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await loginWithOtp(otpEmail, otpCode);
      setUser(user);
      navigate(from, { replace: true });
    } catch {
      setError('Invalid or expired code. Please try again.');
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
          <AppLogo className="mx-auto size-10 rounded-xl" />
          <div>
            <h1 className="text-xl font-semibold text-foreground">Sign in</h1>
            <p className="mt-1 text-sm text-muted-foreground">Your private news platform</p>
          </div>
        </div>

        {keycloakLoginUrl ? (
          <div className="space-y-4">
            <a
              href={keycloakLoginUrl}
              className="flex w-full items-center justify-center rounded-md bg-foreground px-4 py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-90"
            >
              Sign in with Keycloak
            </a>
            {authConfig?.registration_url && (
              <div className="text-center">
                <a
                  href={authConfig.registration_url}
                  className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors underline underline-offset-4"
                >
                  Create Account
                </a>
              </div>
            )}
          </div>
        ) : mode === 'password' ? (
          <div className="space-y-4">
            <form onSubmit={(e) => void handlePasswordSubmit(e)} className="space-y-4">
              <div className="space-y-1">
                <label
                  htmlFor="username"
                  className="block text-xs font-medium text-muted-foreground"
                >
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
                <label
                  htmlFor="password"
                  className="block text-xs font-medium text-muted-foreground"
                >
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

            <div className="text-center">
              <button
                type="button"
                onClick={() => {
                  setMode('otp');
                  setError(null);
                }}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors underline underline-offset-4"
              >
                Use email code instead
              </button>
            </div>
          </div>
        ) : otpStep === 'email' ? (
          <div className="space-y-4">
            <form onSubmit={(e) => void handleOtpEmailSubmit(e)} className="space-y-4">
              <div className="space-y-1">
                <label
                  htmlFor="otp-email"
                  className="block text-xs font-medium text-muted-foreground"
                >
                  Email address
                </label>
                <input
                  id="otp-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={otpEmail}
                  onChange={(e) => setOtpEmail(e.target.value)}
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
                {loading ? 'Sending…' : 'Send code'}
              </button>
            </form>

            <div className="text-center">
              <button
                type="button"
                onClick={() => {
                  setMode('password');
                  setError(null);
                }}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors underline underline-offset-4"
              >
                Back to password sign in
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground text-center">
              A 6-digit code was sent to{' '}
              <span className="font-medium text-foreground">{otpEmail}</span>.
            </p>

            <form onSubmit={(e) => void handleOtpCodeSubmit(e)} className="space-y-4">
              <div className="space-y-1">
                <label
                  htmlFor="otp-code"
                  className="block text-xs font-medium text-muted-foreground"
                >
                  6-digit code
                </label>
                <input
                  id="otp-code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  required
                  autoFocus
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-subtle focus:outline-none focus:ring-2 focus:ring-ring tracking-widest text-center"
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
                {loading ? 'Verifying…' : 'Verify code'}
              </button>
            </form>

            <div className="text-center">
              <button
                type="button"
                onClick={() => {
                  setOtpStep('email');
                  setOtpCode('');
                  setError(null);
                }}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors underline underline-offset-4"
              >
                Resend code
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
