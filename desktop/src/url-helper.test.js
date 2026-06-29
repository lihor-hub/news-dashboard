'use strict';

const assert = require('assert');
const { isAppUrl } = require('./url-helper');

const cases = [
  // Same-origin app routes — allowed
  ['https://news.lihor.ro', true],
  ['https://news.lihor.ro/', true],
  ['https://news.lihor.ro/a/1', true],
  ['https://news.lihor.ro/settings', true],

  // Lookalike host — denied
  ['https://news.lihor.ro.evil.example/', false],
  ['https://news.lihor.roevil.example/', false],

  // Different scheme — denied
  ['http://news.lihor.ro/', false],
  ['ftp://news.lihor.ro/', false],

  // Subdomain — denied
  ['https://sub.news.lihor.ro/', false],

  // Username trick — denied
  ['https://news.lihor.ro@evil.example/', false],

  // Unrelated origins — denied
  ['https://evil.example/', false],
  ['https://evil.example/?next=https://news.lihor.ro', false],

  // Malformed / empty — denied
  ['not-a-url', false],
  ['', false],
  ['javascript:alert(1)', false],
];

let passed = 0;
let failed = 0;

for (const [url, expected] of cases) {
  const result = isAppUrl(url);
  if (result === expected) {
    passed++;
  } else {
    console.error(`FAIL isAppUrl(${JSON.stringify(url)}) => ${result}, expected ${expected}`);
    failed++;
  }
}

console.log(`${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
