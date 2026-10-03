'use strict';

const assert = require('assert');
const Module = require('module');

const originalLoad = Module._load;
let initOptions = null;

Module._load = function patchedLoad(request, parent, isMain) {
  if (request === '@sentry/node') {
    return {
      init: (options) => {
        initOptions = options;
      },
    };
  }
  return originalLoad.call(this, request, parent, isMain);
};

const testDsn = 'https://examplePublicKey@o0.ingest.sentry.io/0';

try {
  process.env.SENTRY_DSN_DESKTOP = testDsn;
  process.env.SENTRY_ENVIRONMENT = 'test';
  process.env.SENTRY_RELEASE = 'news-dashboard-desktop@test';
  const { sentryOptions } = require('./instrument');

  assert.strictEqual(initOptions, sentryOptions);
  assert.strictEqual(sentryOptions.dsn, testDsn);
  assert.strictEqual(sentryOptions.environment, 'test');
  assert.strictEqual(sentryOptions.release, 'news-dashboard-desktop@test');
  assert.deepStrictEqual(sentryOptions.dataCollection, {
    userInfo: false,
    cookies: false,
    httpHeaders: false,
    httpBodies: [],
    urlQueryParams: false,
    genAI: { inputs: false, outputs: false },
    databaseQueryData: false,
    graphQL: { document: false, variables: false },
    queues: false,
    stackFrameVariables: false,
  });
} finally {
  Module._load = originalLoad;
  delete process.env.SENTRY_DSN_DESKTOP;
  delete process.env.SENTRY_ENVIRONMENT;
  delete process.env.SENTRY_RELEASE;
}

console.log('instrument passed');
