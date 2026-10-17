// Aplicativo de campo: o aviso "Sem sinal", o pedido de presença e o botão
// de avisos no celular.
//
// Sem sinal o aplicativo continua funcionando: a passagem e o turno abrem da
// cópia guardada e o que a pessoa lança fica na fila do aparelho
// (fila-offline.js), que sobe sozinha quando o sinal volta.
(function () {
  var selo = document.getElementById('fc-app-rede');
  if (selo) {
    var atualizar = function () { selo.hidden = navigator.onLine !== false; };
    window.addEventListener('online', atualizar);
    window.addEventListener('offline', atualizar);
    atualizar();
  }

  // ── Presença (D48): pergunta ao servidor a cada minuto com a tela à vista.
  // O aviso no celular também chega, mas quem está com o app aberto vê aqui.
  var faixa = document.getElementById('fc-presenca');
  function perguntar() {
    if (!faixa || document.hidden || navigator.onLine === false) return;
    fetch('/app/api/presenca', {credentials: 'same-origin'})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (x) { mostrar(x && x.pedido); })
      .catch(function () {});
  }
  function mostrar(p) {
    while (faixa.firstChild) faixa.removeChild(faixa.firstChild);
    faixa.hidden = !p;
    if (!p) return;
    var texto = document.createElement('div');
    texto.className = 'fw-semibold mb-2';
    texto.textContent = 'Confirme que você está no posto (até ' + p.ate + ').';
    var botao = document.createElement('button');
    botao.type = 'button';
    botao.className = 'btn btn-light btn-lg w-100 fw-bold';
    botao.textContent = 'Estou no posto';
    botao.addEventListener('click', function () {
      botao.disabled = true;
      fetch('/app/api/presenca/' + p.id, {method: 'POST', credentials: 'same-origin'})
        .then(function (r) { return r.json().then(function (x) { return {ok: r.ok, x: x}; }); })
        .then(function (res) {
          while (faixa.firstChild) faixa.removeChild(faixa.firstChild);
          var ok = document.createElement('div');
          ok.className = 'fw-semibold';
          ok.textContent = res.ok ? res.x.mensagem : (res.x.error || 'Não foi possível confirmar.');
          faixa.appendChild(ok);
          setTimeout(perguntar, 4000);
        }, function () {
          botao.disabled = false;
          texto.textContent = 'Sem sinal: a confirmação precisa de internet. Tente de novo.';
        });
    });
    faixa.appendChild(texto);
    faixa.appendChild(botao);
  }
  if (faixa) {
    perguntar();
    setInterval(perguntar, 60000);
    document.addEventListener('visibilitychange', perguntar);
  }

  // ── Avisos no celular (Web Push) ─────────────────────────────────────
  var botaoAvisos = document.getElementById('fc-ativar-avisos');
  if (!botaoAvisos) return;
  var suporta = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  var estado = document.getElementById('fc-avisos-estado');
  function dizer(t) { if (estado) estado.textContent = t; }
  function deBase64(s) {
    var pad = '='.repeat((4 - s.length % 4) % 4);
    var bruto = atob((s + pad).replace(/-/g, '+').replace(/_/g, '/'));
    var out = new Uint8Array(bruto.length);
    for (var i = 0; i < bruto.length; i++) out[i] = bruto.charCodeAt(i);
    return out;
  }
  function inscrever(chave) {
    return navigator.serviceWorker.ready.then(function (reg) {
      return reg.pushManager.getSubscription().then(function (atual) {
        return atual || reg.pushManager.subscribe({userVisibleOnly: true,
                                                   applicationServerKey: deBase64(chave)});
      });
    }).then(function (insc) {
      return fetch('/app/api/push', {method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(insc.toJSON())});
    });
  }
  if (!suporta) {
    botaoAvisos.hidden = true;
    dizer('Este navegador não recebe avisos. No iPhone, instale o aplicativo na Tela de Início primeiro.');
    return;
  }
  fetch('/app/api/push/chave', {credentials: 'same-origin'})
    .then(function (r) { return r.json(); })
    .then(function (x) {
      if (!x.chave) { botaoAvisos.hidden = true; dizer('Os avisos no celular ainda não foram ligados no sistema.'); return; }
      // Já autorizado neste aparelho: renova a inscrição em nome de quem está
      // logado (celular compartilhado: o aviso vai para quem está usando).
      if (Notification.permission === 'granted') {
        botaoAvisos.hidden = true;
        dizer('Avisos ligados neste celular.');
        inscrever(x.chave).catch(function () {});
        return;
      }
      if (Notification.permission === 'denied') {
        botaoAvisos.hidden = true;
        dizer('Os avisos estão bloqueados nas configurações do navegador para este site.');
        return;
      }
      botaoAvisos.addEventListener('click', function () {
        Notification.requestPermission().then(function (p) {
          if (p !== 'granted') { dizer('Sem permissão, o aplicativo não consegue avisar.'); return; }
          return inscrever(x.chave).then(function () {
            botaoAvisos.hidden = true;
            dizer('Pronto: você vai receber os avisos da rota e da presença.');
          });
        }).catch(function () { dizer('Não foi possível ligar os avisos. Tente de novo.'); });
      });
    }).catch(function () {});
})();
