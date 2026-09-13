import { useTranslation } from 'react-i18next';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { navigationShortcutRows } from '@/lib/navigation';

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}

const SECTIONS: { titleKey: string; items: [string, string][] }[] = [
  {
    titleKey: 'shortcuts.sections.navigation',
    items: navigationShortcutRows,
  },
  {
    titleKey: 'shortcuts.sections.articleActions',
    items: [
      ['r or d', 'shortcuts.articleActions.done'],
      ['l', 'shortcuts.articleActions.later'],
      ['s', 'shortcuts.articleActions.star'],
      ['x', 'shortcuts.articleActions.skip'],
      ['e', 'shortcuts.articleActions.archive'],
      ['o', 'shortcuts.articleActions.openOriginal'],
    ],
  },
  {
    titleKey: 'shortcuts.sections.app',
    items: [
      ['⌘K / Ctrl+K', 'shortcuts.app.commandPalette'],
      ['?', 'shortcuts.app.showOverlay'],
    ],
  },
];

export function ShortcutOverlay({ open, onOpenChange }: Props) {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-sm">{t('shortcuts.title')}</DialogTitle>
        </DialogHeader>
        <div className="space-y-5">
          {SECTIONS.map((s) => (
            <div key={s.titleKey}>
              <div className="text-[10px] font-medium uppercase tracking-wider text-subtle mb-2">
                {t(s.titleKey)}
              </div>
              <div className="space-y-1.5">
                {s.items.map(([k, d]) => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{t(d)}</span>
                    <kbd className="font-mono text-[11px] px-1.5 py-0.5 bg-surface-2 border border-border rounded">
                      {k}
                    </kbd>
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
