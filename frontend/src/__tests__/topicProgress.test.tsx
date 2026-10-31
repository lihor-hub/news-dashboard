import { MemoryRouter } from 'react-router';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { TopicProgress } from '@/components/TopicProgress';
import { RewardEmblem } from '@/components/RewardEmblem';
import type { ProgressReward, TopicProgress as TopicData, TopicTrack } from '@/api/progress';

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
function rewards(tracks: TopicTrack[]): ProgressReward[] {
  return tracks.flatMap((t) =>
    [1, 10, 30, 100, 250].map((target, index) => ({
      key: `topic_${t.id}_${target}`,
      topic_id: t.id,
      title: `${t.name} · ${['Explorer', 'Enthusiast', 'Regular', 'Trailblazer', 'Pathfinder'][index]}`,
      description: `Read ${target} qualifying ${t.name} articles.`,
      unlocked: t.count >= target,
      target,
      earned_at: null,
      recorded_at: t.count >= target ? '2026-01-01' : null,
      origin: t.count >= target ? 'import' : null,
    }))
  );
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
  it('uses eleven distinct vector subjects and escalating shape detail, never color-only levels', () => {
    const ids = [
      'python',
      'large_language_models',
      'ai_agents',
      'ai_research',
      'cloud_infrastructure',
      'security',
      'data_engineering',
      'web_development',
      'javascript_typescript',
      'software_engineering',
      'ruby',
    ];
    const { container, rerender } = render(
      <>
        {ids.map((id) => (
          <RewardEmblem key={id} target={1} earned topicId={id} level="Explorer" />
        ))}
      </>
    );
    const symbols = [...container.querySelectorAll('svg')].map((svg) =>
      svg.querySelector('path[stroke-linecap="round"]')?.getAttribute('d')
    );
    expect(new Set(symbols).size).toBe(11);
    expect(symbols.every(Boolean)).toBe(true);
    const simple = container.querySelector('svg')!.querySelectorAll('path').length;
    rerender(<RewardEmblem target={250} earned topicId="python" level="Pathfinder" />);
    expect(container.querySelectorAll('path').length).toBeGreaterThan(simple);
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });
  it('renders exact partial/final counts, top three and accessible all-topics toggle', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <TopicProgress
          rewards={rewards([
            track('Python', 1001),
            track('Ruby', 7),
            track('CSS', 7),
            track('Security', 0),
          ])}
          topics={data([
            track('Python', 1001),
            track('Ruby', 7),
            track('CSS', 7),
            track('Security', 0),
          ])}
        />
      </MemoryRouter>
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
      within(screen.getByRole('list', { name: 'Ruby levels' })).getAllByRole('listitem')
    ).toHaveLength(5);
    const ruby = within(screen.getByRole('list', { name: 'Ruby levels' }));
    for (const [index, target] of [1, 10, 30, 100, 250].entries()) {
      const item = within(ruby.getAllByRole('listitem')[index]);
      expect(item.getByRole('link')).toHaveAttribute(
        'href',
        `/reading-dna?reward=topic_Ruby_${target}#progress`
      );
      expect(item.getByText(`Read ${target} qualifying Ruby articles.`)).toBeInTheDocument();
      expect(item.getByText(index === 0 ? /✓ Earned:/ : /◇ Locked:/)).toBeInTheDocument();
    }
    expect(ruby.getAllByRole('link')).toHaveLength(5);
    expect(
      screen.getAllByText('Original earned date unknown; preserved reward.', { exact: false })
    ).toHaveLength(7);
  });

  it('does not invent topics or expertise in the empty state', async () => {
    render(
      <MemoryRouter>
        <TopicProgress
          topics={data([track('Python', 0)])}
          rewards={rewards([track('Python', 0)])}
        />
      </MemoryRouter>
    );
    expect(screen.getByText(/No topic reads tracked yet/)).toBeInTheDocument();
    expect(screen.queryByText(/✓ Earned:/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Show all topics' }));
    expect(screen.getByText('Not started · 0 qualifying reads')).toBeInTheDocument();
    expect(screen.getByText('0 of 1 toward Explorer')).toBeInTheDocument();
  });
});
