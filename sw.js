self.addEventListener('install', function(e) {
  self.skipWaiting();
});

self.addEventListener('fetch', function(e) {
  // Let network requests pass through
  e.respondWith(fetch(e.request));
});
