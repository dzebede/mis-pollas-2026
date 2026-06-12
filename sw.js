// Service worker: network-first para HTML y datos (siempre lo último cuando hay internet),
// cache-first sólo para iconos/manifest. Cache de respaldo para abrir offline.
const CACHE = 'pollas-v2';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icons/icon-192.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  const isStatic = url.pathname.includes('/icons/') || url.pathname.endsWith('.webmanifest');
  if (isStatic) {
    // cache-first
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
    return;
  }
  // HTML, JS, JSON, etc: network-first, con respaldo a cache
  e.respondWith(
    fetch(e.request).then(r => {
      const cp = r.clone();
      caches.open(CACHE).then(c => c.put(e.request, cp)).catch(() => {});
      return r;
    }).catch(() => caches.match(e.request).then(r => r || caches.match('./index.html')))
  );
});
