import { createPortal } from 'react-dom';
import {
  Star,
  Check,
  Clock,
  X as XIcon,
  Archive,
  Loader2,
  Volume2,
  Square,
  Share2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AudioState } from '@/hooks/useArticleAudio';

function ActionBtn({
  onClick,
  icon: Icon,
  label,
  active,
  disabled,
}: {
  onClick: () => void;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  label: string;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex flex-col items-center justify-center gap-0.5 py-2 rounded-md text-[11px] font-medium transition-colors',
        active ? 'text-star' : 'text-muted-foreground hover:text-foreground hover:bg-surface',
        disabled && 'opacity-30 cursor-not-allowed hover:bg-transparent'
      )}
    >
      <Icon className={cn('size-5', active && 'fill-current')} strokeWidth={1.75} />
      {label}
    </button>
  );
}

export function ArticleActionBar({
  starred,
  onStar,
  onDone,
  onLater,
  onSkip,
  onArchive,
  onShare,
  audioState,
  onListen,
}: {
  starred: boolean;
  onStar: () => void;
  onDone: () => void;
  onLater: () => void;
  onSkip: () => void;
  onArchive: () => void;
  onShare: () => void;
  audioState: AudioState;
  onListen: () => void;
}) {
  // Rendered via portal so its position:fixed always resolves against the
  // viewport regardless of any CSS transform that may exist on an ancestor or
  // sibling of the ArticlePage root during the entry animation
  // (motion-slide-in-right carries transform:translateX in its from-keyframe;
  // even as a sibling, some mobile browser compositors bleed this transform
  // onto nearby fixed elements for the first paint).
  return createPortal(
    <div
      data-testid="action-bar"
      className="fixed bottom-0 inset-x-0 z-20 border-t border-border bg-background/95 backdrop-blur pb-[env(safe-area-inset-bottom)]"
    >
      <div className="mx-auto max-w-2xl grid grid-cols-7 gap-1 p-2">
        <ActionBtn
          onClick={onStar}
          icon={Star}
          label={starred ? 'Unstar' : 'Star'}
          active={starred}
        />
        <ActionBtn onClick={onDone} icon={Check} label="Done" />
        <ActionBtn onClick={onLater} icon={Clock} label="Later" />
        <ActionBtn onClick={onSkip} icon={XIcon} label="Skip" disabled={starred} />
        <ActionBtn onClick={onArchive} icon={Archive} label="Archive" />
        <ActionBtn
          onClick={onListen}
          icon={audioState === 'loading' ? Loader2 : audioState === 'playing' ? Square : Volume2}
          label={
            audioState === 'loading'
              ? 'Loading…'
              : audioState === 'playing'
                ? 'Stop'
                : audioState === 'paused'
                  ? 'Resume'
                  : 'Listen'
          }
          disabled={audioState === 'loading'}
        />
        <ActionBtn onClick={onShare} icon={Share2} label="Share" />
      </div>
    </div>,
    document.body
  );
}
