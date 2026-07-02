// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ArticleTags } from '../components/article/ArticleTags';
import * as tagsApi from '../api/tagsApi';
import type { UserTag } from '../api/tagsApi';

vi.spyOn(console, 'error').mockImplementation(() => undefined);

function makeTag(overrides: Partial<UserTag> = {}): UserTag {
  return {
    id: 1,
    user_id: 1,
    name: 'rust',
    color: null,
    created_at: '2026-06-16T10:00:00Z',
    article_count: 0,
    ...overrides,
  };
}

function renderArticleTags() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ArticleTags articleId="42" />
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ArticleTags', () => {
  it('renders existing tags applied to the article', async () => {
    vi.spyOn(tagsApi, 'fetchArticleTags').mockResolvedValue([makeTag()]);
    vi.spyOn(tagsApi, 'fetchTags').mockResolvedValue([makeTag()]);

    renderArticleTags();

    await waitFor(() => {
      expect(screen.getByText('rust')).toBeTruthy();
    });
  });

  it('applies an existing tag from the dropdown', async () => {
    vi.spyOn(tagsApi, 'fetchArticleTags').mockResolvedValue([]);
    vi.spyOn(tagsApi, 'fetchTags').mockResolvedValue([makeTag({ name: 'python' })]);
    const addSpy = vi.spyOn(tagsApi, 'addArticleTag').mockResolvedValue(undefined);

    renderArticleTags();

    await waitFor(() => {
      expect(screen.getByText('Add tag')).toBeTruthy();
    });
    await userEvent.click(screen.getByText('Add tag'));

    await waitFor(() => {
      expect(screen.getByText('python')).toBeTruthy();
    });
    await userEvent.click(screen.getByText('python'));

    await waitFor(() => {
      expect(addSpy).toHaveBeenCalledWith('42', 1);
    });
  });

  it('creates a new tag and applies it to the article', async () => {
    vi.spyOn(tagsApi, 'fetchArticleTags').mockResolvedValue([]);
    vi.spyOn(tagsApi, 'fetchTags').mockResolvedValue([]);
    const createSpy = vi
      .spyOn(tagsApi, 'createTag')
      .mockResolvedValue(makeTag({ id: 7, name: 'golang' }));
    const addSpy = vi.spyOn(tagsApi, 'addArticleTag').mockResolvedValue(undefined);

    renderArticleTags();

    await waitFor(() => {
      expect(screen.getByText('Add tag')).toBeTruthy();
    });
    await userEvent.click(screen.getByText('Add tag'));

    const input = screen.getByPlaceholderText('New tag…');
    await userEvent.type(input, 'golang');
    await userEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith('golang');
      expect(addSpy).toHaveBeenCalledWith('42', 7);
    });
  });

  it('removes a tag from the article', async () => {
    vi.spyOn(tagsApi, 'fetchArticleTags').mockResolvedValue([makeTag()]);
    vi.spyOn(tagsApi, 'fetchTags').mockResolvedValue([makeTag()]);
    const removeSpy = vi.spyOn(tagsApi, 'removeArticleTag').mockResolvedValue(undefined);

    renderArticleTags();

    await waitFor(() => {
      expect(screen.getByText('rust')).toBeTruthy();
    });
    await userEvent.click(screen.getByRole('button', { name: 'Remove tag rust' }));

    await waitFor(() => {
      expect(removeSpy).toHaveBeenCalledWith('42', 1);
    });
  });
});
