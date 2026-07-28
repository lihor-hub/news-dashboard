import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, waitFor } from '@testing-library/react';
import { DifyChatWidget } from './DifyChatWidget';
import type { User } from '@/types';

const user: User = {
  id: 42,
  username: 'alice',
  email: 'alice@example.com',
  is_admin: false,
};

const scriptSelector = 'script[data-news-dashboard-dify="true"]';

function configResponse(dify: unknown): Response {
  return new Response(JSON.stringify({ dify }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

function enabledConfig() {
  return {
    enabled: true,
    base_url: 'https://dify.example.test',
    app_token: 'public-embed-token',
    title: 'News Assistant',
  };
}

function difyConfig(): unknown {
  return (window as typeof window & { difyChatbotConfig?: unknown }).difyChatbotConfig;
}

function mockScriptLoading(): void {
  const sources = new WeakMap<HTMLScriptElement, string>();
  vi.spyOn(HTMLScriptElement.prototype, 'src', 'set').mockImplementation(function (
    this: HTMLScriptElement,
    value: string
  ) {
    sources.set(this, value);
  });
  vi.spyOn(HTMLScriptElement.prototype, 'src', 'get').mockImplementation(function (
    this: HTMLScriptElement
  ) {
    return sources.get(this) ?? '';
  });
}

afterEach(() => {
  cleanup();
  document.querySelectorAll(scriptSelector).forEach((script) => script.remove());
  document.getElementById('dify-chatbot-bubble-button')?.remove();
  document.getElementById('dify-chatbot-bubble-window')?.remove();
  delete (window as typeof window & { difyChatbotConfig?: unknown }).difyChatbotConfig;
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('DifyChatWidget', () => {
  it('keeps Dify inert when the public configuration is disabled', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        configResponse({ enabled: false, base_url: null, app_token: null, title: 'News Assistant' })
      );
    vi.stubGlobal('fetch', fetchMock);

    render(<DifyChatWidget user={user} />);

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/config', { credentials: 'same-origin' })
    );
    expect(document.querySelector(scriptSelector)).toBeNull();
    expect(difyConfig()).toBeUndefined();
  });

  it('keeps Dify inert when an enabled response has an unsafe base URL', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      configResponse({
        enabled: true,
        base_url: 'http://dify.example.test',
        app_token: 'public-embed-token',
        title: 'News Assistant',
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    render(<DifyChatWidget user={user} />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(document.querySelector(scriptSelector)).toBeNull();
    expect(difyConfig()).toBeUndefined();
  });

  it('loads Dify once with the opaque user ID as its only system context', async () => {
    mockScriptLoading();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(configResponse(enabledConfig())));

    const { rerender } = render(<DifyChatWidget user={user} />);

    await waitFor(() => expect(document.querySelector(scriptSelector)).not.toBeNull());
    rerender(<DifyChatWidget user={{ ...user }} />);

    const script = document.querySelector<HTMLScriptElement>(scriptSelector);
    expect(document.querySelectorAll(scriptSelector)).toHaveLength(1);
    expect(script?.src).toBe('https://dify.example.test/embed.min.js');
    expect(difyConfig()).toEqual({
      token: 'public-embed-token',
      baseUrl: 'https://dify.example.test',
      dynamicScript: true,
      systemVariables: { user_id: '42' },
      containerProps: { title: 'News Assistant' },
    });
  });

  it('removes its script, global configuration, and Dify DOM after unmounting', async () => {
    mockScriptLoading();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(configResponse(enabledConfig())));

    const { unmount } = render(<DifyChatWidget user={user} />);

    await waitFor(() => expect(document.querySelector(scriptSelector)).not.toBeNull());
    const bubble = document.createElement('div');
    bubble.id = 'dify-chatbot-bubble-button';
    document.body.append(bubble);
    const windowElement = document.createElement('iframe');
    windowElement.id = 'dify-chatbot-bubble-window';
    document.body.append(windowElement);

    unmount();

    expect(document.querySelector(scriptSelector)).toBeNull();
    expect(difyConfig()).toBeUndefined();
    expect(document.getElementById('dify-chatbot-bubble-button')).toBeNull();
    expect(document.getElementById('dify-chatbot-bubble-window')).toBeNull();
  });
});
