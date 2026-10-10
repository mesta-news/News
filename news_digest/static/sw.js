// Offline support: always try the network first so each new edition shows up
// right away, and fall back to the last saved copy when offline or when the
// network is too slow to answer (e.g. a weak mobile signal).
const CACHE = "brief-v3";
const SLOW_MS = 4000;
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
