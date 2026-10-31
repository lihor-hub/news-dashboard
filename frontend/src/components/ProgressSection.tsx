import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router';
import { RewardDetail } from './RewardDetail';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/auth';
import {
  fetchDailyStreak,
  fetchProgressPreferences,
  fetchProgressRewards,
  saveProgressPreferences,
  type ProgressPreferences,
  rewardHref,
} from '@/api/progress';
import { SevenDayStrip } from './DailyProgress';
import { Button } from './ui/button';
import { RewardEmblem } from './RewardEmblem';
import { TopicProgress } from './TopicProgress';
import { ActivityProgress } from './ActivityProgress';

function category(key: string) {
  if (key.startsWith('daily_streak_')) return 'Daily visits';
  if (key.startsWith('articles_read_') || key === 'hundred_articles_read')
    return 'Qualifying reads';
  if (key.startsWith('active_time_')) return 'Approximate active time badges';
  if (key.startsWith('breadth_')) return 'Topic breadth';
  return key === 'first_quiz_passed' ? 'Learning' : 'Preserved rewards';
}

export function ProgressSection() {
  const { user } = useAuth();
  const accountId = user?.id;
  const cache = useQueryClient();
  const location = useLocation();
  const heading = useRef<HTMLHeadingElement>(null);
  const enabled = !!user && !user.is_guest;
  const daily = useQuery({
    queryKey: ['daily-streak', accountId],
    queryFn: fetchDailyStreak,
    enabled,
  });
  const preferences = useQuery({
    queryKey: ['progress-preferences', accountId],
    queryFn: fetchProgressPreferences,
    enabled,
  });
  const rewards = useQuery({
    queryKey: ['progress-rewards', accountId],
    queryFn: fetchProgressRewards,
    enabled,
  });
  const requestedKey = new URLSearchParams(location.search).get('reward');
  const [zone, setZone] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (preferences.data) setZone(preferences.data.progress_timezone);
  }, [preferences.data]);
  useEffect(() => {
    if (location.hash === '#progress' && !requestedKey) heading.current?.focus();
  }, [location.key, location.hash, requestedKey]);
  async function save(patch: Partial<Omit<ProgressPreferences, 'timezone_initialized'>>) {
    setSaving(true);
    setError(null);
    const previous = preferences.data;
    if (previous)
      cache.setQueryData(['progress-preferences', accountId], { ...previous, ...patch });
    try {
      const result = await saveProgressPreferences(patch);
      cache.setQueryData(['progress-preferences', accountId], result);
      await cache.invalidateQueries({ queryKey: ['daily-streak', accountId] });
    } catch (err) {
      if (previous) cache.setQueryData(['progress-preferences', accountId], previous);
      setError(err instanceof Error ? err.message : 'Could not save preferences');
    } finally {
      setSaving(false);
    }
  }
  return (
    <section
      id="progress"
      className="min-w-0 scroll-mt-4 space-y-4 rounded-xl border p-4 break-words"
      aria-labelledby="progress-heading"
    >
      <h2 id="progress-heading" tabIndex={-1} ref={heading} className="text-xl font-semibold">
        Progress &amp; achievements
      </h2>
      {!enabled ? (
        <p>Sign in with a personal account to record daily progress.</p>
      ) : (
        <>
          {requestedKey && rewards.isSuccess && (
            <RewardDetail
              requestedKey={requestedKey}
              reward={rewards.data.items.find((reward) => reward.key === requestedKey)}
            />
          )}
          {daily.isPending ? (
            <p>Loading daily progress…</p>
          ) : daily.isError ? (
            <div role="status">
              Daily progress is unavailable. Your saved progress has not changed.{' '}
              <Button
                variant="outline"
                className="h-auto min-h-9 max-w-full whitespace-normal"
                onClick={() => void daily.refetch()}
              >
                Retry daily progress
              </Button>
            </div>
          ) : (
            daily.data?.available && (
              <>
                <p>
                  Daily streak: <strong>{daily.data.current_streak_days} days</strong> · Personal
                  best: {daily.data.best_streak_days} days
                </p>
                <SevenDayStrip daily={daily.data} />
                <p className="text-sm text-muted-foreground">
                  Visits in {daily.data.timezone}. ✓ credited · ○ observed, timezone guard · – no
                  visit. Separate from the legacy reading streak below.
                </p>
              </>
            )
          )}
          {preferences.isPending && <p>Loading progress preferences…</p>}
          {preferences.data && (
            <fieldset className="min-w-0 space-y-3" disabled={saving}>
              <legend className="max-w-full font-medium">Progress preferences</legend>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={preferences.data.daily_welcome_enabled}
                  onChange={(e) => void save({ daily_welcome_enabled: e.target.checked })}
                />
                Daily welcome popup
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={preferences.data.reward_animations_enabled}
                  onChange={(e) => void save({ reward_animations_enabled: e.target.checked })}
                />
                Reward animations
              </label>
              <form
                className="flex flex-wrap items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void save({ progress_timezone: zone });
                }}
              >
                <label className="grid min-w-0 max-w-full gap-1 text-sm">
                  Progress timezone (IANA)
                  <input
                    className="w-full min-w-0 rounded border bg-background p-2"
                    value={zone}
                    maxLength={255}
                    required
                    onChange={(e) => setZone(e.target.value)}
                  />
                </label>
                <Button type="submit" variant="outline">
                  Save timezone
                </Button>
              </form>
              <p className="text-sm text-muted-foreground">
                Neither control disables tracking. Automatic measurement still respects Privacy
                &amp; analytics consent. Email keeps its own timezone. Travel may suppress a daily
                credit or start a fresh streak; past dates and earned rewards remain.
              </p>
            </fieldset>
          )}
          {preferences.isError && (
            <div role="status">
              Progress preferences are unavailable.{' '}
              <Button
                variant="outline"
                className="h-auto min-h-9 max-w-full whitespace-normal"
                onClick={() => void preferences.refetch()}
              >
                Retry progress preferences
              </Button>
            </div>
          )}
          {error && <p role="alert">{error}</p>}
          {accountId !== undefined && <ActivityProgress key={accountId} accountId={accountId} />}
          <h3 className="font-medium">Permanent collection</h3>
          {rewards.data?.reading_total !== undefined && (
            <div className="space-y-1">
              <p>
                Tracked qualifying reads: <strong>{rewards.data.reading_total}</strong>
              </p>
              <p>
                {rewards.data.next_reading_target
                  ? `Next reading milestone: ${rewards.data.next_reading_target} articles.`
                  : 'All reading milestones earned.'}
              </p>
              {rewards.data.reading_total === 0 && (
                <p>
                  No qualifying reads tracked yet. Choose Done after reading, or complete attentive
                  reading of the loaded article body.
                </p>
              )}
              <p className="text-sm text-muted-foreground">
                Marking unread changes your list, not earned progress. Audio finishing alone does
                not count. Article-kind Reading List items count; other kinds do not.
              </p>
              {rewards.data.history_status === 'reconciliation_pending' && (
                <p className="text-sm text-muted-foreground">
                  Historical reconciliation is pending. This is not your complete lifetime total.
                  All existing rewards remain preserved.
                </p>
              )}
            </div>
          )}
          {rewards.data?.topics && (
            <TopicProgress
              key={accountId}
              topics={rewards.data.topics}
              rewards={rewards.data.items}
            />
          )}
          {rewards.isPending ? (
            <p>Loading rewards…</p>
          ) : rewards.isError ? (
            <div role="status">
              Rewards are unavailable. Saved progress has not changed.{' '}
              <Button variant="outline" onClick={() => void rewards.refetch()}>
                Retry rewards
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {[
                'Daily visits',
                'Qualifying reads',
                'Topic breadth',
                'Approximate active time badges',
                'Learning',
                'Preserved rewards',
              ].map((name) => {
                const items =
                  rewards.data?.items.filter(
                    (reward) => !reward.topic_id && category(reward.key) === name
                  ) ?? [];
                return (
                  items.length > 0 && (
                    <section key={name} aria-label={name} className="space-y-2">
                      <h4 className="font-medium">{name}</h4>
                      <ul className="grid gap-2 sm:grid-cols-2">
                        {items.map((reward) => (
                          <li key={reward.key} className="rounded border p-3">
                            <RewardEmblem
                              target={reward.target}
                              earned={reward.unlocked}
                              rewardKey={reward.key}
                            />
                            <p className="font-medium">
                              <Link
                                to={rewardHref(reward.key)}
                                className="underline decoration-dotted underline-offset-4"
                              >
                                {reward.unlocked ? '✓ Earned: ' : '◇ Locked: '}
                                {reward.title}
                              </Link>
                            </p>
                            <p className="text-sm">{reward.description}</p>
                            {reward.unlocked && (
                              <p className="text-xs text-muted-foreground">
                                {reward.earned_at ? (
                                  <>
                                    <span>Earned </span>
                                    <time dateTime={reward.earned_at}>
                                      {new Date(reward.earned_at).toLocaleDateString()}
                                    </time>
                                  </>
                                ) : (
                                  'Original earned date unknown; preserved reward.'
                                )}
                              </p>
                            )}
                          </li>
                        ))}
                      </ul>
                    </section>
                  )
                );
              })}
            </div>
          )}
        </>
      )}
    </section>
  );
}
