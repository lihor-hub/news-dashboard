'use strict';

const APP_ORIGIN = new URL('https://news.lihor.ro').origin;

/**
 * Returns true if the given URL belongs to the exact app origin.
 * Malformed URLs are treated as external (returns false).
 */
function isAppUrl(url) {
  try {
    return new URL(url).origin === APP_ORIGIN;
  } catch {
    return false;
  }
}

module.exports = { isAppUrl, APP_ORIGIN };
