// 手机网页版的离线缓存（10-23）：页面本身先上网拿，3 秒拿不到（不在家、Mac 睡了）就用存着的那份；课表数据在页面自己的 localStorage 里。
const CACHE='coda-m-1',FILES=['/m','/m/manifest.json','/m/icon.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(FILES)).catch(()=>{}));self.skipWaiting()});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
 const u=new URL(e.request.url);
 if(e.request.method!=='GET'||u.origin!==location.origin)return;
 const key=u.pathname==='/m/'?'/m':u.pathname;
 if(!FILES.includes(key))return;   // /m/data、/m/act 不经过缓存
 e.respondWith((async()=>{
  const cache=await caches.open(CACHE);
  try{
   const net=await Promise.race([fetch(e.request,{cache:'no-store'}),new Promise((_,no)=>setTimeout(()=>no(new Error('timeout')),3000))]);
   if(net.ok)cache.put(key,net.clone());
   return net;
  }catch(err){
   const hit=await cache.match(key);if(hit)return hit;throw err;
  }
 })());
});
