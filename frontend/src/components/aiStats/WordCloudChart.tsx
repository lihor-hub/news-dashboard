import { useMemo, useState } from 'react';
import type { WordCloudTerm } from '@/types';
import { layoutWordCloud } from '@/lib/wordCloudLayout';

const CANVAS_W = 800;
const CANVAS_H = 480;

const TERM_COLORS = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
];

interface WordCloudChartProps {
  terms: WordCloudTerm[];
}

export function WordCloudChart({ terms }: WordCloudChartProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  const placed = useMemo(() => layoutWordCloud(terms, CANVAS_W, CANVAS_H), [terms]);
  const countByTerm = useMemo(() => new Map(terms.map((t) => [t.term, t.count])), [terms]);

  return (
    <svg viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`} className="h-auto w-full" role="img">
      <title>Word cloud of recent article terms</title>
      {placed.map((p) => (
        <text
          key={p.term}
          x={p.x}
          y={p.y}
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={p.fontSize}
          fill={TERM_COLORS[p.colorIndex % TERM_COLORS.length]}
          className="cursor-default select-none font-semibold transition-opacity"
          opacity={hovered === null || hovered === p.term ? 1 : 0.35}
          onMouseEnter={() => setHovered(p.term)}
          onMouseLeave={() => setHovered(null)}
        >
          {p.term}
          <title>{`${p.term} — ${countByTerm.get(p.term) ?? 0} mentions`}</title>
        </text>
      ))}
    </svg>
  );
}
