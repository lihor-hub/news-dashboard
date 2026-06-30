/**
 * Accessibility smoke-test helper.
 *
 * Injects the repo-pinned axe-core package and runs an audit limited to
 * serious/critical violations so tests stay focused on high-signal issues.
 */
import type { Page } from '@playwright/test';
import { expect } from '@playwright/test';
import { source as axeSource } from 'axe-core';

export interface A11yCheckOptions {
  /**
   * axe rule IDs to exclude. Use sparingly; add a comment explaining why
   * each exclusion is safe.
   */
  exclude?: string[];
}

/**
 * Inject axe-core and assert no serious/critical violations on the current
 * page. Throws an Playwright assertion error listing every violation found.
 */
export async function checkA11y(page: Page, options: A11yCheckOptions = {}): Promise<void> {
  await page.addScriptTag({ content: axeSource });

  const violations = await page.evaluate(
    async ({ excludeRules }: { excludeRules: string[] }) => {
      /* eslint-disable @typescript-eslint/no-explicit-any */
      const axe = (window as any).axe as {
        run: (context: Document, opts: unknown) => Promise<{ violations: AxeViolation[] }>;
      };
      /* eslint-enable @typescript-eslint/no-explicit-any */

      interface AxeViolation {
        id: string;
        impact: string;
        description: string;
        nodes: { html: string }[];
      }

      const result = await axe.run(document, {
        runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'best-practice'] },
        rules: Object.fromEntries(excludeRules.map((id) => [id, { enabled: false }])),
        resultTypes: ['violations'],
      });

      return result.violations.filter((v) => v.impact === 'critical' || v.impact === 'serious');
    },
    { excludeRules: options.exclude ?? [] }
  );

  if (violations.length > 0) {
    const lines = violations.map((v) => {
      const nodeSnippets = v.nodes
        .slice(0, 3)
        .map((n) => `    • ${n.html}`)
        .join('\n');
      return `[${v.impact}] ${v.id}: ${v.description}\n${nodeSnippets}`;
    });
    expect
      .soft(violations, `Accessibility violations found:\n\n${lines.join('\n\n')}`)
      .toHaveLength(0);
  }
}
