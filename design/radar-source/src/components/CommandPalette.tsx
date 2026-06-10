import { useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { Command } from "cmdk";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useApp } from "@/lib/store";
import { Inbox, Clock, Star, Search, Sparkles, Radio, BarChart3, Archive, Settings, FileText, RefreshCw } from "lucide-react";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}

export function CommandPalette({ open, onOpenChange }: Props) {
  const navigate = useNavigate();
  const articles = useApp((s) => s.articles);
  const refreshNow = useApp((s) => s.refreshNow);
  const [q, setQ] = useState("");

  useEffect(() => {
    if (!open) setQ("");
  }, [open]);

  const results = useMemo(() => {
    if (!q.trim()) return [];
    const lq = q.toLowerCase();
    return articles
      .filter((a) => a.title.toLowerCase().includes(lq) || a.reason.toLowerCase().includes(lq))
      .slice(0, 6);
  }, [q, articles]);

  const go = (to: string) => {
    onOpenChange(false);
    navigate({ to });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-0 max-w-xl overflow-hidden gap-0">
        <Command shouldFilter={false} className="bg-popover text-popover-foreground">
          <div className="flex items-center px-3 border-b border-border">
            <Search className="size-4 text-muted-foreground" />
            <Command.Input
              autoFocus
              value={q}
              onValueChange={setQ}
              placeholder="Jump to a view, search articles, run actions…"
              className="flex h-11 w-full bg-transparent px-3 text-sm outline-none placeholder:text-subtle"
            />
          </div>
          <Command.List className="max-h-[60vh] overflow-y-auto p-2">
            <Command.Empty className="py-8 text-center text-sm text-muted-foreground">
              No results
            </Command.Empty>
            {results.length > 0 && (
              <Command.Group heading="Articles" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-subtle">
                {results.map((a) => (
                  <Command.Item
                    key={a.id}
                    onSelect={() => {
                      onOpenChange(false);
                      navigate({ to: "/a/$id", params: { id: a.id } });
                    }}
                    className="flex flex-col items-start gap-0.5 px-2 py-2 rounded-md cursor-pointer data-[selected=true]:bg-surface-2"
                  >
                    <div className="flex items-center gap-2 text-[11px] text-subtle">
                      <FileText className="size-3" />
                      {a.sourceName} · {a.category}
                    </div>
                    <div className="text-sm font-medium">{a.title}</div>
                    <div className="text-xs text-muted-foreground line-clamp-1">{a.reason}</div>
                  </Command.Item>
                ))}
              </Command.Group>
            )}
            <Command.Group heading="Navigation" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-subtle">
              <Item icon={Inbox} label="Today" onSelect={() => go("/")} />
              <Item icon={Clock} label="Later" onSelect={() => go("/later")} />
              <Item icon={Star} label="Starred" onSelect={() => go("/starred")} />
              <Item icon={Search} label="Search" onSelect={() => go("/search")} />
              <Item icon={Sparkles} label="Ask AI" onSelect={() => go("/ask")} />
              <Item icon={Radio} label="Feeds" onSelect={() => go("/feeds")} />
              <Item icon={BarChart3} label="Stats" onSelect={() => go("/stats")} />
              <Item icon={Archive} label="Archive" onSelect={() => go("/archive")} />
              <Item icon={Settings} label="Settings" onSelect={() => go("/settings")} />
            </Command.Group>
            <Command.Group heading="Actions" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-subtle">
              <Item icon={RefreshCw} label="Refresh feeds now" onSelect={() => { refreshNow(); onOpenChange(false); }} />
            </Command.Group>
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}

function Item({ icon: Icon, label, onSelect }: { icon: any; label: string; onSelect: () => void }) {
  return (
    <Command.Item
      onSelect={onSelect}
      className="flex items-center gap-2.5 px-2 py-1.5 rounded-md text-sm cursor-pointer data-[selected=true]:bg-surface-2"
    >
      <Icon className="size-4 text-muted-foreground" />
      {label}
    </Command.Item>
  );
}
