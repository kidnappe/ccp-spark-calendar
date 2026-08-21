/* ============================================================
 * sw.js —— 星火日历 Service Worker（PWA 离线缓存）
 * 策略：
 *   - /api/*        ：一律不缓存（工具依赖实时数据）
 *   - 文档/iframe   ：网络优先，离线时回退缓存（保证 build_data.py 重建后立即生效）
 *   - 其余静态资源  ：缓存优先 + 后台更新（stale-while-revalidate）
 * 注意：仅 https 或 localhost 生效；file:// 打开时浏览器不会注册本脚本。
 * ============================================================ */
const CACHE = 'spark-calendar-v1';
const CORE = ['./manifest.webmanifest'];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(CORE)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.pathname.indexOf('/api/') >= 0) return;      // API 走网络
  if (req.destination === 'document' || req.destination === 'iframe') {
    e.respondWith(networkFirst(req));
  } else {
    e.respondWith(staleWhileRevalidate(req));
  }
});

async function networkFirst(req) {
  const cache = await caches.open(CACHE);
  try {
    const fresh = await fetch(req);
    if (fresh && fresh.ok) cache.put(req, fresh.clone());
    return fresh;
  } catch (err) {
    const hit = await cache.match(req);
    if (hit) return hit;
    const home = await cache.match('./index.html');
    return home || Response.error();
  }
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(req);
  const net = fetch(req)
    .then((res) => {
      if (res && res.ok) cache.put(req, res.clone());
      return res;
    })
    .catch(() => null);
  if (hit) return hit;
  const res = await net;
  return res || Response.error();
}
