// Leitor de QR do aplicativo de campo.
//
// A câmera de trás abre na própria página (getUserMedia). Cada quadro vai
// para o BarcodeDetector do navegador, quando existe (Chrome do Android), ou
// para o jsQR (static/vendor/jsqr), que funciona em qualquer navegador —
// inclusive no Safari do iPhone.
//
// Só abre QR DO PRÓPRIO SISTEMA: o endereço lido precisa ser deste site e
// do caminho /q/<código>. Um QR qualquer colado na parede (propaganda, golpe)
// não leva o celular do posto para fora daqui.
(function () {
  var caixa = document.getElementById('fc-leitor');
  if (!caixa) return;
  var video = document.getElementById('fc-leitor-video');
  var canvas = document.getElementById('fc-leitor-canvas');
  var msg = document.getElementById('fc-leitor-msg');
  var tentar = document.getElementById('fc-leitor-tentar');
  var form = document.getElementById('fc-leitor-form');
  var campo = document.getElementById('fc-leitor-codigo');
  var fluxo = null;
  var detector = null;
  var lendo = false;
  var CODIGO = /^[A-Za-z0-9_-]{8,32}$/;

  function dizer(texto) { msg.textContent = texto; }

  // O destino do QR, ou null se o QR não for deste sistema.
  function destino(texto) {
    var url;
    try { url = new URL(String(texto || '').trim(), location.href); } catch (e) { return null; }
    if (url.origin !== location.origin) return null;
    var m = /^\/q\/([A-Za-z0-9_-]{8,32})\/?$/.exec(url.pathname);
    return m ? '/q/' + m[1] : null;
  }
  window.TrinoLeitorQR = { destino: destino };

  function abrir(texto) {
    var alvo = destino(texto);
    if (!alvo) {
      dizer('Este QR não é do Trino Facilities. Procure a etiqueta do local.');
      return false;
    }
    parar();
    dizer('QR lido. Abrindo…');
    if (navigator.vibrate) { try { navigator.vibrate(80); } catch (e) {} }
    // No aplicativo, o QR abre o turno já no ponto lido: essa tela tem cópia
    // no aparelho e funciona também sem sinal.
    location.assign('/app/turno?ponto=' + encodeURIComponent(alvo.slice(3)));
    return true;
  }

  function parar() {
    lendo = false;
    if (fluxo) { fluxo.getTracks().forEach(function (t) { t.stop(); }); fluxo = null; }
  }

  function quadro() {
    if (!lendo) return;
    if (video.readyState < 2) { requestAnimationFrame(quadro); return; }
    if (detector) {
      detector.detect(video).then(function (achados) {
        if (achados.length && abrir(achados[0].rawValue)) return;
        setTimeout(quadro, 150);
      }).catch(function () { detector = null; setTimeout(quadro, 150); });
      return;
    }
    if (!window.jsQR) { dizer('O leitor não carregou. Digite o código da etiqueta abaixo.'); return; }
    var w = video.videoWidth, h = video.videoHeight;
    var escala = Math.min(1, 640 / Math.max(w, h));
    canvas.width = Math.round(w * escala);
    canvas.height = Math.round(h * escala);
    var ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    var img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    var achado = window.jsQR(img.data, img.width, img.height, { inversionAttempts: 'dontInvert' });
    if (achado && abrir(achado.data)) return;
    setTimeout(quadro, 120);
  }

  function iniciar() {
    tentar.hidden = true;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      dizer('Este navegador não abre a câmera. Digite o código da etiqueta abaixo.');
      return;
    }
    dizer('Abrindo a câmera…');
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
      .then(function (s) {
        fluxo = s;
        video.srcObject = s;
        return video.play();
      })
      .then(function () {
        if ('BarcodeDetector' in window) {
          try { detector = new window.BarcodeDetector({ formats: ['qr_code'] }); }
          catch (e) { detector = null; }
        }
        lendo = true;
        dizer('Aponte para o QR. A leitura é automática.');
        quadro();
      })
      .catch(function (erro) {
        parar();
        tentar.hidden = false;
        dizer(erro && erro.name === 'NotAllowedError'
          ? 'O celular não deixou usar a câmera. Libere a câmera para este site nas configurações do navegador, ou digite o código abaixo.'
          : 'Não foi possível abrir a câmera. Tente de novo ou digite o código abaixo.');
      });
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    var bruto = (campo.value || '').trim();
    if (CODIGO.test(bruto)) { abrir(location.origin + '/q/' + bruto); return; }
    if (!abrir(bruto)) { dizer('Código inválido. Confira as letras embaixo do QR.'); }
  });
  tentar.addEventListener('click', iniciar);
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { parar(); } else if (!fluxo) { iniciar(); }
  });
  window.addEventListener('pagehide', parar);
  iniciar();
})();
