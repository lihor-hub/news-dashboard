// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

const { mockFetchMcpTokens } = vi.hoisted(() => ({
  mockFetchMcpTokens: vi.fn(),
}));

vi.mock('@/api', () => ({
  fetchMcpTokens: mockFetchMcpTokens,
  createMcpToken: vi.fn(),
  revokeMcpToken: vi.fn(),
}));

import { McpTokensSection } from '../components/settings/McpTokensSection';

beforeEach(() => {
  mockFetchMcpTokens.mockResolvedValue({ items: [], enabled: true });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('McpTokensSection', () => {
  it('describes default-enabled read-only access and the Ask AI boundary', async () => {
    render(<McpTokensSection />);

    expect(await screen.findByText(/enabled by default/i)).toBeInTheDocument();
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
    expect(screen.getByText(/Ask requires server-side AI/i)).toBeInTheDocument();
  });
});
