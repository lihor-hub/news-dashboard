// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import english from '@/locales/en/translation.json';
import { ThemeSwitcher } from '../components/ThemeSwitcher';

let i18n = createInstance();

beforeEach(async () => {
  i18n = createInstance();
  await i18n.init({ lng: 'en', resources: { en: { translation: english } } });
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ThemeSwitcher', () => {
  it('renders one toggle button per theme option', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <ThemeSwitcher />
      </I18nextProvider>
    );
    expect(screen.getByLabelText('Light')).toBeTruthy();
    expect(screen.getByLabelText('System')).toBeTruthy();
    expect(screen.getByLabelText('Dark')).toBeTruthy();
  });

  it('marks the active theme as pressed and switches on click', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <ThemeSwitcher />
      </I18nextProvider>
    );
    const dark = screen.getByLabelText('Dark');
    expect(dark.getAttribute('aria-pressed')).toBe('false');

    fireEvent.click(dark);

    expect(dark.getAttribute('aria-pressed')).toBe('true');
    expect(localStorage.getItem('theme')).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });
});
