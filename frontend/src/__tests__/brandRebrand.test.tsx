// @vitest-environment happy-dom
/**
 * Tests for #621 — rebrand to "News Dashboard — Your private news platform".
 * Ensures the LoginPage renders the new tagline and the web manifest
 * carries the canonical name and description.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../contexts/auth';
import { LoginPage } from '../pages/LoginPage';
import * as api from '../api';
import { readFileSync } from 'fs';
import { join } from 'path';

vi.spyOn(console, 'error').mockImplementation(() => undefined);

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

function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderLoginPage() {
  return render(
    <QueryClientProvider client={makeQc()}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/']}>
          <Routes>
            <Route path="/" element={<LoginPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

const TAGLINE = 'Your private news platform';

describe('Brand rebrand (#621)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, 'fetchAuthConfig').mockResolvedValue({
      provider: 'password',
      keycloak_enabled: false,
      login_url: null,
      logout_url: '/api/auth/logout',
    });
  });

  it('renders the new tagline on the login page', () => {
    renderLoginPage();
    return waitFor(() => {
      expect(screen.getByText(TAGLINE)).toBeTruthy();
    });
  });

  it('does not render the old branding strings', () => {
    renderLoginPage();
    return waitFor(() => {
      expect(screen.queryByText(/radar dashboard/i)).toBeNull();
      expect(screen.queryByText(/news\.lihor\.ro/)).toBeNull();
    });
  });
});

describe('Web manifest brand consistency (#621)', () => {
  it('manifest name and description match the canonical brand', () => {
    const manifestPath = join(process.cwd(), 'public', 'manifest.webmanifest');
    const manifestContent = readFileSync(manifestPath, 'utf-8');
    const manifest = JSON.parse(manifestContent) as { name: string; description: string };

    expect(manifest.name).toBe('News Dashboard');
    expect(manifest.description).toContain('private');
    expect(manifest.description).not.toContain('Personal AI-curated');
  });
});
