self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  // 保持預設網路請求，確保 API 與畫面正常運作
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
