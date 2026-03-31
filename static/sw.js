const CACHE = 'caja-magica-v1'
const ASSETS = ['/', '/static/index.html', '/static/manifest.json',
  '/static/icons/icon-192.svg', '/static/icons/icon-512.svg']

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)))
  self.skipWaiting()
})

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ))
  self.clients.claim()
})

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url)
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(fetch(e.request).catch(() => new Response('{"error":"offline"}', {headers:{'Content-Type':'application/json'}})))
  } else {
    e.respondWith(caches.match(e.request).then(cached => cached || fetch(e.request)))
  }
})
