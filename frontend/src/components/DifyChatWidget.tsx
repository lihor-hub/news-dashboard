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

function removeDifyDomState(): void {
  document.getElementById(DIFY_BUBBLE_ID)?.remove();
  document.getElementById(DIFY_WINDOW_ID)?.remove();

  document.head.querySelectorAll('style').forEach((style) => {
    try {
      const isDifyStyle = Array.from(style.sheet?.cssRules ?? []).some((rule) =>
        rule.cssText.includes(`#${DIFY_BUBBLE_ID}`)
      );
      if (isDifyStyle) style.remove();
    } catch {
      // Cross-origin stylesheets cannot be inspected and are never Dify-owned inline styles.
    }
  });
}

export function DifyChatWidget({ user }: { user: User }) {
  useEffect(() => {
    let disposed = false;
    let ownedScript: HTMLScriptElement | null = null;
    let ownedConfig: DifyChatbotConfig | null = null;
    const difyWindow = window as DifyWindow;

    const clearOwnedState = (): void => {
      ownedScript?.remove();
      ownedScript = null;
      if (ownedConfig && difyWindow.difyChatbotConfig === ownedConfig) {
        delete difyWindow.difyChatbotConfig;
      }
      ownedConfig = null;
      removeDifyDomState();
    };

    const loadWidget = async (): Promise<void> => {
      try {
        const { dify } = await fetchPublicConfig();
        if (disposed || !dify.enabled) return;
        if (!dify.app_token || !dify.base_url || !dify.title) return;

        if (document.getElementById(SCRIPT_ID)) return;

        const config: DifyChatbotConfig = {
          token: dify.app_token,
          baseUrl: dify.base_url,
          dynamicScript: true,
          systemVariables: { user_id: String(user.id) },
          containerProps: { title: dify.title },
        };
        difyWindow.difyChatbotConfig = config;
        ownedConfig = config;

        const script = document.createElement('script');
        script.id = SCRIPT_ID;
        script.dataset.newsDashboardDify = 'true';
        script.src = `${dify.base_url}/embed.min.js`;
        script.async = true;
        script.addEventListener('error', clearOwnedState, { once: true });
        ownedScript = script;
        document.body.append(script);
      } catch {
        // This optional third-party integration must never interrupt navigation.
        clearOwnedState();
      }
    };

    void loadWidget();

    return () => {
      disposed = true;
      clearOwnedState();
    };
  }, [user.id]);

  return null;
}
