// Registra o service worker do app instalável (ver static/pwa/sw.js).
// Arquivo estático: não passa pelo Jinja, então o endereço é literal.
(function () {
  // Na tela de login ninguém está dentro do sistema: as telas guardadas para
  // abrir sem internet (a passagem de quem estava aqui antes)
  // saem do aparelho. Cobre também a sessão que venceu sem ninguém clicar em
  // "Sair". O que foi escrito sem sinal NÃO mora nesse cache — está na fila
  // do aparelho e continua lá (ver static/js/fila-offline.js).
  if (/^\/login(\/|$)/.test(location.pathname) && window.caches && caches.delete) {
    caches.delete('trino-telas').catch(function () {});
  }
  vigiarVersao();
  if (!('serviceWorker' in navigator)) return;
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {
      // Sem service worker o sistema funciona igual, só não mostra a página
      // "Sem conexão". Não há o que avisar ao usuário.
    });
  });

  // ── Versão nova do sistema ─────────────────────────────────────────────
  // A tela sabe com que versão foi montada (<meta name="app-versao">) e
  // pergunta ao servidor qual está no ar (/app/versao): ao abrir, a cada 5
  // minutos com a tela à vista, ao voltar para o app e ao voltar o sinal.
  // Mudou → a faixa "Nova versão do sistema" com o botão "Atualizar".
  //
  // Nunca atualiza sozinho: a pessoa pode estar no meio de uma passagem de
  // turno. Se há algo digitado e não enviado, o botão pergunta antes. O que
  // está guardado na fila do aparelho (sem internet) não é tocado.
  function vigiarVersao() {
    var meta = document.querySelector('meta[name="app-versao"]');
    var minha = meta && meta.content;
    if (!minha || !window.fetch) return;
    var digitado = false;
    document.addEventListener('input', function () { digitado = true; }, true);
    document.addEventListener('submit', function () { digitado = false; }, true);

    function conferir() {
      if (document.hidden || navigator.onLine === false) return;
      if (document.getElementById('faixaVersao')) return;
      fetch('/app/versao', { cache: 'no-store', credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) {
          if (d && d.versao && d.versao !== minha) mostrar();
        })
        .catch(function () {});
    }

    function mostrar() {
      if (document.getElementById('faixaVersao') || !document.body) return;
      var faixa = document.createElement('div');
      faixa.id = 'faixaVersao';
      faixa.className = 'faixa-versao';
      faixa.setAttribute('role', 'status');
      faixa.setAttribute('data-testid', 'aviso-de-nova-versao');
      faixa.innerHTML =
        '<strong>Nova versão do sistema disponível.</strong>' +
        '<span class="faixa-versao-botoes">' +
        '<button type="button" class="faixa-versao-nao">Agora não</button>' +
        '<button type="button" class="faixa-versao-sim">Atualizar</button>' +
        '</span>';
      faixa.querySelector('.faixa-versao-nao').addEventListener('click', function () {
        // Volta na próxima conferência: a versão velha continua velha.
        faixa.remove();
      });
      faixa.querySelector('.faixa-versao-sim').addEventListener('click', function () {
        atualizar(this);
      });
      document.body.appendChild(faixa);
    }

    function atualizar(botao) {
      if (navigator.onLine === false) {
        botao.textContent = 'Sem conexão agora';
        return;
      }
      if (digitado && !window.confirm(
        'Há algo digitado nesta tela que ainda não foi salvo. Atualizar agora ' +
        'recarrega a tela e o que não foi salvo se perde. Atualizar mesmo assim?')) {
        return;
      }
      botao.disabled = true;
      botao.textContent = 'Atualizando…';
      var passos = [];
      if ('serviceWorker' in navigator) {
        passos.push(navigator.serviceWorker.getRegistration()
          .then(function (reg) { return reg && reg.update(); })
          .catch(function () {}));
      }
      // As cópias de tela e de CSS/JS guardadas para abrir sem internet são
      // da versão velha: saem, e a tela atual volta a ser guardada ao abrir.
      // A fila de envios (IndexedDB) não é cache e fica onde está.
      if (window.caches && caches.keys) {
        passos.push(caches.keys().then(function (nomes) {
          return Promise.all(nomes.filter(function (n) {
            return n === 'trino-telas' || n.indexOf('trino-estaticos') === 0;
          }).map(function (n) { return caches.delete(n); }));
        }).catch(function () {}));
      }
      Promise.all(passos).then(function () {
        digitado = false;          // a pessoa já confirmou
        location.reload();
      });
    }

    setInterval(conferir, 5 * 60 * 1000);
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) conferir();
    });
    window.addEventListener('online', conferir);
    window.addEventListener('load', function () { setTimeout(conferir, 2000); });
  }
})();
