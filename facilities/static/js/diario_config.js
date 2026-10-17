/* Cadastro do modelo de passagem de turno, contrato a contrato.
 *
 * A versão da Fase 1 era meio cadastro: `editing` era sempre `configs[0]`, não
 * havia lista nem botão de novo, e o seletor de contrato não fazia nada — dava
 * para trocar o contrato na tela e salvar os dados do contrato anterior.
 *
 * Como o arquivo é SERVIDO COMO ESTÁTICO, nada de `url_for` aqui: ele nunca
 * passa pelo Jinja e viraria texto cru dentro do fetch.
 */
(function () {
  'use strict';

  var raiz = document.getElementById('diario-config-app');
  if (!raiz) { return; }

  var modelos = [];
  try { modelos = JSON.parse(raiz.dataset.configs || '[]'); } catch (e) { modelos = []; }
  var CLIENTE = Number(raiz.dataset.client || 0);
  var editando = null;   // null = modelo novo

  function esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/[&<>"']/g, function (m) {
        return {'&': '&amp;', '<': '&lt;', '>': '&gt;',
                '"': '&quot;', "'": '&#039;'}[m];
      });
  }

  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : '';
  }

  function linha(caixa, html) {
    var d = document.createElement('div');
    d.className = 'row g-2 mb-2 config-row';
    d.innerHTML = html;
    document.getElementById(caixa).appendChild(d);
    return d;
  }

  var BTN_X = '<div class="col-2"><button type="button" class="btn btn-outline-danger w-100" ' +
              'onclick="this.closest(\'.config-row\').remove()">×</button></div>';

  function addCfgShift(valor) {
    var d = linha('cfg-shifts',
      '<div class="col-10"><input class="form-control cfg-shift" placeholder="Ex.: T1"></div>' + BTN_X);
    if (valor) { d.querySelector('.cfg-shift').value = valor; }
  }

  // Uma pergunta por linha, com o tipo da RESPOSTA e as setas de ordem. A
  // ordem importa: é a sequência em que o encarregado vê as perguntas na
  // tela, e ela vai gravada dentro do próprio JSON do modelo.
  function addCfgPergunta(nome, tipo, obrigatorio) {
    var d = linha('cfg-perguntas',
      '<div class="col-5"><input class="form-control cfg-p-nome" placeholder="Ex.: O 5S da área foi feito?"></div>' +
      '<div class="col-3"><select class="form-select cfg-p-tipo">' +
        '<option value="sim_nao">Sim / Não</option>' +
        '<option value="numero">Número</option>' +
        '<option value="texto">Texto</option>' +
        '<option value="texto_longo">Texto longo</option></select></div>' +
      '<div class="col-2"><select class="form-select cfg-p-obrig">' +
        '<option value="true">Obrigatória</option>' +
        '<option value="false">Opcional</option></select></div>' +
      '<div class="col-2 d-flex gap-1">' +
        '<button type="button" class="btn btn-outline-secondary flex-fill" ' +
          'title="Subir" onclick="moverPergunta(this,-1)">↑</button>' +
        '<button type="button" class="btn btn-outline-secondary flex-fill" ' +
          'title="Descer" onclick="moverPergunta(this,1)">↓</button>' +
        '<button type="button" class="btn btn-outline-danger flex-fill" ' +
          'onclick="this.closest(\'.config-row\').remove()">×</button>' +
      '</div>');
    if (nome) { d.querySelector('.cfg-p-nome').value = nome; }
    d.querySelector('.cfg-p-tipo').value = tipo || 'sim_nao';
    d.querySelector('.cfg-p-obrig').value = String(obrigatorio !== false);
  }

  function moverPergunta(botao, passo) {
    var linha = botao.closest('.config-row');
    var alvo = passo < 0 ? linha.previousElementSibling : linha.nextElementSibling;
    if (!alvo) { return; }
    if (passo < 0) { linha.parentNode.insertBefore(linha, alvo); }
    else { linha.parentNode.insertBefore(alvo, linha); }
  }

  function addCfgOccurrence(valor) {
    var d = linha('cfg-occurrences',
      '<div class="col-10"><input class="form-control cfg-occ" placeholder="Ex.: Devolução"></div>' + BTN_X);
    if (valor) { d.querySelector('.cfg-occ').value = valor; }
  }

  // ── Abrir um modelo da lista (ou começar um novo) ─────────────────────
  function limpar() {
    ['cfg-shifts', 'cfg-perguntas', 'cfg-occurrences']
      .forEach(function (id) { document.getElementById(id).innerHTML = ''; });
    document.getElementById('cfg-name').value = '';
    document.getElementById('cfg-description').value = '';
    document.getElementById('cfg-ativo').value = 'true';
  }

  function marcarSelecionado(id) {
    document.querySelectorAll('#cfg-lista .cf-item').forEach(function (b) {
      b.classList.toggle('ativo-sel', String(b.dataset.id) === String(id));
    });
  }

  function preencher(m) {
    limpar();
    if (!m) {
      document.getElementById('cfg-editando').textContent =
        'Novo modelo — ainda não salvo.';
      document.getElementById('cfg-aviso-uso').textContent = '';
      marcarSelecionado(0);
      return;
    }
    document.getElementById('cfg-name').value = m.nome || '';
    document.getElementById('cfg-description').value = m.descricao || '';
    document.getElementById('cfg-ativo').value = String(m.ativo !== false);
    preencherAreas();
    (m.turnos || []).forEach(function (x) { addCfgShift(x.nome || x); });
    (m.perguntas || []).forEach(function (x) {
      addCfgPergunta(x.nome, x.tipo, x.obrigatorio);
    });
    (m.tipos_ocorrencia || []).forEach(function (x) { addCfgOccurrence(x.nome || x); });
    document.getElementById('cfg-editando').textContent = 'Editando: ' + (m.nome || '');
    marcarSelecionado(m.id);

    // Editar um modelo já usado NÃO reescreve o passado: cada turno guarda a
    // régua do dia em que foi encerrado. O aviso existe para que quem edita
    // saiba o que muda e o que não muda.
    // O número vem do `data-usos` da linha, não do texto dela: pescar
    // "N turno(s) lançado" com expressão regular quebrava em silêncio assim
    // que o texto da linha passou a ter o plural certo.
    var botao = document.querySelector('#cfg-lista .cf-item[data-id="' + m.id + '"]');
    var usados = botao ? Number(botao.dataset.usos || 0) : 0;
    document.getElementById('cfg-aviso-uso').textContent = usados
      ? 'Este modelo já foi usado em ' + usados +
        (usados === 1 ? ' turno' : ' turnos') + '. Alterar as rotinas ' +
        'vale dos próximos turnos em diante — os já encerrados guardam a régua ' +
        'do dia em que foram fechados.'
      : '';
  }

  function abrirModelo(id) {
    for (var i = 0; i < modelos.length; i++) {
      if (String(modelos[i].id) === String(id)) {
        editando = modelos[i];
        preencher(editando);
        return;
      }
    }
  }

  function novoModelo() {
    editando = null;
    preencher(null);
    document.getElementById('cfg-name').focus();
  }

  // ── Salvar ────────────────────────────────────────────────────────────
  function codigoDe(nome) {
    return String(nome).trim().toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
  }

  function saveConfig() {
    var nome = document.getElementById('cfg-name').value.trim();
    if (!nome) { alert('Informe o nome do modelo.'); return; }

    var turnos = [].slice.call(document.querySelectorAll('.cfg-shift'))
      .map(function (v) { return {nome: v.value.trim()}; })
      .filter(function (x) { return x.nome; });

    // A ORDEM das linhas na tela é a ordem das perguntas para o encarregado,
    // e é por isso que se percorre a linha inteira em vez de cada classe
    // separadamente: percorrer por classe perderia a intercalação entre
    // sim/não e número.
    var perguntas = [].slice.call(document.querySelectorAll('#cfg-perguntas .config-row'))
      .map(function (linha) {
        var nomeP = linha.querySelector('.cfg-p-nome').value.trim();
        return {nome: nomeP, codigo: codigoDe(nomeP),
                tipo: linha.querySelector('.cfg-p-tipo').value,
                obrigatorio: linha.querySelector('.cfg-p-obrig').value === 'true'};
      }).filter(function (x) { return x.nome; });

    var ocorrencias = [].slice.call(document.querySelectorAll('.cfg-occ'))
      .map(function (v) { return {nome: v.value.trim()}; })
      .filter(function (x) { return x.nome; });

    // Dois códigos iguais viram a MESMA linha em dados_json: a segunda
    // pergunta sobrescreveria a primeira e a aderência contaria errado.
    var vistos = {}, repetido = null;
    perguntas.forEach(function (x) {
      if (vistos[x.codigo]) { repetido = x.nome; }
      vistos[x.codigo] = true;
    });
    if (repetido) {
      alert('Há duas perguntas com o mesmo nome ("' + repetido + '"). ' +
            'Renomeie uma delas: as duas viram a mesma linha no turno.');
      return;
    }

    var corpo = {
      client_id: CLIENTE, nome: nome,
      area_id: Number(document.getElementById('cfg-area').value || 0) || null,
      descricao: document.getElementById('cfg-description').value,
      ativo: document.getElementById('cfg-ativo').value === 'true',
      turnos: turnos, perguntas: perguntas,
      tipos_ocorrencia: ocorrencias
    };
    var url = editando
      ? '/passagem-de-turno/api/configuracoes/' + editando.id
      : '/passagem-de-turno/api/configuracoes';

    fetch(url, {
      method: editando ? 'PUT' : 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
      body: JSON.stringify(corpo)
    }).then(function (r) {
      return r.json().then(function (x) { return {ok: r.ok, x: x}; });
    }).then(function (res) {
      if (!res.ok) { alert(res.x.error || 'Erro ao salvar.'); return; }
      window.location = '/passagem-de-turno/configuracao?client_id=' + CLIENTE +
                        '&editar=' + res.x.id;
    });
  }

  // ── As áreas do contrato ──────────────────────────────────────────────
  //
  // Cadastro, não campo digitado. Com vinte encarregados lançando, o nome
  // escrito à mão vira "Expedição", "expedicao" e "EXPEDIÇÃO" na mesma
  // semana — e o painel passa a mostrar três áreas onde existe uma.
  var caixaAreas = document.getElementById('cfg-areas-card');
  var areas = [];
  if (caixaAreas) {
    try { areas = JSON.parse(caixaAreas.dataset.areas || '[]'); } catch (e) { areas = []; }
  }

  // "1 modelo(s)" é a tela admitindo que não sabe contar.
  function nModelos(n) {
    n = Number(n) || 0;
    return n + (n === 1 ? ' modelo' : ' modelos');
  }

  function desenharAreas() {
    var alvo = document.getElementById('cfg-areas');
    if (!alvo) { return; }
    alvo.innerHTML = areas.length ? areas.map(function (a) {
      // As duas ações num grupo só (`.ar-acoes`): soltas na linha, cada uma
      // quebrava para um lado no celular e ficavam desalinhadas.
      return '<div class="ar-item' + (a.ativo ? '' : ' off') + '">' +
        '<span class="ar-nome">' + esc(a.nome) + '</span>' +
        '<span class="ar-meta">' + nModelos(a.modelos) + '</span>' +
        '<span class="ar-acoes">' +
        '<button type="button" class="btn btn-sm btn-link p-0" ' +
          'onclick="renomearArea(' + a.id + ')">renomear</button>' +
        '<button type="button" class="btn btn-sm btn-link p-0" ' +
          'onclick="alternarArea(' + a.id + ')">' +
          (a.ativo ? 'desativar' : 'reativar') + '</button>' +
        '</span>' +
      '</div>';
    }).join('') : '<div class="text-muted small">Nenhuma área cadastrada. ' +
                  'Sem área, o contrato tem uma passagem só.</div>';
  }

  function preencherAreas() {
    var sel = document.getElementById('cfg-area');
    if (!sel) { return; }
    var atual = editando ? String(editando.area_id || '') : sel.value;
    sel.innerHTML = '<option value="">Sem área — contrato não dividido</option>' +
      areas.filter(function (a) { return a.ativo; }).map(function (a) {
        return '<option value="' + a.id + '">' + esc(a.nome) + '</option>';
      }).join('');
    sel.value = atual || '';
  }

  function chamarArea(url, metodo, corpo) {
    return fetch(url, {
      method: metodo,
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
      body: JSON.stringify(corpo)
    }).then(function (r) {
      return r.json().then(function (x) { return {ok: r.ok, x: x}; });
    }).then(function (res) {
      if (!res.ok) { alert(res.x.error || 'Não foi possível salvar a área.'); return; }
      window.location.reload();
    }).catch(function () { alert('Falha de rede.'); });
  }

  window.novaArea = function () {
    var nome = prompt('Nome da área (ex.: Expedição, Almoxarifado, CD):');
    if (nome === null) { return; }
    nome = nome.trim();
    if (!nome) { return; }
    chamarArea('/passagem-de-turno/api/areas', 'POST',
               {client_id: CLIENTE, nome: nome});
  };

  window.renomearArea = function (id) {
    var atual = '';
    areas.forEach(function (a) { if (a.id === id) { atual = a.nome; } });
    var nome = prompt('Novo nome da área:', atual);
    if (nome === null) { return; }
    nome = nome.trim();
    if (!nome || nome === atual) { return; }
    chamarArea('/passagem-de-turno/api/areas/' + id, 'PUT', {nome: nome});
  };

  window.alternarArea = function (id) {
    var alvo = null;
    areas.forEach(function (a) { if (a.id === id) { alvo = a; } });
    if (!alvo) { return; }
    // Desativar NÃO apaga: a área some dos seletores e continua amparando as
    // passagens já lançadas por ela.
    if (alvo.ativo && alvo.modelos &&
        !confirm('A área "' + alvo.nome + '" ampara ' + nModelos(alvo.modelos) +
                 '. Desativar esconde a área de quem lança; o que ' +
                 'já foi lançado continua no histórico. Continuar?')) {
      return;
    }
    chamarArea('/passagem-de-turno/api/areas/' + id, 'PUT', {ativo: !alvo.ativo});
  };

  desenharAreas();
  preencherAreas();

  window.addCfgShift = addCfgShift;
  window.addCfgPergunta = addCfgPergunta;
  window.moverPergunta = moverPergunta;
  window.addCfgOccurrence = addCfgOccurrence;
  window.saveConfig = saveConfig;
  window.abrirModelo = abrirModelo;
  window.novoModelo = novoModelo;

  // Abre o modelo pedido pela URL (volta do salvar), ou o primeiro da lista.
  var pedido = Number(raiz.dataset.editar || 0);
  if (pedido) { abrirModelo(pedido); }
  else if (modelos.length) { abrirModelo(modelos[0].id); }
  else { preencher(null); }
}());
