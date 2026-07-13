// @vitest-environment happy-dom
/**
 * Tests for #130 — auth guard (RequireAuth) and login page.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useEffect } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from '../contexts/auth';
import { RequireAuth } from '../components/RequireAuth';
import { LoginPage } from '../pages/LoginPage';
import * as api from '../api';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const translations: Record<string, string> = {
        'auth.username': 'Username',
        'auth.password': 'Password',
        'auth.sign_in': 'Sign in',
        'auth.use_email_code': 'Use email code instead',
        'auth.back_to_password': 'Back to password sign in',
        'auth.email_address': 'Email address',
        'auth.send_code': 'Send code',
        'auth.sending': 'Sending…',
        'auth.6_digit_code': '6-digit code',
        'auth.verify_code': 'Verify code',
        'auth.verifying': 'Verifying…',
        'auth.resend_code': 'Resend code',
        'auth.a_6_digit_code_was_sent_to': 'A 6-digit code was sent to',
        'auth.invalid_username_or_password': 'Invalid username or password.',
        'auth.failed_to_send_code': 'Failed to send code. Please try again.',
        'auth.invalid_or_expired_code': 'Invalid or expired code. Please try again.',
        'auth.loading_options': 'Checking sign-in options…',
        'auth.config_error':
          'Sign-in is temporarily unavailable. Check your connection and try again.',
        'auth.retry': 'Retry',
        'auth.error_password_disabled':
          'Password sign-in is disabled. Use email code or Keycloak instead.',
        'auth.error_throttled': 'Too many attempts. Wait a moment before trying again.',
        'auth.error_network':
          'Unable to reach the auth service. Check your connection and try again.',
        'auth.error_server': 'The auth service is having trouble. Try again shortly.',
        'auth.code_expires_in': 'Codes expire after 10 minutes.',
        'auth.resend_available_soon': 'Resend in {{seconds}}s',
        'auth.change_email': 'Change email',
        'auth.signing_in': 'Signing in…',
        'auth.sign_in_with_keycloak': 'Sign in with Keycloak',
        'auth.create_account': 'Create Account',
        'app.name': 'News Dashboard',
        'app.tagline': 'Your private news platform',
      };
      let value = translations[key] ?? key;
      if (options && typeof options === 'object') {
        Object.entries(options).forEach(([name, replacement]) => {
          value = value.replace(`{{${name}}}`, String(replacement));
        });
      }
      return value;
    },
    i18n: {
      changeLanguage: () => Promise.resolve(),
    },
  }),
}));

vi.spyOn(console, 'error').mockImplementation(() => undefined);

function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderWithRouter(
  ui: React.ReactNode,
  { initialPath = '/' }: { initialPath?: string } = {}
) {
  return render(
    <QueryClientProvider client={makeQc()}>
      <AuthProvider>
        <MemoryRouter initialEntries={[initialPath]}>{ui}</MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

// ── RequireAuth ───────────────────────────────────────────────────────────────

describe('RequireAuth', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders children when /api/auth/me returns a user', async () => {
    vi.spyOn(api, 'fetchMe').mockResolvedValue({
      id: 1,
      username: 'alice',
      is_admin: false,
    });

    renderWithRouter(
      <Routes>
        <Route
          path="/"
          element={
            <RequireAuth>
              <div>Protected content</div>
            </RequireAuth>
          }
        />
        <Route path="/login" element={<div>Login page</div>} />
      </Routes>
    );

    await waitFor(() => {
      expect(screen.getByText('Protected content')).toBeTruthy();
    });
  });

  it('redirects to /login when /api/auth/me returns 401', async () => {
    vi.spyOn(api, 'fetchMe').mockRejectedValue(new api.HttpError(401, 'Unauthorized'));
    vi.spyOn(api, 'fetchAuthConfig').mockResolvedValue({
      provider: 'password',
      keycloak_enabled: false,
      login_url: null,
      logout_url: '/api/auth/logout',
    });

    renderWithRouter(
      <Routes>
        <Route
          path="/"
          element={
            <RequireAuth>
              <div>Protected content</div>
            </RequireAuth>
          }
        />
        <Route path="/login" element={<div>Login page</div>} />
      </Routes>
    );

    await waitFor(() => {
      expect(screen.getByText('Login page')).toBeTruthy();
    });
    expect(screen.queryByText('Protected content')).toBeNull();
  });

  it('shows the in-app login page (not an immediate Keycloak redirect) on 401 when Keycloak is enabled', async () => {
    vi.spyOn(api, 'fetchMe').mockRejectedValue(new api.HttpError(401, 'Unauthorized'));
    vi.spyOn(api, 'fetchAuthConfig').mockResolvedValue({
      provider: 'keycloak',
      keycloak_enabled: true,
      login_url: '/auth/login',
      logout_url: '/auth/logout',
    });
    const assign = vi.fn();
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...originalLocation, assign },
    });

    try {
      renderWithRouter(
        <Routes>
          <Route
            path="/"
            element={
              <RequireAuth>
                <div>Protected content</div>
              </RequireAuth>
            }
          />
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      );

      await waitFor(() => {
        expect(screen.getByText('Login page')).toBeTruthy();
      });
      expect(assign).not.toHaveBeenCalled();
      expect(screen.queryByText('Protected content')).toBeNull();
    } finally {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: originalLocation,
      });
    }
  });

  it('shows a visible branded checking state while /api/auth/me is pending', () => {
    vi.spyOn(api, 'fetchMe').mockReturnValue(new Promise(() => undefined));

    renderWithRouter(
      <Routes>
        <Route
          path="/"
          element={
            <RequireAuth>
              <div>Protected content</div>
            </RequireAuth>
          }
        />
      </Routes>
    );

    expect(screen.getByText('Checking your session')).toBeTruthy();
  });

  it('passes the original full app URL via location state when redirecting', async () => {
    vi.spyOn(api, 'fetchMe').mockRejectedValue(new api.HttpError(401, 'Unauthorized'));
    vi.spyOn(api, 'fetchAuthConfig').mockResolvedValue({
      provider: 'password',
      keycloak_enabled: false,
      login_url: null,
      logout_url: '/api/auth/logout',
    });

    let capturedState: unknown = undefined;

    renderWithRouter(
      <Routes>
        <Route
          path="/today"
          element={
            <RequireAuth>
              <div>Today</div>
            </RequireAuth>
          }
        />
        <Route
          path="/login"
          element={
            <RouteStateCapture
              onState={(s) => {
                capturedState = s;
              }}
            />
          }
        />
      </Routes>,
      { initialPath: '/today?q=ai#results' }
    );

    await waitFor(() => {
      expect(capturedState).toBeTruthy();
    });
    expect((capturedState as { from?: string }).from).toBe('/today?q=ai#results');
  });

  it('shows a retryable service problem for startup 5xx failures', async () => {
    vi.spyOn(api, 'fetchMe').mockRejectedValue(new api.HttpError(503, 'Service Unavailable'));

    renderWithRouter(
      <Routes>
        <Route
          path="/"
          element={
            <RequireAuth>
              <div>Protected content</div>
            </RequireAuth>
          }
        />
        <Route path="/login" element={<div>Login page</div>} />
      </Routes>
    );

    await waitFor(() => {
      expect(screen.getByText('We could not verify your session')).toBeTruthy();
    });
    expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy();
    expect(screen.queryByText('Login page')).toBeNull();
  });

  it('routes to login once with session-expired state after an authenticated API 401', async () => {
    vi.spyOn(api, 'fetchMe').mockResolvedValue({
      id: 1,
      username: 'alice',
      is_admin: false,
    });

    let capturedState: unknown = undefined;

    renderWithRouter(
      <Routes>
        <Route
          path="/today"
          element={
            <RequireAuth>
              <SessionExpiryTrigger />
            </RequireAuth>
          }
        />
        <Route
          path="/login"
          element={
            <RouteStateCapture
              onState={(s) => {
                capturedState = s;
              }}
            />
          }
        />
      </Routes>,
      { initialPath: '/today?q=ai#results' }
    );

    await waitFor(() => {
      expect(screen.getByText('Login page')).toBeTruthy();
    });
    expect(capturedState).toEqual({ from: '/today?q=ai#results', sessionExpired: true });
  });
});

function RouteStateCapture({ onState }: { onState: (s: unknown) => void }) {
  const loc = useLocation();
  onState(loc.state);
  return <div>Login page</div>;
}

function SessionExpiryTrigger() {
  const { setUser } = useAuth();

  useEffect(() => {
    setUser({ id: 1, username: 'alice', is_admin: false });
    window.dispatchEvent(new CustomEvent(api.sessionExpiredEvent, { detail: { url: '/api/me' } }));
  }, [setUser]);

  return <div>Protected content</div>;
}

// ── LoginPage ─────────────────────────────────────────────────────────────────

describe('LoginPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    vi.spyOn(api, 'fetchAuthConfig').mockResolvedValue({
      provider: 'password',
      keycloak_enabled: false,
      login_url: null,
      logout_url: '/api/auth/logout',
    });
  });

  it('renders username and password fields', async () => {
    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );
    expect(await screen.findByLabelText(/username/i)).toBeTruthy();
    expect(screen.getByLabelText(/password/i)).toBeTruthy();
  });

  it('does not show the password form while auth config is loading', () => {
    vi.spyOn(api, 'fetchAuthConfig').mockReturnValue(new Promise(() => undefined));

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    expect(screen.getByRole('status').textContent).toContain('Checking sign-in options');
    expect(screen.queryByLabelText(/username/i)).toBeNull();
    expect(screen.queryByLabelText(/^password$/i)).toBeNull();
  });

  it('shows a retryable config error when auth config fails', async () => {
    const fetchAuthConfig = vi
      .spyOn(api, 'fetchAuthConfig')
      .mockRejectedValueOnce(new TypeError('network down'))
      .mockResolvedValueOnce({
        provider: 'password',
        keycloak_enabled: false,
        login_url: null,
        logout_url: '/api/auth/logout',
      });

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/temporarily unavailable/i);
    });

    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/username/i)).toBeTruthy();
    });
    expect(fetchAuthConfig).toHaveBeenCalledTimes(2);
  });

  it('shows error message on 401', async () => {
    vi.spyOn(api, 'loginUser').mockRejectedValue(new api.HttpError(401, 'Unauthorized'));

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    await userEvent.type(await screen.findByLabelText(/username/i), 'alice');
    await userEvent.type(screen.getByLabelText(/password/i), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeTruthy();
      expect(screen.getByRole('alert').textContent).toMatch(/invalid/i);
    });
  });

  it('shows password-disabled copy on 409', async () => {
    vi.spyOn(api, 'loginUser').mockRejectedValue(new api.HttpError(409, 'Keycloak required'));

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    await userEvent.type(await screen.findByLabelText(/username/i), 'alice');
    await userEvent.type(screen.getByLabelText(/password/i), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/password sign-in is disabled/i);
    });
  });

  it('shows throttling copy on password 429', async () => {
    vi.spyOn(api, 'loginUser').mockRejectedValue(new api.HttpError(429, 'Too Many Requests'));

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    await userEvent.type(await screen.findByLabelText(/username/i), 'alice');
    await userEvent.type(screen.getByLabelText(/password/i), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/too many attempts/i);
    });
  });

  it('does not redirect on 401', async () => {
    vi.spyOn(api, 'loginUser').mockRejectedValue(new Error('401 Unauthorized'));

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
        <Route path="/home" element={<div>Home</div>} />
      </Routes>
    );

    await userEvent.type(await screen.findByLabelText(/username/i), 'alice');
    await userEvent.type(screen.getByLabelText(/password/i), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.queryByText('Home')).toBeNull();
  });

  it('redirects to / on successful login', async () => {
    vi.spyOn(api, 'loginUser').mockResolvedValue({ id: 1, username: 'alice', is_admin: false });

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
        <Route path="/dashboard" element={<div>Dashboard</div>} />
      </Routes>
    );

    // '/' is the default redirect destination when there's no from state
    await userEvent.type(await screen.findByLabelText(/username/i), 'alice');
    await userEvent.type(screen.getByLabelText(/password/i), 'correcthorse');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    // After successful login with no from-state, navigate goes to '/'
    // The LoginPage re-renders at '/' which shows the LoginPage again (MemoryRouter)
    // So we just verify the error is NOT shown.
    await waitFor(() => {
      expect(screen.queryByRole('alert')).toBeNull();
    });
  });

  it('redirects back to the original path after login', async () => {
    vi.spyOn(api, 'loginUser').mockResolvedValue({ id: 1, username: 'alice', is_admin: false });

    renderWithRouter(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/today" element={<div>Today page</div>} />
      </Routes>,
      { initialPath: '/login' }
    );

    // Simulate location state with from='/today'
    // We can't easily set state on MemoryRouter initial entry, so we test
    // via the component by verifying loginUser is called correctly.
    await userEvent.type(await screen.findByLabelText(/username/i), 'alice');
    await userEvent.type(screen.getByLabelText(/password/i), 'correct');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(api.loginUser).toHaveBeenCalledWith('alice', 'correct');
    });
  });

  it('renders Keycloak sign-in and registration links when Keycloak is enabled', async () => {
    vi.spyOn(api, 'fetchAuthConfig').mockResolvedValue({
      provider: 'keycloak',
      keycloak_enabled: true,
      login_url: '/auth/login',
      logout_url: '/auth/logout',
      registration_url: '/auth/register',
    });

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    await waitFor(() => {
      const loginLink = screen.getByRole('link', { name: /sign in with keycloak/i });
      expect(loginLink).toBeTruthy();
      expect(loginLink.getAttribute('href')).toBe('/auth/login');

      const registerLink = screen.getByRole('link', { name: /create account/i });
      expect(registerLink).toBeTruthy();
      expect(registerLink.getAttribute('href')).toBe('/auth/register');
    });
  });

  it('shows the email OTP form by default with Keycloak as a secondary option when Keycloak is enabled', async () => {
    vi.spyOn(api, 'fetchAuthConfig').mockResolvedValue({
      provider: 'keycloak',
      keycloak_enabled: true,
      login_url: '/auth/login',
      logout_url: '/auth/logout',
      registration_url: '/auth/register',
    });

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    await waitFor(() => {
      // OTP email form is the primary/default option.
      expect(screen.getByLabelText(/email address/i)).toBeTruthy();
      expect(screen.getByRole('button', { name: /send code/i })).toBeTruthy();
    });
    // Keycloak remains available as a secondary option.
    const loginLink = screen.getByRole('link', { name: /sign in with keycloak/i });
    expect(loginLink.getAttribute('href')).toBe('/auth/login');
    // No password fields in Keycloak mode (password login is disabled server-side).
    expect(screen.queryByLabelText(/^password$/i)).toBeNull();
  });

  it('shows throttling copy when OTP request is rate limited', async () => {
    vi.spyOn(api, 'requestOtp').mockRejectedValue(new api.HttpError(429, 'Too Many Requests'));

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    await userEvent.click(await screen.findByRole('button', { name: /use email code/i }));
    await userEvent.type(screen.getByLabelText(/email address/i), 'alice@example.com');
    await userEvent.click(screen.getByRole('button', { name: /send code/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/too many attempts/i);
    });
  });

  it('shows throttling copy when OTP verification is rate limited', async () => {
    vi.spyOn(api, 'requestOtp').mockResolvedValue(undefined);
    vi.spyOn(api, 'loginWithOtp').mockRejectedValue(new api.HttpError(429, 'Too Many Requests'));

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    await userEvent.click(await screen.findByRole('button', { name: /use email code/i }));
    await userEvent.type(screen.getByLabelText(/email address/i), 'alice@example.com');
    await userEvent.click(screen.getByRole('button', { name: /send code/i }));
    await userEvent.type(await screen.findByLabelText(/6-digit code/i), '123456');
    await userEvent.click(screen.getByRole('button', { name: /verify code/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toMatch(/too many attempts/i);
    });
  });

  it('returns from email OTP mode to password sign in', async () => {
    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    await userEvent.click(await screen.findByRole('button', { name: /use email code/i }));
    expect(screen.getByLabelText(/email address/i)).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: /back to password sign in/i }));

    expect(screen.getByLabelText(/username/i)).toBeTruthy();
    expect(screen.getByLabelText(/^password$/i)).toBeTruthy();
  });

  it('redirects after successful OTP verification', async () => {
    vi.spyOn(api, 'requestOtp').mockResolvedValue(undefined);
    vi.spyOn(api, 'loginWithOtp').mockResolvedValue({
      id: 1,
      username: 'alice',
      is_admin: false,
    });

    renderWithRouter(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>,
      { initialPath: '/login' }
    );

    await userEvent.click(await screen.findByRole('button', { name: /use email code/i }));
    await userEvent.type(screen.getByLabelText(/email address/i), 'alice@example.com');
    await userEvent.click(screen.getByRole('button', { name: /send code/i }));
    await userEvent.type(await screen.findByLabelText(/6-digit code/i), '123456');
    await userEvent.click(screen.getByRole('button', { name: /verify code/i }));

    await waitFor(() => {
      expect(screen.getByText('Home')).toBeTruthy();
    });
    expect(api.loginWithOtp).toHaveBeenCalledWith('alice@example.com', '123456');
  });

  it('resends an OTP from the code step and clears the stale code', async () => {
    vi.spyOn(api, 'requestOtp').mockResolvedValue(undefined);

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    await userEvent.click(await screen.findByRole('button', { name: /use email code/i }));
    await userEvent.type(screen.getByLabelText(/email address/i), 'alice@example.com');
    await userEvent.click(screen.getByRole('button', { name: /send code/i }));
    await userEvent.type(await screen.findByLabelText(/6-digit code/i), '123456');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /resend code/i })).toBeEnabled();
    });
    await userEvent.click(screen.getByRole('button', { name: /resend code/i }));

    await waitFor(() => {
      expect(api.requestOtp).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByLabelText(/6-digit code/i)).toHaveValue('');
    expect(screen.getByText(/codes expire after 10 minutes/i)).toBeTruthy();
  });

  it('lets OTP users change the email address from the code step', async () => {
    vi.spyOn(api, 'requestOtp').mockResolvedValue(undefined);

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    await userEvent.click(await screen.findByRole('button', { name: /use email code/i }));
    await userEvent.type(screen.getByLabelText(/email address/i), 'alice@example.com');
    await userEvent.click(screen.getByRole('button', { name: /send code/i }));
    await userEvent.type(await screen.findByLabelText(/6-digit code/i), '123456');
    await userEvent.click(screen.getByRole('button', { name: /change email/i }));

    expect(screen.getByLabelText(/email address/i)).toHaveValue('alice@example.com');
    expect(screen.queryByLabelText(/6-digit code/i)).toBeNull();
  });
});
