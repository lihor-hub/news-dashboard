// @vitest-environment happy-dom
/**
 * App shell layout: desktop hub rail, hub tab strip, mobile bottom bar and the
 * "You" / avatar account menu.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import '@/lib/i18n';

const authState = vi.hoisted(() => ({ isAdmin: false }));

vi.mock('@/contexts/auth', () => ({
  useAuth: () => ({
    user: { id: 7, username: 'alice', email: 'a@example.com', is_admin: authState.isAdmin },
  }),
}));
vi.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: undefined }) }));
vi.mock('@/api', () => ({
  fetchSummary: vi.fn(),
  fetchSharesUnreadCount: vi.fn(),
  fetchAnalyticsSettings: vi.fn().mockRejectedValue(new Error('offline')),
}));
vi.mock('@/hooks/useWhatsNew', () => ({ useWhatsNew: () => null }));
vi.mock('@/hooks/useOnboardingWizard', () => ({
  useOnboardingWizard: () => ({ open: false, skip: vi.fn() }),
}));
vi.mock('@/hooks/useElectronBriefNotifier', () => ({ useElectronBriefNotifier: vi.fn() }));
vi.mock('@/hooks/useLogout', () => ({ useLogout: () => vi.fn() }));
vi.mock('@/lib/analytics', () => ({
  setAnalyticsAllowed: vi.fn(),
  startAnalytics: vi.fn(),
  stopAnalytics: vi.fn(),
  trackRoute: vi.fn(),
}));
vi.mock('@/components/ListenQueuePlayer', () => ({ ListenQueuePlayer: () => null }));
vi.mock('@/components/DifyChatWidget', () => ({ DifyChatWidget: () => null }));
vi.mock('@/components/CommandPalette', () => ({ CommandPalette: () => null }));
vi.mock('@/components/ShortcutOverlay', () => ({ ShortcutOverlay: () => null }));
vi.mock('@/components/WhatsNewDialog', () => ({ WhatsNewDialog: () => null }));
vi.mock('@/components/OnboardingWizard', () => ({ OnboardingWizard: () => null }));

import { AppShell } from '../components/AppShell';

function renderShell(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppShell />
    </MemoryRouter>
  );
}

const hrefs = (links: HTMLElement[]) => links.map((l) => l.getAttribute('href'));

afterEach(() => {
  authState.isAdmin = false;
});

describe('desktop hub rail', () => {
  it('lists the five hubs and highlights the one owning the page', () => {
    const { container } = renderShell('/today');
    const rail = container.querySelector('aside')!;
    const links = within(rail).getAllByRole('link');
    expect(hrefs(links)).toEqual(['/', '/later', '/ask', '/learn', '/recap']);
    expect(within(rail).getByRole('link', { name: 'Read' }).getAttribute('aria-current')).toBe(
      'true'
    );
    expect(
      within(rail).getByRole('link', { name: 'Library' }).getAttribute('aria-current')
    ).toBeNull();
  });

  it('shows the signed-in user on the account button at the bottom of the rail', () => {
    const { container } = renderShell('/');
    const rail = container.querySelector('aside')!;
    expect(within(rail).getByRole('button', { name: /alice/ })).toBeTruthy();
  });

  it('opens the account menu with Feeds, Settings, theme and log out', async () => {
    const { container } = renderShell('/');
    await userEvent.click(
      within(container.querySelector('aside')!).getByRole('button', { name: /alice/ })
    );
    const menu = await screen.findByRole('dialog');
    expect(hrefs(within(menu).getAllByRole('link'))).toEqual(
      expect.arrayContaining(['/feeds', '/settings'])
    );
    expect(within(menu).queryByRole('link', { name: 'Analytics' })).toBeNull();
    expect(within(menu).getByRole('group', { name: 'Theme' })).toBeTruthy();
    expect(within(menu).getByRole('button', { name: 'Log out' })).toBeTruthy();
  });

  it('adds admin pages to the account menu for admins', async () => {
    authState.isAdmin = true;
    const { container } = renderShell('/');
    await userEvent.click(
      within(container.querySelector('aside')!).getByRole('button', { name: /alice/ })
    );
    const menu = await screen.findByRole('dialog');
    expect(hrefs(within(menu).getAllByRole('link'))).toEqual(
      expect.arrayContaining(['/analytics', '/admin'])
    );
  });
});

describe('hub tab strip', () => {
  it('renders the hub sub-pages above the content with the page marked current', () => {
    renderShell('/today');
    const tabs = screen.getByRole('navigation', { name: 'Read' });
    expect(hrefs(within(tabs).getAllByRole('link'))).toEqual(['/', '/today', '/briefs']);
    expect(within(tabs).getByRole('link', { name: 'Today' }).getAttribute('aria-current')).toBe(
      'page'
    );
  });

  it('is absent on pages outside a hub', () => {
    renderShell('/settings');
    expect(screen.queryByRole('navigation', { name: 'Read' })).toBeNull();
    expect(screen.queryByRole('navigation', { name: 'Library' })).toBeNull();
  });
});

describe('mobile bottom bar', () => {
  function bottomBar(container: HTMLElement) {
    return container.querySelector<HTMLElement>('nav.fixed')!;
  }

  it('shows Read, Library, Ask (centre), Learn and a You button', () => {
    const { container } = renderShell('/');
    const bar = bottomBar(container);
    expect(hrefs(within(bar).getAllByRole('link'))).toEqual(['/', '/later', '/ask', '/learn']);
    const slots = Array.from(bar.querySelectorAll(':scope > div > *'));
    expect(slots).toHaveLength(5);
    expect(slots[2].getAttribute('href')).toBe('/ask');
    expect(within(bar).getByRole('button', { name: 'You' })).toBeTruthy();
  });

  it('opens the You sheet with Insights pages and account items', async () => {
    const { container } = renderShell('/');
    await userEvent.click(within(bottomBar(container)).getByRole('button', { name: 'You' }));
    const sheet = await screen.findByRole('dialog');
    expect(hrefs(within(sheet).getAllByRole('link'))).toEqual(
      expect.arrayContaining([
        '/recap',
        '/reading-dna',
        '/topic-map',
        '/ai-stats',
        '/feeds',
        '/settings',
      ])
    );
    expect(within(sheet).queryByRole('link', { name: 'Stats' })).toBeNull();
  });

  it('marks You active on Insights and account pages', () => {
    const { container } = renderShell('/reading-dna');
    expect(within(bottomBar(container)).getByRole('button', { name: 'You' }).dataset.active).toBe(
      'true'
    );
  });
});
