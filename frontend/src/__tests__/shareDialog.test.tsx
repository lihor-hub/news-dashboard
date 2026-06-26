// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ShareDialog } from '../components/ShareDialog';
import * as api from '../api';

vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

function renderDialog(onOpenChange = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ShareDialog
        open
        onOpenChange={onOpenChange}
        article={{ id: 7, title: 'Big News', url: 'https://example.com/x' }}
      />
    </QueryClientProvider>
  );
  return { onOpenChange };
}

describe('ShareDialog', () => {
  it('offers internal and external choices', () => {
    renderDialog();
    expect(screen.getByText('Send inside the platform')).toBeTruthy();
    expect(screen.getByText('Share externally')).toBeTruthy();
  });

  it('lists users and shares to the chosen recipient', async () => {
    vi.spyOn(api, 'fetchShareableUsers').mockResolvedValue([
      { id: 2, username: 'alice', email: 'alice@example.com' },
      { id: 3, username: 'bob', email: null },
    ]);
    const shareSpy = vi.spyOn(api, 'shareArticle').mockResolvedValue();
    const { onOpenChange } = renderDialog();

    await userEvent.click(screen.getByText('Send inside the platform'));
    await waitFor(() => expect(screen.getByText('alice')).toBeTruthy());

    await userEvent.click(screen.getByText('alice'));
    await waitFor(() => expect(shareSpy).toHaveBeenCalledWith(7, 2, ''));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('uses the Web Share API for external sharing when available', async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'share', { value: share, configurable: true });
    renderDialog();

    await userEvent.click(screen.getByText('Share externally'));
    await waitFor(() =>
      expect(share).toHaveBeenCalledWith({ title: 'Big News', url: 'https://example.com/x' })
    );
    Reflect.deleteProperty(navigator, 'share');
  });
});
