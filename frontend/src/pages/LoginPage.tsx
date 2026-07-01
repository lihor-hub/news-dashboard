import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { fetchAuthConfig, loginUser, requestOtp, loginWithOtp, type AuthConfig } from '@/api';
import { useAuth } from '@/contexts/auth';
import { AppLogo } from '@/components/AppLogo';

type OtpStep = 'email' | 'code';
type LoginMode = 'password' | 'otp';

export function LoginPage() {
  const { t } = useTranslation();
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
      setError(t('auth.invalid_username_or_password'));
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
      setError(t('auth.failed_to_send_code'));
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
      setError(t('auth.invalid_or_expired_code'));
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
            <h1 className="text-xl font-semibold text-foreground">{t('app.name')}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{t('app.tagline')}</p>
          </div>
        </div>

        {keycloakLoginUrl ? (
          <div className="space-y-4">
            <a
              href={keycloakLoginUrl}
              className="flex w-full items-center justify-center rounded-md bg-foreground px-4 py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-90"
            >
              {t('auth.sign_in_with_keycloak')}
            </a>
            {authConfig?.registration_url && (
              <div className="text-center">
                <a
                  href={authConfig.registration_url}
                  className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors underline underline-offset-4"
                >
                  {t('auth.create_account')}
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
                  {t('auth.username')}
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
                  {t('auth.password')}
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
                {loading ? t('auth.signing_in') : t('auth.sign_in')}
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
                {t('auth.use_email_code')}
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
                  {t('auth.email_address')}
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
                {loading ? t('auth.sending') : t('auth.send_code')}
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
                {t('auth.back_to_password')}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground text-center">
              {t('auth.a_6_digit_code_was_sent_to')}{' '}
              <span className="font-medium text-foreground">{otpEmail}</span>.
            </p>

            <form onSubmit={(e) => void handleOtpCodeSubmit(e)} className="space-y-4">
              <div className="space-y-1">
                <label
                  htmlFor="otp-code"
                  className="block text-xs font-medium text-muted-foreground"
                >
                  {t('auth.6_digit_code')}
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
                {loading ? t('auth.verifying') : t('auth.verify_code')}
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
                {t('auth.resend_code')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
