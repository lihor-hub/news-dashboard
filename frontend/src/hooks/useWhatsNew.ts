import { useCallback, useEffect, useState } from 'react';
import { requestJson } from '@/api';

const STORAGE_KEY = 'lastSeenVersion';

interface ChangelogEntry {
  version: string;
  items: string[];
}

interface ChangelogResponse {
  version: string;
  entries: ChangelogEntry[];
}

export interface WhatsNewState {
  open: boolean;
  version: string;
  items: string[];
  dismiss: () => void;
}

export function useWhatsNew(): WhatsNewState {
  const [open, setOpen] = useState(false);
  const [version, setVersion] = useState('');
  const [items, setItems] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    requestJson<ChangelogResponse>('/api/changelog')
      .then((data) => {
        if (cancelled) return;
        const { version: current, entries } = data;
        const lastSeen = localStorage.getItem(STORAGE_KEY);
        if (lastSeen === current) return;
        const entry = entries.find((e) => e.version === current);
        setVersion(current);
        setItems(entry?.items ?? []);
        setOpen(true);
      })
      .catch(() => {
        // silently ignore — changelog is non-critical
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const dismiss = useCallback(() => {
    if (version) {
      localStorage.setItem(STORAGE_KEY, version);
    }
    setOpen(false);
  }, [version]);

  return { open, version, items, dismiss };
}
