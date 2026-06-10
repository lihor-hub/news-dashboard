import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}

const SECTIONS: { title: string; items: [string, string][] }[] = [
  {
    title: "Navigation",
    items: [
      ["j / k", "Move down / up in list"],
      ["Enter", "Open selected article"],
      ["g t / g l / g s", "Go to Today / Later / Starred"],
      ["g a / g f", "Go to Ask / Feeds"],
    ],
  },
  {
    title: "Article actions",
    items: [
      ["r or d", "Mark Done"],
      ["l", "Send to Later"],
      ["s", "Star / Unstar"],
      ["x", "Skip (unless Starred)"],
      ["e", "Archive"],
      ["o", "Open original externally"],
    ],
  },
  {
    title: "App",
    items: [
      ["⌘K / Ctrl+K", "Command palette"],
      ["?", "Show this overlay"],
    ],
  },
];

export function ShortcutOverlay({ open, onOpenChange }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-sm">Keyboard shortcuts</DialogTitle>
        </DialogHeader>
        <div className="space-y-5">
          {SECTIONS.map((s) => (
            <div key={s.title}>
              <div className="text-[10px] font-medium uppercase tracking-wider text-subtle mb-2">{s.title}</div>
              <div className="space-y-1.5">
                {s.items.map(([k, d]) => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{d}</span>
                    <kbd className="font-mono text-[11px] px-1.5 py-0.5 bg-surface-2 border border-border rounded">{k}</kbd>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
