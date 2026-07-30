// Service worker for PWA installability + push notifications.
//
// Caching rule, and the reason for it: the app shell (page, JS, icons) is
// cached so the installed PWA opens instantly and survives a dropped link, but
// /api/* is NEVER cached. This dashboard's whole job is reporting the current
// state of live sessions -- serving a stale session list from cache would be
// worse than showing nothing, because it looks authoritative.

const CACHE = 'ctb-shell-v1';

// Deliberately small: the shell, not the data.
const SHELL = [
  '/',
  '/static/js/control-token.js',
  '/static/js/session-control.js',
  '/static/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
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

// Handle notification click -- focus dashboard tab
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if (c.url.includes('/') && 'focus' in c) return c.focus();
      }
      if (clients.openWindow) return clients.openWindow('/');
    })
  );
});
