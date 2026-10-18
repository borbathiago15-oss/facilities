/* O que toda tela do site precisa: esc(), o token CSRF no fetch, a ajuda
   dos ícones e o recado de uma vez só. Era embutido no base.html; saiu
   daqui para a página poder ter CSP sem 'unsafe-inline' (Fase 9A). */
/* esc(): escape de HTML, um só para o sistema inteiro. Escapa também as
   aspas: o texto às vezes cai dentro de um atributo. */
window.esc = function (s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
};
/* CSRF: injeta X-CSRFToken em toda requisição fetch que altera algo. */
(function () {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const csrf = meta ? meta.content : '';
  const orig = window.fetch;
  const SAFE = ['GET', 'HEAD', 'OPTIONS', 'TRACE'];
  window.fetch = function (input, init) {
    init = init || {};
    const method = (init.method ||
      (typeof input === 'object' && input && input.method) || 'GET').toUpperCase();
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    /* Origem de verdade, pelo navegador: '//outro.site/x' e
       'https://app.com.outro.io' começam "parecidos" mas são outro site, e o
       token não pode ir junto. */
    let sameOrigin = false;
    try { sameOrigin = new URL(url, location.href).origin === location.origin; }
    catch (e) { sameOrigin = false; }
    if (csrf && sameOrigin && !SAFE.includes(method)) {
      const headers = new Headers(init.headers ||
        (typeof input === 'object' && input && input.headers) || {});
      if (!headers.has('X-CSRFToken')) headers.set('X-CSRFToken', csrf);
      init.headers = headers;
    }
    return orig(input, init);
  };
})();
/* Ajuda dos ícones (?): o Bootstrap só mostra tooltip criado por JS. No
   celular não há "passar o mouse": o toque abre a ajuda, e tocar em outro
   lugar fecha. O ícone também entra na ordem do teclado (Tab). */
(function () {
  const icones = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  if (!icones.length || !window.bootstrap) return;
  const soToque = !!(window.matchMedia && matchMedia('(hover: none)').matches);
  icones.forEach(function (el) {
    if (!el.hasAttribute('tabindex') && !el.matches('a, button, input, select, textarea')) {
      el.tabIndex = 0;
    }
    bootstrap.Tooltip.getOrCreateInstance(el, soToque ? { trigger: 'click' } : {});
  });
  if (soToque) {
    document.addEventListener('click', function (ev) {
      icones.forEach(function (el) {
        const dica = bootstrap.Tooltip.getInstance(el);
        if (dica && !el.contains(ev.target)) dica.hide();
      });
    }, true);
  }
})();
/* fc-aviso: recado de uma vez só, deixado por uma tela que se recarrega por
   JavaScript (o flash do servidor não alcança esse caso). Quem quer avisar:
     sessionStorage.setItem('fc-aviso', JSON.stringify({texto: '...', tipo: 'success'}));
   e troca de página. Aqui ele aparece no topo do conteúdo, com o X para
   fechar, e é apagado — não volta ao recarregar. */
(function () {
  let bruto = null;
  try {
    bruto = sessionStorage.getItem('fc-aviso');
    sessionStorage.removeItem('fc-aviso');
  } catch (e) { return; }
  if (!bruto) return;
  let aviso = null;
  try { aviso = JSON.parse(bruto); } catch (e) { return; }
  const texto = aviso && String(aviso.texto || '').trim();
  const lugar = document.getElementById('fc-aviso-js');
  if (!texto || !lugar) return;
  const TIPOS = ['success', 'danger', 'warning', 'info'];
  const tipo = aviso.tipo === 'error' ? 'danger'
    : (TIPOS.includes(aviso.tipo) ? aviso.tipo : 'success');
  const caixa = document.createElement('div');
  caixa.className = 'alert alert-' + tipo + ' alert-dismissible fade show';
  caixa.setAttribute('role', tipo === 'danger' ? 'alert' : 'status');
  caixa.textContent = texto;            /* texto puro: nada vira HTML */
  const fechar = document.createElement('button');
  fechar.type = 'button';
  fechar.className = 'btn-close';
  fechar.setAttribute('data-bs-dismiss', 'alert');
  fechar.setAttribute('aria-label', 'Fechar');
  caixa.appendChild(fechar);
  lugar.appendChild(caixa);
})();
/* Menu lateral no celular (gaveta): o botão "Menu" abre; o fundo escuro, o
   Esc e a escolha de um item fecham. No PC o menu fica sempre à mostra. */
(function () {
  const botao = document.querySelector('[data-menu-abrir]');
  const menu = document.getElementById('fc-lateral');
  const fundo = document.querySelector('[data-menu-fechar]');
  if (!botao || !menu || !fundo) return;
  function abrir(sim) {
    document.body.classList.toggle('fc-menu-aberto', sim);
    botao.setAttribute('aria-expanded', sim ? 'true' : 'false');
    fundo.hidden = !sim;
    if (sim) {
      const primeiro = menu.querySelector('.fc-lat-item.ativo, .fc-lat-item');
      if (primeiro) primeiro.focus();
    }
  }
  botao.addEventListener('click', function () {
    abrir(!document.body.classList.contains('fc-menu-aberto'));
  });
  fundo.addEventListener('click', function () { abrir(false); });
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape' && document.body.classList.contains('fc-menu-aberto')) {
      abrir(false);
      botao.focus();
    }
  });
  menu.addEventListener('click', function (ev) {
    if (ev.target.closest('.fc-lat-item')) abrir(false);
  });
})();

