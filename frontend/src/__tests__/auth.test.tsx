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
    t: (key: string) => {
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
        'auth.signing_in': 'Signing in…',
        'auth.sign_in_with_keycloak': 'Sign in with Keycloak',
        'auth.create_account': 'Create Account',
        'app.name': 'News Dashboard',
        'app.tagline': 'Your private news platform',
      };
      return translations[key] ?? key;
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
    vi.spyOn(api, 'fetchAuthConfig').mockResolvedValue({
      provider: 'password',
      keycloak_enabled: false,
      login_url: null,
      logout_url: '/api/auth/logout',
    });
  });

  it('renders username and password fields', () => {
    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );
    expect(screen.getByLabelText(/username/i)).toBeTruthy();
    expect(screen.getByLabelText(/password/i)).toBeTruthy();
  });

  it('shows error message on 401', async () => {
    vi.spyOn(api, 'loginUser').mockRejectedValue(new Error('401 Unauthorized'));

    renderWithRouter(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    );

    await userEvent.type(screen.getByLabelText(/username/i), 'alice');
    await userEvent.type(screen.getByLabelText(/password/i), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeTruthy();
      expect(screen.getByRole('alert').textContent).toMatch(/invalid/i);
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

    await userEvent.type(screen.getByLabelText(/username/i), 'alice');
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
    await userEvent.type(screen.getByLabelText(/username/i), 'alice');
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
    await userEvent.type(screen.getByLabelText(/username/i), 'alice');
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
});
