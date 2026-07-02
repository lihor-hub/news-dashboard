import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import type { WhatsNewState } from '@/hooks/useWhatsNew';

interface WhatsNewDialogProps {
  state: WhatsNewState;
}

export function WhatsNewDialog({ state }: WhatsNewDialogProps) {
  const { open, version, items, dismiss } = state;
  const hasItems = items.length > 0;
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) dismiss();
      }}
    >
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>✨ What's new</DialogTitle>
          <DialogDescription>
            {hasItems
              ? "We've been busy — here's what's new for you in this update."
              : 'Thanks for keeping the app up to date.'}
          </DialogDescription>
        </DialogHeader>
        {hasItems ? (
          <ul className="mt-1 space-y-1.5 text-sm text-foreground">
            {items.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="mt-0.5 text-muted-foreground select-none">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-sm text-muted-foreground">
            This update brings behind-the-scenes improvements to keep everything running smoothly
            and reliably.
          </p>
        )}
        <DialogFooter className="items-center sm:justify-between">
          <span className="text-xs text-muted-foreground">Version {version}</span>
          <Button size="sm" onClick={dismiss}>
            Got it
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
