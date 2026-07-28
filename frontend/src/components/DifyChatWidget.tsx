import { useEffect, useRef, useState } from 'react';
import { MessageCircle, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fetchPublicConfig } from '@/lib/publicConfig';
import type { PublicDifyConfig } from '@/lib/publicConfig';

export function DifyChatWidget() {
  const [dify, setDify] = useState<PublicDifyConfig | null>(null);
  const [open, setOpen] = useState(false);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const restoreLauncherFocus = useRef(false);

  useEffect(() => {
    let mounted = true;

    const loadConfig = async (): Promise<void> => {
      try {
        const config = await fetchPublicConfig();
        if (mounted) setDify(config.dify);
      } catch {
        // This optional integration must never interrupt News Dashboard navigation.
      }
    };

    void loadConfig();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (open) {
      closeRef.current?.focus();
    } else if (restoreLauncherFocus.current) {
      launcherRef.current?.focus();
    }
  }, [open]);

  if (!dify?.enabled || !dify.base_url || !dify.app_token || !dify.title) return null;

  const openLabel = `Open ${dify.title}`;
  const closeLabel = `Close ${dify.title}`;
  const iframeTitle = `${dify.title} conversation`;
  const iframeUrl = `${dify.base_url}/chatbot/${encodeURIComponent(dify.app_token)}`;

  if (!open) {
    return (
      <Button
        ref={launcherRef}
        type="button"
        size="icon"
        className="fixed right-4 bottom-[calc(68px+env(safe-area-inset-bottom))] z-50 size-12 rounded-full shadow-lg focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-background md:bottom-4"
        aria-label={openLabel}
        title={openLabel}
        onClick={() => {
          restoreLauncherFocus.current = true;
          setOpen(true);
        }}
      >
        <MessageCircle className="size-5" aria-hidden="true" />
      </Button>
    );
  }

  return (
    <section
      role="dialog"
      aria-label={dify.title}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          setOpen(false);
        }
      }}
      className="fixed right-2 bottom-[calc(68px+env(safe-area-inset-bottom))] z-50 flex h-[calc(100dvh-76px-env(safe-area-inset-bottom))] max-h-[44rem] w-[calc(100vw-1rem)] flex-col overflow-hidden rounded-xl border border-border bg-background shadow-2xl md:right-4 md:bottom-4 md:h-[min(44rem,calc(100dvh-2rem))] md:max-h-none md:w-96"
    >
      <header className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b border-border px-3">
        <h2 className="truncate text-sm font-semibold">{dify.title}</h2>
        <Button
          ref={closeRef}
          type="button"
          size="icon"
          variant="ghost"
          className="size-11 shrink-0 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          aria-label={closeLabel}
          title={closeLabel}
          onClick={() => setOpen(false)}
        >
          <X aria-hidden="true" />
        </Button>
      </header>
      <iframe
        className="min-h-0 w-full flex-1 border-0 bg-background"
        src={iframeUrl}
        title={iframeTitle}
        referrerPolicy="no-referrer"
      />
    </section>
  );
}
