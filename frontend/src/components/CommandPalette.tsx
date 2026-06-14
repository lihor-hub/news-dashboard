'use client';

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Command } from 'cmdk';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { toast } from 'sonner';
import {
  Newspaper,
  Inbox,
  Clock,
  Star,
  Search,
  Sparkles,
  Radio,
  BarChart3,
  Archive,
  Settings,
  FileText,
  RefreshCw,
  CheckCheck,
  SkipForward,
  ExternalLink,
  History,
} from 'lucide-react';
import { searchArticles, ingestNow } from '@/api';
import { adaptArticle } from '@/api/workflowApi';
import { useTriageMutations } from '@/hooks/useTriageMutations';
import { useFocusedArticle } from '@/contexts/focusedArticle';
import type { WorkflowArticle } from '@/lib/workflowTypes';

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onShortcuts?: () => void;
}

const NAV_ITEMS = [
  { icon: Newspaper, label: 'Brief', to: '/' },
  { icon: History, label: 'Briefing History', to: '/briefs' },
  { icon: Inbox, label: 'Today', to: '/today' },
  { icon: Clock, label: 'Later', to: '/later' },
  { icon: Star, label: 'Starred', to: '/starred' },
  { icon: Search, label: 'Search', to: '/search' },
  { icon: Sparkles, label: 'Ask AI', to: '/ask' },
  { icon: Radio, label: 'Feeds', to: '/feeds' },
  { icon: BarChart3, label: 'Stats', to: '/stats' },
  { icon: Archive, label: 'Archive', to: '/archive' },
  { icon: Settings, label: 'Settings', to: '/settings' },
];

const GROUP_CLS =
  '[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-subtle';

const ITEM_CLS =
  'flex items-center gap-2 px-2 py-2 rounded-md cursor-pointer data-[selected=true]:bg-surface-2';

export function CommandPalette({ open, onOpenChange, onShortcuts }: Props) {
  const navigate = useNavigate();
  const mutations = useTriageMutations();
  const { article: focusedArticle } = useFocusedArticle();

  const [q, setQ] = useState('');
  const [searchResults, setSearchResults] = useState<WorkflowArticle[]>([]);
  const [searching, setSearching] = useState(false);

  // Reset query when palette closes
  useEffect(() => {
    if (!open) {
      setQ('');
      setSearchResults([]);
    }
  }, [open]);

  // Debounced search
  useEffect(() => {
    if (!q.trim()) {
      setSearchResults([]);
      return;
    }
    const doSearch = async () => {
      setSearching(true);
      try {
        const raw = await searchArticles(q.trim(), 6);
        setSearchResults(raw.map(adaptArticle));
      } catch {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    };
    const id = setTimeout(() => {
      void doSearch();
    }, 250);
    return () => clearTimeout(id);
  }, [q]);

  function close() {
    onOpenChange(false);
  }

  function go(to: string) {
    close();
    navigate(to);
  }

  async function handleIngest() {
    close();
    const id = toast.loading('Refreshing feeds…');
    try {
      const result = await ingestNow();
      toast.success(`Done — ${result.inserted} new article${result.inserted !== 1 ? 's' : ''}`, {
        id,
      });
    } catch {
      toast.error('Ingest failed', { id });
    }
  }

  function articleAction(fn: () => void) {
    close();
    fn();
  }

  // #79 not merged — open original URL with TODO seam for reader navigation
  function openArticle(a: WorkflowArticle) {
    close();
    // TODO(#79): navigate(`/a/${a.id}`) once the reader is implemented
    window.open(a.url, '_blank', 'noopener,noreferrer');
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-0 max-w-xl overflow-hidden gap-0">
        <Command shouldFilter={false} className="bg-popover text-popover-foreground">
          <div className="flex items-center px-3 border-b border-border">
            <Search className="size-4 text-muted-foreground shrink-0" />
            <Command.Input
              autoFocus
              value={q}
              onValueChange={setQ}
              placeholder="Jump to a view, search articles, run actions…"
              className="flex h-11 w-full bg-transparent px-3 text-sm outline-none placeholder:text-subtle"
            />
            {searching && (
              <span className="text-[10px] text-subtle shrink-0 animate-pulse">searching…</span>
            )}
          </div>

          <Command.List className="max-h-[60vh] overflow-y-auto p-2">
            <Command.Empty className="py-8 text-center text-sm text-muted-foreground">
              {q.trim() ? 'No articles found' : 'Type to search articles or pick an action'}
            </Command.Empty>

            {/* Article search results */}
            {searchResults.length > 0 && (
              <Command.Group heading="Articles" className={GROUP_CLS}>
                {searchResults.map((a) => (
                  <Command.Item
                    key={a.id}
                    onSelect={() => openArticle(a)}
                    className="flex flex-col items-start gap-0.5 px-2 py-2 rounded-md cursor-pointer data-[selected=true]:bg-surface-2"
                  >
                    <div className="flex items-center gap-2 text-[11px] text-subtle">
                      <FileText className="size-3 shrink-0" />
                      <span className="truncate">
                        {a.sourceName} · {a.category}
                      </span>
                    </div>
                    <div className="text-sm font-medium line-clamp-1">{a.title}</div>
                    <div className="text-xs text-muted-foreground line-clamp-1">{a.reason}</div>
                  </Command.Item>
                ))}
              </Command.Group>
            )}

            {/* Focused article actions */}
            {focusedArticle && (
              <Command.Group
                heading={`On: ${focusedArticle.title.length > 50 ? focusedArticle.title.slice(0, 50) + '…' : focusedArticle.title}`}
                className={GROUP_CLS}
              >
                <Command.Item
                  onSelect={() =>
                    articleAction(() => mutations.setState(focusedArticle, 'done', 'Done'))
                  }
                  className={ITEM_CLS}
                >
                  <CheckCheck className="size-4 text-muted-foreground" />
                  <span className="text-sm">Mark Done</span>
                  <kbd className="ml-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                    r / d
                  </kbd>
                </Command.Item>
                <Command.Item
                  onSelect={() => articleAction(() => mutations.sendLater(focusedArticle))}
                  className={ITEM_CLS}
                >
                  <Clock className="size-4 text-muted-foreground" />
                  <span className="text-sm">Send to Later</span>
                  <kbd className="ml-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                    l
                  </kbd>
                </Command.Item>
                <Command.Item
                  onSelect={() => articleAction(() => mutations.toggleStar(focusedArticle))}
                  className={ITEM_CLS}
                >
                  <Star className="size-4 text-muted-foreground" />
                  <span className="text-sm">{focusedArticle.starred ? 'Unstar' : 'Star'}</span>
                  <kbd className="ml-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                    s
                  </kbd>
                </Command.Item>
                {!focusedArticle.starred && (
                  <Command.Item
                    onSelect={() =>
                      articleAction(() => mutations.setState(focusedArticle, 'skipped', 'Skipped'))
                    }
                    className={ITEM_CLS}
                  >
                    <SkipForward className="size-4 text-muted-foreground" />
                    <span className="text-sm">Skip</span>
                    <kbd className="ml-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                      x
                    </kbd>
                  </Command.Item>
                )}
                <Command.Item
                  onSelect={() =>
                    articleAction(() => mutations.setState(focusedArticle, 'archived', 'Archived'))
                  }
                  className={ITEM_CLS}
                >
                  <Archive className="size-4 text-muted-foreground" />
                  <span className="text-sm">Archive</span>
                  <kbd className="ml-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                    e
                  </kbd>
                </Command.Item>
                <Command.Item
                  onSelect={() =>
                    articleAction(() =>
                      window.open(focusedArticle.url, '_blank', 'noopener,noreferrer')
                    )
                  }
                  className={ITEM_CLS}
                >
                  <ExternalLink className="size-4 text-muted-foreground" />
                  <span className="text-sm">Open original</span>
                  <kbd className="ml-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                    o
                  </kbd>
                </Command.Item>
              </Command.Group>
            )}

            {/* Navigation */}
            <Command.Group heading="Navigation" className={GROUP_CLS}>
              {NAV_ITEMS.map(({ icon: Icon, label, to }) => (
                <Command.Item key={to} onSelect={() => go(to)} className={ITEM_CLS}>
                  <Icon className="size-4 text-muted-foreground" />
                  <span className="text-sm">{label}</span>
                </Command.Item>
              ))}
            </Command.Group>

            {/* App actions */}
            <Command.Group heading="Actions" className={GROUP_CLS}>
              <Command.Item
                onSelect={() => {
                  void handleIngest();
                }}
                className={ITEM_CLS}
              >
                <RefreshCw className="size-4 text-muted-foreground" />
                <span className="text-sm">Refresh feeds now</span>
              </Command.Item>
              {onShortcuts && (
                <Command.Item
                  onSelect={() => {
                    close();
                    onShortcuts();
                  }}
                  className={ITEM_CLS}
                >
                  <span className="text-sm text-muted-foreground">Keyboard shortcuts</span>
                  <kbd className="ml-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                    ?
                  </kbd>
                </Command.Item>
              )}
            </Command.Group>
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
