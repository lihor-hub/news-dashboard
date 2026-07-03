// @vitest-environment happy-dom
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import * as api from '../api';
import { ShareTargetPage } from '../pages/ShareTargetPage';
import { extractSharedUrl } from '../lib/shareTarget';
import type { Article } from '../types';

vi.mock('../api', () => ({
  saveSharedUrl: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: vi.fn(),
}));

const SAVED_ARTICLE = { id: 42 } as Article;

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/share-target" element={<ShareTargetPage />} />
        <Route path="/a/:id" element={<div>article view</div>} />
      </Routes>
    </MemoryRouter>
  );
}

describe('extractSharedUrl', () => {
  it('extracts a URL from the url param', () => {
    expect(extractSharedUrl('https://example.com/article', null)).toBe(
      'https://example.com/article'
    );
  });

  it('extracts a URL embedded in the text param when url is absent', () => {
    expect(extractSharedUrl(null, 'Check this out: https://example.com/thing')).toBe(
      'https://example.com/thing'
    );
  });

  it('returns null when neither param contains a URL', () => {
    expect(extractSharedUrl(null, 'just some text')).toBeNull();
  });
});

describe('ShareTargetPage', () => {
  beforeEach(() => {
    vi.mocked(api.saveSharedUrl).mockReset();
  });

  it('saves the shared URL and navigates to the article', async () => {
    vi.mocked(api.saveSharedUrl).mockResolvedValue(SAVED_ARTICLE);

    renderAt('/share-target?url=https%3A%2F%2Fexample.com%2Fpost&title=Hello');

    await waitFor(() => {
      expect(api.saveSharedUrl).toHaveBeenCalledWith('https://example.com/post', 'Hello');
    });
    await screen.findByText('article view');
  });

  it('shows an error state when no URL can be found', async () => {
    renderAt('/share-target?title=nothing%20useful');

    await screen.findByText("Couldn't save link");
    expect(api.saveSharedUrl).not.toHaveBeenCalled();
  });

  it('shows an error state when saving fails', async () => {
    vi.mocked(api.saveSharedUrl).mockRejectedValue(new Error('boom'));

    renderAt('/share-target?url=https%3A%2F%2Fexample.com%2Fpost');

    await screen.findByText('Could not save this link. Please try again.');
  });
});
