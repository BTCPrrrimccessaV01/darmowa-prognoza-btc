const CACHE = 'prognoza-btc-v4';
const SHELL = ['./', './index.html', './manifest.webmanifest', './icons/icon-192.png', './icons/icon-512.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => null))))
    .then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET' || u.origin !== self.location.origin) return;
  const key = u.origin + u.pathname;
  if (e.request.mode === 'navigate' || u.pathname.endsWith('/') || u.pathname.endsWith('.html')) {
    // strona: najpierw świeża z sieci, offline ostatnia kopia
    e.respondWith(fetch(e.request).then(r => { caches.open(CACHE).then(c => c.put(key, r.clone())); return r; })
      .catch(() => caches.match(key)));
    return;
  }
  if (u.pathname.endsWith('.json')) {
    // dane: zawsze najpierw świeże z sieci, offline ostatnia zapisana kopia
    e.respondWith(fetch(e.request).then(r => { caches.open(CACHE).then(c => c.put(key, r.clone())); return r; })
      .catch(() => caches.match(key)));
    return;
  }
  e.respondWith(caches.match(key).then(r => r || fetch(e.request)));
});
