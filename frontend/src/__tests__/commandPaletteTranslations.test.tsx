// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router';
import { toast } from 'sonner';
import { CommandPalette } from '@/components/CommandPalette';
import type { WorkflowArticle } from '@/lib/workflowTypes';
import * as api from '@/api';
import english from '@/locales/en/translation.json';
import bulgarian from '@/locales/bg/translation.json';

const mocks = vi.hoisted(() => ({
  setState: vi.fn(),
  sendLater: vi.fn(),
  toggleStar: vi.fn(),
  onOpenChange: vi.fn(),
  onShortcuts: vi.fn(),
}));
vi.mock('@/hooks/useTriageMutations', () => ({ useTriageMutations: () => mocks }));
vi.mock('@/contexts/auth', () => ({ useAuth: () => ({ user: { is_admin: true } }) }));
vi.mock('@/contexts/focusedArticle', () => ({
  useFocusedArticle: () => ({ article: focusedArticle }),
}));
vi.mock('sonner', () => ({
  toast: { loading: vi.fn(() => 'toast-id'), success: vi.fn(), error: vi.fn() },
}));

const article: WorkflowArticle = {
  id: '42',
  title: 'Focused article',
  sourceId: 'source',
  sourceName: 'Source',
  category: 'ai',
  url: 'https://example.com/article',
  publishedAt: '',
  ingestedAt: '',
  reason: '',
  summary: '',
  signal: 'high',
  tags: [],
  bodyStatus: 'missing',
  state: 'today',
  starred: false,
};

let focusedArticle = article;

async function renderPalette(language = 'en') {
  const i18n = createInstance();
  await i18n.init({
    lng: language,
    fallbackLng: 'en',
    resources: { en: { translation: english }, bg: { translation: bulgarian } },
  });
  render(
    <I18nextProvider i18n={i18n}>
      <MemoryRouter>
        <CommandPalette open onOpenChange={mocks.onOpenChange} onShortcuts={mocks.onShortcuts} />
      </MemoryRouter>
    </I18nextProvider>
  );
  return i18n;
}

beforeEach(() => {
  vi.clearAllMocks();
  focusedArticle = article;
});

describe('command palette translations', () => {
  it('updates accessible labels, navigation and focused article actions on a live language change', async () => {
    const i18n = await renderPalette();
    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeVisible();
    await act(() => i18n.changeLanguage('bg'));
    expect(screen.getByRole('dialog', { name: 'Палитра с команди' })).toBeVisible();
    expect(screen.getByRole('combobox', { name: 'Търсене и команди' })).toHaveAttribute(
      'placeholder',
      'Към изглед, търсене на статии, изпълнение на действия…'
    );
    expect(screen.getByRole('option', { name: /^Днес$/ })).toBeVisible();
    expect(screen.getByRole('listbox', { name: 'Предложения' })).toBeVisible();
    expect(screen.getByText('За: Focused article')).toBeVisible();
    expect(screen.getByText('Навигация')).toBeVisible();
    expect(screen.getByText('Действия')).toBeVisible();
    await userEvent.click(screen.getByText('Маркирайте като готово'));
    expect(mocks.setState).toHaveBeenCalledWith(article, 'done', 'Готово');
  });

  it.each([
    [0, 'Готово — 0 нови статии'],
    [1, 'Готово — 1 нова статия'],
    [2, 'Готово — 2 нови статии'],
  ])('pluralizes the Bulgarian ingest toast for %i articles', async (count, message) => {
    vi.spyOn(api, 'ingestNow').mockResolvedValue({
      inserted: Number(count),
      results: {},
      run_id: 1,
      total_errors: 0,
      failed_sources: [],
    });
    await renderPalette('bg');
    await userEvent.click(screen.getByText('Обновете емисиите сега'));
    expect(toast.loading).toHaveBeenCalledWith('Обновяване на емисиите…');
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(message, { id: 'toast-id' }));
  });

  it('translates ingest failures', async () => {
    vi.spyOn(api, 'ingestNow').mockRejectedValue(new Error('offline'));
    await renderPalette('bg');
    await userEvent.click(screen.getByText('Обновете емисиите сега'));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Обновяването бе неуспешно', { id: 'toast-id' })
    );
  });

  it.each([
    ['Пропуснете', 'skipped', 'Пропуснато'],
    ['Архивирайте', 'archived', 'Архивирано'],
  ])(
    'runs the translated %s action and reports its localized status',
    async (label, state, status) => {
      await renderPalette('bg');
      await userEvent.click(screen.getByRole('option', { name: new RegExp(`^${label}`) }));
      expect(mocks.setState).toHaveBeenCalledWith(article, state, status);
      expect(mocks.onOpenChange).toHaveBeenCalledWith(false);
    }
  );

  it('sends the focused article to Later through its translated action', async () => {
    await renderPalette('bg');
    await userEvent.click(screen.getByText('Изпратете за по-късно'));
    expect(mocks.sendLater).toHaveBeenCalledWith(article);
    expect(mocks.onOpenChange).toHaveBeenCalledWith(false);
  });

  it('offers Unstar instead of Star and hides Skip for a starred article', async () => {
    focusedArticle = { ...article, starred: true, title: 'A'.repeat(60) };
    await renderPalette('bg');
    expect(screen.getByText(`За: ${'A'.repeat(50)}…`)).toBeVisible();
    expect(screen.queryByText('Пропуснете')).not.toBeInTheDocument();
    await userEvent.click(screen.getByText('Премахнете от любими'));
    expect(mocks.toggleStar).toHaveBeenCalledWith(focusedArticle);
    expect(mocks.onOpenChange).toHaveBeenCalledWith(false);
  });

  it('opens the original URL from its translated action', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null);
    await renderPalette('bg');
    await userEvent.click(screen.getByText('Отворете оригинала'));
    expect(open).toHaveBeenCalledWith(article.url, '_blank', 'noopener,noreferrer');
    expect(mocks.onOpenChange).toHaveBeenCalledWith(false);
  });

  it('opens shortcut help from the translated command', async () => {
    await renderPalette('bg');
    await userEvent.click(screen.getByText('Клавишни комбинации'));
    expect(mocks.onShortcuts).toHaveBeenCalledOnce();
    expect(mocks.onOpenChange).toHaveBeenCalledWith(false);
  });

  it('shows localized pending search text and clears it when the request fails', async () => {
    let rejectSearch: (reason: Error) => void = () => {};
    const pending = new Promise<never>((_resolve, reject) => {
      rejectSearch = reject;
    });
    vi.spyOn(api, 'searchArticles').mockReturnValue(pending);
    await renderPalette('bg');
    await userEvent.type(screen.getByRole('combobox'), 'missing article');
    expect(await screen.findByText('търсене…')).toBeVisible();
    await act(async () => {
      rejectSearch(new Error('offline'));
    });
    await waitFor(() => expect(screen.queryByText('търсене…')).not.toBeInTheDocument());
    expect(screen.getByRole('option', { name: /^Днес$/ })).toBeVisible();
  });
});
