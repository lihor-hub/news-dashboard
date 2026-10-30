/** Decorative vector; the adjacent earned/locked name and requirement carry meaning. */
export function RewardEmblem({
  target,
  earned,
  level,
  symbol,
}: {
  target: number | null;
  earned: boolean;
  level?: string | null;
  symbol?: string;
}) {
  const rank =
    ['Explorer', 'Enthusiast', 'Regular', 'Trailblazer', 'Pathfinder'].indexOf(level ?? '') + 1;
  return (
    <svg
      viewBox="0 0 64 72"
      width="48"
      height="54"
      aria-hidden="true"
      focusable="false"
      className="shrink-0"
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
      {earned && <path d="m24 43 5 5 11-12" fill="none" stroke="currentColor" strokeWidth="2" />}
    </svg>
  );
}
