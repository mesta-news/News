// Offline support: always try the network first so each new edition shows up
// right away, and fall back to the last saved copy when offline or when the
// network is too slow to answer (e.g. a weak mobile signal).
const CACHE = "brief-v5";
const SLOW_MS = 4000;
const SHELL = ["./", "index.html", "archive.html", "app.js", "manifest.webmanifest",
               "icon-192.png", "apple-touch-icon.png"];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key);
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  const network = fetch(req, { cache: "no-cache" }).then((res) => {  // revalidate past the HTTP cache
    if (res.ok) {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy));
    }
    return res;
  });
  event.waitUntil(network.catch(() => {}));  // let a slow response still refresh the cache
  event.respondWith((async () => {
    const cached = caches.match(req);
    const slow = new Promise((resolve) => setTimeout(resolve, SLOW_MS));
    try {
      // Network wins unless it is slow and we have a saved copy to show instead.
      const res = await Promise.race([network, slow.then(() => cached).then((c) => c || network)]);
      if (res) return res;
    } catch {}
    return (await cached) || (await caches.match("index.html")) || Response.error();
  })());
});

// Push notifications from the daily GitHub Action (see news_digest/push.py).
self.addEventListener("push", (event) => {
  let msg = {};
  try { msg = event.data ? event.data.json() : {}; } catch { msg = { body: event.data && event.data.text() }; }
  event.waitUntil(self.registration.showNotification(msg.title || "The Daily Brief", {
    body: msg.body || "",
    icon: msg.icon || "icon-192.png",
    badge: "badge-72.png",
    tag: msg.tag || "brief",
    data: { url: msg.url || "./" },
  }));
});

// Tapping a notification opens the app on that notification's tab.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || "./", self.registration.scope).href;
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const win = wins.find((w) => w.url.startsWith(self.registration.scope));
    if (win) {
      await win.focus();
      return win.navigate(url).catch(() => self.clients.openWindow(url));
    }
    return self.clients.openWindow(url);
  })());
});
