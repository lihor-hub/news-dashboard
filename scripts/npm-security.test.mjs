import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import test from 'node:test';
import { parse } from 'smol-toml';

const require = createRequire(import.meta.url);
const { SourceMapConsumer } = require('source-map-js');

// GHSA-68fv-2mgg-jv7q: reject the offset before any consumer can expand it.
test('indexed source maps reject offsets that amplify tiny input', () => {
  assert.throws(
    () =>
      new SourceMapConsumer({
        version: 3,
        sections: [
          {
            offset: { line: 1e12, column: 0 },
            map: { version: 3, sources: ['input.js'], names: [], mappings: 'AAAA' },
          },
        ],
      }),
    /offset/i
  );
});

// GHSA-r4xh-jqrq-34v2: ordinary dot-free keys previously caused quadratic work.
// A child process bounds the reproducer even if a vulnerable parser is restored.
test('large flat TOML documents parse without quadratic scanning', () => {
  const ordinary = parse('[build]\n"source.map" = "input.js"');
  assert.equal(ordinary.build['source.map'], 'input.js');
  const result = spawnSync(
    process.execPath,
    [
      '--input-type=module',
      '-e',
      `
    import assert from 'node:assert/strict';
    import { parse } from 'smol-toml';
    const count = 512000;
    const doc = Array.from({ length: count }, (_, i) => 'k' + i + ' = 1').join('\\n');
    const parsed = parse(doc);
    assert.equal(Object.keys(parsed).length, count);
    assert.equal(parsed.k0, 1);
    assert.equal(parsed.k511999, 1);
  `,
    ],
    { cwd: new URL('..', import.meta.url), timeout: 10000, encoding: 'utf8' }
  );
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
});
