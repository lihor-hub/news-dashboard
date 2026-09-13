'use client';

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { Command } from 'cmdk';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { toast } from 'sonner';
import {
  Clock,
  Star,
  Search,
  Archive,
  FileText,
  RefreshCw,
  CheckCheck,
  SkipForward,
  ExternalLink,
} from 'lucide-react';
import { searchArticles, ingestNow } from '@/api';
import { adaptArticle } from '@/api/workflowApi';
import { useTriageMutations } from '@/hooks/useTriageMutations';
import { useFocusedArticle } from '@/contexts/focusedArticle';
import { useAuth } from '@/contexts/auth';
import type { WorkflowArticle } from '@/lib/workflowTypes';
import { commandNavigationItemsFor } from '@/lib/navigation';
import { trackFeature } from '@/lib/analytics';

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onShortcuts?: () => void;
}

const GROUP_CLS =
  '[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-foreground';

const ITEM_CLS =
  'flex items-center gap-2 px-2 py-2 rounded-md cursor-pointer data-[selected=true]:bg-surface-2';

export function CommandPalette({ open, onOpenChange, onShortcuts }: Props) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const mutations = useTriageMutations();
  const { article: focusedArticle } = useFocusedArticle();
  const { user } = useAuth();

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
      trackFeature('search');
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
    void navigate(to);
  }

  async function handleIngest() {
    close();
    trackFeature('ingest_now');
    const id = toast.loading(t('command_palette.ingest.loading'));
    try {
      const result = await ingestNow();
      toast.success(t('command_palette.ingest.success', { count: result.inserted }), {
        id,
      });
    } catch {
      toast.error(t('command_palette.ingest.error'), { id });
    }
  }

  function articleAction(fn: () => void) {
    close();
    fn();
  }

  function openArticle(a: WorkflowArticle) {
    close();
    void navigate(`/a/${a.id}`);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-0 max-w-xl overflow-hidden gap-0">
        <DialogTitle className="sr-only">{t('command_palette.title')}</DialogTitle>
        <DialogDescription className="sr-only">
          {t('command_palette.description')}
        </DialogDescription>
        <Command
          label={t('command_palette.input_label')}
          shouldFilter={false}
          className="bg-popover text-popover-foreground"
        >
          <div className="flex items-center px-3 border-b border-border">
            <Search className="size-4 text-muted-foreground shrink-0" />
            <Command.Input
              autoFocus
              value={q}
              onValueChange={setQ}
              aria-label={t('command_palette.input_label')}
              placeholder={t('command_palette.placeholder')}
              className="flex h-11 w-full bg-transparent px-3 text-sm outline-none placeholder:text-subtle"
            />
            {searching && (
              <span className="text-[10px] text-subtle shrink-0 animate-pulse">
                {t('command_palette.searching')}
              </span>
            )}
          </div>

          <Command.List
            label={t('command_palette.suggestions')}
            className="max-h-[60vh] overflow-y-auto p-2"
          >
            <Command.Empty className="py-8 text-center text-sm text-muted-foreground">
              {t(q.trim() ? 'command_palette.no_results' : 'command_palette.empty')}
            </Command.Empty>

            {/* Article search results */}
            {searchResults.length > 0 && (
              <Command.Group heading={t('command_palette.groups.articles')} className={GROUP_CLS}>
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
                heading={t('command_palette.focused_article', {
                  title:
                    focusedArticle.title.length > 50
                      ? focusedArticle.title.slice(0, 50) + '…'
                      : focusedArticle.title,
                })}
                className={GROUP_CLS}
              >
                <Command.Item
                  onSelect={() =>
                    articleAction(() =>
                      mutations.setState(focusedArticle, 'done', t('command_palette.status.done'))
                    )
                  }
                  className={ITEM_CLS}
                >
                  <CheckCheck className="size-4 text-muted-foreground" />
                  <span className="text-sm">{t('command_palette.actions.done')}</span>
                  <kbd className="ms-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                    r / d
                  </kbd>
                </Command.Item>
                <Command.Item
                  onSelect={() => articleAction(() => mutations.sendLater(focusedArticle))}
                  className={ITEM_CLS}
                >
                  <Clock className="size-4 text-muted-foreground" />
                  <span className="text-sm">{t('command_palette.actions.later')}</span>
                  <kbd className="ms-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                    l
                  </kbd>
                </Command.Item>
                <Command.Item
                  onSelect={() => articleAction(() => mutations.toggleStar(focusedArticle))}
                  className={ITEM_CLS}
                >
                  <Star className="size-4 text-muted-foreground" />
                  <span className="text-sm">
                    {t(
                      focusedArticle.starred
                        ? 'command_palette.actions.unstar'
                        : 'command_palette.actions.star'
                    )}
                  </span>
                  <kbd className="ms-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                    s
                  </kbd>
                </Command.Item>
                {!focusedArticle.starred && (
                  <Command.Item
                    onSelect={() =>
                      articleAction(() =>
                        mutations.setState(
                          focusedArticle,
                          'skipped',
                          t('command_palette.status.skipped')
                        )
                      )
                    }
                    className={ITEM_CLS}
                  >
                    <SkipForward className="size-4 text-muted-foreground" />
                    <span className="text-sm">{t('command_palette.actions.skip')}</span>
                    <kbd className="ms-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                      x
                    </kbd>
                  </Command.Item>
                )}
                <Command.Item
                  onSelect={() =>
                    articleAction(() =>
                      mutations.setState(
                        focusedArticle,
                        'archived',
                        t('command_palette.status.archived')
                      )
                    )
                  }
                  className={ITEM_CLS}
                >
                  <Archive className="size-4 text-muted-foreground" />
                  <span className="text-sm">{t('command_palette.actions.archive')}</span>
                  <kbd className="ms-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
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
                  <span className="text-sm">{t('command_palette.actions.open_original')}</span>
                  <kbd className="ms-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                    o
                  </kbd>
                </Command.Item>
              </Command.Group>
            )}

            {/* Navigation */}
            <Command.Group heading={t('command_palette.groups.navigation')} className={GROUP_CLS}>
              {commandNavigationItemsFor(Boolean(user?.is_admin)).map(
                ({ icon: Icon, labelKey, to }) => (
                  <Command.Item key={to} onSelect={() => go(to)} className={ITEM_CLS}>
                    <Icon className="size-4 text-muted-foreground" />
                    <span className="text-sm">{t(labelKey)}</span>
                  </Command.Item>
                )
              )}
            </Command.Group>

            {/* App actions */}
            <Command.Group heading={t('command_palette.groups.actions')} className={GROUP_CLS}>
              {user?.is_admin && (
                <Command.Item
                  onSelect={() => {
                    void handleIngest();
                  }}
                  className={ITEM_CLS}
                >
                  <RefreshCw className="size-4 text-muted-foreground" />
                  <span className="text-sm">{t('command_palette.actions.refresh')}</span>
                </Command.Item>
              )}
              {onShortcuts && (
                <Command.Item
                  onSelect={() => {
                    close();
                    onShortcuts();
                  }}
                  className={ITEM_CLS}
                >
                  <span className="text-sm text-muted-foreground">
                    {t('command_palette.actions.shortcuts')}
                  </span>
                  <kbd className="ms-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
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
