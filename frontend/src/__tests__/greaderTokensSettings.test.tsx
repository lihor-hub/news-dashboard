// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const { mockFetchGreaderTokens, mockCreateGreaderToken, mockRevokeGreaderToken } = vi.hoisted(
  () => ({
    mockFetchGreaderTokens: vi.fn(),
    mockCreateGreaderToken: vi.fn(),
    mockRevokeGreaderToken: vi.fn(),
  })
);

vi.mock('@/api', () => ({
  fetchGreaderTokens: mockFetchGreaderTokens,
  createGreaderToken: mockCreateGreaderToken,
  revokeGreaderToken: mockRevokeGreaderToken,
}));

import { GreaderTokensSection } from '../components/settings/GreaderTokensSection';

beforeEach(() => {
  mockFetchGreaderTokens.mockResolvedValue({ items: [] });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('GreaderTokensSection', () => {
  it('renders the section heading', async () => {
    render(<GreaderTokensSection />);
    await waitFor(() =>
      expect(screen.getByText('RSS Client Sync (Google Reader API)')).toBeInTheDocument()
    );
  });

  it('shows existing tokens', async () => {
    mockFetchGreaderTokens.mockResolvedValue({
      items: [
        {
          id: 1,
          name: 'NetNewsWire',
          token_prefix: 'ndgr_abcd1234',
          created_at: '2026-01-01T00:00:00Z',
          last_used_at: null,
          revoked_at: null,
        },
      ],
    });
    render(<GreaderTokensSection />);
    expect(await screen.findByText('NetNewsWire')).toBeInTheDocument();
  });

  it('creates a token and shows the minted secret once', async () => {
    const user = userEvent.setup();
    mockCreateGreaderToken.mockResolvedValue({
      id: 2,
      name: 'Reeder',
      token_prefix: 'ndgr_efgh5678',
      created_at: '2026-01-02T00:00:00Z',
      last_used_at: null,
      revoked_at: null,
      token: 'ndgr_efgh5678secret',
    });
    render(<GreaderTokensSection />);

    const input = await screen.findByLabelText('New RSS sync token name');
    await user.type(input, 'Reeder');
    await user.click(screen.getByRole('button', { name: 'Create token' }));

    await waitFor(() => expect(mockCreateGreaderToken).toHaveBeenCalledWith('Reeder'));
    expect(await screen.findByText('ndgr_efgh5678secret')).toBeInTheDocument();
  });

  it('revokes a token', async () => {
    const user = userEvent.setup();
    mockFetchGreaderTokens.mockResolvedValue({
      items: [
        {
          id: 3,
          name: 'Unread',
          token_prefix: 'ndgr_ijkl9012',
          created_at: '2026-01-03T00:00:00Z',
          last_used_at: null,
          revoked_at: null,
        },
      ],
    });
    mockRevokeGreaderToken.mockResolvedValue({
      id: 3,
      name: 'Unread',
      token_prefix: 'ndgr_ijkl9012',
      created_at: '2026-01-03T00:00:00Z',
      last_used_at: null,
      revoked_at: '2026-01-04T00:00:00Z',
    });
    render(<GreaderTokensSection />);

    const revokeBtn = await screen.findByRole('button', { name: 'Revoke RSS sync token' });
    await user.click(revokeBtn);

    await waitFor(() => expect(mockRevokeGreaderToken).toHaveBeenCalledWith(3));
    expect(await screen.findByText(/revoked/)).toBeInTheDocument();
  });
});
