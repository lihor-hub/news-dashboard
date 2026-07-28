import { useEffect } from 'react';
import type { User } from '@/types';
import { fetchPublicConfig } from '@/lib/publicConfig';

const SCRIPT_ID = 'news-dashboard-dify-chatbot-script';
const DIFY_BUBBLE_ID = 'dify-chatbot-bubble-button';
const DIFY_WINDOW_ID = 'dify-chatbot-bubble-window';

interface DifyChatbotConfig {
  token: string;
  baseUrl: string;
  dynamicScript: true;
  systemVariables: { user_id: string };
  containerProps: { title: string };
}

type DifyWindow = Window & { difyChatbotConfig?: DifyChatbotConfig };

interface DifyWidgetSession {
  userId: string;
  config: DifyChatbotConfig;
  script: HTMLScriptElement;
  observer: MutationObserver;
  detachedNodes: HTMLElement[];
  active: boolean;
  loaded: boolean;
  canRestore: boolean;
}

let session: DifyWidgetSession | null = null;

function detachDifyDomState(widgetSession: DifyWidgetSession): void {
  [DIFY_BUBBLE_ID, DIFY_WINDOW_ID].forEach((id) => {
    const node = document.getElementById(id);
    if (node && !widgetSession.detachedNodes.includes(node)) {
      widgetSession.detachedNodes.push(node);
      node.remove();
    }
  });
}

function restoreDifyDomState(widgetSession: DifyWidgetSession): void {
  document.body.append(...widgetSession.detachedNodes);
  widgetSession.detachedNodes = [];
}

function hideSession(widgetSession: DifyWidgetSession): void {
  widgetSession.active = false;
  const difyWindow = window as DifyWindow;
  if (difyWindow.difyChatbotConfig === widgetSession.config) {
    delete difyWindow.difyChatbotConfig;
  }
  detachDifyDomState(widgetSession);
}

function createSession(
  userId: string,
  config: DifyChatbotConfig,
  script: HTMLScriptElement
): DifyWidgetSession {
  let widgetSession: DifyWidgetSession;
  const observer = new MutationObserver(() => {
    if (!widgetSession.script.isConnected) {
      widgetSession.observer.disconnect();
      return;
    }
    if (!widgetSession.active) detachDifyDomState(widgetSession);
  });
  widgetSession = {
    userId,
    config,
    script,
    observer,
    detachedNodes: [],
    active: true,
    loaded: false,
    canRestore: true,
  };
  widgetSession.observer.observe(document.body, { childList: true, subtree: true });
  return widgetSession;
}

export function DifyChatWidget({ user }: { user: User }) {
  useEffect(() => {
    let mounted = true;
    const userId = String(user.id);

    const loadWidget = async (): Promise<void> => {
      try {
        if (session && !session.loaded) {
          if (session.userId !== userId) {
            session.canRestore = false;
            hideSession(session);
            return;
          }
          if (session.canRestore) {
            session.active = true;
            (window as DifyWindow).difyChatbotConfig = session.config;
            restoreDifyDomState(session);
          }
          return;
        }

        const { dify } = await fetchPublicConfig();
        if (!mounted || !dify.enabled || !dify.app_token || !dify.base_url || !dify.title) return;

        if (session) {
          // Dify's embed captures its config and installs global listeners without a teardown API.
          // A second execution would retain the first user's closure, so this document fails closed.
          if (session.userId !== userId) {
            session.canRestore = false;
            hideSession(session);
            return;
          }
          if (session.canRestore) {
            session.active = true;
            (window as DifyWindow).difyChatbotConfig = session.config;
            restoreDifyDomState(session);
          }
          return;
        }

        const config: DifyChatbotConfig = {
          token: dify.app_token,
          baseUrl: dify.base_url,
          dynamicScript: true,
          systemVariables: { user_id: userId },
          containerProps: { title: dify.title },
        };
        const script = document.createElement('script');
        script.id = SCRIPT_ID;
        script.dataset.newsDashboardDify = 'true';
        script.src = `${dify.base_url}/embed.min.js`;
        script.async = true;

        const widgetSession = createSession(userId, config, script);
        session = widgetSession;
        (window as DifyWindow).difyChatbotConfig = config;
        script.addEventListener(
          'load',
          () => {
            widgetSession.loaded = true;
            if (!widgetSession.active) {
              widgetSession.canRestore = false;
              hideSession(widgetSession);
            }
          },
          { once: true }
        );
        script.addEventListener(
          'error',
          () => {
            widgetSession.canRestore = false;
            hideSession(widgetSession);
          },
          { once: true }
        );
        document.body.append(script);
      } catch {
        // This optional third-party integration must never interrupt navigation.
      }
    };

    // Deferring the initial request lets React StrictMode discard its probe effect
    // before any third-party global state or script can be created.
    queueMicrotask(() => {
      if (mounted) void loadWidget();
    });

    return () => {
      mounted = false;
      if (session?.userId === userId) {
        hideSession(session);
      }
    };
  }, [user.id]);

  return null;
}
