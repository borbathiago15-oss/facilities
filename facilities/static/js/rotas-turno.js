// "Meu turno" — o aplicativo de campo executando a rota (Fase 4A).
//
// A tela chega com TUDO que precisa num JSON (#turno-dados): as tarefas de
// hoje, os checklists delas e os pontos pelo código do QR. Por isso ela
// abre e funciona SEM internet (o service worker guarda a cópia):
//
//   ler o QR → /app/turno?ponto=<código> → o ponto, o procedimento e as
//   tarefas dele → "Fazer agora" → o checklist → Confirmar.
//
// Com sinal, a hora da leitura é a do SERVIDOR (o selo de /app/api/leitura).
// Sem sinal, vale a hora do celular, e a execução vai marcada "feito sem
// sinal" (R4); o envio fica na fila do aparelho (fila-offline.js) e sobe
// sozinho quando o sinal volta. O mesmo envio nunca vira duas execuções
// (envio_id).
(function () {
  'use strict';
  var raiz = document.getElementById('turno-app');
  if (!raiz) return;
  var dados = JSON.parse(document.getElementById('turno-dados').textContent);
  var secLista = document.getElementById('turno-lista');
  var secPonto = document.getElementById('turno-ponto');
  var secExec = document.getElementById('turno-execucao');
  var caixaItens = document.getElementById('turno-itens');
  var aviso = document.getElementById('turno-aviso');
  var leitura = null;   // {ponto, selo, lido_em}
  var CHAVE_LOCAL = 'trino-turno-feitas-' + dados.usuario;

  // ── Ajudantes ─────────────────────────────────────────────────────────
  function el(tag, attrs, filhos) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'texto') { n.textContent = attrs[k]; }
      else if (k === 'classe') { n.className = attrs[k]; }
      else if (k.indexOf('on') === 0) { n.addEventListener(k.slice(2), attrs[k]); }
      else if (attrs[k] !== false && attrs[k] !== null && attrs[k] !== undefined) {
        n.setAttribute(k, attrs[k] === true ? '' : attrs[k]);
      }
    });
    (filhos || []).forEach(function (f) {
      if (f === null || f === undefined || f === false) return;
      n.appendChild(typeof f === 'string' ? document.createTextNode(f) : f);
    });
    return n;
  }
  function limpar(n) { while (n.firstChild) n.removeChild(n.firstChild); }
  function dizer(texto, tipo) {
    limpar(aviso);
    if (!texto) return;
    aviso.appendChild(el('div', {classe: 'alert alert-' + (tipo || 'info'), texto: texto}));
    aviso.scrollIntoView({block: 'nearest'});
  }
  function hora(iso) {
    var d = new Date(iso);
    return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
  }
  function novoId() {
    if (window.TrinoFila && window.TrinoFila.novoId) return window.TrinoFila.novoId();
    return 'e' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }
  function feitasNoAparelho() {
    try { return JSON.parse(localStorage.getItem(CHAVE_LOCAL) || '{}'); } catch (e) { return {}; }
  }
  function marcarFeita(id, rotulo) {
    var f = feitasNoAparelho();
    f[id] = rotulo;
    try { localStorage.setItem(CHAVE_LOCAL, JSON.stringify(f)); } catch (e) {}
  }

  // A situação AGORA (a do servidor envelhece com a tela aberta).
  function situacao(t) {
    var guardada = feitasNoAparelho()[t.id];
    if (guardada) return {cod: 'guardada', rotulo: guardada};
    if (t.status !== 'prevista') return {cod: t.status, rotulo: dados.situacoes[t.status]};
    var agora = Date.now();
    var prev = Date.parse(t.previsto);
    var tol = t.tolerancia * 60000;
    if (agora < prev - tol) return {cod: 'prevista', rotulo: 'Prevista'};
    if (agora <= prev + tol) return {cod: 'no_horario', rotulo: 'No horário'};
    if (agora > Date.parse(t.fim_turno)) return {cod: 'perdida', rotulo: 'Turno encerrado'};
    return {cod: 'atrasada', rotulo: 'Atrasada'};
  }
  function podeFazer(t) {
    var s = situacao(t).cod;
    return s === 'no_horario' || s === 'atrasada';
  }

  // ── Lista do turno ────────────────────────────────────────────────────
  // ``n``: o número da tarefa no roteiro do dia (1, 2, 3…); ``proxima``: a
  // que a pessoa deve fazer agora — fica destacada.
  function cartaoTarefa(t, comBotoes, n, proxima) {
    var s = situacao(t);
    var v = dados.versoes[t.versao];
    var passos = v && v.itens ? v.itens.length : 0;
    var linha = el('div', {classe: 'fc-app-item' + (proxima ? ' fc-proxima' : '')}, [
      el('div', {classe: 'd-flex align-items-center gap-2'}, [
        n ? el('span', {classe: 'fc-roteiro-n', texto: String(n), 'aria-label': 'Passo ' + n + ' do roteiro'}) : null,
        el('span', {classe: 'fs-5 fw-bold', texto: t.hora}),
        proxima ? el('span', {classe: 'badge text-bg-danger', texto: 'Próxima'}) : null,
        el('span', {classe: 'badge fc-sit fc-sit-' + s.cod, texto: s.rotulo}),
        t.minha ? el('span', {classe: 'badge text-bg-light', texto: 'Sua'}) : null
      ]),
      el('span', {classe: 'fw-semibold', texto: t.ambiente + ' · ' + t.ponto_nome}),
      el('span', {classe: 'small text-muted',
                  texto: v.modelo + (passos ? ' · ' + passos + (passos > 1 ? ' passos' : ' passo') : '') +
                         ' · ' + t.local + (t.escalado && !t.minha ? ' · escala: ' + t.escalado : '')})
    ]);
    if (comBotoes && (s.cod === 'prevista' || s.cod === 'no_horario' || s.cod === 'atrasada')) {
      var barra = el('div', {classe: 'd-flex gap-2 mt-2'});
      if (podeFazer(t)) {
        barra.appendChild(el('button', {type: 'button', classe: 'btn btn-primary fc-app-acao flex-grow-1',
          onclick: function () { abrirExecucao(t, dados.versoes[t.versao]); }},
          [el('i', {classe: 'bi bi-check2-square'}), ' Fazer agora']));
      } else {
        var desde = new Date(Date.parse(t.previsto) - t.tolerancia * 60000).toISOString();
        barra.appendChild(el('span', {classe: 'small text-muted align-self-center flex-grow-1',
          texto: 'Pode ser feita a partir das ' + hora(desde) + '.'}));
      }
      barra.appendChild(el('button', {type: 'button', classe: 'btn btn-outline-secondary',
        onclick: function () { abrirNaoRealizada(t); }}, ['Não realizada']));
      linha.appendChild(barra);
    }
    return linha;
  }

  function mostrarLista() {
    secPonto.hidden = true; secExec.hidden = true; secLista.hidden = false;
    limpar(caixaItens);
    // O roteiro do dia na ordem dos horários (1, 2, 3…), como a rota foi
    // pensada; a próxima a fazer fica destacada — a atrasada ou a da hora
    // primeiro, senão a primeira que ainda vai chegar.
    var tarefas = dados.tarefas.slice().sort(function (a, b) {
      return Date.parse(a.previsto) - Date.parse(b.previsto);
    });
    var abertas = tarefas.filter(function (t) {
      var c = situacao(t).cod;
      return c === 'atrasada' || c === 'no_horario';
    });
    var proxima = abertas[0] || tarefas.filter(function (t) { return situacao(t).cod === 'prevista'; })[0];
    if ((dados.preventivas || []).length) {
      caixaItens.appendChild(el('div', {classe: 'alert alert-info',
        texto: dados.preventivas.length + ' preventiva(s) em aberto. Leia o QR do ponto para fazer o checklist.'}));
    }
    if ((dados.ocorrencias || []).length) {
      caixaItens.appendChild(el('div', {classe: 'alert alert-warning',
        texto: dados.ocorrencias.length + ' aviso(s) do público esperando. Leia o QR do local para atender.'}));
    }
    if (!tarefas.length) {
      caixaItens.appendChild(el('div', {classe: 'fc-cartao fc-vazio',
        texto: 'Nenhuma tarefa de rota para hoje nos seus locais.'}));
      return;
    }
    var cartao = el('div', {classe: 'fc-cartao'});
    tarefas.forEach(function (t, i) { cartao.appendChild(cartaoTarefa(t, false, i + 1, t === proxima)); });
    caixaItens.appendChild(cartao);
    caixaItens.appendChild(el('p', {classe: 'small text-muted mt-2',
      texto: 'Para fazer uma tarefa, leia o QR do local: o checklist abre na hora.'}));
  }

  // ── O ponto (depois de ler o QR) ──────────────────────────────────────
  // O selo (hora do servidor) é a prova de que a pessoa leu o QR no ponto: só
  // é pedido quando a CÂMERA leu agora (``lido=camera`` vindo do leitor). O
  // link de um aviso, o código digitado e a página recarregada abrem o ponto,
  // mas a execução fica com a hora do celular — marcada para a gestão.
  function lerNoServidor(codigo, comCamera) {
    if (leitura && leitura.ponto === codigo) return;     // voltou ao mesmo ponto
    leitura = {ponto: codigo, selo: null, lido_em: new Date().toISOString()};
    if (!comCamera || navigator.onLine === false || !window.fetch) return;
    fetch('/app/api/leitura', {method: 'POST', headers: {'Content-Type': 'application/json'},
                               body: JSON.stringify({ponto: codigo})})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (x) { if (x && leitura && leitura.ponto === codigo) leitura.selo = x.selo; })
      .catch(function () { /* sem sinal: fica a hora do aparelho */ });
  }

  function abrirPonto(codigo, comCamera) {
    var p = dados.pontos[codigo];
    secLista.hidden = true; secExec.hidden = true; secPonto.hidden = false;
    limpar(secPonto);
    if (!p) {
      secPonto.appendChild(el('div', {classe: 'alert alert-warning',
        texto: 'Este QR não é de um ponto dos seus locais (ou foi desativado). ' +
               'Confira a etiqueta ou avise a gestão.'}));
      secPonto.appendChild(el('button', {type: 'button', classe: 'btn btn-outline-secondary',
        onclick: mostrarLista}, ['Voltar ao meu turno']));
      return;
    }
    lerNoServidor(codigo, comCamera);
    secPonto.appendChild(el('h1', {classe: 'fc-titulo', texto: p.nome}));
    if (!leitura.selo && !comCamera) {
      secPonto.appendChild(el('p', {classe: 'small text-muted',
        texto: 'Aberto sem ler o QR com a câmera: o que você fizer aqui fica com a hora do ' +
               'celular. Para valer como feito no ponto, leia o QR do local.'}));
    }
    secPonto.appendChild(el('p', {classe: 'fc-sub', texto: p.ambiente + ' · ' + p.local}));
    if (p.descricao) {
      secPonto.appendChild(el('div', {classe: 'fc-cartao mb-3'}, [
        el('div', {classe: 'small fw-semibold text-muted', texto: 'Sobre este ponto'}),
        el('div', {texto: p.descricao})]));
    }
    var avisos = (dados.ocorrencias || []).filter(function (o) { return o.ponto === codigo; });
    if (avisos.length) secPonto.appendChild(cartaoOcorrencias(avisos));
    var prevs = (dados.preventivas || []).filter(function (x) { return x.ponto === codigo; });
    if (prevs.length) secPonto.appendChild(cartaoPreventivas(prevs));
    var doPonto = dados.tarefas.filter(function (t) { return t.ponto === codigo; });
    var cartao = el('div', {classe: 'fc-cartao mb-3'},
      [el('h2', {classe: 'h6 fw-bold', texto: 'Tarefas deste ponto hoje'})]);
    if (!doPonto.length) cartao.appendChild(el('p', {classe: 'small text-muted mb-0',
      texto: 'Nenhuma tarefa de rota aqui hoje.'}));
    doPonto.forEach(function (t) { cartao.appendChild(cartaoTarefa(t, true)); });
    secPonto.appendChild(cartao);
    var extras = (p.extras || []).map(function (vid) { return dados.versoes[vid]; })
      .filter(Boolean);
    if (extras.length) {
      var sel = el('select', {classe: 'form-select', id: 'extra-modelo', 'aria-label': 'Checklist'},
        extras.map(function (v) { return el('option', {value: v.id, texto: v.modelo}); }));
      secPonto.appendChild(el('details', {classe: 'fc-cartao mb-3'}, [
        el('summary', {classe: 'fw-semibold', texto: 'Atividade extra (fora da rota)'}),
        el('p', {classe: 'small text-muted mt-2',
          texto: 'Para registrar uma limpeza ou vistoria fora do horário da rota.'}),
        sel,
        el('button', {type: 'button', classe: 'btn btn-outline-primary fc-app-acao w-100 mt-2',
          onclick: function () { abrirExecucao(null, dados.versoes[sel.value]); }},
          ['Fazer atividade extra'])]));
    }
    secPonto.appendChild(el('button', {type: 'button', classe: 'btn btn-outline-secondary w-100',
      onclick: function () { history.replaceState(null, '', '/app/turno'); mostrarLista(); }},
      ['Ver o turno inteiro']));
  }

  // ── Preventivas deste ponto (Fase 5) ──────────────────────────────────
  function cartaoPreventivas(lista) {
    var cartao = el('div', {classe: 'fc-cartao mb-3 border-primary'},
      [el('h2', {classe: 'h6 fw-bold', texto: 'Preventiva a fazer aqui'})]);
    lista.forEach(function (x) {
      cartao.appendChild(el('div', {classe: 'fc-app-item'}, [
        el('div', {classe: 'd-flex align-items-center gap-2'}, [
          el('span', {classe: 'fw-semibold', texto: x.titulo}),
          x.atrasada ? el('span', {classe: 'badge fc-sit fc-sit-atrasada', texto: 'Atrasada'}) : null,
          x.minha ? el('span', {classe: 'badge text-bg-light', texto: 'Sua'}) : null]),
        el('span', {classe: 'small text-muted',
                    texto: x.numero + ' · vence ' + x.vence + ' · ' + (dados.versoes[x.versao] || {}).modelo}),
        el('button', {type: 'button', classe: 'btn btn-primary fc-app-acao w-100 mt-2',
          onclick: function () { abrirExecucao(null, dados.versoes[x.versao], x); }},
          [el('i', {classe: 'bi bi-tools'}), ' Fazer a preventiva'])]));
    });
    return cartao;
  }

  // ── Avisos do público pelo QR (Fase 4B) ───────────────────────────────
  function cartaoOcorrencias(lista) {
    var cartao = el('div', {classe: 'fc-cartao mb-3 border-warning'},
      [el('h2', {classe: 'h6 fw-bold', texto: 'Avisos do público aqui'})]);
    lista.forEach(function (o) {
      var linha = el('div', {classe: 'fc-app-item'}, [
        el('span', {classe: 'fw-semibold', texto: o.tipo + (o.atrasada ? ' · fora do prazo' : '')}),
        el('span', {classe: 'small text-muted', texto: 'às ' + o.hora + (o.texto ? ' · "' + o.texto + '"' : '') +
                                                     (o.prazo ? ' · prazo ' + o.prazo : '')})]);
      var barra = el('div', {classe: 'd-flex gap-2 mt-2'});
      function agir(acao, botao) {
        botao.disabled = true;
        fetch('/app/api/ocorrencias/' + o.id + '/' + acao, {method: 'POST',
          headers: {'Content-Type': 'application/json'}, body: '{}'})
          .then(function (r) { return r.json().then(function (x) { return {ok: r.ok, x: x}; }); })
          .then(function (res) {
            if (!res.ok) { botao.disabled = false; dizer(res.x.error || 'Não foi possível.', 'danger'); return; }
            o.status = res.x.status;
            if (o.status === 'resolvida') {
              dados.ocorrencias = dados.ocorrencias.filter(function (x) { return x.id !== o.id; });
              linha.remove();
              dizer('Aviso resolvido. Quem avisou vê a resposta pelo QR.', 'success');
            } else {
              botao.textContent = 'Em atendimento';
            }
          }, function () { botao.disabled = false; dizer('Sem sinal: tente de novo.', 'warning'); });
      }
      if (o.status === 'aberta') {
        var b1 = el('button', {type: 'button', classe: 'btn btn-outline-primary flex-fill', texto: 'Vou atender'});
        b1.addEventListener('click', function () { agir('atender', b1); });
        barra.appendChild(b1);
      }
      var b2 = el('button', {type: 'button', classe: 'btn btn-success flex-fill', texto: 'Resolvido'});
      b2.addEventListener('click', function () { agir('resolver', b2); });
      barra.appendChild(b2);
      linha.appendChild(barra);
      cartao.appendChild(linha);
    });
    return cartao;
  }

  // ── O checklist ───────────────────────────────────────────────────────
  function campoDoItem(it) {
    var nome = 'r_' + it.codigo;
    var titulo = el('div', {classe: 'fw-semibold mb-1', texto: it.texto + (it.obrigatorio ? ' *' : '')});
    var corpo;
    function botoes(opcoes) {
      return el('div', {classe: 'd-flex gap-2', role: 'radiogroup', 'aria-label': it.texto},
        opcoes.map(function (o) {
          var id = nome + '_' + o[0];
          return el('label', {classe: 'fc-opcao flex-fill', for: id}, [
            el('input', {type: 'radio', name: nome, id: id, value: o[0], classe: 'fc-opcao-radio'}),
            el('span', {texto: o[1]})]);
        }));
    }
    if (it.tipo === 'sim_nao') corpo = botoes([['sim', 'Sim'], ['nao', 'Não']]);
    else if (it.tipo === 'conforme') corpo = botoes([['conforme', 'Conforme'], ['nao_conforme', 'Não conforme']]);
    else if (it.tipo === 'numero') {
      var faixa = (it.minimo !== null && it.minimo !== undefined ? 'de ' + it.minimo : '') +
                  (it.maximo !== null && it.maximo !== undefined ? ' até ' + it.maximo : '');
      corpo = el('div', {}, [el('input', {classe: 'form-control form-control-lg', name: nome,
        inputmode: 'decimal', 'aria-label': it.texto}),
        faixa ? el('div', {classe: 'form-text', texto: 'Aceitável: ' + faixa.trim()}) : null]);
    } else if (it.tipo === 'escolha') {
      corpo = el('select', {classe: 'form-select form-select-lg', name: nome, 'aria-label': it.texto},
        [el('option', {value: '', texto: 'Escolha'})].concat(
          (it.opcoes || []).map(function (o) { return el('option', {value: o, texto: o}); })));
    } else if (it.tipo === 'data_hora') {
      corpo = el('input', {type: 'datetime-local', classe: 'form-control form-control-lg',
                           name: nome, 'aria-label': it.texto});
    } else {
      corpo = el('input', {classe: 'form-control form-control-lg', name: nome, maxlength: '300',
                           'aria-label': it.texto});
    }
    // "Como fazer" e a foto de como deve ficar, cadastrados no checklist.
    var ajuda = [];
    if (it.como_fazer) ajuda.push(el('div', {classe: 'small fc-como-fazer', texto: it.como_fazer}));
    if (it.foto_ref_url) {
      ajuda.push(el('img', {classe: 'fc-ref', src: it.foto_ref_url, loading: 'lazy',
                            alt: 'Como deve ficar: ' + it.texto}));
    }
    var bloco = el('div', {classe: 'fc-cartao mb-2 fc-item', 'data-codigo': it.codigo},
                   [titulo].concat(ajuda, [corpo]));
    if (it.exige_foto) bloco.appendChild(campoFoto('item:' + it.codigo, 'Foto deste item *'));
    return bloco;
  }

  function campoFoto(chave, rotulo) {
    var id = 'f_' + chave.replace(/[^a-z0-9]/gi, '_');
    var estado = el('span', {classe: 'small text-muted', texto: 'Nenhuma foto ainda.'});
    var entrada = el('input', {type: 'file', accept: 'image/*', capture: 'environment', id: id,
                               classe: 'fc-foto-input', 'data-foto': chave});
    entrada.addEventListener('change', function () {
      estado.textContent = entrada.files.length ? 'Foto pronta.' : 'Nenhuma foto ainda.';
      estado.className = 'small ' + (entrada.files.length ? 'text-success fw-semibold' : 'text-muted');
    });
    return el('div', {classe: 'mt-2 fc-foto'}, [
      el('div', {classe: 'form-label small fw-semibold', texto: rotulo}),
      entrada,
      el('label', {classe: 'btn btn-outline-primary fc-app-acao w-100', for: id},
         [el('i', {classe: 'bi bi-camera'}), ' Tirar foto']),
      estado]);
  }

  function valores(form) {
    var r = {};
    [].slice.call(form.elements).forEach(function (c) {
      if (!c.name || c.name.indexOf('r_') !== 0) return;
      if ((c.type === 'radio' || c.type === 'checkbox') && !c.checked) return;
      r[c.name.slice(2)] = c.value;
    });
    return r;
  }

  function aplicarCondicoes(form, itens) {
    var r = valores(form);
    itens.forEach(function (it) {
      if (!it.mostrar_se) return;
      var bloco = form.querySelector('[data-codigo="' + it.codigo + '"]');
      var ver = String(r[it.mostrar_se.codigo] || '').toLowerCase() ===
                String(it.mostrar_se.valor || '').toLowerCase();
      if (bloco) bloco.hidden = !ver;
    });
  }

  function abrirExecucao(tarefa, versao, prev) {
    if (!versao) { dizer('Checklist não encontrado. Recarregue com sinal.', 'warning'); return; }
    var codigo = tarefa ? tarefa.ponto : (leitura && leitura.ponto);
    if (!leitura || leitura.ponto !== codigo) lerNoServidor(codigo);
    var inicio = new Date().toISOString();
    secLista.hidden = true; secPonto.hidden = true; secExec.hidden = false;
    limpar(secExec);
    dizer('');
    var p = dados.pontos[codigo] || {nome: tarefa ? tarefa.ponto_nome : ''};
    secExec.appendChild(el('h1', {classe: 'fc-titulo', texto: versao.modelo}));
    secExec.appendChild(el('p', {classe: 'fc-sub', texto: p.nome + (tarefa ? ' · ' + tarefa.hora : prev ? ' · preventiva ' + prev.numero : ' · atividade extra')}));
    var docs = versao.documentos || [];
    if (versao.procedimento || docs.length) {
      // O resumo do POP/FIT, escrito pela gestão; o documento completo abre à parte.
      secExec.appendChild(el('details', {classe: 'fc-cartao mb-2 fc-procedimento'}, [
        el('summary', {classe: 'fw-semibold', texto: 'Como fazer (resumo do POP)'}),
        versao.procedimento ? el('div', {classe: 'mt-2 fc-texto-livre', texto: versao.procedimento}) : null,
        docs.length ? el('div', {classe: 'mt-2 d-flex flex-wrap gap-2'}, docs.map(function (d) {
          return el('a', {classe: 'btn btn-sm btn-outline-primary', href: d.url, target: '_blank',
                          rel: 'noopener', texto: 'Ver o POP completo: ' + d.nome});
        })) : null]));
    }
    var form = el('form', {novalidate: true});
    if (versao.foto_antes) form.appendChild(el('div', {classe: 'fc-cartao mb-2'}, [campoFoto('antes', 'Foto de ANTES *')]));
    versao.itens.forEach(function (it) { form.appendChild(campoDoItem(it)); });
    form.appendChild(el('div', {classe: 'fc-cartao mb-2'}, [
      el('label', {classe: 'form-label small fw-semibold', for: 'obs', texto: 'Observação (opcional)'}),
      el('textarea', {classe: 'form-control', id: 'obs', name: 'observacao', rows: '2'})]));
    if (versao.foto_depois) form.appendChild(el('div', {classe: 'fc-cartao mb-2'}, [campoFoto('depois', 'Foto de DEPOIS *')]));
    var confirmar = el('button', {type: 'submit', classe: 'btn btn-primary btn-lg w-100 fc-app-acao'},
      [el('i', {classe: 'bi bi-check-circle'}), ' Confirmar']);
    form.appendChild(confirmar);
    form.appendChild(el('button', {type: 'button', classe: 'btn btn-link w-100 mt-1',
      onclick: function () { codigo ? abrirPonto(codigo) : mostrarLista(); }}, ['Cancelar']));
    form.addEventListener('change', function () { aplicarCondicoes(form, versao.itens); });
    aplicarCondicoes(form, versao.itens);
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      enviar(form, tarefa, versao, codigo, inicio, confirmar, prev);
    });
    secExec.appendChild(form);
    window.scrollTo(0, 0);
  }

  function faltando(form, versao) {
    var r = valores(form);
    for (var i = 0; i < versao.itens.length; i++) {
      var it = versao.itens[i];
      var bloco = form.querySelector('[data-codigo="' + it.codigo + '"]');
      if (bloco && bloco.hidden) continue;
      if (it.obrigatorio && !String(r[it.codigo] || '').trim()) return 'Responda: "' + it.texto + '".';
      if (it.exige_foto) {
        var f = form.querySelector('[data-foto="item:' + it.codigo + '"]');
        if (f && !f.files.length) return 'Tire a foto de "' + it.texto + '".';
      }
    }
    var antes = form.querySelector('[data-foto="antes"]');
    if (antes && !antes.files.length) return 'Tire a foto de ANTES.';
    var depois = form.querySelector('[data-foto="depois"]');
    if (depois && !depois.files.length) return 'Tire a foto de DEPOIS.';
    return null;
  }

  function enviar(form, tarefa, versao, codigo, inicio, botao, prev) {
    var erro = faltando(form, versao);
    if (erro) { dizer(erro, 'warning'); return; }
    botao.disabled = true;
    var respostas = valores(form);
    // Respostas de perguntas escondidas não vão (a condição não se cumpriu).
    versao.itens.forEach(function (it) {
      var b = form.querySelector('[data-codigo="' + it.codigo + '"]');
      if (b && b.hidden) delete respostas[it.codigo];
    });
    var corpo = {
      envio_id: novoId(), ponto: codigo, respostas: respostas,
      observacao: form.querySelector('[name=observacao]').value,
      selo_leitura: leitura && leitura.ponto === codigo ? leitura.selo : null,
      lido_em: leitura && leitura.ponto === codigo ? leitura.lido_em : inicio,
      concluida_em: new Date().toISOString(),
      sem_sinal: !(leitura && leitura.selo)
    };
    if (tarefa) corpo.tarefa_id = tarefa.id; else corpo.versao_id = versao.id;
    if (prev) corpo.chamado_id = prev.id;
    var entradas = [].slice.call(form.querySelectorAll('[data-foto]'));
    var reduzir = window.TrinoFoto ? window.TrinoFoto.reduzirTodos : function (fs) { return Promise.resolve(fs); };
    Promise.all(entradas.map(function (e) {
      return reduzir([].slice.call(e.files || [])).then(function (fs) {
        return fs.map(function (f) { return {campo: e.getAttribute('data-foto'), arquivo: f}; });
      });
    })).then(function (listas) {
      var fotos = [].concat.apply([], listas);
      return mandar(corpo, fotos).then(function (res) { concluir(res, tarefa, codigo, corpo, fotos, botao, prev); });
    });
  }

  function formulario(corpo, fotos) {
    var fd = new FormData();
    fd.append('corpo', JSON.stringify(corpo));
    fotos.forEach(function (f) { fd.append(f.campo, f.arquivo, f.arquivo.name || 'foto.jpg'); });
    return fd;
  }

  function mandar(corpo, fotos) {
    if (navigator.onLine === false) return Promise.resolve({conexao: true});
    return fetch('/app/api/execucoes', {method: 'POST', body: formulario(corpo, fotos)})
      .then(function (r) {
        if (window.TrinoFila && window.TrinoFila.ehFalhaDeConexao(r)) return {conexao: true};
        return r.json().then(function (x) { return {ok: r.ok, x: x}; },
                             function () { return {conexao: true}; });
      }, function () { return {conexao: true}; });
  }

  function concluir(res, tarefa, codigo, corpo, fotos, botao, prev) {
    function tirarPreventiva() {
      if (!prev) return;
      dados.preventivas = (dados.preventivas || []).filter(function (x) { return x.id !== prev.id; });
    }
    if (res.conexao) {
      if (!window.TrinoFila) {
        botao.disabled = false;
        dizer('Sem sinal, e este aparelho não guarda envios. Tente de novo com sinal.', 'danger');
        return;
      }
      // Sem sinal: a hora da conclusão é a do aparelho, e a execução vai
      // marcada assim.
      corpo.sem_sinal = true;
      window.TrinoFila.guardar({tipo: 'execucao', rotulo: (tarefa ? tarefa.hora + ' · ' : '') +
                                 (dados.pontos[codigo] || {}).nome,
                                tarefa_id: tarefa ? tarefa.id : null,
                                corpo: corpo, fotos: fotos}).then(function () {
        if (tarefa) marcarFeita(tarefa.id, 'Guardada no aparelho');
        tirarPreventiva();
        dizer('Sem sinal: a execução ficou guardada no aparelho e sobe sozinha quando o sinal voltar.', 'warning');
        mostrarLista();
      }, function () {
        botao.disabled = false;
        dizer('Sem sinal, e não foi possível guardar. Não feche a tela; tente de novo.', 'danger');
      });
      return;
    }
    if (!res.ok) {
      botao.disabled = false;
      dizer(res.x.error || 'Não foi possível registrar.', 'danger');
      return;
    }
    if (tarefa) { tarefa.status = res.x.status; }
    tirarPreventiva();
    dizer('Registrado: ' + res.x.situacao + '.' +
          (res.x.nao_conformes ? ' ' + res.x.nao_conformes + ' item(ns) não conforme(s): chamado aberto para a gestão.' : ''),
          res.x.nao_conformes ? 'warning' : 'success');
    if (codigo) abrirPonto(codigo); else mostrarLista();
  }

  // ── Não realizada ─────────────────────────────────────────────────────
  function abrirNaoRealizada(t) {
    secLista.hidden = true; secPonto.hidden = true; secExec.hidden = false;
    limpar(secExec);
    secExec.appendChild(el('h1', {classe: 'fc-titulo', texto: 'Não deu para fazer'}));
    secExec.appendChild(el('p', {classe: 'fc-sub', texto: t.hora + ' · ' + t.ponto_nome}));
    var form = el('form', {});
    var motivos = el('div', {classe: 'fc-cartao mb-2', role: 'radiogroup', 'aria-label': 'Motivo'});
    Object.keys(dados.motivos).forEach(function (k) {
      motivos.appendChild(el('label', {classe: 'd-flex gap-2 py-2'}, [
        el('input', {type: 'radio', name: 'motivo', value: k}), el('span', {texto: dados.motivos[k]})]));
    });
    form.appendChild(motivos);
    form.appendChild(el('div', {classe: 'fc-cartao mb-2'}, [
      el('label', {classe: 'form-label small fw-semibold', for: 'nrtexto', texto: 'O que aconteceu'}),
      el('input', {classe: 'form-control', id: 'nrtexto', name: 'texto', maxlength: '300'}),
      el('label', {classe: 'd-flex gap-2 mt-2'}, [el('input', {type: 'checkbox', name: 'chamado'}),
        el('span', {texto: 'Abrir chamado para resolver'})])]));
    var botao = el('button', {type: 'submit', classe: 'btn btn-primary btn-lg w-100 fc-app-acao',
                              texto: 'Registrar'});
    form.appendChild(botao);
    form.appendChild(el('button', {type: 'button', classe: 'btn btn-link w-100',
      onclick: function () { leitura ? abrirPonto(leitura.ponto) : mostrarLista(); }}, ['Cancelar']));
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var m = form.querySelector('[name=motivo]:checked');
      if (!m) { dizer('Escolha o motivo.', 'warning'); return; }
      botao.disabled = true;
      var corpo = {motivo: m.value, texto: form.querySelector('[name=texto]').value,
                   abrir_chamado: form.querySelector('[name=chamado]').checked};
      fetch('/app/api/tarefas/' + t.id + '/nao-realizada', {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corpo)})
        .then(function (r) { return r.json().then(function (x) { return {ok: r.ok, x: x}; }); })
        .then(function (res) {
          if (!res.ok) { botao.disabled = false; dizer(res.x.error || 'Não foi possível registrar.', 'danger'); return; }
          t.status = 'nao_realizada';
          dizer('Registrado como não realizada.' + (res.x.chamado_id ? ' Chamado aberto.' : ''), 'success');
          leitura ? abrirPonto(leitura.ponto) : mostrarLista();
        }, function () {
          botao.disabled = false;
          dizer('Sem sinal: "não realizada" precisa de sinal para avisar a gestão. Tente de novo quando voltar.', 'warning');
        });
    });
    secExec.appendChild(form);
  }

  // A fila subiu uma execução guardada: só AQUELA tarefa deixa de ser
  // "guardada no aparelho" — as outras ainda estão na fila.
  window.addEventListener('trino-fila:enviado', function (ev) {
    if (!ev.detail || ev.detail.tipo !== 'execucao' || !ev.detail.tarefa_id) return;
    var f = feitasNoAparelho();
    if (!(ev.detail.tarefa_id in f)) return;
    f[ev.detail.tarefa_id] = 'Enviada';
    try { localStorage.setItem(CHAVE_LOCAL, JSON.stringify(f)); } catch (e) {}
  });

  var params = new URLSearchParams(location.search);
  var ponto = params.get('ponto');
  var comCamera = params.get('lido') === 'camera';
  if (comCamera && window.history && history.replaceState) {
    // Recarregar a tela não vale como uma nova leitura do QR.
    params.delete('lido');
    history.replaceState(null, '', location.pathname + '?' + params.toString());
  }
  if (ponto) abrirPonto(ponto, comCamera); else mostrarLista();
})();
