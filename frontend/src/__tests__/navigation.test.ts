import { describe, expect, it } from 'vitest';
import {
  commandNavigationItems,
  getPageTitle,
  getShortcutTarget,
  isNavigationItemActive,
  mobilePrimaryOverflowItems,
  mobileNavigationItems,
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

  it('surfaces Shared (not Later) in the fixed 5-slot mobile bottom bar', () => {
    const mobileTargets = mobileNavigationItems.map((item) => item.to);
    expect(mobileTargets).toEqual(['/', '/today', '/shared', '/starred', '/search']);
    expect(mobileTargets).toContain('/shared');
    expect(mobileTargets).not.toContain('/later');
  });

  it('puts Later (and Ask) in the mobile primary overflow for the More sheet', () => {
    const overflowTargets = mobilePrimaryOverflowItems.map((item) => item.to);
    expect(overflowTargets).toContain('/later');
    expect(overflowTargets).toContain('/ask');
    // Overflow must not duplicate items already in the bottom bar.
    expect(overflowTargets).not.toContain('/shared');
    expect(overflowTargets).not.toContain('/');
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

describe('AI Stats navigation', () => {
  it('lists /ai-stats in the secondary navigation', () => {
    const targets = secondaryNavigationItems.map((item) => item.to);
    expect(targets).toContain('/ai-stats');
  });

  it('titles the AI Stats page', () => {
    expect(getPageTitle('/ai-stats')).toBe('AI Stats');
  });
});
