'use client';

import { useEffect, useState } from 'react';
import { Command } from 'cmdk';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import {
  Inbox,
  Clock,
  Star,
  Search,
  Sparkles,
  Radio,
  BarChart3,
  Archive,
  Settings,
} from 'lucide-react';

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onNavigate?: (to: string) => void;
  onShortcuts?: () => void;
}

const NAV_ITEMS = [
  { icon: Inbox, label: 'Today', to: '/' },
  { icon: Clock, label: 'Later', to: '/later' },
  { icon: Star, label: 'Starred', to: '/starred' },
  { icon: Search, label: 'Search', to: '/search' },
  { icon: Sparkles, label: 'Ask AI', to: '/ask' },
  { icon: Radio, label: 'Feeds', to: '/feeds' },
  { icon: BarChart3, label: 'Stats', to: '/stats' },
  { icon: Archive, label: 'Archive', to: '/archive' },
  { icon: Settings, label: 'Settings', to: '/settings' },
];

export function CommandPalette({ open, onOpenChange, onNavigate, onShortcuts }: Props) {
  const [q, setQ] = useState('');

  useEffect(() => {
    if (!open) setQ('');
  }, [open]);

  function go(to: string) {
    onOpenChange(false);
    onNavigate?.(to);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-0 max-w-xl overflow-hidden gap-0">
        <Command shouldFilter={true} className="bg-popover text-popover-foreground">
          <div className="flex items-center px-3 border-b border-border">
            <Search className="size-4 text-muted-foreground" />
            <Command.Input
              autoFocus
              value={q}
              onValueChange={setQ}
              placeholder="Jump to a view…"
              className="flex h-11 w-full bg-transparent px-3 text-sm outline-none placeholder:text-subtle"
            />
          </div>
          <Command.List className="max-h-[60vh] overflow-y-auto p-2">
            <Command.Empty className="py-8 text-center text-sm text-muted-foreground">
              No results
            </Command.Empty>
            <Command.Group
              heading="Navigation"
              className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-subtle"
            >
              {NAV_ITEMS.map(({ icon: Icon, label, to }) => (
                <Command.Item
                  key={to}
                  onSelect={() => go(to)}
                  className="flex items-center gap-2 px-2 py-2 rounded-md cursor-pointer data-[selected=true]:bg-surface-2"
                >
                  <Icon className="size-4 text-muted-foreground" />
                  <span className="text-sm">{label}</span>
                </Command.Item>
              ))}
            </Command.Group>
            {onShortcuts && (
              <Command.Group
                heading="App"
                className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-subtle"
              >
                <Command.Item
                  onSelect={onShortcuts}
                  className="flex items-center gap-2 px-2 py-2 rounded-md cursor-pointer data-[selected=true]:bg-surface-2"
                >
                  <span className="text-sm text-muted-foreground">Keyboard shortcuts</span>
                  <kbd className="ml-auto font-mono text-[10px] px-1 py-0.5 bg-surface-2 border border-border rounded">
                    ?
                  </kbd>
                </Command.Item>
              </Command.Group>
            )}
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
