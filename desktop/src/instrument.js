'use strict';

const Sentry = require('@sentry/node');

const sentryOptions = {
  dsn: process.env.SENTRY_DSN_DESKTOP || undefined,
  environment: process.env.SENTRY_ENVIRONMENT || 'production',
  release: process.env.SENTRY_RELEASE || undefined,
  // Keep collection explicit when SDK defaults change between major versions.
  dataCollection: {
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
  },
};

// Only initialize when a DSN is configured; otherwise stay a no-op so a
// missing env var never blocks the desktop app from starting.
if (sentryOptions.dsn) {
  Sentry.init(sentryOptions);
}

module.exports = { sentryOptions };
