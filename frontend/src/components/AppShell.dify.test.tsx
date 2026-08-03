import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';

const { captureDifyProps } = vi.hoisted(() => ({
  captureDifyProps: vi.fn(),
}));

vi.mock('./DifyChatWidget', () => ({
  DifyChatWidget: (props: Record<string, unknown>) => {
    captureDifyProps(props);
    return <div data-testid="dify-assistant-boundary" />;
  },
}));

vi.mock('@/contexts/auth', () => ({
  useAuth: () => ({
    user: {
      id: 42,
      username: 'alice',
      email: 'alice@example.com',
      is_admin: false,
    },
  }),
}));

vi.mock('@tanstack/react-query', () => ({
  useQuery: () => ({ data: undefined }),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/api', () => ({
  fetchSummary: vi.fn(),
  fetchSharesUnreadCount: vi.fn(),
  fetchAnalyticsSettings: vi.fn().mockRejectedValue(new Error('offline')),
}));

vi.mock('@/hooks/useWhatsNew', () => ({
  useWhatsNew: () => null,
}));

vi.mock('@/hooks/useOnboardingWizard', () => ({
  useOnboardingWizard: () => ({ open: false, skip: vi.fn() }),
}));

vi.mock('@/hooks/useElectronBriefNotifier', () => ({
  useElectronBriefNotifier: vi.fn(),
}));

vi.mock('@/hooks/useLogout', () => ({
  useLogout: () => vi.fn(),
}));

vi.mock('@/lib/analytics', () => ({
  setAnalyticsAllowed: vi.fn(),
  startAnalytics: vi.fn(),
  stopAnalytics: vi.fn(),
  trackRoute: vi.fn(),
}));

vi.mock('./ListenQueuePlayer', () => ({
  ListenQueuePlayer: () => null,
}));

vi.mock('./CommandPalette', () => ({
  CommandPalette: () => null,
}));

vi.mock('./ShortcutOverlay', () => ({
  ShortcutOverlay: () => null,
}));

vi.mock('./WhatsNewDialog', () => ({
  WhatsNewDialog: () => null,
}));

vi.mock('./OnboardingWizard', () => ({
  OnboardingWizard: () => null,
}));

import { AppShell } from './AppShell';

afterEach(() => {
  vi.clearAllMocks();
});

describe('AppShell Dify privacy boundary', () => {
  it('mounts the authenticated assistant without passing user context', async () => {
    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>
    );

    expect(await screen.findByTestId('dify-assistant-boundary')).toBeInTheDocument();
    await waitFor(() => expect(captureDifyProps).toHaveBeenCalled());
    expect(captureDifyProps.mock.calls.at(-1)?.[0]).toEqual({});
  });
});
