import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';
import { cn } from '../lib/utils';

const srcDir = join(import.meta.dirname, '..');
const css = readFileSync(join(srcDir, 'globals.css'), 'utf8');

function block(selector: RegExp): string {
  return selector.exec(css)?.[0] ?? '';
}

const rootBlock = block(/(^|\n):root\s*\{[^}]*\}/);
const darkBlock = block(/\[data-theme='dark'\]\s*\{[^}]*\}/);
const themeInline = block(/@theme inline\s*\{[^}]*\}/);

describe('layout design tokens', () => {
  it('uses a 10px base radius so controls land on 8px and dialogs on 16px', () => {
    expect(rootBlock).toMatch(/--radius:\s*0\.625rem/);
    expect(themeInline).toMatch(/--radius-md:\s*calc\(var\(--radius\) - 2px\)/);
    expect(themeInline).toMatch(/--radius-2xl:\s*calc\(var\(--radius\) \+ 6px\)/);
  });

  it('defines three elevation tokens in every theme block so themes can override them', () => {
    for (const themeBlock of [rootBlock, darkBlock]) {
      for (const level of [1, 2, 3]) {
        expect(themeBlock).toMatch(new RegExp(`--shadow-${level}:`));
      }
    }
    for (const level of [1, 2, 3]) {
      expect(themeInline).toContain(`--shadow-elevation-${level}: var(--shadow-${level})`);
    }
  });

  it('exposes motion tokens, including a spring ease for sheets', () => {
    expect(css).toMatch(/--ease-spring:/);
    expect(css).toMatch(/--ease-standard:/);
    for (const name of ['fast', 'base', 'slow', 'sheet']) {
      expect(rootBlock).toMatch(new RegExp(`--duration-${name}:`));
    }
  });

  it('collapses motion durations under prefers-reduced-motion', () => {
    const reduced = /@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*?\n\}/.exec(css)?.[0];
    expect(reduced).toBeDefined();
    expect(reduced).toMatch(/--duration-base:\s*0ms/);
    expect(reduced).toMatch(/--duration-sheet:\s*0ms/);
  });

  it('defines a 44px touch-target size and readable meta/reading text utilities', () => {
    expect(css).toMatch(/--spacing-touch:\s*2\.75rem/);
    expect(css).toMatch(/@utility text-meta\s*\{/);
    expect(css).toMatch(/@utility text-reading\s*\{/);
  });

  it('defines one mobile bottom bar height token that includes the safe-area inset', () => {
    expect(css).toMatch(/--spacing-mobile-nav:\s*4rem/);
    expect(rootBlock).toMatch(
      /--mobile-nav-h:\s*calc\(var\(--spacing-mobile-nav\) \+ [\d.]+rem \+ env\(safe-area-inset-bottom\)\)/
    );
    expect(rootBlock).toMatch(/--listen-player-h:\s*[\d.]+rem/);
  });

  it('keeps meta/reading text sizes separate from text colours when merging classes', () => {
    expect(cn('text-meta', 'text-muted-foreground')).toBe('text-meta text-muted-foreground');
    expect(cn('text-sm', 'text-meta')).toBe('text-meta');
    expect(cn('text-reading', 'text-foreground')).toBe('text-reading text-foreground');
  });
});

// Files owned by parallel layout workers; they sweep their own small text.
const PENDING_OWNERS = new Set([
  'components/AppShell.tsx',
  'components/NavLink.tsx',
  'components/CommandPalette.tsx',
  'components/CategoryFilter.tsx',
  'components/BriefingView.tsx',
  'components/EmptyState.tsx',
  'components/PageState.tsx',
  'pages/BriefPage.tsx',
  'pages/ArticlePage.tsx',
  'pages/InboxPage.tsx',
  'pages/LaterPage.tsx',
  'pages/StarredPage.tsx',
  'pages/SharedPage.tsx',
  'pages/ArchivePage.tsx',
  'pages/SearchPage.tsx',
]);

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (name === '__tests__' || name === 'node_modules') return [];
    if (statSync(full).isDirectory()) return walk(full);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [full] : [];
  });
}

describe('minimum text size', () => {
  it('never renders text below 12px via arbitrary text-[9-11px] classes', () => {
    const offenders = walk(srcDir)
      .map((file) => relative(srcDir, file))
      .filter((rel) => !PENDING_OWNERS.has(rel) && !rel.startsWith('components/article/'))
      .filter((rel) =>
        /text-\[(9|10|11)(\.\d+)?px\]/.test(readFileSync(join(srcDir, rel), 'utf8'))
      );
    expect(offenders).toEqual([]);
  });
});
