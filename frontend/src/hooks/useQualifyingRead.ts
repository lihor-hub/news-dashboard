import { useEffect, useState, type RefObject } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/auth';
import { requestJson } from '@/api/core';
import { fetchAnalyticsSettings } from '@/api/settings';

interface EvidenceResult {
  available: boolean;
  token?: string;
  sequence?: number;
  required_ms?: number;
  credited: boolean;
}

/** Body-only connected evidence, never generic app time or an offline outbox. */
export function useQualifyingRead(
  articleId: string,
  body: string | undefined,
  element: RefObject<HTMLDivElement | null>
) {
  const { user } = useAuth();
  const cache = useQueryClient();
  const [status, setStatus] = useState(
    'Automatic reading requires a loaded article, focus and analytics consent. Manual Done remains available.'
  );
  useEffect(() => {
    if (!user || user.is_guest || !body || !element.current) return;
    let disposed = false;
    let busy = false;
    let finished = false;
    let lease: EvidenceResult | null = null;
    let version = '';
    let consent = false;
    let visible = false;
    let progress = 0;
    let attentive = 0;
    let end = 0;
    let lastInteraction = performance.now();
    let previous = performance.now();
    let nextSend = previous;
    const accountId = user.id;
    const interact = () => {
      lastInteraction = performance.now();
    };
    const events = ['pointerdown', 'pointermove', 'touchstart', 'keydown', 'scroll'] as const;
    events.forEach((event) =>
      window.addEventListener(event, interact, { passive: true, capture: true })
    );
    const node = element.current;
    // Body geometry includes pane clipping and layout changes, not whole-reader scroll.
    function geometry() {
      const rect = node!.getBoundingClientRect();
      let top = 0;
      let bottom = window.innerHeight;
      for (let parent = node!.parentElement; parent; parent = parent.parentElement) {
        if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(parent).overflowY)) {
          const bounds = parent.getBoundingClientRect();
          top = Math.max(top, bounds.top);
          bottom = Math.min(bottom, bounds.bottom);
        }
      }
      visible =
        rect.height > 0 &&
        rect.width > 0 &&
        rect.right > 0 &&
        rect.left < window.innerWidth &&
        rect.bottom > top &&
        rect.top < bottom &&
        getComputedStyle(node!).visibility === 'visible';
      progress = visible
        ? Math.min(1, Math.max(0, (Math.min(bottom, rect.bottom) - rect.top) / rect.height))
        : 0;
    }
    async function send() {
      if (busy || disposed || finished || !version || !consent) return;
      busy = true;
      const sentAttentive = Math.min(15000, Math.floor(attentive));
      const sentEnd = Math.min(sentAttentive, Math.floor(end));
      attentive = 0;
      end = 0;
      try {
        const result = await requestJson<EvidenceResult>(
          `/api/articles/${articleId}/reading-evidence`,
          {
            method: 'POST',
            body: JSON.stringify(
              lease
                ? {
                    body_version: version,
                    token: lease.token,
                    sequence: (lease.sequence ?? 0) + 1,
                    attentive_ms: sentAttentive,
                    end_ms: sentEnd,
                    progress,
                  }
                : { body_version: version }
            ),
          }
        );
        if (disposed) return;
        lease = result.available ? result : null;
        if (!result.available) {
          consent = false;
          setStatus('Automatic reading is disabled. Manual Done still records progress.');
        } else if (result.credited) {
          finished = true;
          setStatus('Qualifying read recorded. Marking unread does not remove earned progress.');
          void cache.invalidateQueries({ queryKey: ['progress-rewards', accountId] });
          void cache.invalidateQueries({ queryKey: ['achievements'] });
          // Keep the active pane in place; its list refreshes on the next navigation.
        } else {
          setStatus(
            `Automatic completion: 90% of the article body, at least ${Math.round((result.required_ms ?? 120000) / 1000)} attentive seconds and 2 seconds at the end. Manual Done remains available.`
          );
        }
      } catch {
        lease = null;
        setStatus(
          'Automatic reading is paused or unavailable for this article. Use Done where article actions are authorized; no offline time is saved.'
        );
      } finally {
        busy = false;
        nextSend = performance.now() + (lease ? 10000 : 21000);
      }
    }
    void Promise.all([
      crypto.subtle.digest('SHA-256', new TextEncoder().encode(body)),
      fetchAnalyticsSettings(),
    ])
      .then(([digest, settings]) => {
        if (disposed) return;
        version = Array.from(new Uint8Array(digest), (byte) =>
          byte.toString(16).padStart(2, '0')
        ).join('');
        consent = settings.enabled && settings.global_enabled;
        if (!consent)
          setStatus('Automatic reading is disabled. Manual Done still records progress.');
      })
      .catch(() => {
        /* No consent response means no evidence. */
      });
    const timer = window.setInterval(() => {
      const now = performance.now();
      const delta = Math.max(0, Math.min(250, now - previous));
      previous = now;
      geometry();
      const eligible =
        document.visibilityState === 'visible' &&
        document.hasFocus() &&
        navigator.onLine &&
        visible &&
        now - lastInteraction < 300000;
      if (eligible && consent && lease) {
        attentive = Math.min(15000, attentive + delta);
        if (progress >= 0.9) end = Math.min(15000, end + delta);
        else end = 0;
      }
      if (eligible && now >= nextSend) void send();
    }, 250);
    return () => {
      disposed = true;
      clearInterval(timer);
      events.forEach((event) => window.removeEventListener(event, interact, true));
    };
  }, [articleId, body, element, user, cache]);
  return status;
}
