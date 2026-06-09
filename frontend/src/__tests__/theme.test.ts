// @vitest-environment happy-dom
import { describe, it, expect, beforeEach } from 'vitest';
import { applyTheme, getStoredTheme, setStoredTheme, initTheme } from '../lib/theme';

describe('theme management', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('defaults to system when no preference is stored', () => {
    expect(getStoredTheme()).toBe('system');
  });

  it('stores and applies dark theme', () => {
    setStoredTheme('dark');
    expect(localStorage.getItem('theme')).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('stores and applies light theme', () => {
    setStoredTheme('light');
    expect(localStorage.getItem('theme')).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('applyTheme sets dark attribute directly', () => {
    applyTheme('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('applyTheme sets light attribute directly', () => {
    applyTheme('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('initTheme reads stored preference and applies it', () => {
    localStorage.setItem('theme', 'dark');
    initTheme();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('initTheme falls back to system when no preference stored', () => {
    // jsdom does not match dark prefers-color-scheme, so system resolves to light
    initTheme();
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('setStoredTheme persists across reads', () => {
    setStoredTheme('dark');
    expect(getStoredTheme()).toBe('dark');
    setStoredTheme('light');
    expect(getStoredTheme()).toBe('light');
    setStoredTheme('system');
    expect(getStoredTheme()).toBe('system');
  });
});
