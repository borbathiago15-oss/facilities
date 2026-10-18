// Service worker do app instalável.
//
// Fase 1: quando a navegação não chega ao servidor, mostra a página "Sem
// conexão" em vez do erro do navegador.
//
// Fase 3: duas telas funcionam SEM internet — a nova passagem de turno e a
// auditoria AGL já aberta. Para isso, e só para isso, este arquivo guarda uma
// cópia delas no aparelho a cada abertura com conexão. Tudo o mais continua
// sem cópia: as outras páginas trazem dado de cliente, folha e financeiro, e
// o celular do galpão é compartilhado.
//
// As cópias guardadas moram num cache à parte (TELAS) e são APAGADAS ao sair
// do sistema e ao abrir a tela de login (static/js/fila-offline.js e
// app-instalavel.js) — quem pega o aparelho depois não abre a tela de quem
// saiu. O que a pessoa escreveu sem sinal não mora aqui: fica na fila do
// aparelho (IndexedDB), é de quem escreveu e só sobe com essa pessoa logada.
//
// CSS, JS, fontes e ícones (/static/) passam a ter cópia também, porque a tela
// guardada precisa deles para abrir sem rede. São públicos e não têm dado de
// ninguém. Com rede, vêm sempre da rede (um deploy aparece na hora); a
// cópia só é usada quando não há conexão.
//
// Trocar VERSAO força o navegador a instalar a versão nova e apagar a antiga.
// v4: identidade nova — ícone e página "Sem conexão" guardados de novo.
const VERSAO = 'facilities-app-v5';
const TELAS = 'trino-telas';
const ESTATICOS = 'trino-estaticos-v3';
const OFFLINE = '/static/pwa/offline.html';
const GUARDAR = [OFFLINE, '/static/pwa/icone-192.png'];
// As únicas telas que ganham cópia no aparelho.
const TELAS_SEM_INTERNET = [
  /^\/passagem-de-turno\/turno\/?$/,   // nova passagem de turno
  /^\/app\/?$/,                         // início do aplicativo de campo
  /^\/app\/ler-qr\/?$/,                 // leitor de QR (não tem dado de ninguém)
  /^\/app\/turno\/?$/,                  // meu turno: tarefas e checklists do dia
];

self.addEventListener('install', (evento) => {
  evento.waitUntil(
    caches.open(VERSAO).then((cache) => cache.addAll(GUARDAR)).then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (evento) => {
  const manter = [VERSAO, TELAS, ESTATICOS];
  evento.waitUntil(
    caches.keys()
      .then((nomes) => Promise.all(nomes.filter((n) => !manter.includes(n)).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

// A página pede para apagar as telas guardadas (ao sair do sistema).
self.addEventListener('message', (evento) => {
  if (evento.data && evento.data.tipo === 'apagar-telas') {
    evento.waitUntil(caches.delete(TELAS));
  }
});

function eTelaSemInternet(url) {
  return url.origin === self.location.origin
    && TELAS_SEM_INTERNET.some((re) => re.test(url.pathname));
}

// Rede primeiro; com resposta boa, guarda a cópia. Sem rede, a cópia; sem
// cópia, a página "Sem conexão". Só guarda 200 de verdade da própria tela —
// nunca o login para onde uma sessão vencida redirecionaria.
async function telaSemInternet(pedido) {
  try {
    const resposta = await fetch(pedido);
    if (resposta.ok && !resposta.redirected && resposta.type === 'basic') {
      const cache = await caches.open(TELAS);
      await cache.put(pedido.url, resposta.clone());
    }
    return resposta;
  } catch (e) {
    const cache = await caches.open(TELAS);
    const guardada = (await cache.match(pedido.url))
      // A passagem aberta com outro ?client_id= ainda serve: é a mesma tela,
      // do mesmo usuário, e o contrato se troca nela.
      || (await cache.match(pedido.url, { ignoreSearch: true }));
    return guardada || caches.match(OFFLINE, { cacheName: VERSAO });
  }
}

// Rede primeiro (o cache HTTP do navegador continua valendo, então é rápido
// e um deploy aparece na hora); a cópia só entra quando não há rede.
async function estatico(pedido) {
  const cache = await caches.open(ESTATICOS);
  try {
    const resposta = await fetch(pedido);
    if (resposta.ok && resposta.type === 'basic') {
      await cache.put(pedido, resposta.clone());
    }
    return resposta;
  } catch (e) {
    const guardado = await cache.match(pedido);
    if (guardado) return guardado;
    throw e;
  }
}

self.addEventListener('fetch', (evento) => {
  const pedido = evento.request;
  if (pedido.method !== 'GET') return;          // envios são da página e da fila
  const url = new URL(pedido.url);
  if (url.origin !== self.location.origin) return;
  // Os arquivos da própria página "Sem conexão" saem do aparelho.
  if (GUARDAR.includes(url.pathname)) {
    evento.respondWith(
      caches.match(pedido, { cacheName: VERSAO }).then((guardado) => guardado || fetch(pedido)),
    );
    return;
  }
  if (pedido.mode === 'navigate') {
    if (eTelaSemInternet(url)) {
      evento.respondWith(telaSemInternet(pedido));
      return;
    }
    evento.respondWith(
      fetch(pedido).catch(() => caches.match(OFFLINE, { cacheName: VERSAO })),
    );
    return;
  }
  if (url.pathname.startsWith('/static/')) {
    evento.respondWith(estatico(pedido));
  }
  // Chamadas de API e o resto: do navegador, como sempre foi.
});

// ── Fase 2: notificação no celular ───────────────────────────────────────
// A mensagem chega cifrada do servidor (RFC 8291) e o navegador já a entrega
// aberta aqui. Ela traz título, texto e o caminho da tela que a explica.
self.addEventListener('push', (evento) => {
  let dados = {};
  try {
    dados = evento.data ? evento.data.json() : {};
  } catch (e) {
    dados = {};
  }
  const titulo = dados.titulo || 'Trino Facilities';
  evento.waitUntil(self.registration.showNotification(titulo, {
    body: dados.corpo || '',
    icon: '/static/pwa/icone-192.png',
    badge: '/static/pwa/icone-192.png',
    tag: dados.tag || undefined,
    data: { url: dados.url || '/avisos' },
    lang: 'pt-BR',
  }));
});

self.addEventListener('notificationclick', (evento) => {
  evento.notification.close();
  const pedido = (evento.notification.data && evento.notification.data.url) || '/avisos';
  // Só caminho do próprio sistema: uma URL de fora nunca vira destino de toque.
  const destino = (typeof pedido === 'string' && pedido.startsWith('/') && !pedido.startsWith('//'))
    ? pedido : '/avisos';
  evento.waitUntil((async () => {
    const janelas = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const j of janelas) {
      if (new URL(j.url).origin === self.location.origin && 'focus' in j) {
        await j.focus();
        return j.navigate(destino);
      }
    }
    return self.clients.openWindow(destino);
  })());
});

// ── Avisos no celular (Web Push, Fase 4B) ──────────────────────────────
// O servidor manda {titulo, texto, link, marca}. A "marca" faz o aviso novo
// da mesma coisa substituir o anterior em vez de empilhar.
self.addEventListener('push', (evento) => {
  let d = {};
  try { d = evento.data ? evento.data.json() : {}; } catch (e) { d = {}; }
  const titulo = d.titulo || 'Trino Facilities';
  evento.waitUntil(self.registration.showNotification(titulo, {
    body: d.texto || '',
    tag: d.marca || undefined,
    renotify: !!d.marca,
    icon: '/static/pwa/icone-192.png',
    badge: '/static/pwa/icone-192.png',
    data: { link: d.link || '/app/' },
  }));
});

// Tocar no aviso abre (ou traz para a frente) o aplicativo no link do aviso.
// Só caminho interno: um link que não começa com "/" vira o início do app.
self.addEventListener('notificationclick', (evento) => {
  evento.notification.close();
  let link = (evento.notification.data && evento.notification.data.link) || '/app/';
  if (typeof link !== 'string' || !link.startsWith('/') || link.startsWith('//')) link = '/app/';
  evento.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    .then((janelas) => {
      for (const j of janelas) {
        if (new URL(j.url).origin === self.location.origin && 'focus' in j) {
          return j.navigate(link).then((w) => (w || j).focus());
        }
      }
      return self.clients.openWindow(link);
    }));
});
