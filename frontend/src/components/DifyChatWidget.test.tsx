import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import type { User } from '@/types';

let DifyChatWidget: typeof import('./DifyChatWidget').DifyChatWidget;

const user: User = {
  id: 42,
  username: 'alice',
  email: 'alice@example.com',
  is_admin: false,
};

const anotherUser: User = {
  id: 99,
  username: 'bob',
  email: 'bob@example.com',
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

function appendSpy() {
  const append = document.body.append.bind(document.body);
  return vi
    .spyOn(document.body, 'append')
    .mockImplementation((...nodes: (Node | string)[]) => append(...nodes));
}

function appendedScripts(spy: ReturnType<typeof appendSpy>): HTMLScriptElement[] {
  return spy.mock.calls
    .flat()
    .filter((node): node is HTMLScriptElement => node instanceof HTMLScriptElement);
}

function addDifyDom(): void {
  const bubble = document.createElement('div');
  bubble.id = 'dify-chatbot-bubble-button';
  document.body.append(bubble);
  const windowElement = document.createElement('iframe');
  windowElement.id = 'dify-chatbot-bubble-window';
  document.body.append(windowElement);
}

function markScriptLoaded(): void {
  document.querySelector<HTMLScriptElement>(scriptSelector)?.dispatchEvent(new Event('load'));
}

beforeEach(async () => {
  vi.resetModules();
  ({ DifyChatWidget } = await import('./DifyChatWidget'));
});

afterEach(() => {
  cleanup();
  document.querySelectorAll(scriptSelector).forEach((script) => script.remove());
  document.getElementById('dify-chatbot-bubble-button')?.remove();
  document.getElementById('dify-chatbot-bubble-window')?.remove();
  document.getElementById('host-dify-style')?.remove();
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

  it('keeps the singleton script installed but hides Dify after unmounting', async () => {
    mockScriptLoading();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(configResponse(enabledConfig())));

    const { unmount } = render(<DifyChatWidget user={user} />);

    await waitFor(() => expect(document.querySelector(scriptSelector)).not.toBeNull());
    markScriptLoaded();
    unmount();
    addDifyDom();

    expect(document.querySelector(scriptSelector)).not.toBeNull();
    expect(difyConfig()).toBeUndefined();
    await waitFor(() => {
      expect(document.getElementById('dify-chatbot-bubble-button')).toBeNull();
      expect(document.getElementById('dify-chatbot-bubble-window')).toBeNull();
    });
  });

  it('restores the detached Dify DOM for a same-user remount without a second script', async () => {
    mockScriptLoading();
    const spy = appendSpy();
    const fetchMock = vi
      .fn()
      .mockImplementation(() => Promise.resolve(configResponse(enabledConfig())));
    vi.stubGlobal('fetch', fetchMock);

    const firstMount = render(<DifyChatWidget user={user} />);

    await waitFor(() => expect(appendedScripts(spy)).toHaveLength(1));
    markScriptLoaded();
    addDifyDom();
    firstMount.unmount();
    expect(document.getElementById('dify-chatbot-bubble-button')).toBeNull();
    expect(document.getElementById('dify-chatbot-bubble-window')).toBeNull();

    render(<DifyChatWidget user={user} />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(difyConfig()).not.toBeUndefined());
    await waitFor(() => {
      expect(document.getElementById('dify-chatbot-bubble-button')).not.toBeNull();
      expect(document.getElementById('dify-chatbot-bubble-window')).not.toBeNull();
    });
    expect(appendedScripts(spy)).toHaveLength(1);
    expect(difyConfig()).toEqual({
      token: 'public-embed-token',
      baseUrl: 'https://dify.example.test',
      dynamicScript: true,
      systemVariables: { user_id: '42' },
      containerProps: { title: 'News Assistant' },
    });
  });

  it('clears the global configuration when Dify fails before loading', async () => {
    mockScriptLoading();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(configResponse(enabledConfig())));

    render(<DifyChatWidget user={user} />);

    await waitFor(() => expect(document.querySelector(scriptSelector)).not.toBeNull());
    document.querySelector<HTMLScriptElement>(scriptSelector)?.dispatchEvent(new Event('error'));

    expect(difyConfig()).toBeUndefined();
  });

  it('clears the global configuration when unmounted before Dify loads', async () => {
    mockScriptLoading();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(configResponse(enabledConfig())));

    const { unmount } = render(<DifyChatWidget user={user} />);

    await waitFor(() => expect(document.querySelector(scriptSelector)).not.toBeNull());
    unmount();

    expect(difyConfig()).toBeUndefined();
  });

  it('completes a pending Dify load after the same user remounts', async () => {
    mockScriptLoading();
    const spy = appendSpy();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(configResponse(enabledConfig())));

    const firstMount = render(<DifyChatWidget user={user} />);

    await waitFor(() => expect(appendedScripts(spy)).toHaveLength(1));
    firstMount.unmount();
    expect(difyConfig()).toBeUndefined();

    render(<DifyChatWidget user={user} />);

    await waitFor(() => expect(difyConfig()).not.toBeUndefined());
    addDifyDom();
    markScriptLoaded();

    expect(appendedScripts(spy)).toHaveLength(1);
    expect(document.getElementById('dify-chatbot-bubble-button')).not.toBeNull();
    expect(document.getElementById('dify-chatbot-bubble-window')).not.toBeNull();
  });

  it('does not execute Dify again after a same-document user switch', async () => {
    mockScriptLoading();
    const spy = appendSpy();
    const fetchMock = vi.fn().mockResolvedValue(configResponse(enabledConfig()));
    vi.stubGlobal('fetch', fetchMock);

    const { rerender } = render(<DifyChatWidget user={user} />);

    await waitFor(() => expect(appendedScripts(spy)).toHaveLength(1));
    markScriptLoaded();
    addDifyDom();
    rerender(<DifyChatWidget user={anotherUser} />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(appendedScripts(spy)).toHaveLength(1);
    expect(difyConfig()).toBeUndefined();
    expect(document.getElementById('dify-chatbot-bubble-button')).toBeNull();
    expect(document.getElementById('dify-chatbot-bubble-window')).toBeNull();
  });

  it('does not duplicate the singleton script in React StrictMode', async () => {
    mockScriptLoading();
    const spy = appendSpy();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(configResponse(enabledConfig())));

    render(
      <StrictMode>
        <DifyChatWidget user={user} />
      </StrictMode>
    );

    await waitFor(() => expect(appendedScripts(spy)).toHaveLength(1));
    expect(document.querySelectorAll(scriptSelector)).toHaveLength(1);
  });

  it('preserves host styles that target Dify bubble elements', async () => {
    mockScriptLoading();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(configResponse(enabledConfig())));
    const hostStyle = document.createElement('style');
    hostStyle.id = 'host-dify-style';
    hostStyle.textContent = '#dify-chatbot-bubble-button { color: red; }';
    document.head.append(hostStyle);

    const { unmount } = render(<DifyChatWidget user={user} />);

    await waitFor(() => expect(document.querySelector(scriptSelector)).not.toBeNull());
    unmount();

    expect(document.getElementById('host-dify-style')).toBe(hostStyle);
  });
});
