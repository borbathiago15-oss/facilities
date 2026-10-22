// A página pública do QR (sem login), passo a passo no celular:
//   "É aqui?" → o que está acontecendo (itens do checklist) → foto → enviar.
// Sem JavaScript o formulário inteiro aparece de uma vez e funciona igual.
(function () {
  'use strict';
  var form = document.querySelector('[data-passos]');
  if (!form) return;
  var passos = [].slice.call(form.querySelectorAll('.fc-qr-passo'));
  var atual = 0;

  function mostrar(n) {
    atual = n;
    passos.forEach(function (p, i) { p.hidden = i !== n; });
    window.scrollTo(0, 0);
    var foco = passos[n].querySelector('h1, h2');
    if (foco) { foco.setAttribute('tabindex', '-1'); foco.focus(); }
  }

  function problemaOk() {
    var marcado = form.querySelector('[name=itens]:checked, [name=tipo]:checked');
    var texto = form.querySelector('[name=texto]');
    return !!(marcado || (texto && texto.value.trim()));
  }

  form.querySelectorAll('[data-proximo]').forEach(function (b) {
    b.addEventListener('click', function () {
      var passo = passos[atual].getAttribute('data-passo');
      if (passo === 'problema') {
        var erro = form.querySelector('[data-erro-problema]');
        if (!problemaOk()) { erro.hidden = false; return; }
        erro.hidden = true;
      }
      mostrar(Math.min(atual + 1, passos.length - 1));
    });
  });
  var voltar = form.querySelector('[data-voltar-pagina]');
  if (voltar) {
    voltar.addEventListener('click', function () {
      if (history.length > 1) history.back(); else location.assign('/');
    });
  }
  // O check visual do item (quadrado → quadrado marcado).
  form.querySelectorAll('.fc-qr-item input').forEach(function (c) {
    c.addEventListener('change', function () {
      var i = c.parentNode.querySelector('i');
      if (i) i.className = c.checked ? 'bi bi-check-square-fill' : 'bi bi-square';
    });
  });
  var foto = form.querySelector('[name=foto]');
  var estado = form.querySelector('[data-foto-estado]');
  if (foto && estado) {
    foto.addEventListener('change', function () {
      estado.textContent = foto.files.length ? 'Foto pronta.' : 'Nenhuma foto.';
    });
  }
  // Marcou ou escreveu algo: o aviso de "marque o que está acontecendo" some.
  form.addEventListener('change', function () { if (problemaOk()) form.querySelector('[data-erro-problema]').hidden = true; });
  form.addEventListener('input', function () { if (problemaOk()) form.querySelector('[data-erro-problema]').hidden = true; });
  form.addEventListener('submit', function (ev) {
    if (!problemaOk()) { ev.preventDefault(); mostrar(1); form.querySelector('[data-erro-problema]').hidden = false; }
  });
  mostrar(0);
})();
