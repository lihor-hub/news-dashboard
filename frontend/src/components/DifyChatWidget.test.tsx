import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DifyChatWidget } from './DifyChatWidget';

let previousFetchInterceptor: unknown;

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

function renderWidget() {
  return render(<DifyChatWidget />);
}

async function renderEnabledWidget() {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(configResponse(enabledConfig())));
  const view = renderWidget();
  const launcher = await screen.findByRole('button', { name: 'Open News Assistant' });
  return { ...view, launcher };
}

beforeEach(() => {
  const happyDom = (
    window as typeof window & {
      happyDOM?: { settings: { fetch: { interceptor: unknown } } };
    }
  ).happyDOM;
  previousFetchInterceptor = happyDom?.settings.fetch.interceptor;
  if (happyDom) {
    happyDom.settings.fetch.interceptor = {
      beforeAsyncRequest: async () =>
        new Response('<!doctype html><html><body></body></html>', {
          status: 200,
          headers: { 'Content-Type': 'text/html' },
        }),
    };
  }
});

afterEach(() => {
  cleanup();
  const happyDom = (
    window as typeof window & {
      happyDOM?: { settings: { fetch: { interceptor: unknown } } };
    }
  ).happyDOM;
  if (happyDom) {
    happyDom.settings.fetch.interceptor = previousFetchInterceptor;
  }
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('DifyChatWidget', () => {
  it.each([
    ['disabled', { enabled: false, base_url: null, app_token: null, title: 'News Assistant' }],
    [
      'malformed',
      {
        enabled: true,
        base_url: 'http://dify.example.test',
        app_token: 'public-embed-token',
        title: 'News Assistant',
      },
    ],
  ])('shows no launcher when public configuration is %s', async (_case, dify) => {
    const fetchMock = vi.fn().mockResolvedValue(configResponse(dify));
    vi.stubGlobal('fetch', fetchMock);

    renderWidget();

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/config', { credentials: 'same-origin' })
    );
    expect(screen.queryByRole('button', { name: /News Assistant/ })).not.toBeInTheDocument();
    expect(document.querySelector('iframe')).toBeNull();
  });

  it('shows a launcher without loading Dify until the launcher is opened', async () => {
    const { launcher } = await renderEnabledWidget();

    expect(launcher).toHaveAttribute('title', 'Open News Assistant');
    expect(document.querySelector('iframe')).toBeNull();
  });

  it('opens an accessibly named popup and exact Dify WebApp iframe from the keyboard', async () => {
    const keyboard = userEvent.setup();
    const { launcher } = await renderEnabledWidget();

    await keyboard.tab();
    expect(launcher).toHaveFocus();
    await keyboard.keyboard('{Enter}');

    expect(screen.getByRole('dialog', { name: 'News Assistant' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Close News Assistant' })).toBeInTheDocument();
    const iframe = screen.getByTitle<HTMLIFrameElement>('News Assistant conversation');
    expect(iframe.src).toBe('https://dify.example.test/chatbot/public-embed-token');
  });

  it('does not render a second host heading above Dify', async () => {
    const pointer = userEvent.setup();
    const { launcher } = await renderEnabledWidget();
    await pointer.click(launcher);

    const dialog = screen.getByRole('dialog', { name: 'News Assistant' });
    expect(within(dialog).queryByRole('heading')).not.toBeInTheDocument();
  });

  it('sandboxes Dify capabilities without granting top navigation', async () => {
    const pointer = userEvent.setup();
    const { launcher } = await renderEnabledWidget();
    await pointer.click(launcher);

    const iframe = screen.getByTitle<HTMLIFrameElement>('News Assistant conversation');
    const sandboxTokens = iframe.sandbox;
    expect([...sandboxTokens]).toEqual([
      'allow-scripts',
      'allow-same-origin',
      'allow-forms',
      'allow-downloads',
      'allow-popups',
    ]);
    expect([...sandboxTokens].some((token) => token.startsWith('allow-top-navigation'))).toBe(
      false
    );
    expect(sandboxTokens).not.toContain('allow-popups-to-escape-sandbox');
  });

  it('removes the iframe when the popup closes', async () => {
    const pointer = userEvent.setup();
    const { launcher } = await renderEnabledWidget();
    await pointer.click(launcher);

    await pointer.click(screen.getByRole('button', { name: 'Close News Assistant' }));

    expect(screen.queryByRole('dialog', { name: 'News Assistant' })).not.toBeInTheDocument();
    expect(screen.queryByTitle('News Assistant conversation')).not.toBeInTheDocument();
  });

  it('removes an open iframe when the component unmounts', async () => {
    const pointer = userEvent.setup();
    const { launcher, unmount } = await renderEnabledWidget();
    await pointer.click(launcher);
    expect(screen.getByTitle('News Assistant conversation')).toBeInTheDocument();

    unmount();

    expect(screen.queryByTitle('News Assistant conversation')).not.toBeInTheDocument();
  });

  it('creates a fresh iframe when reopened after a load failure', async () => {
    const pointer = userEvent.setup();
    const { launcher } = await renderEnabledWidget();
    await pointer.click(launcher);
    const failedIframe = screen.getByTitle<HTMLIFrameElement>('News Assistant conversation');
    fireEvent.error(failedIframe);

    await pointer.click(screen.getByRole('button', { name: 'Close News Assistant' }));
    const retryLauncher = screen.getByRole('button', { name: 'Open News Assistant' });
    await pointer.click(retryLauncher);

    const retryIframe = screen.getByTitle<HTMLIFrameElement>('News Assistant conversation');
    expect(retryIframe).not.toBe(failedIframe);
    expect(retryIframe.src).toBe('https://dify.example.test/chatbot/public-embed-token');
  });

  it('handles Escape while focus is in the parent dialog and restores launcher focus', async () => {
    const keyboard = userEvent.setup();
    const { launcher } = await renderEnabledWidget();
    expect(launcher.tagName).toBe('BUTTON');

    launcher.focus();
    await keyboard.keyboard(' ');
    const closeButton = screen.getByRole('button', { name: 'Close News Assistant' });
    expect(closeButton.tagName).toBe('BUTTON');
    expect(closeButton).toHaveAttribute('title', 'Close News Assistant');
    expect(closeButton).toHaveFocus();

    await keyboard.keyboard('{Escape}');

    const restoredLauncher = screen.getByRole('button', { name: 'Open News Assistant' });
    expect(restoredLauncher).toHaveFocus();
  });

  it('sends no News Dashboard identity or context in the iframe URL', async () => {
    const pointer = userEvent.setup();
    const { launcher } = await renderEnabledWidget();
    await pointer.click(launcher);

    const iframe = screen.getByTitle<HTMLIFrameElement>('News Assistant conversation');
    const iframeUrl = new URL(iframe.src);
    expect(iframeUrl.origin).toBe('https://dify.example.test');
    expect(iframeUrl.pathname).toBe('/chatbot/public-embed-token');
    expect(iframeUrl.search).toBe('');
    expect(iframeUrl.hash).toBe('');
    expect(iframe).toHaveAttribute('referrerpolicy', 'no-referrer');
  });
});
