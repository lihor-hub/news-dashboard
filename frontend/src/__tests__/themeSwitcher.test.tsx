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

  it('meets touch-target and icon size minimums with token colours and a focus ring', () => {
    render(
      <I18nextProvider i18n={i18n}>
        <ThemeSwitcher />
      </I18nextProvider>
    );
    const group = screen.getByRole('group', { name: 'Theme' });
    expect(group.className).toContain('bg-muted');
    expect(group.className).not.toContain('var(--');

    for (const label of ['Light', 'System', 'Dark']) {
      const button = screen.getByLabelText(label);
      const classes = button.className.split(/\s+/);
      expect(classes).toContain('size-9');
      expect(classes).toContain('pointer-coarse:size-touch');
      expect(classes).toContain('focus-visible:ring-2');
      expect(button.className).not.toContain('var(--');
      const icon = button.querySelector('svg');
      expect(Number(icon?.getAttribute('width'))).toBeGreaterThanOrEqual(16);
      expect(icon?.getAttribute('aria-hidden')).toBe('true');
    }
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
