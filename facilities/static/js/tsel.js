/* O select padrão do sistema — e a opção de incluir, que faltava.
 *
 * ATENÇÃO: arquivo SERVIDO COMO ESTÁTICO, nunca passa pelo Jinja. Toda URL
 * aqui é literal.
 *
 * O PROBLEMA. Metade das listas do sistema era fechada e a outra metade era
 * texto livre, e as duas metades erravam pelo mesmo motivo. Na lista fechada,
 * incluir um tipo novo significava sair da tela, achar o cadastro e voltar —
 * no meio de uma passagem de turno, ninguém faz isso. No texto livre, o
 * encarregado digitava, e em três meses "avaria", "Avaria" e "avarias" eram
 * três tipos diferentes: nenhum relatório fecha em cima disso.
 *
 * A REGRA. Toda lista de opções tem a mesma última linha — "＋ incluir…" — e
 * ela abre um campo ali mesmo, sem sair da tela. O que foi digitado vira uma
 * opção de verdade do próprio select, então o formulário continua enviando um
 * campo só e o servidor não precisa saber que houve inclusão.
 *
 * Uso mínimo no template:
 *
 *   <div class="tsel" data-tsel>
 *     <label for="tipo">Tipo</label>
 *     <select class="form-select" id="tipo" name="tipo">
 *       <option value="">Escolha…</option>
 *       <option value="avaria">Avaria</option>
 *       <option value="__novo__">＋ incluir novo tipo…</option>
 *     </select>
 *   </div>
 *
 * `data-tsel-rotulo="tipo"` muda o texto do campo que abre ("Novo tipo").
 */
(function () {
  'use strict';

  var MARCA = '__novo__';

  function campoDe(caixa, select) {
    var ja = caixa.querySelector('.tsel-novo');
    if (ja) { return ja; }

    var rotulo = caixa.dataset.tselRotulo || 'item';
    var linha = document.createElement('div');
    linha.className = 'tsel-novo';

    var texto = document.createElement('input');
    texto.type = 'text';
    texto.className = 'form-control form-control-sm';
    texto.placeholder = 'Novo ' + rotulo;
    texto.maxLength = 80;

    var ok = document.createElement('button');
    ok.type = 'button';
    ok.className = 'btn btn-sm btn-primary';
    ok.textContent = 'Incluir';

    var nao = document.createElement('button');
    nao.type = 'button';
    nao.className = 'btn btn-sm btn-light';
    nao.textContent = 'Cancelar';

    linha.appendChild(texto);
    linha.appendChild(ok);
    linha.appendChild(nao);
    caixa.appendChild(linha);

    function fechar() {
      linha.classList.remove('on');
      texto.value = '';
    }

    function incluir() {
      var v = (texto.value || '').trim();
      if (!v) { texto.focus(); return; }
      // Já existe com outra caixa? Seleciona o que existe em vez de criar um
      // gêmeo — é exatamente o "avaria" / "Avaria" que este campo veio
      // impedir.
      var iguais = [].slice.call(select.options).filter(function (o) {
        return o.value !== MARCA &&
               o.textContent.trim().toLowerCase() === v.toLowerCase();
      });
      if (iguais.length) {
        select.value = iguais[0].value;
      } else {
        var nova = document.createElement('option');
        nova.value = v;
        nova.textContent = v;
        // Antes da linha "＋ incluir…", que fica sempre por último.
        select.insertBefore(nova, select.querySelector(
          'option[value="' + MARCA + '"]'));
        select.value = v;
      }
      fechar();
      // Quem escuta o select (um filtro que recarrega, por exemplo) precisa
      // saber que o valor mudou — atribuir .value não dispara `change`.
      select.dispatchEvent(new Event('change', {bubbles: true}));
    }

    ok.addEventListener('click', incluir);
    nao.addEventListener('click', function () {
      fechar();
      select.value = caixa.dataset.tselAnterior || '';
    });
    texto.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); incluir(); }
      if (ev.key === 'Escape') { nao.click(); }
    });
    return linha;
  }

  // Delegação no documento: a tela pode montar o select depois (a passagem de
  // turno monta as atividades por JS), e um bind no carregamento perderia
  // todos eles.
  document.addEventListener('change', function (ev) {
    var select = ev.target;
    if (!select || select.tagName !== 'SELECT') { return; }
    var caixa = select.closest ? select.closest('[data-tsel]') : null;
    if (!caixa) { return; }
    if (select.value !== MARCA) {
      caixa.dataset.tselAnterior = select.value;
      return;
    }
    var linha = campoDe(caixa, select);
    linha.classList.add('on');
    linha.querySelector('input').focus();
  });
}());
