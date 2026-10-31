import { useEffect, useRef } from 'react';
import { Link } from 'react-router';
import type { WeeklyRecap } from '../types';

import { formatCalendarDate as recapDate } from '../lib/format';

export function RecapProgress({
  recap,
  full = false,
  rewardKey,
}: {
  recap: WeeklyRecap;
  full?: boolean;
  rewardKey?: string | null;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const { progress, period } = recap.data;
  const selected = progress?.rewards.find((reward) => reward.key === rewardKey);
  useEffect(() => {
    if (full) heading.current?.focus();
  }, [full, recap.id, rewardKey]);
  const href = `/reading-dna?recap=${recap.id}`;
  if (!progress || !period)
    return full ? <p>This legacy recap has no frozen progress measurements.</p> : null;
  const active = progress.active_seconds;
  const rewards = full ? progress.rewards : progress.rewards.slice(0, 3);
  return (
    <section
      aria-label="Your week in progress"
      className="min-w-0 space-y-3 rounded border p-3 break-words"
    >
      <h3 tabIndex={-1} ref={heading} className="font-semibold">
        {full && rewardKey
          ? (selected?.title ?? 'Reward not found in this recap')
          : 'Your week in progress'}
      </h3>
      <p>
        {recapDate(recap.data.week_start)} – {recapDate(recap.data.week_end)} · {period.timezone}
      </p>
      <p className="text-sm text-muted-foreground">
        Seven completed local dates. Frozen snapshot; late activity does not change this report.
      </p>
      {progress.days_visited === null && active === null && (
        <p>Progress tracking was not available for this period.</p>
      )}
      <dl className="space-y-2">
        <div>
          <dt>Days visited</dt>
          <dd>
            {progress.days_visited === null ? 'Unavailable' : `${progress.days_visited} of 7`} ·{' '}
            {progress.coverage.visits.status} coverage
          </dd>
        </div>
        <div>
          <dt>Approximate active time</dt>
          <dd>
            {active === null
              ? 'Unavailable'
              : active === 0
                ? '0 minutes measured'
                : active < 60
                  ? 'Less than a minute measured'
                  : `${Math.floor(active / 60)} minutes measured`}{' '}
            · {progress.coverage.active_time.status} coverage
          </dd>
        </div>
      </dl>
      <p className="text-sm text-muted-foreground">
        Measured connected, visible and focused use, not reading-only time. Missing observations,
        consent gaps, travel and unknown global availability can leave coverage incomplete.
      </p>
      <p>
        {progress.rewards.length} rewards earned in this period · {progress.coverage.rewards.status}{' '}
        coverage (trusted live rewards only)
      </p>
      <ul className="space-y-2">
        {rewards.map((reward) => (
          <li key={reward.key}>
            <Link
              className="underline"
              to={`${href}&reward=${encodeURIComponent(reward.key)}#progress`}
            >
              {reward.title}
            </Link>
            {full && (
              <p>
                {reward.description} Earned{' '}
                <time dateTime={reward.earned_at}>
                  {new Date(reward.earned_at).toLocaleString()}
                </time>
                .
              </p>
            )}
          </li>
        ))}
      </ul>
      {full && rewardKey && selected && <p>{selected.description}</p>}
      {full ? (
        <Link className="underline" to={`/recap?recap=${recap.id}`}>
          Back to this recap
        </Link>
      ) : (
        <Link className="underline" to={`${href}#progress`}>
          {progress.rewards.length > 3
            ? `View all ${progress.rewards.length} rewards and weekly progress`
            : 'View weekly progress'}
        </Link>
      )}
    </section>
  );
}
