const CHART_COLORS = [
  'var(--color-chart-1)',
  'var(--color-chart-2)',
  'var(--color-chart-3)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
] as const;

/**
 * Stable category → chart-color mapping: categories are sorted so the same
 * corpus always yields the same assignment, independent of point order.
 */
export function categoryColorMap(categories: (string | null | undefined)[]): Map<string, string> {
  const unique = [...new Set(categories.map((c) => c ?? 'other'))].sort();
  return new Map(unique.map((category, i) => [category, CHART_COLORS[i % CHART_COLORS.length]]));
}

export function colorForCategory(
  map: Map<string, string>,
  category: string | null | undefined
): string {
  return map.get(category ?? 'other') ?? CHART_COLORS[0];
}
