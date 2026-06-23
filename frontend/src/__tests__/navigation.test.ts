import { describe, expect, it } from 'vitest';
import {
  commandNavigationItems,
  getPageTitle,
  getShortcutTarget,
  isNavigationItemActive,
  primaryNavigationItems,
  secondaryNavigationItems,
} from '../lib/navigation';

describe('navigation metadata', () => {
  it('keeps shell and command palette destinations in sync', () => {
    const shellTargets = [...primaryNavigationItems, ...secondaryNavigationItems].map((item) => ({
      label: item.commandLabel ?? item.label,
      to: item.to,
    }));

    expect(commandNavigationItems.map(({ label, to }) => ({ label, to }))).toEqual(shellTargets);
  });

  it('derives titles for nested route families', () => {
    expect(getPageTitle('/')).toBe('Brief');
    expect(getPageTitle('/briefs/123')).toBe('Briefs');
    expect(getPageTitle('/feeds/runs')).toBe('Feeds');
    expect(getPageTitle('/unknown')).toBe('Radar');
  });

  it('defines g-key shortcuts only for existing app routes', () => {
    expect(getShortcutTarget('b')).toBe('/');
    expect(getShortcutTarget('t')).toBe('/today');
    expect(getShortcutTarget('h')).toBe('/briefs');
    expect(getShortcutTarget('z')).toBeNull();
  });

  it('matches exact roots but prefix-matches nested families', () => {
    // '/' and '/today' must match exactly so they don't light up everywhere.
    expect(isNavigationItemActive('/', '/')).toBe(true);
    expect(isNavigationItemActive('/', '/today')).toBe(false);
    expect(isNavigationItemActive('/today', '/today')).toBe(true);
    expect(isNavigationItemActive('/today', '/today/123')).toBe(false);

    // Other destinations match their whole sub-tree.
    expect(isNavigationItemActive('/briefs', '/briefs/123')).toBe(true);
    expect(isNavigationItemActive('/feeds', '/stats')).toBe(false);
  });
});
