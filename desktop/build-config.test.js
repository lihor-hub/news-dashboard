'use strict';

// Exercise the real builder config and the universal merger's glob semantics.
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const path = require('node:path');
const { getConfig, validateConfiguration } = require('app-builder-lib/out/util/config/config');
const { minimatch } = createRequire(require.resolve('@electron/universal'))('minimatch');

async function main() {
  const config = await getConfig(__dirname, path.join(__dirname, 'electron-builder.yml'), null);
  await validateConfiguration(config);
  const pattern = config.mac.x64ArchFiles;
  assert.equal(typeof pattern, 'string');
  for (const arch of ['arm64', 'x64']) {
    const file = `Contents/Resources/app.asar.unpacked/node_modules/@oxc-parser/binding-darwin-${arch}/parser.darwin-${arch}.node`;
    assert.ok(minimatch(file, pattern, { matchBase: true }), `Must preserve ${arch} parser binary`);
  }
  for (const file of [
    'Contents/MacOS/News Dashboard',
    'Contents/Frameworks/Electron Framework.framework/Electron Framework',
    'Contents/Resources/app.asar.unpacked/node_modules/other/addon.node',
  ]) {
    assert.ok(!minimatch(file, pattern, { matchBase: true }), `Must not bypass merging ${file}`);
  }
  for (const target of ['dmg', 'zip']) {
    assert.ok(config.mac.target.some((entry) => entry.target === target && entry.arch.includes('universal')));
  }
  console.log('Desktop universal packaging configuration passed');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
