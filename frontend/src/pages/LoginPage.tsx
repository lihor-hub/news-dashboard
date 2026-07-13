import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  HttpError,
  fetchAuthConfig,
  loginUser,
  requestOtp,
  loginWithOtp,
  type AuthConfig,
} from '@/api';
import { useAuth } from '@/contexts/auth';
import { AppLogo } from '@/components/AppLogo';

type OtpStep = 'email' | 'code';
type LoginMode = 'password' | 'otp';
type AuthConfigStatus = 'loading' | 'ready' | 'error';
type AuthAction = 'password' | 'otp-request' | 'otp-verify';

const OTP_RESEND_COOLDOWN_SECONDS = 1;

function isNetworkError(error: unknown) {
  return error instanceof TypeError;
}

const OAUTH_ERROR_KEYS: Record<string, string> = {
  oauth_state: 'auth.error_oauth_state',
  oauth_code: 'auth.error_oauth_code',
  oauth_denied: 'auth.error_oauth_denied',
  oauth_exchange_failed: 'auth.error_oauth_exchange_failed',
};

function oauthErrorKey(authError: string) {
  return OAUTH_ERROR_KEYS[authError] ?? 'auth.error_oauth_generic';
}

function withNextParam(url: string, from: string) {
  if (from === '/') return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}next=${encodeURIComponent(from)}`;
}

function authErrorKey(action: AuthAction, error: unknown) {
  if (isNetworkError(error)) return 'auth.error_network';

  if (error instanceof HttpError) {
    if (error.status === 429) return 'auth.error_throttled';
    if (error.status >= 500) return 'auth.error_server';
    if (action === 'password' && error.status === 409) return 'auth.error_password_disabled';
    if (action === 'password' && error.status === 401) {
      return 'auth.invalid_username_or_password';
    }
    if (action === 'otp-verify' && error.status === 401) {
      return 'auth.invalid_or_expired_code';
    }
  }

  if (action === 'otp-request') return 'auth.failed_to_send_code';
  if (action === 'otp-verify') return 'auth.invalid_or_expired_code';
  return 'auth.invalid_username_or_password';
}

export function LoginPage() {
  const { t } = useTranslation();
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = location.state as { from?: string; sessionExpired?: boolean } | null;
  const from = locationState?.from ?? '/';
  const oauthError = new URLSearchParams(location.search).get('auth_error');

  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null);
  const [authConfigStatus, setAuthConfigStatus] = useState<AuthConfigStatus>('loading');
  const [mode, setMode] = useState<LoginMode>('password');
  const [otpStep, setOtpStep] = useState<OtpStep>('email');

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [otpEmail, setOtpEmail] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [error, setError] = useState<string | null>(
    locationState?.sessionExpired ? 'Your session expired. Sign in again to continue.' : null
  );
  const [loading, setLoading] = useState(false);
  const [resendCooldown, setResendCooldown] = useState(0);

  useEffect(() => {
    setAuthConfigStatus('loading');
    void fetchAuthConfig()
      .then((config) => {
        setAuthConfig(config);
        setAuthConfigStatus('ready');
        // When Keycloak SSO is enabled, password login is disabled server-side,
        // so default to the email OTP flow (Keycloak stays as a secondary option).
        if (config.provider === 'keycloak') {
          setMode('otp');
        }
      })
      .catch(() => setAuthConfigStatus('error'));
  }, []);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = window.setTimeout(() => setResendCooldown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [resendCooldown]);

  async function loadAuthConfig() {
    setError(null);
    setAuthConfigStatus('loading');
    try {
      const config = await fetchAuthConfig();
      setAuthConfig(config);
      setAuthConfigStatus('ready');
      setMode(config.provider === 'keycloak' ? 'otp' : 'password');
    } catch {
      setAuthConfigStatus('error');
    }
  }

  async function handlePasswordSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await loginUser(username, password);
      setUser(user);
      void navigate(from, { replace: true });
    } catch (err) {
      setError(t(authErrorKey('password', err)));
    } finally {
      setLoading(false);
    }
  }

  async function sendOtpCode() {
    await requestOtp(otpEmail);
    setOtpCode('');
    setOtpStep('code');
    setResendCooldown(OTP_RESEND_COOLDOWN_SECONDS);
  }

  async function handleOtpEmailSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await sendOtpCode();
    } catch (err) {
      setError(t(authErrorKey('otp-request', err)));
    } finally {
      setLoading(false);
    }
  }

  async function handleOtpResend() {
    setError(null);
    setLoading(true);
    try {
      await sendOtpCode();
    } catch (err) {
      setError(t(authErrorKey('otp-request', err)));
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
      void navigate(from, { replace: true });
    } catch (err) {
      setError(t(authErrorKey('otp-verify', err)));
    } finally {
      setLoading(false);
    }
  }

  const keycloakEnabled = authConfig?.provider === 'keycloak';
  const keycloakLoginUrl = keycloakEnabled
    ? withNextParam(authConfig.login_url ?? '/auth/login', from)
    : null;

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

        {oauthError && (
          <div className="mb-4 space-y-2 rounded-md border border-border bg-surface p-3 text-center">
            <p role="alert" className="text-xs text-[color:var(--err)]">
              {t(oauthErrorKey(oauthError))}
            </p>
            <button
              type="button"
              onClick={() => void navigate('/', { replace: true })}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors underline underline-offset-4"
            >
              {t('auth.return_home')}
            </button>
          </div>
        )}

        {authConfigStatus === 'loading' ? (
          <div role="status" className="text-center text-sm text-muted-foreground">
            {t('auth.loading_options')}
          </div>
        ) : authConfigStatus === 'error' ? (
          <div className="space-y-4">
            <p role="alert" className="text-sm text-[color:var(--err)]">
              {t('auth.config_error')}
            </p>
            <button
              type="button"
              onClick={() => void loadAuthConfig()}
              className="w-full rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity disabled:opacity-50"
            >
              {t('auth.retry')}
            </button>
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

            {keycloakLoginUrl ? (
              <div className="space-y-3 border-t border-border pt-4">
                <a
                  href={keycloakLoginUrl}
                  className="flex w-full items-center justify-center rounded-md border border-border bg-surface px-4 py-2.5 text-sm font-medium text-foreground transition-opacity hover:opacity-90"
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
            ) : (
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
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground text-center">
              {t('auth.a_6_digit_code_was_sent_to')}{' '}
              <span className="font-medium text-foreground">{otpEmail}</span>.
            </p>
            <p className="text-xs text-muted-foreground text-center">{t('auth.code_expires_in')}</p>

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

            <div className="flex items-center justify-center gap-3 text-center">
              <button
                type="button"
                onClick={() => void handleOtpResend()}
                disabled={loading || resendCooldown > 0}
                className="text-sm text-muted-foreground transition-colors underline underline-offset-4 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
              >
                {resendCooldown > 0
                  ? t('auth.resend_available_soon', { seconds: resendCooldown })
                  : t('auth.resend_code')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setOtpStep('email');
                  setOtpCode('');
                  setError(null);
                }}
                className="text-sm text-muted-foreground hover:text-foreground transition-colors underline underline-offset-4"
              >
                {t('auth.change_email')}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
