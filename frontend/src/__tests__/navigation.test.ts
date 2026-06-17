import { describe, expect, it } from 'vitest';
import {
  commandNavigationItems,
  getPageTitle,
  getShortcutTarget,
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
});
