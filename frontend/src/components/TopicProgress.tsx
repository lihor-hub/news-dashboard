import { useState } from 'react';
import type { TopicProgress as TopicProgressData } from '@/api/progress';
import { Button } from './ui/button';
import { RewardEmblem } from './RewardEmblem';

export function TopicProgress({ topics }: { topics: TopicProgressData }) {
  const [all, setAll] = useState(false);
  const tracks = all
    ? topics.tracks
    : topics.tracks.filter((track) => topics.top_track_ids.includes(track.id));
  return (
    <div className="space-y-3" aria-labelledby="topic-progress-heading">
      <h3 id="topic-progress-heading" className="font-medium">
        Topic progression
      </h3>
      <p className="text-sm text-muted-foreground">
        Up to {topics.attribution_cap} relevant tracks per qualifying read, frozen at first credit.
        Levels celebrate reading, not professional expertise. Tags and interests alone do not count.
      </p>
      {topics.top_track_ids.length === 0 && (
        <p>No topic reads tracked yet. Your first relevant read starts a track.</p>
      )}
      <Button
        variant="outline"
        aria-expanded={all}
        aria-controls="topic-tracks"
        onClick={() => setAll(!all)}
      >
        {all ? 'Show top three topics' : 'Show all topics'}
      </Button>
      <ul id="topic-tracks" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {tracks.map((track) => (
          <li key={track.id} className="space-y-2 rounded border p-3">
            <h4 className="font-medium">{track.name}</h4>
            <RewardEmblem
              target={track.count}
              earned={track.count > 0}
              level={track.level}
              symbol={track.name.slice(0, 2)}
            />
            <p>
              {track.level ?? 'Not started'} · {track.count} qualifying reads
            </p>
            <p>
              {track.next_target !== null
                ? `${track.count} of ${track.next_target} toward ${track.next_level}`
                : `Pathfinder · ${track.count} reads; all levels earned.`}
            </p>
            <ul aria-label={`${track.name} earned levels`}>
              {track.earned_levels.map((reward) => (
                <li key={reward.key} className="text-sm">
                  <span>✓ Earned: {reward.title}. </span>
                  {reward.earned_at ? (
                    <time dateTime={reward.earned_at}>
                      Earned {new Date(reward.earned_at).toLocaleDateString()}
                    </time>
                  ) : (
                    'Original earned date unknown; preserved reward.'
                  )}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      <p>
        Breadth: {topics.breadth_count} topics with at least 3 reads each. Milestones: 3, 5 and 10
        topics.
      </p>
    </div>
  );
}
