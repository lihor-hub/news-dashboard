import { useEffect, useRef } from 'react';
import { Link } from 'react-router';
import type { ProgressReward } from '@/api/progress';
import { RewardEmblem } from './RewardEmblem';

export function RewardDetail({
  reward,
  requestedKey,
}: {
  reward?: ProgressReward;
  requestedKey: string;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, [requestedKey]);
  return (
    <section aria-labelledby="reward-detail-heading" className="space-y-2 rounded-xl border p-4">
      <h3 id="reward-detail-heading" ref={heading} tabIndex={-1} className="text-lg font-semibold">
        {reward?.title ?? 'Achievement not found'}
      </h3>
      {reward ? (
        <>
          <RewardEmblem
            target={reward.target}
            earned={reward.unlocked}
            topicId={reward.topic_id ?? undefined}
            rewardKey={reward.key}
          />
          <p>
            {reward.unlocked ? '✓ Earned' : '◇ Locked'} · {reward.description}
          </p>
          {reward.unlocked && (
            <>
              <p>
                {reward.earned_at ? (
                  <>
                    Earned{' '}
                    <time dateTime={reward.earned_at}>
                      {new Date(reward.earned_at).toLocaleString()}
                    </time>
                  </>
                ) : (
                  'Original earned date unknown; preserved reward.'
                )}
              </p>
              <p>
                Provenance: {reward.origin ?? 'legacy'}.
                {reward.retired ? ' Retired or original reward; permanently preserved.' : ''}
              </p>
              {reward.recorded_at && (
                <p>
                  Recorded{' '}
                  <time dateTime={reward.recorded_at}>
                    {new Date(reward.recorded_at).toLocaleDateString()}
                  </time>
                  . Recording date is not an unknown earned date.
                </p>
              )}
            </>
          )}
        </>
      ) : (
        <p>No matching achievement is available in your collection.</p>
      )}
      <Link to="/reading-dna#progress" className="underline">
        Back to collection
      </Link>
    </section>
  );
}
