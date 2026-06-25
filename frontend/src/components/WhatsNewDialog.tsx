import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import type { WhatsNewState } from '@/hooks/useWhatsNew';

interface WhatsNewDialogProps {
  state: WhatsNewState;
}

export function WhatsNewDialog({ state }: WhatsNewDialogProps) {
  const { open, version, items, dismiss } = state;
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) dismiss();
      }}
    >
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>What's new in v{version}</DialogTitle>
        </DialogHeader>
        <ul className="mt-1 space-y-1.5 text-sm text-foreground">
          {items.map((item) => (
            <li key={item} className="flex gap-2">
              <span className="mt-0.5 text-muted-foreground select-none">•</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
        <DialogFooter>
          <Button size="sm" onClick={dismiss}>
            Got it
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
