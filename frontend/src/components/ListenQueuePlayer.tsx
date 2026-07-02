import { Link } from 'react-router-dom';
import { Loader2, Pause, Play, SkipBack, SkipForward, X } from 'lucide-react';
import { useListenQueue } from '@/contexts/listenQueue';
import { cn } from '@/lib/utils';

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function ListenQueuePlayer() {
  const {
    current,
    currentIndex,
    queue,
    isPlaying,
    isLoading,
    currentTime,
    duration,
    playPause,
    next,
    prev,
    seek,
    stop,
  } = useListenQueue();

  if (!current) return null;

  return (
    <div
      role="region"
      aria-label="Listen queue player"
      className="fixed inset-x-0 bottom-[68px] z-40 border-t border-border bg-background/95 backdrop-blur md:bottom-0"
    >
      <input
        type="range"
        aria-label="Seek"
        min={0}
        max={duration || 0}
        step={1}
        value={Math.min(currentTime, duration || 0)}
        onChange={(e) => seek(Number(e.target.value))}
        className="h-1 w-full cursor-pointer appearance-none bg-transparent accent-primary"
      />
      <div className="flex items-center gap-3 px-3 py-2 md:px-5">
        <Link
          to={`/a/${current.id}`}
          className="min-w-0 flex-1 truncate text-sm font-medium hover:underline"
        >
          {current.title}
        </Link>
        <span className="hidden shrink-0 text-xs text-muted-foreground tabular-nums sm:inline">
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
          {currentIndex + 1}/{queue.length}
        </span>
        <button
          type="button"
          aria-label="Previous"
          onClick={prev}
          disabled={currentIndex <= 0}
          className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-40"
        >
          <SkipBack className="size-4" />
        </button>
        <button
          type="button"
          aria-label={isPlaying ? 'Pause' : 'Play'}
          onClick={playPause}
          disabled={isLoading}
          className={cn(
            'shrink-0 rounded-full bg-primary p-2 text-primary-foreground hover:bg-primary/90',
            isLoading && 'opacity-60'
          )}
        >
          {isLoading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : isPlaying ? (
            <Pause className="size-4" />
          ) : (
            <Play className="size-4" />
          )}
        </button>
        <button
          type="button"
          aria-label="Next"
          onClick={next}
          disabled={currentIndex >= queue.length - 1}
          className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-40"
        >
          <SkipForward className="size-4" />
        </button>
        <button
          type="button"
          aria-label="Close player"
          onClick={stop}
          className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted"
        >
          <X className="size-4" />
        </button>
      </div>
    </div>
  );
}
