// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { ThemeSwitcher } from '@/components/ThemeSwitcher';
import { ShortcutOverlay } from '@/components/ShortcutOverlay';
import english from '@/locales/en/translation.json';

const translated = {
  theme: {
    label: 'Тема',
    options: { light: 'Светла', system: 'Системна', dark: 'Тъмна' },
  },
  shortcuts: {
    title: 'Клавишни комбинации',
    sections: { navigation: 'Навигация', articleActions: 'Действия със статии', app: 'Приложение' },
    navigation: {
      move: 'Надолу / нагоре в списъка',
      open: 'Отворете избраната статия',
      briefToday: 'Към Обзор / Днес',
      laterStarred: 'Към За по-късно / Любими',
      askFeeds: 'Към Попитайте / Емисии',
      history: 'Към историята на обзорите',
    },
    articleActions: {
      done: 'Маркирайте като готово',
      later: 'Изпратете за по-късно',
      star: 'Добавете / премахнете от любими',
      skip: 'Пропуснете (освен любимите)',
      archive: 'Архивирайте',
      openOriginal: 'Отворете оригинала външно',
      backToList: 'Назад към списъка',
      previousArticle: 'Предишна статия',
      nextArticle: 'Следваща статия',
    },
    app: { commandPalette: 'Палитра с команди', showOverlay: 'Покажете този прозорец' },
  },
};

async function instance() {
  const i18n = createInstance();
  await i18n.init({
    lng: 'en',
    fallbackLng: 'en',
    resources: { en: { translation: english }, bg: { translation: translated } },
  });
  return i18n;
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  );
});

describe('chrome translations', () => {
  it('updates theme accessible names and tooltips when language changes, preserving theme selection', async () => {
    const i18n = await instance();
    render(
      <I18nextProvider i18n={i18n}>
        <ThemeSwitcher />
      </I18nextProvider>
    );
    expect(screen.getByRole('group', { name: 'Theme' })).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Dark' }));
    await act(() => i18n.changeLanguage('bg'));
    expect(screen.getByRole('group', { name: translated.theme.label })).toBeVisible();
    for (const label of Object.values(translated.theme.options)) {
      expect(screen.getByRole('button', { name: label })).toHaveAttribute('title', label);
    }
    expect(screen.getByRole('button', { name: 'Тъмна' })).toHaveAttribute('aria-pressed', 'true');
    expect(localStorage.getItem('theme')).toBe('dark');
  });

  it('updates every shortcut label in an open dialog while preserving key chords', async () => {
    const i18n = await instance();
    render(
      <I18nextProvider i18n={i18n}>
        <ShortcutOverlay open onOpenChange={vi.fn()} />
      </I18nextProvider>
    );
    const dialog = screen.getByRole('dialog', { name: 'Keyboard shortcuts' });
    const keys = Array.from(dialog.querySelectorAll('kbd'), (key) => key.textContent);
    await act(() => i18n.changeLanguage('bg'));
    expect(screen.getByRole('dialog', { name: translated.shortcuts.title })).toBeVisible();
    for (const group of [
      translated.shortcuts.sections,
      translated.shortcuts.navigation,
      translated.shortcuts.articleActions,
      translated.shortcuts.app,
    ]) {
      for (const label of Object.values(group))
        expect(within(dialog).getByText(label)).toBeVisible();
    }
    expect(Array.from(dialog.querySelectorAll('kbd'), (key) => key.textContent)).toEqual(keys);
  });
});
