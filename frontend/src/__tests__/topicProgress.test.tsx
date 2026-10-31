import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { TopicProgress } from '@/components/TopicProgress';
import type { TopicProgress as TopicData, TopicTrack } from '@/api/progress';

function track(id: string, count: number): TopicTrack {
  return {
    id,
    name: id,
    count,
    level: count ? (count >= 250 ? 'Pathfinder' : 'Explorer') : null,
    next_target: count >= 250 ? null : count ? 10 : 1,
    next_level: count >= 250 ? null : count ? 'Enthusiast' : 'Explorer',
    earned_levels: count
      ? [
          {
            key: `topic_${id}_1`,
            title: `${id} · Explorer`,
            description: 'Read one article',
            unlocked: true,
            target: 1,
            earned_at: null,
            recorded_at: '2026-01-01',
            origin: 'import',
          },
        ]
      : [],
  };
}
function data(tracks: TopicTrack[]): TopicData {
  return {
    taxonomy_version: 1,
    rule_version: 1,
    attribution_cap: 2,
    tracks,
    top_track_ids: tracks
      .filter((t) => t.count > 0)
      .slice(0, 3)
      .map((t) => t.id),
    breadth_count: 0,
  };
}

describe('topic collection', () => {
  it('renders exact partial/final counts, top three and accessible all-topics toggle', async () => {
    const user = userEvent.setup();
    render(
      <TopicProgress
        topics={data([
          track('Python', 1001),
          track('Ruby', 7),
          track('CSS', 7),
          track('Security', 0),
        ])}
      />
    );
    expect(screen.getByText('Pathfinder · 1001 reads; all levels earned.')).toBeInTheDocument();
    expect(screen.getAllByText('7 of 10 toward Enthusiast')).toHaveLength(2);
    expect(screen.queryByRole('heading', { name: 'Security' })).not.toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: 'Show all topics', expanded: false });
    await user.click(toggle);
    expect(screen.getByRole('heading', { name: 'Security' })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Show top three topics', expanded: true })
    ).toHaveFocus();
    expect(
      within(screen.getByRole('list', { name: 'Ruby earned levels' })).getAllByRole('listitem')
    ).toHaveLength(1);
    expect(
      screen.getAllByText('Original earned date unknown; preserved reward.', { exact: false })
    ).toHaveLength(3);
  });

  it('does not invent topics or expertise in the empty state', async () => {
    render(<TopicProgress topics={data([track('Python', 0)])} />);
    expect(screen.getByText(/No topic reads tracked yet/)).toBeInTheDocument();
    expect(screen.queryByText(/✓ Earned:/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Show all topics' }));
    expect(screen.getByText('Not started · 0 qualifying reads')).toBeInTheDocument();
    expect(screen.getByText('0 of 1 toward Explorer')).toBeInTheDocument();
  });
});
