/* ============================================================
 * sw.js —— 星火日历 Service Worker（PWA 离线缓存）
 * 策略：
 *   - /api/*        ：一律不缓存（工具依赖实时数据）
 *   - 文档/iframe/changelog.json/manifest.webmanifest：网络优先，离线时回退缓存（保证构建产物重建后立即生效，PWA 安装后也能拿到最新 orientation 等 manifest 配置）
 *   - 其余静态资源  ：缓存优先 + 后台更新（stale-while-revalidate）
 * 注意：仅 https 或 localhost 生效；file:// 打开时浏览器不会注册本脚本。
 * ============================================================ */
const CACHE = 'spark-calendar-v2';
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
  if (url.pathname.indexOf('/tools/') >= 0) return;    // 工具页面/脚本：一律直连，永不缓存
  if (req.destination === 'document' || req.destination === 'iframe' || url.pathname.indexOf('changelog.json') >= 0 || url.pathname.indexOf('manifest.webmanifest') >= 0) {
    e.respondWith(networkFirst(req));   // 文档 / 更新日志 / manifest：网络优先（构建后立即生效，离线回退缓存）
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
