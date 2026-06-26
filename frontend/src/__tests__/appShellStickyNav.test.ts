import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, it, expect } from 'vitest';

// The DesktopRail <aside> uses `position: sticky` to keep the nav fixed while
// the article list scrolls. `overflow-x: hidden` on an ancestor (`.app-shell`)
// silently turns it into a scroll container and breaks sticky positioning.
// `overflow-x: clip` guards against horizontal overflow without that side
// effect. This guards against regressing back to `hidden`.
describe('.app-shell horizontal overflow', () => {
  const css = readFileSync(join(import.meta.dirname, '../globals.css'), 'utf8');

  const appShellBlock = /\.app-shell\s*\{[^}]*\}/.exec(css)?.[0] ?? '';

  it('exists', () => {
    expect(appShellBlock).toContain('overflow-x');
  });

  it('uses overflow-x: clip so sticky nav keeps working', () => {
    expect(appShellBlock).toMatch(/overflow-x:\s*clip/);
    expect(appShellBlock).not.toMatch(/overflow-x:\s*hidden/);
  });
});
