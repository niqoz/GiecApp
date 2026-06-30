/* Service worker — Climat Commune.
   Cache l'app shell et le JSON climatique. Strategie reseau d'abord, cache en
   repli pour garder la derniere version disponible hors-ligne. */
const CACHE = "climat-commune-tasmax-v6";
const ASSETS = [
  "./",
  "./index.html",
  "./manifest.webmanifest",
  "./climat_france_tasmax.json",
  "./icon-192.png",
  "./icon-512.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok && new URL(request.url).origin === self.location.origin) {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      })
      .catch(() =>
        caches.match(request).then((cached) =>
          cached || (request.mode === "navigate" ? caches.match("./index.html") : undefined)
        )
      )
  );
});
