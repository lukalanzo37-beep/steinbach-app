const CACHE='steinbach-v15-pilot1';
const CORE=['./','./manifest.webmanifest','./config.js','./static/pilot-backend.js','./assets/img/logo.webp','./assets/icons/icon-192.png','./assets/icons/icon-512.png','./assets/icons/icon-maskable-512.png'];
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(c=>c.addAll(CORE)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',event=>{
  const req=event.request;
  if(req.method!=='GET') return;
  const url=new URL(req.url);
  if(url.pathname.startsWith('/api/') || url.pathname.startsWith('/uploads/')) return;
  if(req.mode==='navigate'){
    event.respondWith(fetch(req).then(res=>{const clone=res.clone();caches.open(CACHE).then(c=>c.put('./index.html',clone));return res}).catch(()=>caches.match('./index.html')));
    return;
  }
  if(url.origin===self.location.origin){
    event.respondWith(caches.match(req).then(hit=>hit||fetch(req).then(res=>{if(res.ok){const clone=res.clone();caches.open(CACHE).then(c=>c.put(req,clone))}return res})));
    return;
  }
  if(req.destination==='image'){
    event.respondWith(caches.match(req).then(hit=>hit||fetch(req).then(res=>{const clone=res.clone();caches.open(CACHE).then(c=>c.put(req,clone));return res}).catch(()=>caches.match('./assets/img/logo.webp'))));
  }
});
self.addEventListener('push',event=>{
  let data={title:'Immobilienservice Steinbach',body:'Neue Benachrichtigung im Portal.',url:'/?portal=customer'};
  try{if(event.data)data={...data,...event.data.json()}}catch{try{data.body=event.data.text()}catch{}}
  event.waitUntil(self.registration.showNotification(data.title||'Immobilienservice Steinbach',{body:data.body||'',icon:'./assets/icons/icon-192.png',badge:'./assets/icons/icon-192.png',data:{url:data.url||'/?portal=customer'},tag:'steinbach-portal',renotify:true}));
});
self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const target=new URL(event.notification.data?.url||'/?portal=customer',self.location.origin).href;
  event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(list=>{for(const client of list){if('focus'in client){client.navigate(target);return client.focus()}}return clients.openWindow(target)}));
});
