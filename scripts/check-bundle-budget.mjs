#!/usr/bin/env node
// Fails the build if any emitted JS chunk exceeds the configured budget, so
// bundle-size regressions are caught in CI instead of discovered later in
// production first-load metrics. Mirrors Vite's own chunkSizeWarningLimit
// (500 kB) but turns it into a hard failure rather than a build-log warning.
import { readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const ASSETS_DIR = 'frontend/dist/assets';
const BUDGET_BYTES = 500 * 1024;

let files;
try {
  files = readdirSync(ASSETS_DIR).filter((f) => f.endsWith('.js'));
} catch (err) {
  console.error(`check-bundle-budget: could not read ${ASSETS_DIR}: ${err.message}`);
  process.exit(1);
}

const overBudget = files
  .map((name) => ({ name, size: statSync(join(ASSETS_DIR, name)).size }))
  .filter(({ size }) => size > BUDGET_BYTES)
  .sort((a, b) => b.size - a.size);

if (overBudget.length > 0) {
  console.error(
    `check-bundle-budget: ${overBudget.length} chunk(s) exceed the ${(BUDGET_BYTES / 1024).toFixed(0)} kB budget:`
  );
  for (const { name, size } of overBudget) {
    console.error(`  ${name}: ${(size / 1024).toFixed(1)} kB`);
  }
  console.error(
    'Split the offending route/component with a dynamic import(), or if the growth is ' +
      'justified (e.g. an isolated, lazy-loaded vendor library), raise BUDGET_BYTES in ' +
      'scripts/check-bundle-budget.mjs with a comment explaining why.'
  );
  process.exit(1);
}

console.log(
  `check-bundle-budget: all ${files.length} JS chunks are within the ${(BUDGET_BYTES / 1024).toFixed(0)} kB budget.`
);
