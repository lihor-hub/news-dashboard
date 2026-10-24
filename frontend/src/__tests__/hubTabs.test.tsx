// @vitest-environment happy-dom
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { HubTabs } from '../components/HubTabs';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function renderTabs(pathname: string, props: Partial<React.ComponentProps<typeof HubTabs>> = {}) {
  return render(
    <MemoryRouter initialEntries={[pathname]}>
      <HubTabs pathname={pathname} isAdmin={false} {...props} />
    </MemoryRouter>
  );
}

describe('HubTabs', () => {
  it('renders the current hub sub-pages as a labelled tab strip', () => {
    renderTabs('/today');
    const strip = screen.getByRole('navigation', { name: 'nav.hub_read' });
    const links = within(strip).getAllByRole('link');
    expect(links.map((l) => l.getAttribute('href'))).toEqual(['/', '/today', '/briefs']);
  });

  it('marks only the active sub-page as current', () => {
    renderTabs('/learn/library');
    expect(
      screen.getByRole('link', { name: 'nav.lesson_library' }).getAttribute('aria-current')
    ).toBe('page');
    expect(screen.getByRole('link', { name: 'nav.learn' }).getAttribute('aria-current')).toBeNull();
  });

  it('keeps the parent tab active on nested detail routes', () => {
    renderTabs('/briefs/42');
    expect(
      screen.getByRole('link', { name: 'nav.briefing_history' }).getAttribute('aria-current')
    ).toBe('page');
  });

  it('shows Ask AI and Search as two tabs of the Ask hub', () => {
    renderTabs('/search');
    const strip = screen.getByRole('navigation', { name: 'nav.hub_ask' });
    expect(
      within(strip)
        .getAllByRole('link')
        .map((l) => l.getAttribute('href'))
    ).toEqual(['/ask', '/search']);
  });

  it('hides admin-only tabs from regular users', () => {
    renderTabs('/recap');
    expect(screen.queryByRole('link', { name: 'nav.stats' })).toBeNull();
    renderTabs('/recap', { isAdmin: true });
    expect(screen.getByRole('link', { name: 'nav.stats' })).toBeTruthy();
  });

  it('renders per-tab counts when provided', () => {
    renderTabs('/later', { counts: { '/starred': 4 } });
    expect(screen.getByRole('link', { name: /nav\.starred/ }).textContent).toContain('4');
  });

  it('renders nothing outside a hub', () => {
    const { container } = renderTabs('/settings');
    expect(container.querySelector('nav')).toBeNull();
  });
});
