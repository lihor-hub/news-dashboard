import { describe, expect, it } from 'vitest';
import {
  accountNavigationItemsFor,
  commandNavigationItemsFor,
  getActiveHub,
  getActiveHubItem,
  getPageTitle,
  getPageTitleKey,
  getShortcutTarget,
  hubItemsFor,
  hubTarget,
  isAccountRoute,
  isNavigationItemActive,
  mobileBarHubIds,
  navigationHubs,
  navigationItemsFor,
} from '../lib/navigation';

const hub = (id: string) => navigationHubs.find((h) => h.id === id)!;
const targets = (id: string, isAdmin = false) => hubItemsFor(hub(id), isAdmin).map((i) => i.to);

// Every page the shell exposed before the hub restructure; none may be lost.
const LEGACY_DESTINATIONS = [
  '/',
  '/today',
  '/later',
  '/starred',
  '/shared',
  '/search',
  '/ask',
  '/reading-list',
  '/learn',
  '/learn/library',
  '/learn/recap',
  '/offline-saved',
  '/briefs',
  '/topic-map',
  '/ai-stats',
  '/feeds',
  '/reading-dna',
  '/recap',
  '/archive',
  '/collections',
  '/settings',
  '/stats',
  '/analytics',
  '/admin',
];

describe('navigation hubs', () => {
  it('groups pages into five hubs in display order', () => {
    expect(navigationHubs.map((h) => h.id)).toEqual([
      'read',
      'library',
      'ask',
      'learn',
      'insights',
    ]);
    expect(targets('read')).toEqual(['/', '/today', '/briefs']);
    expect(targets('library')).toEqual([
      '/later',
      '/starred',
      '/shared',
      '/collections',
      '/reading-list',
      '/offline-saved',
      '/archive',
    ]);
    expect(targets('ask')).toEqual(['/ask', '/search']);
    expect(targets('learn')).toEqual(['/learn', '/learn/library', '/learn/recap']);
    expect(targets('insights', true)).toEqual([
      '/recap',
      '/reading-dna',
      '/topic-map',
      '/stats',
      '/ai-stats',
    ]);
  });

  it('wires every hub to a translation key', () => {
    expect(navigationHubs.map((h) => h.labelKey)).toEqual([
      'nav.hub_read',
      'nav.hub_library',
      'nav.hub_ask',
      'nav.hub_learn',
      'nav.hub_insights',
    ]);
  });

  it('opens each hub on its main page', () => {
    expect(navigationHubs.map(hubTarget)).toEqual(['/', '/later', '/ask', '/learn', '/recap']);
  });

  it('keeps admin-only pages out of non-admin hubs and the account menu', () => {
    expect(targets('insights')).not.toContain('/stats');
    expect(accountNavigationItemsFor(false).map((i) => i.to)).toEqual(['/feeds', '/settings']);
    expect(accountNavigationItemsFor(true).map((i) => i.to)).toEqual([
      '/feeds',
      '/settings',
      '/analytics',
      '/admin',
    ]);
  });

  it('puts four hubs in the mobile bar with Ask in the centre', () => {
    expect(mobileBarHubIds).toEqual(['read', 'library', 'ask', 'learn']);
  });
});

describe('active hub and tab', () => {
  it.each([
    ['/', 'read'],
    ['/today', 'read'],
    ['/briefs/123', 'read'],
    ['/shared/abc', 'library'],
    ['/collections/7', 'library'],
    ['/search', 'ask'],
    ['/learn/42', 'learn'],
    ['/learn/library', 'learn'],
    ['/recap', 'insights'],
    ['/stats', 'insights'],
  ])('%s belongs to the %s hub', (pathname, id) => {
    expect(getActiveHub(pathname)?.id).toBe(id);
  });

  it('returns no hub for account pages and unknown routes', () => {
    expect(getActiveHub('/settings')).toBeNull();
    expect(getActiveHub('/feeds/runs')).toBeNull();
    expect(getActiveHub('/nope')).toBeNull();
    expect(isAccountRoute('/feeds/runs')).toBe(true);
    expect(isAccountRoute('/today')).toBe(false);
  });

  it('picks the most specific tab inside a hub', () => {
    expect(getActiveHubItem(hub('learn'), '/learn/library')?.to).toBe('/learn/library');
    expect(getActiveHubItem(hub('learn'), '/learn/42')?.to).toBe('/learn');
    expect(getActiveHubItem(hub('read'), '/today')?.to).toBe('/today');
    expect(getActiveHubItem(hub('read'), '/briefs/9')?.to).toBe('/briefs');
    // /recap (Insights) must not light up from /learn/recap.
    expect(getActiveHubItem(hub('insights'), '/learn/recap')).toBeNull();
  });
});

describe('navigation metadata', () => {
  it('keeps every legacy destination reachable for admins', () => {
    expect(
      navigationItemsFor(true)
        .map((i) => i.to)
        .sort()
    ).toEqual([...LEGACY_DESTINATIONS].sort());
  });

  it('keeps shell and command palette destinations in sync', () => {
    for (const isAdmin of [false, true]) {
      expect(commandNavigationItemsFor(isAdmin).map((i) => i.to)).toEqual(
        navigationItemsFor(isAdmin).map((i) => i.to)
      );
    }
    expect(commandNavigationItemsFor(false).find((i) => i.to === '/ask')?.label).toBe('Ask AI');
  });

  it('exposes analytics to admins only', () => {
    expect(navigationItemsFor(true).map((i) => i.to)).toContain('/analytics');
    expect(navigationItemsFor(false).map((i) => i.to)).not.toContain('/analytics');
  });

  it('derives titles for nested route families', () => {
    expect(getPageTitle('/')).toBe('Brief');
    expect(getPageTitle('/briefs/123')).toBe('Briefs');
    expect(getPageTitle('/learn')).toBe('Learn');
    expect(getPageTitle('/feeds/runs')).toBe('Feeds');
    expect(getPageTitle('/unknown')).toBe('Radar');
    expect(getPageTitle('/learn/library')).toBe('Lesson Library');
    expect(getPageTitle('/ai-stats')).toBe('AI Stats');
    expect(getPageTitleKey('/learn')).toBe('page_title.learn');
    expect(getPageTitleKey('/learn/library')).toBe('page_title.lesson_library');
  });

  it('keeps g-key shortcuts pointing at the same routes', () => {
    expect(getShortcutTarget('b')).toBe('/');
    expect(getShortcutTarget('t')).toBe('/today');
    expect(getShortcutTarget('l')).toBe('/later');
    expect(getShortcutTarget('s')).toBe('/starred');
    expect(getShortcutTarget('a')).toBe('/ask');
    expect(getShortcutTarget('f')).toBe('/feeds');
    expect(getShortcutTarget('h')).toBe('/briefs');
    expect(getShortcutTarget('r')).toBe('/reading-list');
    expect(getShortcutTarget('o')).toBe('/offline-saved');
    expect(getShortcutTarget('z')).toBeNull();
  });

  it('matches exact roots but prefix-matches nested families', () => {
    expect(isNavigationItemActive('/', '/')).toBe(true);
    expect(isNavigationItemActive('/', '/today')).toBe(false);
    expect(isNavigationItemActive('/today', '/today')).toBe(true);
    expect(isNavigationItemActive('/today', '/today/123')).toBe(false);
    expect(isNavigationItemActive('/briefs', '/briefs/123')).toBe(true);
    expect(isNavigationItemActive('/feeds', '/stats')).toBe(false);
    expect(isNavigationItemActive('/learn', '/learn/library')).toBe(false);
  });
});
