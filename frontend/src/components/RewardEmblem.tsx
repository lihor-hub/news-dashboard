const symbols: Record<string, string> = {
  python: 'M24 22h12v8H24v8h16M24 26h-4v16h16v-8h8V18H28',
  large_language_models: 'M19 20h26v18H30l-8 6v-6h-3Z M25 26h14m-14 6h10',
  ai_agents: 'M22 22h20v20H22Z M27 28h2m6 0h2m-10 8h10M32 16v6m-15 8h5m20 0h5',
  ai_research: 'M28 18h8m-6 0v12L20 44h24L34 30V18m-8 19h12',
  cloud_infrastructure: 'M23 35a7 7 0 1 1 1-14 9 9 0 0 1 17 4 5 5 0 0 1 0 10Z M24 41h16m-8-6v6',
  security: 'M20 22l12-5 12 5v11L32 46 20 33Z M26 31l4 4 9-10',
  data_engineering: 'M20 23c0-7 24-7 24 0s-24 7-24 0v17c0 7 24 7 24 0V23m-24 8c0 7 24 7 24 0',
  web_development: 'M19 19h26v26H19Z M19 26h26m-19 0v19m-7-23h2m3 0h2',
  javascript_typescript: 'M25 23l-7 9 7 9m14-18 7 9-7 9m-5-20-4 24',
  software_engineering: 'M24 20h16v9H24Zm0 18h16v9H24ZM32 29v9m-14-6h28',
  ruby: 'M18 27l7-9h14l7 9-14 20Zm0 0h28m-21-9 7 29 7-29',
  daily: 'M20 23h24v22H20Zm0 6h24m-18-12v10m12-10v10m-11 10 4 4 7-8',
  read: 'M18 21c7-3 10-2 14 1 4-3 7-4 14-1v24c-7-3-10-2-14 1-4-3-7-4-14-1Zm14 1v24',
  time: 'M45 32a13 13 0 1 1-26 0 13 13 0 0 1 26 0ZM32 23v10l7 4',
  breadth: 'M32 19v27m-12-7 12-9 12 9m-24-13 12 9 12-9',
  quiz: 'M22 20h20v26H22Zm4 9 3 3 8-8m-11 15h12',
};

/** Decorative vector; adjacent text carries requirements and earned/locked meaning. */
export function RewardEmblem({
  target,
  earned,
  level,
  symbol,
  topicId,
  rewardKey,
}: {
  target: number | null;
  earned: boolean;
  level?: string | null;
  symbol?: string;
  topicId?: string;
  rewardKey?: string;
}) {
  const category = rewardKey?.startsWith('daily_')
    ? 'daily'
    : rewardKey?.startsWith('active_time_')
      ? 'time'
      : rewardKey?.startsWith('breadth_')
        ? 'breadth'
        : rewardKey === 'first_quiz_passed'
          ? 'quiz'
          : 'read';
  const tiers = {
    daily: [3, 7, 14, 30, 100],
    read: [1, 10, 50, 100, 500],
    time: [900, 3600, 18000, 72000],
    breadth: [3, 5, 10],
    quiz: [1],
  };
  const rank = level
    ? ['Explorer', 'Enthusiast', 'Regular', 'Trailblazer', 'Pathfinder'].indexOf(level) + 1
    : (topicId ? [1, 10, 30, 100, 250] : tiers[category]).indexOf(target ?? 0) + 1;
  const path = symbols[topicId ?? category];
  return (
    <svg
      viewBox="0 0 64 72"
      width="48"
      height="54"
      aria-hidden="true"
      focusable="false"
      className={`shrink-0 ${earned ? 'text-amber-800 dark:text-amber-200' : 'text-muted-foreground'}`}
    >
      <path
        d="M8 4h48v38L32 66 8 42Z"
        fill="none"
        stroke="currentColor"
        strokeWidth={earned ? 3 : 1.5}
        strokeDasharray={earned ? undefined : '4 3'}
      />
      <path d="M18 12h28M20 50l12 12 12-12" fill="none" stroke="currentColor" strokeWidth="2" />
      {rank >= 2 && <path d="M13 9h38v31L32 59 13 40Z" fill="none" stroke="currentColor" />}
      {rank >= 3 && <path d="m18 17 4-4 4 4m12 0 4-4 4 4" fill="none" stroke="currentColor" />}
      {rank >= 4 && (
        <path
          d="m4 25 4 4m48 0 4-4M4 35l4 4m48 0 4-4"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        />
      )}
      {rank >= 5 && (
        <path d="m24 8 4-6 4 6 4-6 4 6" fill="none" stroke="currentColor" strokeWidth="2" />
      )}
      {path ? (
        <path
          d={path}
          stroke="currentColor"
          strokeWidth="1.8"
          fill="none"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      ) : (
        <text
          x="32"
          y="36"
          textAnchor="middle"
          fill="currentColor"
          fontSize={String(target ?? '').length > 2 ? 16 : 20}
          fontWeight="700"
        >
          {symbol ?? target ?? '★'}
        </text>
      )}
      {earned && <path d="m24 43 5 5 11-12" fill="none" stroke="currentColor" strokeWidth="2" />}
    </svg>
  );
}
