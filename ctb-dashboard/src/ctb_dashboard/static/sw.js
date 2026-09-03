// Service worker for PWA installability + push notifications.
//
// Caching rule, and the reason for it: the app shell (page, JS, icons) is
// cached so the installed PWA opens instantly and survives a dropped link, but
// /api/* is NEVER cached. This dashboard's whole job is reporting the current
// state of live sessions -- serving a stale session list from cache would be
// worse than showing nothing, because it looks authoritative.

const CACHE = 'ctb-shell-v3';

// Deliberately small: the shell, not the data.
const SHELL = [
  '/',
  '/static/js/control-token.js',
  '/static/js/session-control.js',
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/img/parchment.jpg',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE)
      // cache.addAll is atomic -- a single 404 would discard the whole install,
      // so add entries one at a time and tolerate misses.
      .then((cache) => Promise.all(SHELL.map((url) => cache.add(url).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Live data: network only. Never cached, never served stale.
  if (url.pathname.startsWith('/api/')) return;

  // Shell: network first so a deploy is picked up immediately, with the cache
  // as the offline floor.
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((hit) => hit || Response.error()))
  );
});

/* A push arrives whether or not the app is running -- this is the only path
 * that reaches a phone with the screen off, since everything else the
 * dashboard shows is drawn by an open page. */
self.addEventListener('push', (e) => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (_) {}
  const title = data.title || 'Claude 작업 완료';
  e.waitUntil(self.registration.showNotification(title, {
    body: data.body || '',
    icon: '/static/icon-192.png',
    badge: '/static/icon-192.png',
    // One notification per session: a second completion replaces the first
    // rather than stacking up behind it.
    tag: data.session ? 'ctb-done-' + data.session : 'ctb-done',
    renotify: true,
    vibrate: [200, 100, 200],
    data: { url: data.url || '/' },
  }));
});

// Handle notification click -- focus dashboard tab
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const target = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if (c.url.includes('/') && 'focus' in c) {
          // Take the tab to the session the notification is about.
          if ('navigate' in c && target !== '/') c.navigate(target).catch(() => {});
          return c.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(target);
    })
  );
});
