// Service worker: makes the assistant installable as an app. Everything comes from the Spark, so the app always
// shows the current version. Only when the Spark does not answer at all (no network) does it fall back to the page
// a trusted browser kept for "Verlauf offline lesen" (verlauf.js, cache "spark-shell": the page and its scripts,
// never personal data; an untrusted browser has no such cache). Never the API.
const SHELL = 'spark-shell';
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== 'GET' || u.origin !== self.location.origin) return;
  const page = r.mode === 'navigate' && u.pathname === '/';
  if (!page && !u.pathname.startsWith('/static/')) return;
  e.respondWith(fetch(r).catch(() => caches.match(page ? '/' : r, {cacheName: SHELL, ignoreSearch: page})
    .then(x => x || Response.error())));
});
// Reminders as notifications, also while no page is open (see push.py). A visible page rings
// the reminder itself, so then no notification is shown.
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data.json(); } catch (x) { d = {title: 'Spark', body: e.data ? e.data.text() : ''}; }
  e.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(list => {
    if (d.tag !== 'hello' && list.some(c => c.visibilityState === 'visible')) return;
    return self.registration.showNotification(d.title || 'Spark', {body: d.body || '', tag: d.tag || undefined,
      icon: '/static/icon-192.png', badge: '/static/icon-192.png', data: {weg: typeof d.weg === 'string' ? d.weg.slice(0, 200) : '',
        vg: /^v[0-9a-f]{10}$/.test(d.vg || '') ? d.vg : ''}});
  }));
});
// a note naming a place in the panel ("Ich → Gedächtnis", push.py) opens it there (way.js); only navigation.
// A note about a Vorgang (vg) tells the page it was opened, the page says "gesehen" (reminders.js, zustellung.py)
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const weg = (e.notification.data && e.notification.data.weg) || '', vg = (e.notification.data && e.notification.data.vg) || '';
  e.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(list => {
    const to = weg ? '/#weg=' + encodeURIComponent(weg) : '/';
    if (!list.length) return self.clients.openWindow(vg ? '/?vg=' + vg + to.slice(1) : to);
    if (weg) list[0].postMessage({weg});
    if (vg) list[0].postMessage({vg});
    return list[0].focus();
  }));
});
