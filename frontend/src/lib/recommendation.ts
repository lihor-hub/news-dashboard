/**
 * Compact recommendation labels for the Today feed.
 *
 * The backend exposes a per-user `recommendation_score` (0–100) blended from
 * behavioral affinity, semantic similarity, freshness, and novelty. We collapse
 * that continuous score into three scannable bands so a ranked feed stays
 * readable without surfacing raw numbers. When no score is available (the user
 * has no recommendation metadata for an article yet) the helper returns `null`,
 * and callers fall back to the existing importance-derived visual signal.
 */

import type { RecommendationSignals } from './workflowTypes';

export type RecommendationLabel = 'recommended' | 'relevant' | 'low';

// Band thresholds on the 0–100 recommendation score. Tuned so "Recommended" is
// reserved for genuinely strong matches while most ranked items read "Relevant".
const RECOMMENDED_THRESHOLD = 70;
const RELEVANT_THRESHOLD = 45;

export function recommendationLabel(score: number | null | undefined): RecommendationLabel | null {
  if (score == null || Number.isNaN(score)) return null;
  if (score >= RECOMMENDED_THRESHOLD) return 'recommended';
  if (score >= RELEVANT_THRESHOLD) return 'relevant';
  return 'low';
}

export const RECOMMENDATION_LABEL_TEXT: Record<RecommendationLabel, string> = {
  recommended: 'Recommended',
  relevant: 'Relevant',
  low: 'Low signal',
};

// ─── On-demand explanations ───────────────────────────────────────────────────

/**
 * Minimum signed point contribution for a factor to be worth naming. Tiny
 * adjustments (sub-point nudges) are noise and would produce misleading reasons,
 * so we only surface factors that meaningfully moved the score.
 */
const FACTOR_REASON_THRESHOLD = 1.0;

export interface RecommendationExplanation {
  /** Concise, user-facing reasons naming the real contributing factors. */
  reasons: string[];
  /**
   * True when no per-factor signals were available and the explanation falls
   * back to a generic-but-useful description (cold-start or unranked article).
   */
  fallback: boolean;
}

interface ExplanationInput {
  score?: number | null;
  signals?: RecommendationSignals | null;
}

/**
 * Derive concise explanation reasons from recommendation metadata.
 *
 * Each contributing factor (behavioral affinity, semantic similarity, freshness,
 * novelty) is named only when it actually lifted the score by a meaningful
 * amount, so the explanation reflects real signals rather than boilerplate. When
 * no per-factor breakdown is present — an unranked article, or a cold-start score
 * with no learned signals yet — we return a single useful fallback reason rather
 * than an empty or misleading list.
 */
export function recommendationExplanation(input: ExplanationInput): RecommendationExplanation {
  const { score, signals } = input;
  const reasons: string[] = [];

  if (signals) {
    if ((signals.affinity_adjustment ?? 0) >= FACTOR_REASON_THRESHOLD) {
      reasons.push('Matches sources and topics you engage with');
    }
    if ((signals.semantic_adjustment ?? 0) >= FACTOR_REASON_THRESHOLD) {
      reasons.push('Similar to articles you’ve starred or read');
    }
    if ((signals.freshness_adjustment ?? 0) >= FACTOR_REASON_THRESHOLD) {
      reasons.push('Fresh and timely right now');
    }
    if ((signals.novelty_adjustment ?? 0) >= FACTOR_REASON_THRESHOLD) {
      reasons.push('Brings something new to your feed');
    }
  }

  if (reasons.length > 0) {
    return { reasons, fallback: false };
  }

  // No factor stood out. Produce a useful fallback rather than an empty UI.
  if (score != null && !Number.isNaN(score)) {
    return {
      reasons: ['Ranked by overall relevance and importance for you'],
      fallback: true,
    };
  }
  return {
    reasons: ['Not personalized yet — shown based on general importance'],
    fallback: true,
  };
}
