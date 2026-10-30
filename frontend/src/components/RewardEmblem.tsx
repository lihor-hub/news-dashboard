/** Decorative vector; the adjacent earned/locked name and requirement carry meaning. */
export function RewardEmblem({ target, earned }: { target: number | null; earned: boolean }) {
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
      <text
        x="32"
        y="36"
        textAnchor="middle"
        fill="currentColor"
        fontSize={String(target ?? '').length > 2 ? 16 : 20}
        fontWeight="700"
      >
        {target ?? '★'}
      </text>
      {earned && <path d="m24 43 5 5 11-12" fill="none" stroke="currentColor" strokeWidth="2" />}
    </svg>
  );
}
