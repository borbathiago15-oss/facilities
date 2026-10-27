// Posição do local (GPS na leitura do QR, 27/10/2026): a gestão, DENTRO do
// local, toca em "Marcar a posição deste local"; o celular dá a posição e o
// formulário é enviado com ela. Sem permissão ou sem GPS, diz o que fazer.
(function () {
  'use strict';
  var form = document.querySelector('[data-form-posicao]');
  if (!form) return;
  var botao = form.querySelector('[data-marcar-posicao]');
  var estado = document.querySelector('[data-posicao-estado]');
  function dizer(t) { if (estado) estado.textContent = t; }
  botao.addEventListener('click', function () {
    if (!navigator.geolocation) { dizer('Este aparelho não informa a localização.'); return; }
    botao.disabled = true;
    dizer('Pegando a posição do celular…');
    navigator.geolocation.getCurrentPosition(function (pos) {
      form.querySelector('[name=lat]').value = pos.coords.latitude;
      form.querySelector('[name=lng]').value = pos.coords.longitude;
      form.querySelector('[name=precisao]').value = Math.round(pos.coords.accuracy || 0);
      dizer('Posição encontrada (precisão de ' + Math.round(pos.coords.accuracy || 0) + ' m). Salvando…');
      form.submit();
    }, function (e) {
      botao.disabled = false;
      dizer(e && e.code === 1
        ? 'O celular não deixou usar a localização. Libere a localização para este site e tente de novo.'
        : 'Não foi possível pegar a posição. Vá para perto de uma janela ou área aberta e tente de novo.');
    }, {enableHighAccuracy: true, timeout: 20000, maximumAge: 0});
  });
})();
