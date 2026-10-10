// Offline support: always try the network first so each new edition shows up
// right away, and fall back to the last saved copy when offline.
const CACHE = "brief-v1";
const SHELL = ["./", "index.html", "archive.html", "manifest.webmanifest",
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
  event.respondWith((async () => {
    try {
      const res = await fetch(req, { cache: "no-cache" });  // revalidate past the HTTP cache
      if (res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return res;
    } catch {
      return (await caches.match(req)) || (await caches.match("index.html")) || Response.error();
    }
  })());
});
