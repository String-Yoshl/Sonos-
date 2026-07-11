/* Service Worker: アプリシェルをキャッシュしてアプリのように素早く起動する。
   API レスポンスはキャッシュせず常に最新を取得する（スケジュール状態は鮮度が重要）。 */
const CACHE = "sleep-bgm-v4";
const SHELL = [
  "./",
  "./index.html",
  "./style.css",
  "./app.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // API は常にネットワーク優先（キャッシュしない）。
  if (url.pathname.startsWith("/api/")) {
    return; // デフォルトのネットワーク処理に任せる
  }
  // アプリシェルはキャッシュ優先（オフラインでも起動できる）。
  event.respondWith(
    caches.match(event.request).then((hit) => hit || fetch(event.request))
  );
});
