// @vitest-environment happy-dom
/**
 * Tests for #414 — replace in-app RD placeholder with real app logo.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppLogo } from '../components/AppLogo';
import { LoginPage } from '../pages/LoginPage';
import * as api from '../api';
import { AuthProvider } from '../contexts/auth';

vi.spyOn(console, 'error').mockImplementation(() => undefined);

// ── AppLogo component ──────────────────────────────────────────────────────────

describe('AppLogo', () => {
  it('renders an image element pointing to the favicon', () => {
    render(<AppLogo />);
    const img = screen.getByRole('img');
    expect(img).toBeTruthy();
    expect(img.getAttribute('src')).toBe('/favicon.svg');
  });

  it('has an accessible alt text by default', () => {
    render(<AppLogo />);
    const img = screen.getByRole('img');
    expect(img.getAttribute('alt')).toBeTruthy();
    expect(img.getAttribute('alt')).not.toBe('');
  });

  it('accepts a custom className', () => {
    render(<AppLogo className="size-10" />);
    const img = screen.getByRole('img');
    expect(img.className).toContain('size-10');
  });

  it('does not render "RD" text', () => {
    render(<AppLogo />);
    expect(screen.queryByText('RD')).toBeNull();
  });
});

// ── AppShell source-level check ────────────────────────────────────────────────

describe('AppShell', () => {
  const src = readFileSync(join(import.meta.dirname, '../components/AppShell.tsx'), 'utf8');

  it('does not contain the hardcoded RD logo text badge', () => {
    // The old pattern was: ...grid place-items-center text-background...>RD</div>
    // Ensure no text node containing exactly "RD" remains inside a div used as logo
    expect(src).not.toMatch(/>[\s]*RD[\s]*</);
  });

  it('uses the AppLogo component in the header', () => {
    expect(src).toContain('AppLogo');
  });
});

// ── LoginPage ──────────────────────────────────────────────────────────────────

function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render a visible RD logo badge', async () => {
    vi.spyOn(api, 'fetchAuthConfig').mockResolvedValue({
      provider: 'password',
      keycloak_enabled: false,
      login_url: null,
      logout_url: '/api/auth/logout',
    });
    vi.spyOn(api, 'fetchMe').mockRejectedValue(new Error('401'));

    render(
      <QueryClientProvider client={makeQc()}>
        <AuthProvider>
          <MemoryRouter>
            <LoginPage />
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.queryByRole('form')).toBeDefined();
    });

    // The old RD text badge must not appear
    expect(screen.queryByText('RD')).toBeNull();
  });

  it('renders the app logo image on the login page', async () => {
    vi.spyOn(api, 'fetchAuthConfig').mockResolvedValue({
      provider: 'password',
      keycloak_enabled: false,
      login_url: null,
      logout_url: '/api/auth/logout',
    });
    vi.spyOn(api, 'fetchMe').mockRejectedValue(new Error('401'));

    render(
      <QueryClientProvider client={makeQc()}>
        <AuthProvider>
          <MemoryRouter>
            <LoginPage />
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>
    );

    await waitFor(() => {
      const img = screen.getByRole('img', { name: /readingdna/i });
      expect(img.getAttribute('src')).toBe('/favicon.svg');
    });
  });
});
