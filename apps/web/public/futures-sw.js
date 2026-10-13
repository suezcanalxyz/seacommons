// Futures: cache static assets only; never cache authenticated HTML or API responses.
const CACHE = 'seacommons-futures-static-v1';
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil((async () => {
  for (const key of await caches.keys()) if (key.startsWith('seacommons-futures-static-') && key !== CACHE) await caches.delete(key);
  await self.clients.claim();
})()));
self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin || req.mode === 'navigate' ||
      url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/') ||
      req.headers.has('authorization') || req.credentials === 'include') return;
  if (!url.pathname.startsWith('/assets/') && !url.pathname.startsWith('/futures-icons/')) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const cached = await cache.match(req);
    if (cached) return cached;
    const response = await fetch(req);
    if (response.ok && response.type === 'basic' && !response.headers.has('set-cookie')) await cache.put(req, response.clone());
    return response;
  })());
});
