import { useEffect, useRef, useState } from 'react';
import { rewardHref, type ProgressReward } from '@/api/progress';
import { RewardEmblem } from './RewardEmblem';

/** Sonner owns placement; this clock also pauses on keyboard focus and hidden documents. */
export function RewardFeedback({
  rewards,
  onClose,
  onView,
}: {
  rewards: ProgressReward[];
  onClose: () => void;
  onView: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [hidden, setHidden] = useState(document.visibilityState !== 'visible');
  const remaining = useRef(8000);
  useEffect(() => {
    const change = () => setHidden(document.visibilityState !== 'visible');
    document.addEventListener('visibilitychange', change);
    return () => document.removeEventListener('visibilitychange', change);
  }, []);
  useEffect(() => {
    if (hovered || focused || hidden) return;
    const start = Date.now();
    const timer = setTimeout(onClose, remaining.current);
    return () => {
      clearTimeout(timer);
      remaining.current = Math.max(0, remaining.current - (Date.now() - start));
    };
  }, [hovered, focused, hidden, onClose]);
  return (
    <div
      data-reward-feedback
      className="w-full max-w-sm space-y-2 rounded-xl border bg-background p-4 text-foreground shadow-sm"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setFocused(false);
      }}
    >
      <div className="flex items-start gap-3">
        <RewardEmblem
          target={rewards[0]?.target ?? null}
          earned
          rewardKey={rewards[0]?.key}
          topicId={rewards[0]?.topic_id ?? undefined}
        />
        <div>
          <p className="font-semibold">Progress earned</p>
          <p>
            {rewards
              .slice(0, 3)
              .map((reward) => reward.title)
              .join(' · ')}
            {rewards.length > 3 ? ` and ${rewards.length - 3} more` : ''}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-4">
        <a
          className="rounded underline focus-visible:outline-2"
          href={rewardHref(rewards[0].key)}
          onClick={(event) => {
            event.preventDefault();
            onView();
          }}
        >
          View achievement
        </a>
        <button className="rounded underline focus-visible:outline-2" onClick={onClose}>
          Dismiss celebration
        </button>
      </div>
    </div>
  );
}
