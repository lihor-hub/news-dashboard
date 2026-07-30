#!/usr/bin/env node
// Verify that the production HTML and service-worker registration can run
// under the application's script-src 'self' policy.
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const DIST_DIR = process.argv[2] ?? 'frontend/dist';
const INDEX_PATH = join(DIST_DIR, 'index.html');

function fail(message) {
  console.error(`check-csp-build: ${message}`);
  process.exit(1);
}

let html;
try {
  html = readFileSync(INDEX_PATH, 'utf-8');
} catch (error) {
  fail(`could not read ${INDEX_PATH}: ${error.message}`);
}

if (/<[^>]+\son[a-z][\w:-]*\s*=/i.test(html)) {
  fail('index.html contains an inline event handler blocked by script-src self');
}
if (
  /<[^>]+\s[\w:-]+\s*=\s*(?:"\s*javascript:|'\s*javascript:|javascript:[^\s>]*)/i.test(html)
) {
  fail('index.html contains a javascript URL blocked by script-src self');
}

const scriptTags = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)];
let externalRegistration;

for (const [, attributes, body] of scriptTags) {
  const srcMatch = attributes.match(/\bsrc=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/i);
  const src = srcMatch?.[1] ?? srcMatch?.[2] ?? srcMatch?.[3];
  if (body.trim() !== '' || src === undefined) {
    fail('index.html contains an inline script blocked by script-src self');
  }
  if (!src.startsWith('/') || src.startsWith('//') || src.includes('..')) {
    fail(`index.html references a non-same-origin script: ${src}`);
  }

  const scriptPath = join(DIST_DIR, src.slice(1).split(/[?#]/, 1)[0]);
  let script;
  try {
    script = readFileSync(scriptPath, 'utf-8');
  } catch (error) {
    fail(`could not read emitted script ${scriptPath}: ${error.message}`);
  }
  if (script.includes('serviceWorker.register')) {
    externalRegistration = src;
  }
}

if (externalRegistration === undefined) {
  fail('no external service-worker registration script was emitted');
}
for (const requiredFile of ['sw.js', 'manifest.webmanifest']) {
  if (!existsSync(join(DIST_DIR, requiredFile))) {
    fail(`required PWA artifact is missing: ${requiredFile}`);
  }
}

console.log(
  `check-csp-build: external service-worker registration ${externalRegistration} is CSP-compatible.`
);
