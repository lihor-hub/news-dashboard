/* Push notification event handlers — imported by the Workbox-generated SW. */

self.addEventListener('push', function (event) {
  let title = 'Daily Brief';
  let body = 'Your daily brief is ready.';
  try {
    const data = event.data ? event.data.json() : {};
    if (data.title) title = data.title;
    if (data.body) body = data.body;
  } catch {
    // keep defaults if payload is not valid JSON
  }
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-monochrome-512.png',
      tag: 'daily-brief',
      renotify: true,
    })
  );
});

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  event.waitUntil(
    clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then(function (windowClients) {
        for (const client of windowClients) {
          if ('focus' in client) {
            client.focus();
            return;
          }
        }
        if (clients.openWindow) {
          return clients.openWindow('/');
        }
      })
  );
});
