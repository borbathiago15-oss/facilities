/* Passagem de turno — a tela que o encarregado preenche no fim do expediente.
 *
 * Quem usa isto é colaborador de piso, muitas vezes no celular, com pressa e
 * às vezes com luva. Daí as escolhas daqui: um alvo de toque grande por
 * atividade, nenhuma pergunta que o sistema já saiba responder, e o erro dito
 * em português no lugar onde aconteceu.
 *
 * ATENÇÃO: este arquivo é SERVIDO COMO ESTÁTICO e nunca passa pelo Jinja. Um
 * `url_for` aqui vira o texto cru dentro do fetch — foi exatamente assim que
 * a Fase 1 ficou sem salvar turno nenhum. Toda URL aqui é literal.
 */
(function () {
  'use strict';

  var raiz = document.getElementById('diario-turno-app');
  if (!raiz) { return; }

  var configs = [];
  try { configs = JSON.parse(raiz.dataset.configs || '[]'); } catch (e) { configs = []; }
  var selConfig = document.getElementById('diario-config');
  var configAtual = null;

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

  function chaveDe(item) {
    return item.codigo || item.nome || String(item);
  }

  // ── Desenho das perguntas a partir do modelo do contrato ──────────────
  //
  // Uma pergunta por cartão, na ordem do modelo. Para quem preenche não
  // existe "atividade" e "campo": existe a pergunta e a resposta. O que muda
  // é o TIPO da resposta — sim/não, número ou texto —, e é só isso que o
  // cartão decide aqui.
  function cartaoPergunta(p, i) {
    var chave = esc(chaveDe(p));
    var tipo = p.tipo || 'sim_nao';
    var marca = p.obrigatorio ? ' <span class="obrig">*</span>' : '';
    var corpo;

    if (tipo === 'sim_nao') {
      corpo =
        '<div class="form-check form-switch dt-switch">' +
          '<input class="form-check-input diario-activity" type="checkbox" ' +
                 'id="p-' + i + '" data-key="' + chave + '">' +
          '<label class="form-check-label" for="p-' + i + '">Concluído</label>' +
        '</div>' +
        '<textarea class="form-control mt-2 diario-activity-note" ' +
                  'data-key="' + chave + '" rows="2" ' +
                  'placeholder="Observação (o que houve, se não foi feito)"></textarea>';
    } else if (tipo === 'numero') {
      corpo = '<input type="number" inputmode="numeric" class="form-control diario-field" ' +
              'data-key="' + chave + '">';
    } else if (tipo === 'texto_longo') {
      corpo = '<textarea class="form-control diario-field" rows="3" data-key="' + chave + '"></textarea>';
    } else if (tipo === 'escolha') {
      // O semáforo do recado de WhatsApp: 🟢 NORMAL / 🟡 ATENÇÃO / 🔴 CRÍTICO.
      // Botões, não lista suspensa: no celular, escolher entre três estados
      // é um toque, e a resposta fica VISÍVEL sem abrir nada.
      corpo = '<div class="dt-opcoes" data-key="' + chave + '">' +
        (p.opcoes || []).map(function (o) {
          return '<button type="button" class="dt-opcao" ' +
                 'data-valor="' + esc(o) + '">' + esc(o) + '</button>';
        }).join('') +
        '<input type="hidden" class="diario-field" data-key="' + chave + '">' +
      '</div>';
    } else {
      corpo = '<input type="text" class="form-control diario-field" data-key="' + chave + '">';
    }

    return '' +
      '<div class="dt-p dt-atividade">' +
        '<span class="dt-p-nome">' + esc(p.nome) + marca + '</span>' +
        corpo +
        botoesDeAnexo(chave) +
      '</div>';
  }

  // Dois botões, porque são dois gestos diferentes: "Tirar foto" abre a
  // câmera direto (o encarregado está de pé no corredor, não na mesa), e
  // "Anexar arquivo" abre a galeria ou os documentos — a foto já tirada, o
  // PDF da NF. Um botão só com a câmera forçada impedia o PDF; um botão só
  // sem ela custava dois toques a mais em toda foto.
  function botoesDeAnexo(chave) {
    return '<div class="dt-anexos mt-2">' +
        '<label class="dt-anexo">' +
          '<i class="bi bi-camera"></i> Tirar foto' +
          '<input type="file" class="diario-activity-file" data-key="' + chave + '" ' +
                 'accept="image/*" capture="environment" hidden>' +
        '</label> ' +
        '<label class="dt-anexo">' +
          '<i class="bi bi-paperclip"></i> Anexar arquivo' +
          '<input type="file" class="diario-activity-file" data-key="' + chave + '" ' +
                 'accept="image/*,application/pdf" multiple hidden>' +
        '</label>' +
        '<div class="dt-escolhidos small text-muted mt-1"></div>' +
      '</div>';
  }

  function perguntasDe(cfg) {
    // O servidor já manda a lista única; o par antigo é lido como reserva
    // para quem tiver payload de antes desta mudança em cache.
    if (cfg.perguntas && cfg.perguntas.length) { return cfg.perguntas; }
    var fora = (cfg.atividades || []).map(function (a) {
      return {nome: a.nome || a, codigo: a.codigo || a.nome || a,
              tipo: 'sim_nao', obrigatorio: a.obrigatorio !== false};
    });
    return fora.concat((cfg.campos || []).map(function (c) {
      return {nome: c.nome, codigo: c.codigo || c.nome,
              tipo: c.tipo || 'texto', obrigatorio: c.obrigatorio === true};
    }));
  }

  // A ÁREA manda no resto da tela: um contrato tem várias, e as perguntas,
  // os turnos e os tipos de ocorrência são do modelo DAQUELA área.
  function areaEscolhida() {
    var el = document.getElementById('diario-area');
    return el ? String(el.value || '') : '';
  }

  function modelosDaArea() {
    var area = areaEscolhida();
    if (!area) { return configs; }
    // "Geral (sem área)": os modelos sem área num contrato que já tem áreas
    // (AREA_SEM_CADASTRO no servidor). O area_id que chega já é o efetivo —
    // o modelo de área desativada vem sem área.
    if (area === 'sem-area') {
      return configs.filter(function (c) { return !c.area_id; });
    }
    var so = configs.filter(function (c) {
      return String(c.area_id || '') === area;
    });
    // Contrato sem área cadastrada (ou modelo antigo, sem área) continua
    // vendo os seus modelos: a área é uma divisão nova, não um requisito
    // retroativo.
    return so.length ? so : configs.filter(function (c) { return !c.area_id; });
  }

  function nomesDeTurno(cfg) {
    return (cfg.turnos || []).map(function (x) {
      return (x && x.nome) || String(x);
    }).filter(Boolean);
  }

  // Os turnos de TODA a área, sem repetir e na ordem em que os modelos os
  // declaram. É a união porque cada turno pode ter o SEU modelo: no CD de
  // Simões Filho o T1 registra formulários Q e retrabalho, o T2 registra
  // volumes de OT/PVV/DTS, e o T3 registra carretas em fila e hora de fim de
  // expediente. Três conjuntos de perguntas diferentes, um por turno.
  function turnosDaArea() {
    var vistos = {}, fora = [];
    modelosDaArea().forEach(function (c) {
      nomesDeTurno(c).forEach(function (n) {
        if (!vistos[n]) { vistos[n] = true; fora.push(n); }
      });
    });
    return fora;
  }

  // O modelo é CONSEQUÊNCIA de área + turno, não uma terceira escolha. Quem
  // lança pensa "sou do CD, T2" — e não deve precisar saber que existe um
  // objeto chamado modelo por trás disso.
  function modeloDe(area, turno) {
    var lista = modelosDaArea();
    for (var i = 0; i < lista.length; i++) {
      if (nomesDeTurno(lista[i]).indexOf(turno) !== -1) { return lista[i]; }
    }
    return lista[0] || null;
  }

  // Os turnos que JÁ foram encerrados, por modelo e por data — o servidor
  // manda (``_turnos_ja_encerrados``). Sem isto a tela abria sempre no 1º
  // turno do modelo, e o encarregado do 2º preenchia a passagem inteira num
  // turno que o colega já tinha fechado: o envio terminava em 409.
  var encerrados = {};
  try {
    var dadosEncerrados = document.getElementById('dt-turnos-encerrados');
    encerrados = JSON.parse((dadosEncerrados && dadosEncerrados.textContent) || '{}') || {};
  } catch (e) { encerrados = {}; }

  function jaEncerrado(turno) {
    var dia = document.getElementById('diario-date');
    var cfg = modeloDe(areaEscolhida(), turno);
    if (!cfg || !dia || !dia.value) { return false; }
    var doDia = (encerrados[String(cfg.id)] || {})[dia.value] || [];
    return doDia.indexOf(turno) !== -1;
  }

  // O primeiro turno da área que ainda está em aberto naquela data. Com
  // todos encerrados, fica o 1º — a tela não tem um "turno nenhum" a
  // oferecer, e o servidor continua sendo quem recusa.
  function primeiroEmAberto(disponiveis) {
    for (var i = 0; i < disponiveis.length; i++) {
      if (!jaEncerrado(disponiveis[i])) { return disponiveis[i]; }
    }
    return disponiveis[0];
  }

  // A mesma regra de ``_chave_da_area`` no servidor: a área do modelo, ou a
  // área "do contrato" quando o modelo não tem área — a tela oferece esses
  // modelos juntos e escolhe o modelo pelo turno.
  function chaveDaArea(cfg) {
    if (!cfg) { return ''; }
    return cfg.area_id ? 'area-' + cfg.area_id : 'contrato-0';
  }

  // "O turno anterior deixou" vem um bloco por área; fica à vista só o da
  // área do modelo em uso. Segue o MODELO, e não só o seletor de área:
  // no contrato sem área cadastrada não há seletor, e todos os modelos são
  // da área "do contrato" (chaveDaArea).
  function mostrarAnterior() {
    var chave = chaveDaArea(configAtual);
    document.querySelectorAll('.dt-anterior[data-area]').forEach(function (b) {
      b.hidden = b.dataset.area !== chave;
    });
  }

  // Quem trocou o turno à mão. A escolha dele sobrevive à troca de área ou
  // de data enquanto o turno existir na área e continuar em aberto — trocar
  // de área não pode zerar a escolha de quem já mexeu no campo; mas, se o
  // turno escolhido já está encerrado na data nova, mantê-lo só levaria ao
  // 409 no envio.
  var turnoAMao = false;
  // O modelo cujas perguntas estão desenhadas. Redesenhar o mesmo modelo
  // apagaria o que já foi respondido — e agora a troca de DATA também passa
  // por aqui.
  var desenhadoPara = null;

  function desenhar(preSelecionar) {
    var turnos = document.getElementById('diario-shift');
    var campos = document.getElementById('diario-fields');
    var disponiveis = turnosDaArea();

    if (!disponiveis.length) {
      configAtual = modelosDaArea()[0] || null;
      mostrarAnterior();
      desenhadoPara = null;
      if (turnos) { turnos.innerHTML = ''; }
      if (campos) {
        campos.innerHTML = '<div class="alert alert-warning">' +
          'Esta área ainda não tem um modelo de passagem cadastrado. ' +
          'Peça ao Master para cadastrar em <strong>Configurar</strong>.</div>';
      }
      return;
    }

    var atual = turnos ? turnos.value : '';
    var existe = disponiveis.indexOf(atual) !== -1;
    var escolhido;
    if (!preSelecionar && existe) {
      escolhido = atual;               // a própria pessoa acabou de escolher
    } else if (turnoAMao && existe && !jaEncerrado(atual)) {
      escolhido = atual;
    } else {
      escolhido = primeiroEmAberto(disponiveis);
    }
    // O turno já encerrado continua na lista (pode haver motivo para abri-lo
    // e o servidor é quem decide), mas diz que está fechado.
    turnos.innerHTML = disponiveis.map(function (n) {
      return '<option value="' + esc(n) + '"' +
             (n === escolhido ? ' selected' : '') + '>' + esc(n) +
             (jaEncerrado(n) ? ' — já encerrado' : '') + '</option>';
    }).join('');

    configAtual = modeloDe(areaEscolhida(), escolhido);
    if (selConfig) { selConfig.value = configAtual ? configAtual.id : ''; }
    mostrarAnterior();

    var id = configAtual ? configAtual.id : '';
    if (desenhadoPara === id) { return; }
    desenhadoPara = id;
    var lista = configAtual ? perguntasDe(configAtual) : [];
    campos.innerHTML = lista.length
      ? lista.map(cartaoPergunta).join('')
      : '<div class="dt-vazio">Este turno ainda não tem perguntas cadastradas.</div>';
  }

  // O seletor de modelo vira campo oculto: ele ainda é o que o servidor
  // recebe (``configuracao_id``), mas deixou de ser uma pergunta para quem
  // lança — área e turno já o determinam.
  function preencherModelos() {
    if (!selConfig) { return; }
    selConfig.innerHTML = configs.map(function (c) {
      return '<option value="' + c.id + '">' + esc(c.nome) + '</option>';
    }).join('');
    var caixa = selConfig.closest('div');
    if (caixa) { caixa.hidden = true; }
  }

  if (selConfig) { preencherModelos(); }
  var selTurno = document.getElementById('diario-shift');
  if (selTurno) {
    selTurno.addEventListener('change', function () {
      turnoAMao = true;
      desenhar(false);
    });
  }
  // Trocar de área refaz a tela inteira: modelos, turnos e perguntas são
  // daquela área. Sem isto, escolher "Almoxarifado" deixaria as perguntas da
  // Expedição na tela — e a passagem entraria no modelo errado. A troca de
  // área e a de DATA recalculam o turno pré-selecionado: o que está em
  // aberto muda com as duas.
  //
  // Estes ouvintes precisam vir ANTES dos da tarefa da gestão (mais abaixo):
  // aquela busca lê o turno do seletor, e ele tem de já estar recalculado.
  var selArea = document.getElementById('diario-area');
  if (selArea && selArea.tagName === 'SELECT') {
    selArea.addEventListener('change', function () {
      preencherModelos();
      desenhar(true);
    });
  }
  var selData = document.getElementById('diario-date');
  if (selData) {
    selData.addEventListener('change', function () { desenhar(true); });
  }
  desenhar(true);

  // ── O que a gestão pediu para ESTE turno ───────────────────────────────
  //
  // Busca pelo servidor a cada troca de área, dia ou turno. Não vem no HTML
  // porque as três coisas se escolhem DEPOIS de a página carregar — renderizar
  // no servidor exigiria recarregar a tela a cada troca de área, justamente
  // o que o encarregado faz no celular quando cobre outro setor.
  var FORMA_AJUDA = {sim_nao: 'responda sim ou não',
                     numero: 'responda com o número',
                     texto: 'descreva'};

  function cartaoTarefa(t) {
    if (t.status !== 'pendente') {
      var feita = t.status === 'feita';
      return '<div class="card shadow-sm border-0 mb-2"><div class="card-body py-2">' +
        '<span class="badge ' + (feita ? 'text-bg-success' : 'text-bg-warning') +
        '">' + (feita ? 'feita' : 'virou pendência') + '</span> ' +
        '<strong>' + esc(t.titulo) + '</strong>' +
        '<div class="small text-muted mt-1">' + esc(t.resposta) + '</div>' +
        '</div></div>';
    }
    var campo = t.forma_resposta === 'sim_nao'
      ? '<select class="form-select form-select-sm dt-tg-resp">' +
        '<option value="">—</option><option value="Sim">Sim</option>' +
        '<option value="Não">Não</option></select>'
      : '<input class="form-control form-control-sm dt-tg-resp" ' +
        (t.forma_resposta === 'numero' ? 'inputmode="decimal" ' : '') +
        'placeholder="' + esc(FORMA_AJUDA[t.forma_resposta] || '') + '">';
    return '<div class="card shadow-sm border-0 mb-2" data-tarefa="' + t.id + '">' +
      '<div class="card-body py-2">' +
      '<div class="fw-semibold">' + esc(t.titulo) + '</div>' +
      (t.descricao ? '<div class="small text-muted">' + esc(t.descricao) + '</div>' : '') +
      '<div class="mt-2">' + campo + '</div>' +
      '<div class="d-flex gap-2 mt-2">' +
      '<button type="button" class="btn btn-sm btn-outline-success dt-tg-fiz" ' +
      'style="min-height:38px">Fiz</button>' +
      // A segunda saída é o ponto: sem ela, quem não conseguiu fazer só teria
      // a opção de mentir ou deixar em branco.
      '<button type="button" class="btn btn-sm btn-outline-warning dt-tg-pend" ' +
      'style="min-height:38px">Não deu — vira pendência</button>' +
      '</div></div></div>';
  }

  function carregarTarefasDaGestao() {
    var caixa = document.getElementById('dt-tarefas-gestao');
    var lista = document.getElementById('dt-tarefas-lista');
    var cli = document.getElementById('diario-client');
    var dia = document.getElementById('diario-date');
    var tur = document.getElementById('diario-shift');
    if (!caixa || !lista || !cli || !dia || !tur || !configAtual) { return; }
    if (!dia.value || !tur.value) { caixa.hidden = true; return; }
    fetch('/passagem-de-turno/api/tarefas-turno?client_id=' + cli.value +
          '&configuracao_id=' + configAtual.id +
          '&data_turno=' + encodeURIComponent(dia.value) +
          '&turno=' + encodeURIComponent(tur.value))
      .then(function (r) { return r.json(); })
      .then(function (x) {
        var ts = (x && x.tarefas) || [];
        caixa.hidden = !ts.length;
        lista.innerHTML = ts.map(cartaoTarefa).join('');
      }).catch(function () { caixa.hidden = true; });
  }
  window.dtRecarregarTarefas = carregarTarefasDaGestao;

  ['diario-date', 'diario-shift', 'diario-config', 'diario-area']
    .forEach(function (id) {
      var e = document.getElementById(id);
      if (e) { e.addEventListener('change', carregarTarefasDaGestao); }
    });
  carregarTarefasDaGestao();

  document.addEventListener('click', function (ev) {
    var alvo = ev.target.closest ? ev.target.closest('.dt-tg-fiz, .dt-tg-pend') : null;
    if (!alvo) { return; }
    var cartao = alvo.closest('[data-tarefa]');
    var virou = alvo.classList.contains('dt-tg-pend');
    var campo = cartao.querySelector('.dt-tg-resp');
    var texto = campo ? (campo.value || '').trim() : '';
    if (virou) {
      texto = prompt('Por que não foi possível fazer?') || '';
      texto = texto.trim();
      if (!texto) { return; }
    } else if (!texto) {
      alert('Responda antes de marcar como feita.');
      return;
    }
    alvo.disabled = true;
    fetch('/passagem-de-turno/api/tarefas-turno/' + cartao.dataset.tarefa + '/responder', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
      body: JSON.stringify({resposta: texto, virou_pendencia: virou})
    }).then(function (r) {
      return r.json().then(function (x) { return {ok: r.ok, x: x}; });
    }).then(function (res) {
      if (!res.ok) { alert(res.x.error || 'Não foi possível responder.'); alvo.disabled = false; return; }
      carregarTarefasDaGestao();
    }).catch(function () { alert('Falha de rede.'); alvo.disabled = false; });
  });

  // Semáforo: um toque escolhe, e a escolha fica visível sem abrir nada.
  document.addEventListener('click', function (ev) {
    var botao = ev.target.closest ? ev.target.closest('.dt-opcao') : null;
    if (!botao) { return; }
    var caixa = botao.parentNode;
    caixa.querySelectorAll('.dt-opcao').forEach(function (b) {
      b.classList.toggle('sel', b === botao);
    });
    var campo = caixa.querySelector('.diario-field');
    if (campo) { campo.value = botao.dataset.valor || ''; }
  });

  // Mostra o que foi escolhido: no celular o seletor de arquivo não dá
  // retorno nenhum, e sem isto a pessoa não sabe se a foto entrou. A foto é
  // reduzida aqui, na escolha (static/js/foto-leve.js): sobe em segundos
  // com 4G fraco e ocupa pouco na fila sem internet.
  function atualizarEscolhidos(caixa) {
    var aviso = caixa ? caixa.querySelector('.dt-escolhidos') : null;
    if (!aviso) { return; }
    var arquivos = [];
    caixa.querySelectorAll('.diario-activity-file, #diario-observacao-file').forEach(function (e) {
      [].slice.call(e.files || []).forEach(function (f) { arquivos.push(f); });
    });
    var resumos = [].slice.call(caixa.querySelectorAll('.diario-activity-file, #diario-observacao-file'))
      .map(function (e) { return e._resumo || ''; }).filter(Boolean);
    aviso.textContent = !arquivos.length ? '' :
      (resumos.length ? resumos.join(' + ') :
       (arquivos.length === 1 ? '1 arquivo escolhido' : arquivos.length + ' arquivos escolhidos'));
  }

  document.addEventListener('change', function (ev) {
    var alvo = ev.target;
    if (!alvo.matches || !alvo.matches('.diario-activity-file, #diario-observacao-file')) { return; }
    var caixa = alvo.closest('.dt-anexos') || alvo.closest('.card-body');
    alvo._resumo = '';
    atualizarEscolhidos(caixa);
    if (!window.TrinoFoto || !alvo.files || !alvo.files.length) { return; }
    var aviso = caixa ? caixa.querySelector('.dt-escolhidos') : null;
    if (aviso) { aviso.textContent = 'Preparando a foto…'; }
    alvo._preparo = window.TrinoFoto.prepararEntrada(alvo).then(function (texto) {
      alvo._resumo = texto;
      atualizarEscolhidos(caixa);
    }, function () { atualizarEscolhidos(caixa); });
  });

  // "Encerrar" logo depois de tirar a foto: espera a redução terminar, para
  // não subir a foto de 8 MB que ainda estava sendo preparada.
  function fotosProntas() {
    return Promise.all([].slice.call(document.querySelectorAll(
      '.diario-activity-file, #diario-observacao-file'))
      .map(function (e) { return e._preparo || null; }))
      .catch(function () { return null; });
  }

  // ── Pendências e ocorrências ──────────────────────────────────────────
  // O botão de tirar a linha. No computador é o "×" compacto da última
  // coluna; no celular, onde a coluna vira a largura inteira, o "×" virava
  // uma caixa vermelha do tamanho de um campo — e parecia campo com erro.
  // Lá ele aparece como o link "Remover", alinhado à direita (ver
  // `.dt-linha-remover` em static/css/style.css).
  function botaoRemover(classeDaLinha) {
    return '<div class="col-md-1 dt-linha-remover"><button type="button" ' +
      'class="btn btn-outline-danger w-100" title="Remover esta linha" ' +
      'aria-label="Remover esta linha" ' +
      'onclick="this.closest(\'.' + classeDaLinha + '\').remove()">' +
      '<span class="dt-x" aria-hidden="true">×</span>' +
      '<span class="dt-remover-txt">Remover</span></button></div>';
  }

  function addPending() {
    var d = document.createElement('div');
    d.className = 'row g-2 mb-2 pending-row';
    // A referência ganhou campo próprio: numa devolução, numa NF ou num
    // pedido, o número É a coisa. Antes ele era enfiado dentro do título e
    // depois não havia como procurar por ele.
    d.innerHTML =
      '<div class="col-md-4"><input class="form-control p-title" placeholder="Pendência"></div>' +
      '<div class="col-md-2"><input class="form-control p-ref" placeholder="Nº / referência"></div>' +
      '<div class="col-md-3"><input class="form-control p-desc" placeholder="Descrição"></div>' +
      '<div class="col-md-2"><select class="form-select p-priority">' +
        '<option value="baixa">Baixa</option>' +
        '<option value="media" selected>Média</option>' +
        '<option value="alta">Alta</option></select></div>' +
      botaoRemover('pending-row');
    document.getElementById('pending-list').appendChild(d);
  }

  function addOccurrence() {
    var d = document.createElement('div');
    d.className = 'row g-2 mb-2 occurrence-row';
    var tipos = ((configAtual && configAtual.tipos_ocorrencia) || []).map(function (x) {
      var nome = esc(x.nome || x);
      return '<option value="' + nome + '">' + nome + '</option>';
    }).join('');
    // "Ponto de atenção" e não "Crítica": a palavra descreve o que o gestor
    // vai fazer com ela — ler e analisar —, não o tamanho do problema. O
    // encarregado marca isso com pressa no fim do turno, e "crítico" convida
    // a marcar tudo.
    d.innerHTML =
      '<div class="col-md-3"><select class="form-select o-type">' +
        (tipos || '<option value="Outros">Outros</option>') + '</select></div>' +
      '<div class="col-md-2"><input class="form-control o-ref" placeholder="Número / referência"></div>' +
      '<div class="col-md-4"><input class="form-control o-desc" placeholder="Descrição da ocorrência"></div>' +
      // Rótulo curto porque a coluna é estreita e "Ponto de atenção" era
      // cortado no meio ("Ponto de ate…"), que é pior do que abreviar. O
      // título do campo carrega a frase inteira.
      '<div class="col-md-2"><select class="form-select o-grav" ' +
        'title="Marque &quot;Atenção&quot; para o fato subir à Torre de Comando ' +
        'como ponto de atenção do contrato">' +
        '<option value="normal">Normal</option>' +
        '<option value="critica">⚠ Atenção</option></select></div>' +
      botaoRemover('occurrence-row');
    document.getElementById('occurrence-list').appendChild(d);
  }

  // ── Salvar ────────────────────────────────────────────────────────────
  function coletar() {
    var dados = {};
    document.querySelectorAll('.diario-field').forEach(function (e) {
      dados[e.dataset.key] = e.value;
    });
    document.querySelectorAll('.diario-activity').forEach(function (e) {
      dados['atividade:' + e.dataset.key] = {concluido: e.checked};
    });
    document.querySelectorAll('.diario-activity-note').forEach(function (e) {
      var k = 'atividade:' + e.dataset.key;
      dados[k] = Object.assign({}, dados[k] || {}, {observacao: e.value});
    });
    return dados;
  }

  // Os arquivos só podem subir DEPOIS que o turno existe — é o id dele que
  // ancora o anexo. Por isso o envio é em duas etapas, e não porque se quis
  // duas chamadas: guardar o arquivo antes exigiria um turno provisório que
  // ficaria órfão se a pessoa desistisse.
  //
  // Cada grupo de arquivos leva uma marca de envio: se a conexão cair no meio
  // e o grupo for mandado de novo (pela fila do aparelho), o servidor
  // reconhece o que já chegou e não duplica a foto.
  function gruposDeAnexos() {
    return [].slice.call(document.querySelectorAll(
      '.diario-activity-file, #diario-observacao-file'))
      .filter(function (i) { return i.files && i.files.length; })
      .map(function (i) {
        return {envio: novoEnvio(), atividade: i.dataset.key || '',
                arquivos: [].slice.call(i.files), feito: false};
      });
  }

  function enviarAnexos(turnoId, grupos) {
    var envios = grupos.map(function (g) {
      var corpo = new FormData();
      corpo.append('atividade', g.atividade);
      corpo.append('envio', g.envio);
      g.arquivos.forEach(function (f) { corpo.append('arquivo', f); });
      return fetch('/passagem-de-turno/api/turnos/' + turnoId + '/anexos', {
        method: 'POST', headers: {'X-CSRFToken': csrf()}, body: corpo
      }).then(function (r) {
        if (filaDisponivel() && window.TrinoFila.ehFalhaDeConexao(r)) {
          return {ok: false, conexao: true, grupo: g, x: {}};
        }
        return r.json().then(function (x) { return {ok: r.ok, x: x, grupo: g}; },
                             function () { return {ok: false, x: {}, grupo: g}; });
      }, function () {
        return {ok: false, conexao: true, grupo: g, x: {}};
      });
    });
    if (!envios.length) { return Promise.resolve([]); }
    return Promise.all(envios);
  }

  function novoEnvio() {
    return filaDisponivel() ? window.TrinoFila.novoId()
                            : String(Date.now()) + '-' + Math.random().toString(16).slice(2, 10);
  }

  function filaDisponivel() {
    return !!(window.TrinoFila && window.TrinoFila.guardar);
  }

  function rotuloDoTurno(corpo) {
    var area = configAtual ? configAtual.nome : 'Passagem';
    var d = (corpo.data_turno || '').split('-');
    var dia = d.length === 3 ? d[2] + '/' + d[1] : corpo.data_turno;
    return (corpo.finalizar ? 'Encerramento' : 'Rascunho') + ' — ' + area + ', ' +
           corpo.turno + ' de ' + dia;
  }

  // Sem sinal (ou com a sessão vencida no meio do turno), nada se perde: o
  // turno e as fotos vão para a fila do aparelho e sobem sozinhos quando a
  // conexão voltar. A tela diz isso com todas as letras — "guardado" não é
  // "enviado", e quem lê precisa saber a diferença.
  //
  // E diz a verdade sobre QUANDO sobe. A caixa dizia "pode fechar a tela",
  // mas não existe envio em segundo plano: o service worker não tem 'sync',
  // e a fila (static/js/fila-offline.js) só roda com o sistema aberto em
  // alguma tela deste aparelho. Quem fechava tudo confiando na frase ficava
  // com a passagem presa no celular até abrir o sistema de novo.
  var guardadoAqui = null;   // id do item da fila que esta tela guardou

  function guardarNoAparelho(corpo, grupos, turnoId) {
    var item = {tipo: 'turno', rotulo: rotuloDoTurno(corpo), corpo: turnoId ? null : corpo,
                turno_id: turnoId || null, anexos: grupos};
    if (turnoId) { item.rotulo = 'Fotos — ' + rotuloDoTurno(corpo); }
    return window.TrinoFila.guardar(item).then(function (guardado) {
      guardadoAqui = (guardado && guardado.id) || item.id || null;
      var area = document.getElementById('diario-salvar');
      if (area) {
        area.style.position = 'static';   // a caixa não fica presa ao rodapé
        area.innerHTML =
          '<div class="dt-guardado" role="status" aria-live="polite">' +
          '<strong><i class="bi bi-cloud-arrow-up"></i> Guardado neste aparelho.</strong> ' +
          (turnoId ? 'A passagem foi enviada; as fotos ainda não subiram. '
                   : 'Ainda <u>não foi enviado</u>: está sem conexão agora. ') +
          'Vai subir sozinho quando houver sinal, com o sistema aberto neste ' +
          'aparelho. Enquanto isso, o aviso no alto da tela mostra o que está ' +
          'guardado.' +
          '<div class="mt-2"><button type="button" class="btn btn-sm btn-outline-secondary" ' +
          'onclick="location.reload()">Nova passagem</button></div></div>';
      }
    });
  }

  // A fila avisa quando um item sobe (evento `trino-fila:enviado`). Se é o
  // que ESTA tela guardou, a caixa troca o "guardado" por "enviado" — sem
  // isto, a passagem já estava no sistema e a tela continuava dizendo que
  // não, e o encarregado lançava de novo pelo computador.
  window.addEventListener('trino-fila:enviado', function (ev) {
    var d = ev.detail || {};
    if (!guardadoAqui || d.id !== guardadoAqui) { return; }
    var caixa = document.querySelector('#diario-salvar .dt-guardado');
    if (!caixa) { return; }
    caixa.classList.add('dt-enviado');
    caixa.innerHTML =
      '<strong><i class="bi bi-cloud-check"></i> Enviado.</strong> ' +
      (d.estado === 'aviso'
        ? esc(d.mensagem || 'A passagem subiu, mas com um aviso — veja no alto da tela.')
        : 'A passagem que estava guardada neste aparelho já está no sistema.') +
      (d.turno_id ? ' <a href="/passagem-de-turno/turno/' + Number(d.turno_id) +
                    '">Ver a passagem</a>' : '') +
      '<div class="mt-2"><button type="button" class="btn btn-sm btn-outline-secondary" ' +
      'onclick="location.reload()">Nova passagem</button></div>';
    guardadoAqui = null;
  });

  function salvarTurno(finalizar) {
    if (!configAtual) {
      alert('Este contrato ainda não tem um modelo de passagem cadastrado. ' +
            'Peça ao Master para cadastrar em Configurar.');
      return;
    }
    // A hora do TOQUE em "Encerrar", pelo relógio do aparelho. Sem sinal, o
    // encerramento espera na fila e chega horas depois; sem esta hora, a
    // passagem pareceria fechada atrasada. O servidor confere antes de
    // guardar — relógio de celular erra.
    var tocadoEm = new Date().toISOString();
    if (finalizar) {
      // Tarefa da gestão sem resposta: encerrar assim tem consequência (vira
      // pendência de prioridade alta e quem pediu é avisado), e a pessoa
      // precisa saber ANTES. Só conta o que a lista MOSTRA — se ela não
      // carregou (sem sinal), a caixa fica escondida e nada bloqueia: o
      // servidor faz a mesma coisa quando o encerramento chegar.
      var caixaTarefas = document.getElementById('dt-tarefas-gestao');
      var semResposta = (caixaTarefas && !caixaTarefas.hidden)
        ? caixaTarefas.querySelectorAll('#dt-tarefas-lista [data-tarefa]').length : 0;
      if (semResposta && !confirm((semResposta === 1
            ? 'Há 1 tarefa da gestão sem resposta. Se encerrar assim, ela vira '
            : 'Há ' + semResposta + ' tarefas da gestão sem resposta. Se encerrar ' +
              'assim, cada uma vira ') +
          'pendência de prioridade alta e quem pediu é avisado. Encerrar mesmo assim?')) {
        return;                              // Cancelar: nada é enviado
      }
    }
    var botoes = document.querySelectorAll('#diario-salvar button');
    botoes.forEach(function (b) { b.disabled = true; });
    fotosProntas().then(function () { continuarSalvar(finalizar, botoes, tocadoEm); });
  }

  function continuarSalvar(finalizar, botoes, tocadoEm) {
    var corpo = {
      client_id: Number(document.getElementById('diario-client').value),
      configuracao_id: configAtual.id,
      data_turno: document.getElementById('diario-date').value,
      turno: document.getElementById('diario-shift').value,
      dados: coletar(),
      observacao: document.getElementById('diario-observacao').value,
      pendencias: [].slice.call(document.querySelectorAll('.pending-row')).map(function (r) {
        return {titulo: r.querySelector('.p-title').value,
                referencia: r.querySelector('.p-ref').value,
                descricao: r.querySelector('.p-desc').value,
                prioridade: r.querySelector('.p-priority').value};
      }),
      ocorrencias: [].slice.call(document.querySelectorAll('.occurrence-row')).map(function (r) {
        return {tipo: r.querySelector('.o-type').value,
                referencia: r.querySelector('.o-ref').value,
                descricao: r.querySelector('.o-desc').value,
                gravidade: r.querySelector('.o-grav').value};
      }),
      finalizar: !!finalizar,
      // Uma marca por clique: se este envio chegar e a resposta se perder, o
      // reenvio é reconhecido como o mesmo — não vira "já foi encerrada".
      envio_id: novoEnvio()
    };
    // Vai DENTRO do corpo, e não na hora do envio: se o encerramento cair na
    // fila do aparelho, é este mesmo corpo que sobe depois — com a hora do
    // toque, não a da volta do sinal.
    if (finalizar) { corpo.encerrado_no_aparelho = tocadoEm; }
    var grupos = gruposDeAnexos();

    function semConexao() {
      if (!filaDisponivel()) {
        botoes.forEach(function (b) { b.disabled = false; });
        alert('Falha de rede ao salvar o turno.');
        return;
      }
      guardarNoAparelho(corpo, grupos).catch(function () {
        botoes.forEach(function (b) { b.disabled = false; });
        alert('Sem conexão, e não foi possível guardar neste aparelho. ' +
              'Não feche a tela: tente de novo quando o sinal voltar.');
      });
    }

    if (navigator.onLine === false && filaDisponivel()) { semConexao(); return; }

    fetch('/passagem-de-turno/api/turnos', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
      body: JSON.stringify(corpo)
    }).then(function (r) {
      if (filaDisponivel() && window.TrinoFila.ehFalhaDeConexao(r)) { return {conexao: true}; }
      return r.json().then(function (x) { return {ok: r.ok, x: x}; },
                           function () { return {conexao: true}; });
    }, function () {
      return {conexao: true};
    }).then(function (res) {
      if (res.conexao) { semConexao(); return null; }
      if (!res.ok) {
        botoes.forEach(function (b) { b.disabled = false; });
        alert(res.x.error || 'Não foi possível salvar.');
        return null;
      }
      return enviarAnexos(res.x.id, grupos).then(function (envios) {
        var semRede = (envios || []).filter(function (e) { return e.conexao; });
        var recusados = (envios || []).filter(function (e) { return !e.ok && !e.conexao; });
        if (recusados.length) {
          // O turno JÁ está salvo; avisar e seguir é honesto — esconder a
          // falha do anexo faria a pessoa achar que a foto subiu.
          alert('O turno foi salvo, mas ' + (recusados.length === 1
                  ? '1 anexo não subiu: ' : recusados.length + ' anexos não subiram: ') +
                (recusados[0].x.error || 'tente anexar de novo pela tela do turno.'));
        }
        if (semRede.length && filaDisponivel()) {
          // A conexão caiu entre o turno e as fotos: o turno está salvo, as
          // fotos vão para a fila em vez de se perderem.
          return guardarNoAparelho(corpo, semRede.map(function (e) { return e.grupo; }),
                                   res.x.id);
        }
        window.location = '/passagem-de-turno/?client_id=' + corpo.client_id;
      });
    });
  }

  // ── A trilha da pendência ─────────────────────────────────────────────
  // Duas saídas, e a diferença entre elas é quanto se cobra de quem está de
  // pé no fim do turno:
  //   Resolver  → uma frase obrigatória com o que foi feito. Um "resolver"
  //               que não custa nada vira botão de limpar a tela.
  //   Continua  → uma frase opcional com o que se tentou. Quem não escreve
  //               nada simplesmente encerra o turno: o registro de que este
  //               turno recebeu a pendência é gravado sozinho no servidor.
  // A tela diz de si mesma qual passagem está sendo feita. O servidor só
  // amarra o evento a um turno se ele JÁ existir — o encarregado que resolve
  // antes de salvar deixa um evento sem turno, com quem e quando, e isso
  // basta para a trilha ser lida.
  function enviarNaPendencia(id, caminho, corpo, erroPadrao, aoDarCerto) {
    var dia = document.getElementById('diario-date');
    var turno = document.getElementById('diario-shift');
    corpo.data_turno = dia ? dia.value : '';
    corpo.turno = turno ? turno.value : '';
    // O modelo escolhido: com duas áreas, data + turno não bastam para achar
    // de qual passagem partiu a baixa (ver _turno_do_lancamento).
    corpo.configuracao_id = configAtual ? configAtual.id : null;
    return fetch('/passagem-de-turno/api/pendencias/' + id + '/' + caminho, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
      body: JSON.stringify(corpo)
    }).then(function (r) {
      return r.json().then(function (x) { return {ok: r.ok, x: x}; });
    }).then(function (res) {
      if (!res.ok) { alert(res.x.error || erroPadrao); return; }
      // Atualiza a tela NO LUGAR, sem recarregar. Antes havia um
      // `location.reload()` aqui, e com as duas abas ele virou perigoso: o
      // formulário da passagem é montado por JS, então recarregar apagaria
      // tudo o que a pessoa já tivesse digitado do outro lado.
      if (aoDarCerto) { aoDarCerto(); }
    }).catch(function () { alert('Falha de rede.'); });
  }

  function cartaoDaPendencia(id) {
    return document.querySelector('.diario-pending[data-id="' + id + '"]');
  }

  // Mantém o contador da aba igual ao que está na tela. Se divergirem, a aba
  // passa a mentir sobre quanto falta — e é justamente o número que o
  // encarregado olha enquanto preenche a passagem do outro lado.
  //
  // O cabeçalho do cartão ("Pendências em aberto  N") é o MESMO número, e
  // vinha do servidor: depois da baixa a aba dizia 2 e o cartão, 3. O
  // contador é achado pelo lugar dele (o cabeçalho do cartão dentro do
  // painel de pendências) e não por um id, porque ele é desenhado pelo
  // servidor e esta tela não deve depender de mexer no HTML dele.
  function contadorDoCartao() {
    var painel = document.querySelector('.dt-painel[data-painel="pendencias"]');
    return painel ? painel.querySelector('.card-header > span:last-child') : null;
  }

  function recontarPendencias() {
    var cartoes = document.querySelectorAll('.diario-pending');
    var vencidas = document.querySelectorAll('.diario-pending.vencida');
    var cab = contadorDoCartao();
    if (cab) { cab.textContent = cartoes.length; }
    var aba = document.querySelector('.dt-aba[data-painel="pendencias"]');
    if (!aba) { return; }
    var n = aba.querySelector('.dt-aba-n');
    if (!cartoes.length) {
      if (n) { n.remove(); }
      var vazio = document.querySelector('.dt-sem-pend');
      if (vazio) { vazio.hidden = false; }
      // O cartão fica, mas não vazio e calado: diz que a fila acabou.
      var corpo = cab ? cab.closest('.card').querySelector('.card-body') : null;
      if (corpo && !corpo.querySelector('.dt-vazio')) {
        corpo.innerHTML = '<div class="dt-vazio">Todas as pendências recebidas ' +
                          'foram baixadas.</div>';
      }
      return;
    }
    if (!n) {
      n = document.createElement('span');
      n.className = 'dt-aba-n';
      aba.appendChild(n);
    }
    n.textContent = cartoes.length;
    n.classList.toggle('ruim', vencidas.length > 0);
  }

  function resolverPendencia(id) {
    var texto = prompt('O que foi feito para resolver?');
    if (texto === null) { return; }          // desistiu — nada acontece
    texto = texto.trim();
    if (!texto) { alert('Diga em uma linha o que foi feito.'); return; }
    enviarNaPendencia(id, 'resolver', {resolucao: texto},
                      'Não foi possível resolver.', function () {
      var cartao = cartaoDaPendencia(id);
      if (cartao) { cartao.remove(); }
      recontarPendencias();
      // Resolveu a última: não há mais nada a receber, e o que resta do
      // turno é entregar. Levar para a outra aba poupa um toque e diz, sem
      // texto, que aquele lado acabou.
      if (!document.querySelectorAll('.diario-pending').length) {
        mostrarPainel('passagem');
      }
    });
  }

  function anotarPendencia(id) {
    var texto = prompt('O que você tentou? (fica para o próximo turno)');
    if (texto === null) { return; }
    texto = texto.trim();
    if (!texto) { return; }                  // sem texto não há o que anotar
    enviarNaPendencia(id, 'nota', {texto: texto},
                      'Não foi possível anotar.', function () {
      // A anotação aparece na hora, com o mesmo formato que o servidor
      // devolveria no próximo carregamento. Sem isso o encarregado escreve
      // e não vê nada mudar — e escreve de novo.
      var cartao = cartaoDaPendencia(id);
      if (!cartao) { return; }
      var linha = cartao.querySelector('.dt-pend-tent');
      if (!linha) {
        linha = document.createElement('div');
        linha.className = 'dt-pend-tent';
        var acoes = cartao.querySelector('.dt-pend-acoes');
        cartao.insertBefore(linha, acoes);
      }
      // "— agora" sem nome não dizia QUEM tentou, que é metade do que o
      // turno seguinte precisa saber (é para essa pessoa que ele liga).
      var quem = (raiz.dataset.usuario || '').trim();
      linha.innerHTML = '<span class="dt-pend-tent-rot">Já se tentou</span> ' +
        esc(texto) + ' <span class="dt-pend-tent-quem">— ' +
        (quem ? esc(quem) + ', ' : '') + 'agora</span>';
    });
  }

  // ── As duas abas ──────────────────────────────────────────────────────
  // A página empilhava dois trabalhos diferentes: resolver o que o turno
  // passado deixou (ao CHEGAR) e preencher a passagem (ao SAIR). Com sete
  // pendências abertas, responder uma pergunta do checklist custava rolar a
  // lista inteira.
  //
  // A troca é só no navegador, sem recarregar: o formulário é montado por
  // JS a partir do modelo do contrato, e um recarregamento apagaria o que a
  // pessoa já tivesse digitado.
  function mostrarPainel(nome) {
    document.querySelectorAll('.dt-painel').forEach(function (el) {
      el.hidden = el.dataset.painel !== nome;
    });
    document.querySelectorAll('.dt-aba').forEach(function (b) {
      b.classList.toggle('ativa', b.dataset.painel === nome);
    });
    // Voltar ao topo: sem isto, quem troca de aba no meio da lista cai no
    // meio do formulário e acha que a tela quebrou.
    window.scrollTo({top: 0, behavior: 'smooth'});
  }

  document.addEventListener('click', function (ev) {
    var aba = ev.target.closest ? ev.target.closest('.dt-aba') : null;
    if (aba) { mostrarPainel(aba.dataset.painel); }
  });

  window.addPending = addPending;
  window.addOccurrence = addOccurrence;
  window.salvarTurno = salvarTurno;
  window.resolverPendencia = resolverPendencia;
  window.anotarPendencia = anotarPendencia;
  window.mostrarPainel = mostrarPainel;
}());
