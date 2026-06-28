/* Push notification event handlers — imported by the Workbox-generated SW. */

/** Return url if it is a same-origin relative path starting with /, otherwise '/'. */
function _safeUrl(url) {
  if (typeof url !== 'string' || url === '') return '/';
  if (url === '/' || /^\/[^/]/.test(url)) return url;
  return '/';
}

function _safeTag(tag) {
  if (typeof tag !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(tag)) return 'daily-brief';
  return tag;
}

self.addEventListener('push', function (event) {
  let title = 'Daily Brief';
  let body = 'Your daily brief is ready.';
  let targetUrl = '/';
  let tag = 'daily-brief';
  try {
    const data = event.data ? event.data.json() : {};
    if (data.title) title = data.title;
    if (data.body) body = data.body;
    if (data.url) targetUrl = _safeUrl(data.url);
    if (data.tag) tag = _safeTag(data.tag);
  } catch {
    // keep defaults if payload is not valid JSON
  }
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-monochrome-512.png',
      tag,
      renotify: true,
      data: { url: targetUrl },
    })
  );
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  const targetUrl = _safeUrl(
    event.notification.data && event.notification.data.url ? event.notification.data.url : '/'
  );
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (windowClients) {
      for (const client of windowClients) {
        if (client.url.endsWith(targetUrl) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl);
      }
    })
  );
});
