// Minimal service worker: makes the assistant installable as an app. Everything still comes
// from the Spark (no offline cache), so the app always shows the current version.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
// Reminders as notifications, also while no page is open (see push.py). A visible page rings
// the reminder itself, so then no notification is shown.
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data.json(); } catch (x) { d = {title: 'Spark', body: e.data ? e.data.text() : ''}; }
  e.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(list => {
    if (d.tag !== 'hello' && list.some(c => c.visibilityState === 'visible')) return;
    return self.registration.showNotification(d.title || 'Spark', {body: d.body || '', tag: d.tag || undefined,
      icon: '/static/icon-192.png', badge: '/static/icon-192.png', data: {url: '/'}});
  }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(list =>
    list.length ? list[0].focus() : self.clients.openWindow('/')));
});
