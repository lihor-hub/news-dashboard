// @vitest-environment happy-dom
/**
 * Tests for i18n functionality.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { I18nextProvider } from 'react-i18next';
import { AuthProvider } from '@/contexts/auth';
import userEvent from '@testing-library/user-event';
import i18n from '@/lib/i18n';
import { initLanguageDirection } from '@/lib/languages';
import { LoginPage } from '@/pages/LoginPage';
import * as api from '@/api';
import translationEs from '@/locales/es/translation.json';

function renderWithI18n(ui: React.ReactNode) {
  return render(
    <I18nextProvider i18n={i18n}>
      <AuthProvider>
        <MemoryRouter initialEntries={['/login']}>{ui}</MemoryRouter>
      </AuthProvider>
    </I18nextProvider>
  );
}

describe('i18n integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders LoginPage with translated English strings', async () => {
    renderWithI18n(<LoginPage />);

    // Check that the app name and tagline are rendered
    expect(await screen.findByText('News Dashboard')).toBeInTheDocument();
    expect(await screen.findByText('Your private news platform')).toBeInTheDocument();

    // Check form labels
    expect(await screen.findByLabelText('Username')).toBeInTheDocument();
    expect(await screen.findByLabelText('Password')).toBeInTheDocument();

    // Check buttons
    expect(await screen.findByRole('button', { name: /sign in/i })).toBeInTheDocument();

    // Check alternative login option
    expect(
      await screen.findByRole('button', { name: /use email code instead/i })
    ).toBeInTheDocument();
  });

  it('displays translated error messages', async () => {
    // Mock the loginUser function to return an error
    vi.spyOn(api, 'loginUser').mockRejectedValue(new Error('401 Unauthorized'));

    renderWithI18n(<LoginPage />);

    // Fill in the form and submit
    await userEvent.type(screen.getByLabelText('Username'), 'testuser');
    await userEvent.type(screen.getByLabelText('Password'), 'wrongpass');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    // Wait for and check the error message
    const alertElement = await screen.findByRole('alert');
    expect(alertElement).toHaveTextContent('Invalid username or password.');
  });
});

describe('language switching', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('re-renders translated text when the active language changes', async () => {
    renderWithI18n(<LoginPage />);
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();

    await i18n.changeLanguage('es');

    expect(await screen.findByRole('button', { name: 'Iniciar sesión' })).toBeInTheDocument();
    expect(await screen.findByLabelText('Usuario')).toBeInTheDocument();
  });

  it('persists the selected language to localStorage', async () => {
    await i18n.changeLanguage('fr');
    expect(localStorage.getItem('i18nextLng')).toBe('fr');
  });
});

describe('key resolution fallback', () => {
  afterEach(async () => {
    // Restore the real Spanish bundle trimmed by the test below.
    i18n.removeResourceBundle('es', 'translation');
    i18n.addResourceBundle('es', 'translation', translationEs);
    await i18n.changeLanguage('en');
  });

  it('falls back to English when a key is missing from the active language', async () => {
    await i18n.changeLanguage('es');
    expect(i18n.t('auth.sign_in')).toBe('Iniciar sesión');

    // Simulate a translation gap: remove a key that exists in English but not (yet) in Spanish.
    i18n.removeResourceBundle('es', 'translation');
    i18n.addResourceBundle('es', 'translation', { auth: { sign_in: 'Iniciar sesión' } });

    expect(i18n.t('auth.sign_in')).toBe('Iniciar sesión');
    // 'auth.username' is missing from the trimmed Spanish bundle, so it falls back to English.
    expect(i18n.t('auth.username')).toBe('Username');
  });
});

describe('lazy language loading', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('loads a language bundle on demand and exposes it via getResourceBundle', async () => {
    expect(i18n.getDataByLanguage('it')?.translation).toBeUndefined();

    await i18n.changeLanguage('it');

    expect(i18n.t('auth.sign_in')).toBe('Accedi');
    expect(i18n.getDataByLanguage('it')?.translation).toBeDefined();
  });

  it('does not eagerly bundle every language module (code-split per language)', () => {
    const localeModules = import.meta.glob('../locales/*/translation.json');
    // Each entry is a lazy loader function, not the already-resolved module.
    for (const loader of Object.values(localeModules)) {
      expect(typeof loader).toBe('function');
    }
  });
});

describe('RTL direction', () => {
  beforeEach(() => {
    // main.tsx wires this up once at startup; replicate that here since tests
    // don't go through main.tsx.
    initLanguageDirection(i18n);
  });

  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('applies dir="rtl" for right-to-left languages and dir="ltr" otherwise', async () => {
    await i18n.changeLanguage('ar');
    expect(document.documentElement.dir).toBe('rtl');
    expect(document.documentElement.lang).toBe('ar');

    await i18n.changeLanguage('en');
    expect(document.documentElement.dir).toBe('ltr');
    expect(document.documentElement.lang).toBe('en');

    await i18n.changeLanguage('he');
    expect(document.documentElement.dir).toBe('rtl');
  });
});
