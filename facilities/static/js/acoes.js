/* As ações das telas sem JavaScript embutido no HTML (Fase 9A: CSP sem
   'unsafe-inline'). Em vez de atributo de evento no HTML, a tela marca o elemento:

     data-auto-enviar            <select> que envia o formulário ao mudar
     data-ir-para="/x?id="       <select> que leva a /x?id=<valor> ao mudar
     data-voltar                 botão "voltar à tela anterior"
     data-recarregar             botão que recarrega a página
     data-remover="seletor"      botão que remove o ancestral mais próximo
     data-confirmar="texto"      <form> que pede confirmação antes de enviar
                                 ({nome} vira o data-nome do formulário)
     data-sem-envio              <form> que nunca envia (a tela usa fetch)
     data-acao="nome"            chama a função REGISTRADA em FC_ACOES.nome
     data-args='[1, "x"]'        os argumentos (JSON)
     data-com-elemento           passa também o próprio elemento, por último
     data-com-valor              passa o valor do campo como primeiro argumento
     data-ao-mudar="nome"        como data-acao, mas no "change"

   Só função registrada em window.FC_ACOES é chamada: texto injetado num
   atributo não consegue chamar qualquer função da página. */
(function () {
  'use strict';
  window.FC_ACOES = window.FC_ACOES || {};

  function chamar(nome, el, ev) {
    var fn = window.FC_ACOES[nome];
    if (typeof fn !== 'function') return;
    var args = [];
    if (el.hasAttribute('data-com-valor')) args.push(el.value);
    if (el.dataset.args) {
      try { args = args.concat(JSON.parse(el.dataset.args)); } catch (e) { return; }
    }
    if (el.hasAttribute('data-com-elemento')) args.push(el);
    if (ev) ev.preventDefault();
    fn.apply(null, args);
  }

  document.addEventListener('click', function (ev) {
    var el = ev.target.closest('[data-acao], [data-voltar], [data-recarregar], [data-remover]');
    if (!el) return;
    if (el.hasAttribute('data-voltar')) { ev.preventDefault(); history.back(); return; }
    if (el.hasAttribute('data-recarregar')) { ev.preventDefault(); location.reload(); return; }
    if (el.hasAttribute('data-remover')) {
      ev.preventDefault();
      var alvo = el.closest(el.getAttribute('data-remover'));
      if (alvo) alvo.remove();
      return;
    }
    chamar(el.getAttribute('data-acao'), el, ev);
  });

  document.addEventListener('change', function (ev) {
    var el = ev.target;
    if (!el || !el.matches) return;
    if (el.matches('[data-auto-enviar]') && el.form) { el.form.submit(); return; }
    if (el.matches('[data-ir-para]')) {
      location.href = el.getAttribute('data-ir-para') + encodeURIComponent(el.value);
      return;
    }
    if (el.matches('[data-ao-mudar]')) chamar(el.getAttribute('data-ao-mudar'), el, null);
  });

  document.addEventListener('submit', function (ev) {
    var f = ev.target;
    if (!f || !f.matches) return;
    if (f.matches('[data-sem-envio]')) { ev.preventDefault(); return; }
    if (f.matches('[data-confirmar]')) {
      var texto = f.getAttribute('data-confirmar').replace('{nome}', f.dataset.nome || '');
      if (!window.confirm(texto)) ev.preventDefault();
    }
  });
})();
