// UCSRS v2.0.0 Service Worker — cache bumped so prior visitors get the independent-score edition
const CACHE_NAME = 'ucsrs-v2.0.0';
const ASSETS = ['/', '/index.html', '/manifest.json', '/icon-192x192.png', '/icon-512x512.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE_NAME).then(c => c.addAll(ASSETS)));
  self.skipWaiting();
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))));
  self.clients.claim();
});
// Network-first for the page itself, so updates are picked up; cache fallback for offline
self.addEventListener('fetch', e => {
  e.respondWith(
    fetch(e.request).then(r => {
      const copy = r.clone();
      caches.open(CACHE_NAME).then(c => c.put(e.request, copy)).catch(()=>{});
      return r;
    }).catch(() => caches.match(e.request).then(m => m || caches.match('/index.html')))
  );
});
