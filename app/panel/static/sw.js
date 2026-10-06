// Minimal service worker: makes the assistant installable as an app. Everything still comes
// from the Spark (no offline cache), so the app always shows the current version.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
