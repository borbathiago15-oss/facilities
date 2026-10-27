// "Meu turno" — o aplicativo de campo executando a rota (Fase 4A; redesenho
// do bloco do técnico, etapa 2, decisões do dono de 22/10/2026).
//
// A tela chega com TUDO que precisa num JSON (#turno-dados): os locais da
// carteira (com o QR da entrada e a chegada de hoje), as tarefas de hoje, os
// checklists delas e os pontos pelo código do QR. Por isso ela abre e
// funciona SEM internet (o service worker guarda a cópia).
//
//   /app/turno                → um cartão por local ("ler o QR da entrada" /
//                               "Você está no X — Ver o turno")
//   /app/turno?local=<id>     → o turno de hoje DAQUELE local
//   /app/turno?ponto=<QR>     → QR da ENTRADA: registra a chegada e abre o
//                               turno do local; QR comum: abre DIRETO no que
//                               é para fazer agora ali (foto do antes → um
//                               check por item → foto do depois → Pronto)
//
// Com sinal, a hora da leitura é a do SERVIDOR (o selo de /app/api/leitura).
// Sem sinal, vale a hora do celular, e a execução vai marcada "feito sem
// sinal" (R4); o envio fica na fila do aparelho (fila-offline.js) e sobe
// sozinho quando o sinal volta. O mesmo envio nunca vira duas execuções
// (envio_id). O servidor é a verdade: quando ele já registrou a tarefa, a
// marca local ("guardada"/"enviada") some (22/10).
(function () {
  'use strict';
  var raiz = document.getElementById('turno-app');
  if (!raiz) return;
  var dados = JSON.parse(document.getElementById('turno-dados').textContent);
  var URL_LER_QR = raiz.getAttribute('data-ler-qr') || '/app/ler-qr';
  var secLista = document.getElementById('turno-lista');
  var secPonto = document.getElementById('turno-ponto');
  var secExec = document.getElementById('turno-execucao');
  var aviso = document.getElementById('turno-aviso');
  var leitura = null;   // {ponto, selo, lido_em, pronta (Promise)}
  var CHAVE_LOCAL = 'trino-turno-feitas-' + dados.usuario;
  var CHAVE_CHEGADA = 'trino-turno-chegada-' + dados.usuario;
  // Troca de área (27/10/2026): o motivo escolhido antes de ir ler o QR da
  // outra área sobrevive à ida e volta do leitor (sessionStorage), por 30 min.
  var CHAVE_TROCA = 'trino-turno-troca-' + dados.usuario;
  var VALIDADE_TROCA_MS = 30 * 60000;
  var verColegas = false;
  var materiaisPorLocal = {};

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
  function mostrarSo(sec) {
    [secLista, secPonto, secExec].forEach(function (s) { s.hidden = s !== sec; });
    limpar(sec);
    window.scrollTo(0, 0);
    return sec;
  }
  function hora(iso) {
    var d = iso ? new Date(iso) : new Date();
    return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
  }
  function hojeLocal() {
    var d = new Date();
    return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
  }
  function novoId() {
    if (window.TrinoFila && window.TrinoFila.novoId) return window.TrinoFila.novoId();
    return 'e' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }
  function lerJson(chave) {
    try { return JSON.parse(localStorage.getItem(chave) || '{}'); } catch (e) { return {}; }
  }
  function gravarJson(chave, v) { try { localStorage.setItem(chave, JSON.stringify(v)); } catch (e) {} }
  function feitasNoAparelho() { return lerJson(CHAVE_LOCAL); }
  function marcarFeita(id, rotulo) { var f = feitasNoAparelho(); f[id] = rotulo; gravarJson(CHAVE_LOCAL, f); }
  function desmarcarFeita(id) {
    var f = feitasNoAparelho();
    if (!(id in f)) return;
    delete f[id];
    gravarJson(CHAVE_LOCAL, f);
  }
  function irParaLerQr() { location.assign(URL_LER_QR); }
  function lerTroca() {
    try {
      var t = JSON.parse(sessionStorage.getItem(CHAVE_TROCA) || 'null');
      return t && Date.now() - t.em < VALIDADE_TROCA_MS ? t : null;
    } catch (e) { return null; }
  }
  function guardarTroca(t) {
    try { sessionStorage.setItem(CHAVE_TROCA, JSON.stringify(t)); } catch (e) {}
  }
  function limparTroca() { try { sessionStorage.removeItem(CHAVE_TROCA); } catch (e) {} }
  function botaoLerQr(classe) {
    return el('a', {classe: classe || 'btn btn-primary btn-lg w-100 fc-app-acao', href: URL_LER_QR},
      [el('i', {classe: 'bi bi-qr-code-scan'}), ' Ler o QR']);
  }

  // ── Locais e chegada ──────────────────────────────────────────────────
  function localDe(id) {
    return (dados.locais || []).filter(function (l) { return String(l.id) === String(id); })[0] || null;
  }
  // A chegada de hoje no local: a do servidor ou a guardada no aparelho (sem
  // sinal) no mesmo dia.
  function chegadaDe(local) {
    if (!local) return null;
    if (local.chegada) return local.chegada;
    var m = lerJson(CHAVE_CHEGADA)[local.id];
    return m && m.data === hojeLocal() ? m : null;
  }
  function marcarChegadaLocal(localId, h) {
    var c = lerJson(CHAVE_CHEGADA);
    c[localId] = {hora: h, data: hojeLocal(), guardada: true};
    gravarJson(CHAVE_CHEGADA, c);
  }
  function exigeChegada(local) { return !!(local && local.entrada && !chegadaDe(local)); }

  // A situação AGORA (a do servidor envelhece com a tela aberta).
  function situacao(t) {
    // O servidor é a verdade: quando ele já registrou a tarefa, a marca local
    // ("guardada" ou "enviada") perdeu a razão de existir e some.
    if (t.status !== 'prevista') {
      desmarcarFeita(t.id);
      return {cod: t.status, rotulo: dados.situacoes[t.status]};
    }
    var guardada = feitasNoAparelho()[t.id];
    if (guardada) return {cod: 'guardada', rotulo: guardada};
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
  function emAberto(t) {
    var s = situacao(t).cod;
    return s === 'prevista' || s === 'no_horario' || s === 'atrasada';
  }
  function tarefasDoLocal(localId) {
    return dados.tarefas.filter(function (t) { return String(t.local_id) === String(localId); })
      .sort(function (a, b) { return Date.parse(a.previsto) - Date.parse(b.previsto); });
  }
  // A próxima da rota depois de ``feita``: a atrasada ou a da hora primeiro,
  // senão a primeira que ainda vai chegar.
  // Só as minhas tarefas (27/10/2026); as dos colegas, num toque. Sem
  // nenhuma minha no local (o supervisor), todas.
  function tarefasVisiveis(localId) {
    var doLocal = tarefasDoLocal(localId);
    var minhas = doLocal.filter(function (t) { return t.minha; });
    return {lista: minhas.length && !verColegas ? minhas : doLocal, minhas: minhas.length,
            todas: doLocal.length};
  }

  function proximaTarefa(localId, feita) {
    var abertas = tarefasDoLocal(localId).filter(function (t) {
      return emAberto(t) && (!feita || t.id !== feita.id);
    });
    return abertas.filter(podeFazer)[0] || abertas[0] || null;
  }

  // ── Tela: um cartão por local ─────────────────────────────────────────
  function mostrarLocais() {
    var sec = mostrarSo(secLista);
    sec.appendChild(el('h1', {classe: 'fc-titulo', texto: 'Meu turno'}));
    sec.appendChild(el('p', {classe: 'fc-sub', texto: 'Escolha o local, ou leia o QR da entrada ao chegar.'}));
    sec.appendChild(botaoLerQr('btn btn-primary btn-lg w-100 fc-app-acao mb-3'));
    if (!(dados.locais || []).length) {
      sec.appendChild(el('div', {classe: 'fc-cartao fc-vazio',
        texto: 'Você ainda não tem local liberado. Peça ao seu supervisor ou à gestão.'}));
      return;
    }
    dados.locais.forEach(function (l) { sec.appendChild(cartaoLocal(l)); });
  }
  function cartaoLocal(l) {
    var n = tarefasDoLocal(l.id);
    var abertas = n.filter(emAberto).length;
    var ch = chegadaDe(l);
    var sub = n.length ? abertas + ' de ' + n.length + (n.length > 1 ? ' tarefas' : ' tarefa') + ' por fazer'
                       : 'Nenhuma tarefa da rota hoje';
    if (l.entrada && !ch) {
      return el('a', {classe: 'fc-cartao fc-local-turno mb-2', href: URL_LER_QR, 'data-local': l.id,
                      'data-situacao': 'sem_chegada'}, [
        el('span', {classe: 'fc-local-turno-nome', texto: l.nome}),
        el('span', {classe: 'fc-local-turno-sub', texto: (n.length ? n.length + (n.length > 1 ? ' tarefas' : ' tarefa') + ' hoje · ' : '') +
                                                          'Ao chegar, leia o QR da entrada (' + l.entrada_nome + ')'}),
        el('span', {classe: 'fc-local-turno-acao'}, [el('i', {classe: 'bi bi-qr-code-scan'}), ' Ler o QR da entrada'])]);
    }
    var cartao = el('a', {classe: 'fc-cartao fc-local-turno mb-2' + (ch ? ' fc-local-turno-aqui' : ''),
                          href: '/app/turno?local=' + l.id, 'data-local': l.id,
                          'data-situacao': ch ? 'chegou' : 'sem_entrada'}, [
      el('span', {classe: 'fc-local-turno-nome', texto: ch ? 'Você está no ' + l.nome : l.nome}),
      el('span', {classe: 'fc-local-turno-sub', texto: (ch ? 'Chegou às ' + ch.hora + ' · ' : '') + sub}),
      el('span', {classe: 'fc-local-turno-acao'}, [el('i', {classe: 'bi bi-list-check'}), ' Ver o turno'])]);
    cartao.addEventListener('click', function (ev) {
      ev.preventDefault();
      history.pushState(null, '', '/app/turno?local=' + l.id);
      mostrarTurno(l.id);
    });
    return cartao;
  }

  // ── Tela: o turno de hoje num local ───────────────────────────────────
  // ``n``: o número da tarefa no roteiro do dia (1, 2, 3…); ``proxima``: a
  // que a pessoa deve fazer agora — fica destacada.
  function cartaoTarefa(t, n, proxima) {
    var s = situacao(t);
    var v = dados.versoes[t.versao] || {};
    return el('div', {classe: 'fc-app-item' + (proxima ? ' fc-proxima' : ''), 'data-tarefa': t.id}, [
      el('div', {classe: 'd-flex align-items-center gap-2 flex-wrap'}, [
        n ? el('span', {classe: 'fc-roteiro-n', texto: String(n), 'aria-label': 'Passo ' + n + ' do roteiro'}) : null,
        el('span', {classe: 'fs-5 fw-bold', texto: t.hora}),
        proxima ? el('span', {classe: 'badge text-bg-danger', texto: 'Próxima'}) : null,
        el('span', {classe: 'badge fc-sit fc-sit-' + s.cod, texto: s.rotulo}),
        t.minha ? el('span', {classe: 'badge text-bg-light', texto: 'Sua'}) : null
      ]),
      el('span', {classe: 'fw-semibold', texto: t.ambiente + ' · ' + t.ponto_nome}),
      el('span', {classe: 'small text-muted',
                  texto: (v.modelo || t.rota) + (t.tempo_previsto_min ? ' · ' + t.tempo_previsto_min + ' min' : '') +
                         (t.escalado && !t.minha ? ' · escala: ' + t.escalado : '')})
    ]);
  }

  function mostrarTurno(localId, mensagem) {
    var l = localDe(localId);
    var sec = mostrarSo(secLista);
    if (!l) {
      sec.appendChild(el('div', {classe: 'alert alert-warning', texto: 'Este local não está entre os seus.'}));
      sec.appendChild(el('button', {type: 'button', classe: 'btn btn-outline-secondary w-100 fc-app-acao',
        onclick: mostrarLocais}, ['Ver meus locais']));
      return;
    }
    if (exigeChegada(l)) { telaConfirmeChegada(l); return; }
    var ch = chegadaDe(l);
    if (mensagem) sec.appendChild(el('div', {classe: 'alert alert-success', role: 'status', texto: mensagem}));
    sec.appendChild(el('h1', {classe: 'fc-titulo', texto: ch ? 'Você está no ' + l.nome : l.nome}));
    sec.appendChild(el('p', {classe: 'fc-sub', texto: (ch ? 'Chegou às ' + ch.hora + (ch.guardada ? ' (chegada guardada no aparelho)' : '') + ' · ' : '') + 'Tarefas de hoje'}));
    sec.appendChild(botaoLerQr('btn btn-primary btn-lg w-100 fc-app-acao mb-2'));
    // Ir a outra área antes da ordem da rota: pergunta o motivo e manda ler
    // o QR da área (adiantar uma da rota ou limpar uma fora da rota).
    sec.appendChild(el('button', {type: 'button', classe: 'btn btn-outline-primary w-100 fc-app-acao mb-3',
      'data-trocar-area': '1', onclick: function () {
        folhaTroca('Ir para outra área', function (troca) {
          if (!troca) return;
          troca.em = Date.now();
          guardarTroca(troca);
          irParaLerQr();
        });
      }}, [el('i', {classe: 'bi bi-arrow-left-right'}), ' Ir para outra área']));
    var visiveis = tarefasVisiveis(l.id);
    var tarefas = visiveis.lista;
    var proxima = proximaTarefa(l.id, null);
    var avisos = (dados.ocorrencias || []).filter(function (o) { return (dados.pontos[o.ponto] || {}).local_id === l.id; });
    if (avisos.length) sec.appendChild(cartaoChecarAvisos(avisos));
    var prevs = (dados.preventivas || []).filter(function (x) { return (dados.pontos[x.ponto] || {}).local_id === l.id; });
    if (prevs.length) {
      sec.appendChild(el('div', {classe: 'alert alert-info',
        texto: prevs.length + ' preventiva(s) em aberto. Leia o QR do ponto para fazer o checklist.'}));
    }
    if (!tarefas.length) {
      sec.appendChild(el('div', {classe: 'fc-cartao fc-vazio', texto: 'Nenhuma tarefa de rota para hoje aqui.'}));
    } else {
      var cartao = el('div', {classe: 'fc-cartao', id: 'turno-itens'});
      tarefas.forEach(function (t, i) { cartao.appendChild(cartaoTarefa(t, i + 1, t === proxima)); });
      sec.appendChild(cartao);
      if (visiveis.minhas && visiveis.minhas < visiveis.todas) {
        sec.appendChild(el('button', {type: 'button', classe: 'btn btn-link w-100 mt-1', onclick: function () {
          verColegas = !verColegas;
          mostrarTurno(l.id);
        }}, [verColegas ? 'Ver só as minhas tarefas' :
                          'Ver também as dos colegas (' + (visiveis.todas - visiveis.minhas) + ')']));
      }
      sec.appendChild(el('p', {classe: 'small text-muted mt-2',
        texto: 'Para fazer uma tarefa, leia o QR do ponto: o checklist abre na hora.'}));
    }
    sec.appendChild(el('button', {type: 'button', classe: 'btn btn-link w-100 mt-2',
      onclick: function () { history.replaceState(null, '', '/app/turno'); mostrarLocais(); }},
      ['Outro local']));
    atualizarTurno(l.id);
  }

  // Com sinal, o servidor diz o que já foi feito (por esta pessoa ou outra)
  // e a chegada de hoje; a lista se atualiza no lugar.
  function atualizarTurno(localId) {
    if (navigator.onLine === false || !window.fetch) return;
    fetch('/app/api/turno?local=' + encodeURIComponent(localId), {credentials: 'same-origin'})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (x) {
        if (!x || !x.tarefas) return;
        var l = localDe(localId);
        if (l && x.chegada) l.chegada = x.chegada;
        var porId = {};
        dados.tarefas.forEach(function (t) { porId[t.id] = t; });
        var mudou = false;
        x.tarefas.forEach(function (nt) {
          var t = porId[nt.id];
          if (t && t.status !== nt.status) { t.status = nt.status; mudou = true; }
        });
        if (!mudou) return;
        var cartao = document.getElementById('turno-itens');
        if (!cartao || secLista.hidden) return;
        limpar(cartao);
        var tarefas = tarefasVisiveis(localId).lista;
        var proxima = proximaTarefa(localId, null);
        tarefas.forEach(function (t, i) { cartao.appendChild(cartaoTarefa(t, i + 1, t === proxima)); });
      })
      .catch(function () {});
  }

  // ── Tela: "Confirme a chegada" ────────────────────────────────────────
  function telaConfirmeChegada(local) {
    var sec = mostrarSo(secPonto);
    sec.appendChild(el('div', {classe: 'fc-cartao fc-chegada text-center'}, [
      el('i', {classe: 'bi bi-door-open fc-chegada-icone', 'aria-hidden': 'true'}),
      el('h1', {classe: 'fc-titulo', texto: 'Confirme a chegada'}),
      el('p', {classe: 'fc-sub', texto: 'Leia o QR da entrada do ' + local.nome +
                                          (local.entrada_nome ? ' (' + local.entrada_nome + ')' : '') + '.'}),
      botaoLerQr()]));
  }

  // ── O ponto (depois de ler o QR) ──────────────────────────────────────
  // O selo (hora do servidor) é a prova de que a pessoa leu o QR no ponto: só
  // é pedido quando a CÂMERA leu agora (``lido=camera`` vindo do leitor). O
  // link de um aviso, o código digitado e a página recarregada abrem o ponto,
  // mas a execução fica com a hora do celular — marcada para a gestão.
  // GPS na leitura do QR (27/10/2026): a posição do celular SÓ neste
  // instante, para mostrar que a leitura foi no local. Nunca trava: sem
  // resposta em 10 s, sem permissão ou sem GPS, a leitura segue "sem GPS".
  function obterGps() {
    if (!navigator.geolocation) return Promise.resolve({erro: 'indisponivel'});
    return new Promise(function (ok) {
      var feito = false;
      var limite = setTimeout(function () { if (!feito) { feito = true; ok({erro: 'sem_resposta'}); } }, 10000);
      navigator.geolocation.getCurrentPosition(function (pos) {
        if (feito) return;
        feito = true; clearTimeout(limite);
        ok({lat: pos.coords.latitude, lng: pos.coords.longitude,
            precisao: Math.round(pos.coords.accuracy || 0)});
      }, function (e) {
        if (feito) return;
        feito = true; clearTimeout(limite);
        ok({erro: e && e.code === 1 ? 'negado' : 'indisponivel'});
      }, {enableHighAccuracy: true, timeout: 9000, maximumAge: 60000});
    });
  }

  function lerNoServidor(codigo, comCamera) {
    if (leitura && leitura.ponto === codigo) return leitura.pronta;     // voltou ao mesmo ponto
    leitura = {ponto: codigo, selo: null, lido_em: new Date().toISOString(), comCamera: !!comCamera,
               gps: null};
    var comGps = leitura;
    comGps.gpsPronta = obterGps().then(function (g) { comGps.gps = g; return g; });
    if (!comCamera || navigator.onLine === false || !window.fetch) {
      leitura.pronta = Promise.resolve(null);
      return leitura.pronta;
    }
    var esta = leitura;
    esta.pronta = fetch('/app/api/leitura', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                             body: JSON.stringify({ponto: codigo})})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (x) { if (x && leitura === esta) esta.selo = x.selo; return esta.selo; })
      .catch(function () { return null; /* sem sinal: fica a hora do aparelho */ });
    return esta.pronta;
  }

  function abrirPonto(codigo, comCamera) {
    var p = dados.pontos[codigo];
    if (!p) {
      var sec = mostrarSo(secPonto);
      sec.appendChild(el('div', {classe: 'alert alert-warning',
        texto: 'Este QR não é de um ponto dos seus locais (ou foi desativado). ' +
               'Confira a etiqueta ou avise a gestão.'}));
      sec.appendChild(el('button', {type: 'button', classe: 'btn btn-outline-secondary w-100 fc-app-acao',
        onclick: mostrarLocais}, ['Voltar ao meu turno']));
      return;
    }
    lerNoServidor(codigo, comCamera);
    var local = localDe(p.local_id);
    if (p.entrada) { registrarChegada(p, codigo, local); return; }
    if (exigeChegada(local)) { telaConfirmeChegada(local); return; }
    // A tarefa da hora neste ponto, se é desta pessoa (ou sem dono): abre
    // direto no checklist. A de outra pessoa fica na tela do ponto.
    var agora = dados.tarefas.filter(function (t) { return t.ponto === codigo && podeFazer(t) && (t.minha || !t.escalado); })
      .sort(function (a, b) { return Date.parse(a.previsto) - Date.parse(b.previsto); })[0];
    var troca = lerTroca();
    if (agora) { limparTroca(); abrirExecucao(agora, dados.versoes[agora.versao]); return; }
    if (troca) {
      // Veio de "Ir para outra área": a próxima tarefa desta área na rota é
      // adiantada; sem tarefa aqui, é a área fora da rota, com o escopo dela.
      var futura = tarefaParaAdiantar(codigo);
      if (futura) { abrirExecucao(futura, dados.versoes[futura.versao], null, troca); return; }
      var escopo = (p.escopo || []).map(function (vid) { return dados.versoes[vid]; }).filter(Boolean);
      if (escopo.length === 1) { abrirExecucao(null, escopo[0], null, troca); return; }
    }
    telaPonto(codigo);
  }

  // A pessoa leu o QR da ENTRADA: a chegada do dia fica registrada (com
  // sinal, na hora; sem sinal, guardada no aparelho e enviada depois).
  function registrarChegada(p, codigo, local) {
    var sec = mostrarSo(secPonto);
    sec.appendChild(el('p', {classe: 'fc-sub', role: 'status', texto: 'Registrando a chegada…'}));
    var esta = leitura;
    function chegou(h, guardada) {
      if (local) local.chegada = guardada ? null : {hora: h};
      if (guardada) marcarChegadaLocal(p.local_id, h);
      history.replaceState(null, '', '/app/turno?local=' + p.local_id);
      mostrarTurno(p.local_id, 'Você chegou ao ' + (local ? local.nome : p.local) + ' às ' + h +
                                (guardada ? '. Sem sinal: a chegada ficou guardada no aparelho.' : '.'));
    }
    function guardar() {
      if (!window.TrinoFila) {
        dizer('Sem sinal, e este aparelho não guarda envios. Tente de novo com sinal.', 'danger');
        telaConfirmeChegada(local || {nome: p.local});
        return;
      }
      var h = hora(esta.lido_em);
      window.TrinoFila.guardar({tipo: 'chegada', rotulo: 'Chegada · ' + (local ? local.nome : p.local),
                                corpo: {ponto: codigo, lido_em: esta.lido_em, com_camera: esta.comCamera,
                                        gps: esta.gps}})
        .then(function () { chegou(h, true); },
              function () { dizer('Sem sinal, e não foi possível guardar. Tente de novo.', 'danger'); });
    }
    Promise.all([esta.pronta, esta.gpsPronta]).then(function (r) {
      var selo = r[0];
      if (navigator.onLine === false) { guardar(); return; }
      return fetch('/app/api/chegada', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                        body: JSON.stringify({ponto: codigo, selo_leitura: selo,
                                                              com_camera: esta.comCamera,
                                                              gps: esta.gps})})
        .then(function (r) {
          if (window.TrinoFila && window.TrinoFila.ehFalhaDeConexao(r)) { guardar(); return; }
          return r.json().then(function (x) {
            if (!r.ok) {
              dizer(x.error || 'Não foi possível registrar a chegada.', 'danger');
              telaConfirmeChegada(local || {nome: p.local});
              return;
            }
            chegou(x.chegada.hora, false);
          }, guardar);
        }, guardar);
    });
  }

  // O ponto sem tarefa para fazer agora: o que há ali hoje (horários,
  // preventivas, avisos do público, atividade extra).
  // A próxima tarefa ainda fora da janela do horário neste ponto (desta
  // pessoa ou sem dono): a que "adiantar" conclui.
  function tarefaParaAdiantar(codigo) {
    return dados.tarefas.filter(function (t) {
      return t.ponto === codigo && situacao(t).cod === 'prevista' && !feitasNoAparelho()[t.id] &&
             (t.minha || !t.escalado);
    }).sort(function (a, b) { return Date.parse(a.previsto) - Date.parse(b.previsto); })[0] || null;
  }

  function telaPonto(codigo) {
    var p = dados.pontos[codigo];
    var sec = mostrarSo(secPonto);
    sec.appendChild(el('h1', {classe: 'fc-titulo', texto: p.nome}));
    sec.appendChild(el('p', {classe: 'fc-sub', texto: p.ambiente + ' · ' + p.local}));
    if (p.descricao) {
      sec.appendChild(el('div', {classe: 'fc-cartao mb-3'}, [
        el('div', {classe: 'small fw-semibold text-muted', texto: 'Sobre este ponto'}),
        el('div', {texto: p.descricao})]));
    }
    var avisos = (dados.ocorrencias || []).filter(function (o) { return o.ponto === codigo; });
    if (avisos.length) sec.appendChild(cartaoOcorrencias(avisos));
    var prevs = (dados.preventivas || []).filter(function (x) { return x.ponto === codigo; });
    if (prevs.length) sec.appendChild(cartaoPreventivas(prevs));
    var doPonto = dados.tarefas.filter(function (t) { return t.ponto === codigo; });
    var cartao = el('div', {classe: 'fc-cartao mb-3'},
      [el('h2', {classe: 'h6 fw-bold', texto: 'Tarefas deste ponto hoje'})]);
    if (!doPonto.length) cartao.appendChild(el('p', {classe: 'small text-muted mb-0',
      texto: 'Nenhuma tarefa de rota aqui hoje.'}));
    doPonto.forEach(function (t) {
      var linha = cartaoTarefa(t);
      var s = situacao(t).cod;
      if (s === 'prevista' || s === 'no_horario' || s === 'atrasada') {
        var barra = el('div', {classe: 'd-flex gap-2 mt-2'});
        if (podeFazer(t)) {
          barra.appendChild(el('button', {type: 'button', classe: 'btn btn-primary fc-app-acao flex-grow-1',
            onclick: function () { abrirExecucao(t, dados.versoes[t.versao]); }}, ['Fazer agora']));
        } else if (s === 'prevista' && (t.minha || !t.escalado)) {
          // Adiantar (27/10/2026): pergunta o motivo e abre o checklist.
          barra.appendChild(el('button', {type: 'button', classe: 'btn btn-outline-primary fc-app-acao flex-grow-1',
            'data-adiantar': t.id, onclick: function () {
              folhaTroca('Adiantar: ' + t.ambiente + ' das ' + t.hora, function (troca) {
                if (troca) abrirExecucao(t, dados.versoes[t.versao], null, troca);
              });
            }}, ['Adiantar esta área']));
        } else {
          var desde = new Date(Date.parse(t.previsto) - t.tolerancia * 60000).toISOString();
          barra.appendChild(el('span', {classe: 'small text-muted align-self-center flex-grow-1',
            texto: 'Pode ser feita a partir das ' + hora(desde) + '.'}));
        }
        barra.appendChild(el('button', {type: 'button', classe: 'btn btn-outline-secondary fc-app-acao',
          onclick: function () { abrirNaoRealizada(t); }}, ['Não realizada']));
        linha.appendChild(barra);
      }
      cartao.appendChild(linha);
    });
    sec.appendChild(cartao);
    // Área fora da rota (27/10/2026): o escopo da área (o checklist das
    // rotas que passam por ela) abre direto, com o motivo da troca.
    var escopo = (p.escopo || []).map(function (vid) { return dados.versoes[vid]; }).filter(Boolean);
    escopo.forEach(function (v) {
      sec.appendChild(el('button', {type: 'button', classe: 'btn btn-outline-primary w-100 fc-app-acao mb-2',
        'data-fora-da-rota': v.id, onclick: function () {
          var pendente = lerTroca();
          if (pendente) { abrirExecucao(null, v, null, pendente); return; }
          folhaTroca('Limpar fora da rota: ' + p.nome, function (troca) {
            if (troca) abrirExecucao(null, v, null, troca);
          });
        }}, [el('i', {classe: 'bi bi-plus-circle'}), ' Limpar esta área fora da rota' +
              (escopo.length > 1 ? ' (' + v.modelo + ')' : '')]));
    });
    var extras = (p.extras || []).map(function (vid) { return dados.versoes[vid]; }).filter(Boolean);
    if (extras.length) {
      var sel = el('select', {classe: 'form-select form-select-lg', id: 'extra-modelo', 'aria-label': 'Checklist'},
        extras.map(function (v) { return el('option', {value: v.id, texto: v.modelo}); }));
      sec.appendChild(el('details', {classe: 'fc-cartao mb-3'}, [
        el('summary', {classe: 'fw-semibold', texto: 'Atividade extra (fora da rota)'}),
        el('p', {classe: 'small text-muted mt-2',
          texto: 'Para registrar uma limpeza ou vistoria fora do horário da rota.'}),
        sel,
        el('button', {type: 'button', classe: 'btn btn-outline-primary fc-app-acao w-100 mt-2',
          onclick: function () { abrirExecucao(null, dados.versoes[sel.value], null, lerTroca()); }},
          ['Fazer atividade extra'])]));
    }
    sec.appendChild(el('button', {type: 'button', classe: 'btn btn-outline-secondary w-100 fc-app-acao',
      onclick: function () { history.replaceState(null, '', '/app/turno?local=' + p.local_id); mostrarTurno(p.local_id); }},
      ['Ver o turno']));
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
  // Na lista do turno (27/10/2026): cada aviso é uma tarefa "Checar aviso",
  // a de quem cuida do ponto com o selo "Sua". Tocar abre o ponto, onde se
  // atende e resolve.
  function cartaoChecarAvisos(lista) {
    var cartao = el('div', {classe: 'fc-cartao mb-3 border-warning', id: 'turno-avisos'},
      [el('h2', {classe: 'h6 fw-bold', texto: 'Checar avisos do público (' + lista.length + ')'})]);
    lista.slice().sort(function (a, b) { return (b.minha ? 1 : 0) - (a.minha ? 1 : 0); })
      .forEach(function (o) {
        var item = el('a', {classe: 'fc-app-item text-reset text-decoration-none',
                            href: '/app/turno?ponto=' + encodeURIComponent(o.ponto), 'data-aviso': o.id}, [
          el('div', {classe: 'd-flex align-items-center gap-2 flex-wrap'}, [
            el('span', {classe: 'badge text-bg-warning', texto: 'Checar aviso'}),
            o.atrasada ? el('span', {classe: 'badge fc-sit fc-sit-atrasada', texto: 'Fora do prazo'}) : null,
            o.status === 'em_atendimento' ? el('span', {classe: 'badge fc-ocor-em_atendimento', texto: 'Em atendimento'}) : null,
            o.minha ? el('span', {classe: 'badge text-bg-light', texto: 'Sua'}) : null]),
          el('span', {classe: 'fw-semibold', texto: o.tipo}),
          el('span', {classe: 'small text-muted',
                      texto: o.ambiente + ' · ' + o.ponto_nome + ' · às ' + o.hora +
                             (o.texto ? ' · "' + o.texto + '"' : '') +
                             (o.responsavel && !o.minha ? ' · com ' + o.responsavel : '')})]);
        item.addEventListener('click', function (ev) {
          ev.preventDefault();
          history.pushState(null, '', '/app/turno?ponto=' + encodeURIComponent(o.ponto));
          telaPonto(o.ponto);
        });
        cartao.appendChild(item);
      });
    return cartao;
  }

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
        var b1 = el('button', {type: 'button', classe: 'btn btn-outline-primary flex-fill fc-app-acao', texto: 'Vou atender'});
        b1.addEventListener('click', function () { agir('atender', b1); });
        barra.appendChild(b1);
      }
      var b2 = el('button', {type: 'button', classe: 'btn btn-success flex-fill fc-app-acao', texto: 'Resolvido'});
      b2.addEventListener('click', function () { agir('resolver', b2); });
      barra.appendChild(b2);
      linha.appendChild(barra);
      cartao.appendChild(linha);
    });
    return cartao;
  }

  // ── A execução: antes → um check por item → depois → Pronto ───────────
  // A resposta "boa" de um item de marcar (o check verde).
  function respostaFeito(it) {
    if (it.tipo === 'conforme') return 'conforme';
    return it.problema_se === 'sim' ? 'nao' : 'sim';
  }
  function ehDeMarcar(it) { return it.tipo === 'sim_nao' || it.tipo === 'conforme'; }

  function abrirExecucao(tarefa, versao, prev, troca) {
    if (!versao) { dizer('Checklist não encontrado. Recarregue com sinal.', 'warning'); return; }
    var codigo = tarefa ? tarefa.ponto : (leitura && leitura.ponto);
    if (!leitura || leitura.ponto !== codigo) lerNoServidor(codigo);
    var inicio = new Date().toISOString();
    var p = dados.pontos[codigo] || {nome: tarefa ? tarefa.ponto_nome : '', local_id: tarefa ? tarefa.local_id : null};
    var sec = mostrarSo(secExec);
    dizer('');
    var estado = {respostas: {}, motivos: {}, fotos: {}, motivo_atraso: null, motivo_atraso_texto: null,
                  troca: prev ? null : (troca || null)};
    var linhas = {};

    sec.appendChild(el('h1', {classe: 'fc-titulo', texto: p.nome}));
    sec.appendChild(el('p', {classe: 'fc-sub fc-exec-sub', texto:
      versao.modelo + (tarefa ? ' das ' + tarefa.hora : prev ? ' · preventiva ' + prev.numero : ' · fora da rota') +
      (estado.troca ? ' · ' + (tarefa ? 'adiantada' : 'motivo') + ': ' + estado.troca.rotulo : '') +
      (tarefa && tarefa.tempo_previsto_min ? ' · Previsto: ' + tarefa.tempo_previsto_min + ' min' : '')}));
    if (leitura && !leitura.comCamera && !leitura.selo) {
      sec.appendChild(el('p', {classe: 'small text-muted fc-exec-sem-selo',
        texto: 'Aberto sem ler o QR com a câmera: fica com a hora do celular.'}));
    }

    var form = el('form', {novalidate: true, classe: 'fc-exec'});
    var passo = 0;
    function titulo(texto) { passo += 1; return el('h2', {classe: 'fc-exec-passo', texto: passo + '. ' + texto}); }

    if (versao.foto_antes) {
      form.appendChild(titulo('Foto do antes'));
      form.appendChild(blocoFoto('antes', 'Tirar a foto do antes', estado, atualizar));
    }
    form.appendChild(titulo(versao.foto_antes || versao.foto_depois ? 'O que fazer' : 'Checklist'));
    var lista = el('div', {classe: 'fc-itens'});
    versao.itens.forEach(function (it) {
      var linha = linhaDoItem(it, estado, atualizar, p);
      linhas[it.codigo] = linha;
      lista.appendChild(linha);
    });
    form.appendChild(lista);
    if (versao.foto_depois) {
      form.appendChild(titulo('Foto do depois'));
      form.appendChild(blocoFoto('depois', 'Tirar a foto do depois', estado, atualizar));
    }
    var obs = el('textarea', {classe: 'form-control', id: 'obs', name: 'observacao', rows: '2',
                              'aria-label': 'Observação'});
    form.appendChild(el('details', {classe: 'fc-exec-obs mb-3'}, [
      el('summary', {classe: 'small fw-semibold', texto: 'Quer anotar algo? (opcional)'}), obs]));
    var docs = versao.documentos || [];
    if (versao.procedimento || docs.length) {
      form.appendChild(el('details', {classe: 'fc-exec-obs mb-3 fc-procedimento'}, [
        el('summary', {classe: 'small fw-semibold', texto: 'Ver o procedimento (POP)'}),
        versao.procedimento ? el('div', {classe: 'mt-2 fc-texto-livre small', texto: versao.procedimento}) : null,
        docs.length ? el('div', {classe: 'mt-2 d-flex flex-wrap gap-2'}, docs.map(function (d) {
          return el('a', {classe: 'btn btn-sm btn-outline-primary', href: d.url, target: '_blank',
                          rel: 'noopener', texto: 'Ver o POP completo: ' + d.nome});
        })) : null]));
    }
    var pronto = el('button', {type: 'submit', classe: 'btn btn-success btn-lg w-100 fc-app-acao fc-pronto', disabled: true},
      [el('i', {classe: 'bi bi-check-circle'}), ' Pronto']);
    var faltam = el('p', {classe: 'small text-muted text-center mt-2 fc-faltam', role: 'status'});
    form.appendChild(pronto);
    form.appendChild(faltam);
    var outras = (dados.preventivas || []).filter(function (x) { return x.ponto === codigo; }).length +
                 (dados.ocorrencias || []).filter(function (o) { return o.ponto === codigo; }).length;
    form.appendChild(el('button', {type: 'button', classe: 'btn btn-link w-100 mt-1',
      onclick: function () { codigo ? telaPonto(codigo) : mostrarLocais(); }},
      [outras ? 'Outras coisas neste ponto (' + outras + ')' : 'Voltar']));

    function visivel(it) {
      var se = it.mostrar_se;
      if (!se) return true;
      return String(estado.respostas[se.codigo] || '').toLowerCase() === String(se.valor || '').toLowerCase();
    }
    function faltantes() {
      var lista = [];
      if (versao.foto_antes && !estado.fotos.antes) lista.push('a foto do antes');
      var n = 0;
      versao.itens.forEach(function (it) {
        var linha = linhas[it.codigo];
        var ver = visivel(it);
        linha.hidden = !ver;
        if (!ver) return;
        var r = String(estado.respostas[it.codigo] || '').trim();
        if (!r) { n += 1; return; }
        if (it.exige_foto && r !== 'nao_feito' && !estado.fotos['item:' + it.codigo]) n += 1;
      });
      if (n) lista.push(n + (n > 1 ? ' itens' : ' item'));
      if (versao.foto_depois && !estado.fotos.depois) lista.push('a foto do depois');
      return lista;
    }
    function atualizar() {
      var f = faltantes();
      pronto.disabled = f.length > 0;
      var frase = f.length > 1 ? f.slice(0, -1).join(', ') + ' e ' + f[f.length - 1] : f[0];
      faltam.textContent = f.length ? ('Falta' + (f.length > 1 || /itens/.test(f[0]) ? 'm ' : ' ') + frase) : 'Tudo respondido.';
    }
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      if (faltantes().length) { atualizar(); return; }
      enviar(form, tarefa, versao, codigo, inicio, pronto, prev, estado, visivel, obs);
    });
    sec.appendChild(form);
    atualizar();
  }

  // O botão grande de foto: um toque abre a câmera.
  function blocoFoto(chave, rotulo, estado, atualizar) {
    var id = 'f_' + chave.replace(/[^a-z0-9]/gi, '_');
    var entrada = el('input', {type: 'file', accept: 'image/*', capture: 'environment', id: id,
                               classe: 'fc-foto-input', 'data-foto': chave});
    var botao = el('label', {classe: 'btn btn-outline-primary btn-lg w-100 fc-app-acao fc-foto-botao', for: id},
      [el('i', {classe: 'bi bi-camera'}), ' ' + rotulo]);
    entrada.addEventListener('change', function () {
      estado.fotos[chave] = entrada.files.length ? entrada.files[0] : null;
      botao.className = 'btn btn-lg w-100 fc-app-acao fc-foto-botao ' + (entrada.files.length ? 'btn-success' : 'btn-outline-primary');
      limpar(botao);
      botao.appendChild(el('i', {classe: entrada.files.length ? 'bi bi-check-circle-fill' : 'bi bi-camera'}));
      botao.appendChild(document.createTextNode(' ' + (entrada.files.length ? 'Foto pronta · trocar' : rotulo)));
      atualizar();
    });
    return el('div', {classe: 'fc-foto mb-3'}, [entrada, botao]);
  }

  // Uma linha do checklist: [check] texto [i] [Não deu]. Item de marcar:
  // toca → verde ("Feito"); com foto exigida, o check só fica verde com a
  // foto. Número, texto, escolha e data continuam como campo (exceção).
  function linhaDoItem(it, estado, atualizar, p) {
    var linha = el('div', {classe: 'fc-item', 'data-codigo': it.codigo});
    var marcado = el('span', {classe: 'fc-item-estado', 'aria-live': 'polite'});
    var check = null, campo = null, fotoEntrada = null;
    var topo = el('div', {classe: 'fc-item-topo'});
    function pintar() {
      var r = estado.respostas[it.codigo];
      linha.classList.remove('fc-item-feito', 'fc-item-naodeu');
      marcado.textContent = '';
      if (r === 'nao_feito') {
        linha.classList.add('fc-item-naodeu');
        var m = estado.motivos[it.codigo] || {};
        marcado.textContent = 'Não deu: ' + (m.rotulo || dados.motivos_nao_feito[m.motivo] || '') +
                              (m.texto && m.motivo === 'outro' ? ' — ' + m.texto : '') +
                              (m.material_nome ? ' — ' + m.material_nome : '');
      } else if (r) {
        if (!it.exige_foto || estado.fotos['item:' + it.codigo]) {
          linha.classList.add('fc-item-feito');
          marcado.textContent = ehDeMarcar(it) ? 'Feito' : '';
        } else {
          marcado.textContent = 'Falta a foto';
        }
      }
      if (check) {
        var feito = linha.classList.contains('fc-item-feito');
        check.setAttribute('aria-pressed', feito ? 'true' : 'false');
        check.className = 'fc-check' + (feito ? ' fc-check-feito' : '');
        limpar(check);
        check.appendChild(el('i', {classe: feito ? 'bi bi-check-lg' : 'bi bi-circle', 'aria-hidden': 'true'}));
      }
      atualizar();
    }
    if (ehDeMarcar(it)) {
      check = el('button', {type: 'button', classe: 'fc-check', 'aria-pressed': 'false',
                            'aria-label': 'Feito: ' + it.texto});
      if (it.exige_foto) {
        fotoEntrada = el('input', {type: 'file', accept: 'image/*', capture: 'environment',
                                   classe: 'fc-foto-input', 'data-foto': 'item:' + it.codigo,
                                   id: 'f_item_' + it.codigo, 'aria-label': 'Foto: ' + it.texto});
        fotoEntrada.addEventListener('change', function () {
          estado.fotos['item:' + it.codigo] = fotoEntrada.files.length ? fotoEntrada.files[0] : null;
          if (fotoEntrada.files.length) estado.respostas[it.codigo] = respostaFeito(it);
          pintar();
        });
        linha.appendChild(fotoEntrada);
      }
      check.addEventListener('click', function () {
        if (linha.classList.contains('fc-item-feito')) {
          delete estado.respostas[it.codigo];
          delete estado.fotos['item:' + it.codigo];
          if (fotoEntrada) fotoEntrada.value = '';
          pintar();
          return;
        }
        delete estado.motivos[it.codigo];
        if (it.exige_foto) {
          // O check só fica verde com a foto: um toque abre a câmera.
          fotoEntrada.click();
          return;
        }
        estado.respostas[it.codigo] = respostaFeito(it);
        pintar();
      });
      topo.appendChild(check);
    }
    topo.appendChild(el('div', {classe: 'fc-item-texto'}, [
      el('span', {texto: it.texto}), marcado]));
    if (it.como_fazer || it.foto_ref_url) {
      var ajuda = el('div', {classe: 'fc-item-ajuda', hidden: true}, [
        it.como_fazer ? el('div', {classe: 'small fc-como-fazer', texto: it.como_fazer}) : null,
        it.foto_ref_url ? el('img', {classe: 'fc-ref', src: it.foto_ref_url, loading: 'lazy',
                                     alt: 'Como deve ficar: ' + it.texto}) : null]);
      var info = el('button', {type: 'button', classe: 'fc-item-info', 'aria-label': 'Como fazer: ' + it.texto,
                               'aria-expanded': 'false'}, [el('i', {classe: 'bi bi-info-circle', 'aria-hidden': 'true'})]);
      info.addEventListener('click', function () {
        ajuda.hidden = !ajuda.hidden;
        info.setAttribute('aria-expanded', ajuda.hidden ? 'false' : 'true');
      });
      topo.appendChild(info);
      linha.appendChild(topo);
      linha.appendChild(ajuda);
    } else {
      linha.appendChild(topo);
    }
    var naoDeu = el('button', {type: 'button', classe: 'btn btn-sm btn-outline-secondary fc-naodeu', texto: 'Não deu'});
    naoDeu.addEventListener('click', function () {
      folhaNaoDeu(it, p, function (motivo) {
        if (!motivo) return;
        estado.motivos[it.codigo] = motivo;
        estado.respostas[it.codigo] = 'nao_feito';
        delete estado.fotos['item:' + it.codigo];
        if (fotoEntrada) fotoEntrada.value = '';
        if (campo) campo.value = '';
        pintar();
      });
    });
    topo.appendChild(naoDeu);
    if (!ehDeMarcar(it)) {
      var nome = 'r_' + it.codigo;
      if (it.tipo === 'numero') {
        var faixa = (it.minimo !== null && it.minimo !== undefined ? 'de ' + it.minimo : '') +
                    (it.maximo !== null && it.maximo !== undefined ? ' até ' + it.maximo : '');
        campo = el('input', {classe: 'form-control form-control-lg', name: nome, inputmode: 'decimal', 'aria-label': it.texto,
                             placeholder: faixa ? 'Aceitável: ' + faixa.trim() : ''});
      } else if (it.tipo === 'escolha') {
        campo = el('select', {classe: 'form-select form-select-lg', name: nome, 'aria-label': it.texto},
          [el('option', {value: '', texto: 'Escolha'})].concat(
            (it.opcoes || []).map(function (o) { return el('option', {value: o, texto: o}); })));
      } else if (it.tipo === 'data_hora') {
        campo = el('input', {type: 'datetime-local', classe: 'form-control form-control-lg', name: nome, 'aria-label': it.texto});
      } else {
        campo = el('input', {classe: 'form-control form-control-lg', name: nome, maxlength: '300', 'aria-label': it.texto});
      }
      campo.addEventListener('input', function () {
        if (campo.value.trim()) { estado.respostas[it.codigo] = campo.value.trim(); delete estado.motivos[it.codigo]; }
        else delete estado.respostas[it.codigo];
        pintar();
      });
      campo.addEventListener('change', function () { campo.dispatchEvent(new Event('input')); });
      var corpo = el('div', {classe: 'fc-item-campo'}, [campo]);
      if (it.exige_foto) {
        fotoEntrada = el('input', {type: 'file', accept: 'image/*', capture: 'environment',
                                   classe: 'fc-foto-input', 'data-foto': 'item:' + it.codigo,
                                   id: 'f_item_' + it.codigo});
        var botaoFoto = el('label', {classe: 'btn btn-outline-primary fc-app-acao w-100 mt-2', for: 'f_item_' + it.codigo},
          [el('i', {classe: 'bi bi-camera'}), ' Foto deste item']);
        fotoEntrada.addEventListener('change', function () {
          estado.fotos['item:' + it.codigo] = fotoEntrada.files.length ? fotoEntrada.files[0] : null;
          botaoFoto.className = 'btn fc-app-acao w-100 mt-2 ' + (fotoEntrada.files.length ? 'btn-success' : 'btn-outline-primary');
          pintar();
        });
        corpo.appendChild(fotoEntrada);
        corpo.appendChild(botaoFoto);
      }
      linha.appendChild(corpo);
    }
    return linha;
  }

  // "Não deu" de um item: a folha com os motivos. "Faltou material" abre o
  // catálogo do local; "Outro" pede o texto.
  // ── Folha: por que foi a outra área (27/10/2026) ──────────────────────
  // devolver({motivo, texto, rotulo}) ou devolver(null) ao cancelar.
  function folhaTroca(tituloTexto, devolver) {
    var folha = el('div', {classe: 'fc-folha', role: 'dialog', 'aria-modal': 'true', 'aria-label': tituloTexto});
    var caixa = el('div', {classe: 'fc-folha-caixa'});
    folha.appendChild(caixa);
    function fechar(r) { folha.remove(); document.body.classList.remove('fc-folha-aberta'); devolver(r || null); }
    function inicio() {
      limpar(caixa);
      caixa.appendChild(el('h2', {classe: 'h5 fw-bold', texto: tituloTexto}));
      caixa.appendChild(el('p', {classe: 'small text-muted', texto: 'Por que você vai a outra área agora?'}));
      (dados.motivos_troca_ordem || Object.keys(dados.motivos_troca || {})).forEach(function (k) {
        var b = el('button', {type: 'button', classe: 'btn btn-outline-dark btn-lg w-100 fc-app-acao mb-2 fc-motivo',
                              'data-motivo-troca': k, texto: dados.motivos_troca[k]});
        b.addEventListener('click', function () {
          if (k === 'outro') { outro(); return; }
          fechar({motivo: k, rotulo: dados.motivos_troca[k]});
        });
        caixa.appendChild(b);
      });
      caixa.appendChild(el('button', {type: 'button', classe: 'btn btn-link w-100', onclick: function () { fechar(null); }}, ['Cancelar']));
    }
    function outro() {
      limpar(caixa);
      caixa.appendChild(el('h2', {classe: 'h5 fw-bold', texto: tituloTexto}));
      var campo = el('input', {classe: 'form-control form-control-lg mb-2', maxlength: '300',
                               'aria-label': 'Por que vai a outra área', placeholder: 'Conte em poucas palavras'});
      var erro = el('p', {classe: 'small text-danger', hidden: true, texto: 'Escreva o motivo.'});
      caixa.appendChild(campo);
      caixa.appendChild(erro);
      caixa.appendChild(el('button', {type: 'button', classe: 'btn btn-primary btn-lg w-100 fc-app-acao mb-2', onclick: function () {
        if (!campo.value.trim()) { erro.hidden = false; return; }
        fechar({motivo: 'outro', texto: campo.value.trim(), rotulo: campo.value.trim()});
      }}, ['Confirmar']));
      caixa.appendChild(el('button', {type: 'button', classe: 'btn btn-link w-100', onclick: inicio}, ['Voltar']));
      campo.focus();
    }
    inicio();
    document.body.appendChild(folha);
    document.body.classList.add('fc-folha-aberta');
  }

  function folhaNaoDeu(it, p, devolver) {
    var folha = el('div', {classe: 'fc-folha', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Não deu: ' + it.texto});
    var caixa = el('div', {classe: 'fc-folha-caixa'});
    folha.appendChild(caixa);
    function fechar(motivo) { folha.remove(); document.body.classList.remove('fc-folha-aberta'); devolver(motivo || null); }
    function inicio() {
      limpar(caixa);
      caixa.appendChild(el('h2', {classe: 'h5 fw-bold', texto: 'Não deu: ' + it.texto}));
      caixa.appendChild(el('p', {classe: 'small text-muted', texto: 'O que aconteceu?'}));
      (dados.motivos_nao_feito_ordem || Object.keys(dados.motivos_nao_feito)).forEach(function (k) {
        var b = el('button', {type: 'button', classe: 'btn btn-outline-dark btn-lg w-100 fc-app-acao mb-2 fc-motivo',
                              'data-motivo': k, texto: dados.motivos_nao_feito[k]});
        b.addEventListener('click', function () {
          if (k === 'faltou_material') { material(); return; }
          if (k === 'outro') { outro(); return; }
          fechar({motivo: k, rotulo: dados.motivos_nao_feito[k]});
        });
        caixa.appendChild(b);
      });
      caixa.appendChild(el('button', {type: 'button', classe: 'btn btn-link w-100', onclick: function () { fechar(null); }}, ['Cancelar']));
    }
    function outro() {
      limpar(caixa);
      caixa.appendChild(el('h2', {classe: 'h5 fw-bold', texto: 'Não deu: ' + it.texto}));
      var campo = el('input', {classe: 'form-control form-control-lg mb-2', maxlength: '300', 'aria-label': 'O que aconteceu',
                               placeholder: 'Conte em poucas palavras'});
      var erro = el('p', {classe: 'small text-danger', hidden: true, texto: 'Escreva o que aconteceu.'});
      caixa.appendChild(campo);
      caixa.appendChild(erro);
      caixa.appendChild(el('button', {type: 'button', classe: 'btn btn-primary btn-lg w-100 fc-app-acao mb-2', onclick: function () {
        if (!campo.value.trim()) { erro.hidden = false; return; }
        fechar({motivo: 'outro', texto: campo.value.trim(), rotulo: dados.motivos_nao_feito.outro});
      }}, ['Confirmar']));
      caixa.appendChild(el('button', {type: 'button', classe: 'btn btn-link w-100', onclick: inicio}, ['Voltar']));
      campo.focus();
    }
    function material() {
      limpar(caixa);
      caixa.appendChild(el('h2', {classe: 'h5 fw-bold', texto: 'Faltou qual material?'}));
      var sel = el('select', {classe: 'form-select form-select-lg mb-2', 'aria-label': 'Material'},
        [el('option', {value: '', texto: 'Carregando o catálogo…'})]);
      var livre = el('input', {classe: 'form-control form-control-lg mb-2', maxlength: '300', 'aria-label': 'Qual material',
                               placeholder: 'Ou escreva o que faltou', hidden: true});
      caixa.appendChild(sel);
      caixa.appendChild(livre);
      function preencher(lista) {
        limpar(sel);
        sel.appendChild(el('option', {value: '', texto: 'Escolha o material'}));
        lista.forEach(function (m) { sel.appendChild(el('option', {value: m.id, texto: m.nome + (m.unidade ? ' (' + m.unidade + ')' : '')})); });
        sel.appendChild(el('option', {value: 'livre', texto: 'Não está na lista / não sei'}));
      }
      catalogo(p.local_id).then(function (lista) {
        if (lista && lista.length) { preencher(lista); return; }
        limpar(sel);
        sel.appendChild(el('option', {value: 'livre', texto: 'Escrever o que faltou'}));
        livre.hidden = false;
      });
      sel.addEventListener('change', function () { livre.hidden = sel.value !== 'livre'; });
      var erro = el('p', {classe: 'small text-danger', hidden: true, texto: 'Escolha o material ou escreva o que faltou.'});
      caixa.appendChild(erro);
      caixa.appendChild(el('button', {type: 'button', classe: 'btn btn-primary btn-lg w-100 fc-app-acao mb-2', onclick: function () {
        var m = {motivo: 'faltou_material', rotulo: dados.motivos_nao_feito.faltou_material};
        if (sel.value && sel.value !== 'livre') {
          m.material_id = parseInt(sel.value, 10);
          m.material_nome = sel.options[sel.selectedIndex].textContent;
        } else if (livre.value.trim()) {
          m.texto = livre.value.trim();
          m.material_nome = m.texto;
        } else { erro.hidden = false; return; }
        fechar(m);
      }}, ['Confirmar']));
      caixa.appendChild(el('button', {type: 'button', classe: 'btn btn-link w-100', onclick: inicio}, ['Voltar']));
    }
    inicio();
    document.body.appendChild(folha);
    document.body.classList.add('fc-folha-aberta');
    var primeiro = caixa.querySelector('button');
    if (primeiro) primeiro.focus();
  }

  function catalogo(localId) {
    if (materiaisPorLocal[localId]) return Promise.resolve(materiaisPorLocal[localId]);
    if (navigator.onLine === false || !localId) return Promise.resolve([]);
    return fetch('/app/api/materiais?local=' + encodeURIComponent(localId), {credentials: 'same-origin'})
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (lista) { materiaisPorLocal[localId] = lista; return lista; })
      .catch(function () { return []; });
  }

  // ── Envio ─────────────────────────────────────────────────────────────
  function enviar(form, tarefa, versao, codigo, inicio, botao, prev, estado, visivel, obs) {
    botao.disabled = true;
    var respostas = {}, motivos = {};
    versao.itens.forEach(function (it) {
      if (!visivel(it)) return;      // a condição não se cumpriu: não vai
      var r = estado.respostas[it.codigo];
      if (r === undefined || r === null || r === '') return;
      respostas[it.codigo] = r;
      if (r === 'nao_feito') {
        var m = estado.motivos[it.codigo] || {};
        motivos[it.codigo] = {motivo: m.motivo, texto: m.texto || null, material_id: m.material_id || null};
      }
    });
    var corpo = {
      envio_id: novoId(), ponto: codigo, respostas: respostas, motivos: motivos,
      observacao: obs.value,
      selo_leitura: leitura && leitura.ponto === codigo ? leitura.selo : null,
      lido_em: leitura && leitura.ponto === codigo ? leitura.lido_em : inicio,
      concluida_em: new Date().toISOString(),
      sem_sinal: !(leitura && leitura.selo),
      gps: leitura && leitura.ponto === codigo ? leitura.gps : null
    };
    if (tarefa) corpo.tarefa_id = tarefa.id; else corpo.versao_id = versao.id;
    if (prev) corpo.chamado_id = prev.id;
    if (estado.troca) {
      corpo.motivo_troca = estado.troca.motivo;
      corpo.motivo_troca_texto = estado.troca.texto || null;
    }
    var fotos = Object.keys(estado.fotos).filter(function (k) { return estado.fotos[k]; })
      .map(function (k) { return {campo: k, arquivo: estado.fotos[k]}; });
    var reduzir = window.TrinoFoto ? window.TrinoFoto.reduzirTodos : function (fs) { return Promise.resolve(fs); };
    reduzir(fotos.map(function (f) { return f.arquivo; })).then(function (leves) {
      var prontas = fotos.map(function (f, i) { return {campo: f.campo, arquivo: leves[i] || f.arquivo}; });
      return mandar(corpo, prontas).then(function (res) { concluir(res, tarefa, codigo, corpo, prontas, botao, prev); });
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
    var p = dados.pontos[codigo] || {nome: tarefa ? tarefa.ponto_nome : '', local_id: tarefa ? tarefa.local_id : null};
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
      window.TrinoFila.guardar({tipo: 'execucao', rotulo: (tarefa ? tarefa.hora + ' · ' : '') + p.nome,
                                tarefa_id: tarefa ? tarefa.id : null,
                                corpo: corpo, fotos: fotos}).then(function () {
        if (tarefa) marcarFeita(tarefa.id, 'Guardada no aparelho');
        if (corpo.motivo_troca) limparTroca();
        tirarPreventiva();
        telaDepois(tarefa, p, null, true);
      }, function () {
        botao.disabled = false;
        dizer('Sem sinal, e não foi possível guardar. Não feche a tela; tente de novo.', 'danger');
      });
      return;
    }
    if (!res.ok) {
      var x = res.x || {};
      if (x.motivo === 'motivo_atraso') {
        telaAtraso(x.extra || {}, function (motivo, texto) {
          corpo.motivo_atraso = motivo;
          corpo.motivo_atraso_texto = texto || null;
          mandar(corpo, fotos).then(function (r2) { concluir(r2, tarefa, codigo, corpo, fotos, botao, prev); });
        }, function () { botao.disabled = false; secExec.hidden = false; secPonto.hidden = true; });
        return;
      }
      if (x.motivo === 'motivo_troca') {
        folhaTroca(x.error || 'Por que você foi a esta área agora?', function (troca) {
          if (!troca) { botao.disabled = false; return; }
          corpo.motivo_troca = troca.motivo;
          corpo.motivo_troca_texto = troca.texto || null;
          mandar(corpo, fotos).then(function (r2) { concluir(r2, tarefa, codigo, corpo, fotos, botao, prev); });
        });
        return;
      }
      if (x.motivo === 'sem_chegada') {
        telaConfirmeChegada(localDe(p.local_id) || {nome: p.local || ''});
        return;
      }
      botao.disabled = false;
      dizer(x.error || 'Não foi possível registrar.', 'danger');
      return;
    }
    if (tarefa) { tarefa.status = res.x.status; }
    if (corpo.motivo_troca) limparTroca();
    tirarPreventiva();
    telaDepois(tarefa, p, res.x, false);
  }

  // ── Tela: levou mais que o previsto ───────────────────────────────────
  function telaAtraso(extra, devolver, cancelar) {
    var sec = mostrarSo(secPonto);
    secExec.hidden = true;
    sec.appendChild(el('h1', {classe: 'fc-titulo', texto: 'Esta limpeza levou ' + extra.duracao_min + ' min; o previsto era ' +
                                                          extra.previsto_min + '.'}));
    sec.appendChild(el('p', {classe: 'fc-sub', texto: 'O que aconteceu?'}));
    var caixa = el('div', {classe: 'fc-cartao'});
    var texto = el('input', {classe: 'form-control form-control-lg mb-2', maxlength: '300', hidden: true,
                             'aria-label': 'O que aconteceu', placeholder: 'Conte em poucas palavras'});
    var erro = el('p', {classe: 'small text-danger', hidden: true, texto: 'Escreva o que aconteceu.'});
    (dados.motivos_atraso_ordem || Object.keys(dados.motivos_atraso)).forEach(function (k) {
      var b = el('button', {type: 'button', classe: 'btn btn-outline-dark btn-lg w-100 fc-app-acao mb-2 fc-motivo',
                            'data-motivo': k, texto: dados.motivos_atraso[k]});
      b.addEventListener('click', function () {
        if (k !== 'outro') { devolver(k, null); return; }
        texto.hidden = false;
        texto.focus();
        confirmar.hidden = false;
      });
      caixa.appendChild(b);
    });
    var confirmar = el('button', {type: 'button', classe: 'btn btn-primary btn-lg w-100 fc-app-acao mb-2', hidden: true,
      onclick: function () {
        if (!texto.value.trim()) { erro.hidden = false; return; }
        devolver('outro', texto.value.trim());
      }}, ['Confirmar']);
    caixa.appendChild(texto);
    caixa.appendChild(erro);
    caixa.appendChild(confirmar);
    caixa.appendChild(el('button', {type: 'button', classe: 'btn btn-link w-100', onclick: function () { secPonto.hidden = true; cancelar(); }}, ['Voltar']));
    sec.appendChild(caixa);
  }

  // ── Tela: depois do "Pronto" — a próxima tarefa ───────────────────────
  function telaDepois(tarefa, p, resposta, guardada) {
    var sec = mostrarSo(secPonto);
    var h = hora();
    var cartao = el('div', {classe: 'fc-cartao fc-pronto-feito text-center mb-3'}, [
      el('i', {classe: 'bi bi-check-circle-fill fc-pronto-icone', 'aria-hidden': 'true'}),
      el('h1', {classe: 'fc-titulo', texto: 'Pronto. ' + p.nome + ' feito às ' + h + '.'})]);
    if (guardada) {
      cartao.appendChild(el('p', {classe: 'small text-muted mb-0', texto: 'Guardada no aparelho: sobe sozinha quando o sinal voltar.'}));
    } else if (resposta) {
      if (resposta.situacao && !tarefa) cartao.appendChild(el('p', {classe: 'small text-muted mb-0', texto: resposta.situacao + '.'}));
      if (resposta.nao_conformes) {
        cartao.appendChild(el('p', {classe: 'small text-muted mb-0',
          texto: resposta.nao_conformes + (resposta.nao_conformes > 1 ? ' itens com problema' : ' item com problema') +
                 ': a gestão foi avisada' + (resposta.pedidos_insumo && resposta.pedidos_insumo.length ? ' e o material foi pedido' : '') + '.'}));
      }
      if (resposta.motivo_atraso) cartao.appendChild(el('p', {classe: 'small text-muted mb-0', texto: 'Levou ' + resposta.duracao_min + ' min; o motivo ficou registrado.'}));
    }
    sec.appendChild(cartao);
    var localId = p.local_id || (tarefa ? tarefa.local_id : null);
    var prox = localId ? proximaTarefa(localId, tarefa) : null;
    if (prox) {
      sec.appendChild(el('div', {classe: 'fc-cartao fc-proxima-tarefa'}, [
        el('div', {classe: 'small fw-semibold text-muted', texto: 'Próxima tarefa'}),
        el('div', {classe: 'fs-4 fw-bold', texto: prox.ambiente + ' · ' + prox.ponto_nome}),
        el('div', {classe: 'fc-sub', texto: (dados.versoes[prox.versao] || {}).modelo + ' às ' + prox.hora +
                                              (podeFazer(prox) ? '' : ' (a partir das ' + hora(new Date(Date.parse(prox.previsto) - prox.tolerancia * 60000).toISOString()) + ')')}),
        botaoLerQr()]));
    } else {
      sec.appendChild(el('div', {classe: 'fc-cartao'}, [
        el('div', {classe: 'fs-5 fw-bold', texto: 'Nenhuma outra tarefa da rota por agora.'}),
        el('button', {type: 'button', classe: 'btn btn-outline-primary btn-lg w-100 fc-app-acao mt-2',
          onclick: function () { history.replaceState(null, '', '/app/turno' + (localId ? '?local=' + localId : '')); localId ? mostrarTurno(localId) : mostrarLocais(); }},
          ['Ver o turno'])]));
    }
  }

  // ── Não realizada ─────────────────────────────────────────────────────
  function abrirNaoRealizada(t) {
    var sec = mostrarSo(secExec);
    sec.appendChild(el('h1', {classe: 'fc-titulo', texto: 'Não deu para fazer'}));
    sec.appendChild(el('p', {classe: 'fc-sub', texto: t.hora + ' · ' + t.ponto_nome}));
    var form = el('form', {});
    var motivos = el('div', {classe: 'fc-cartao mb-2', role: 'radiogroup', 'aria-label': 'Motivo'});
    Object.keys(dados.motivos).forEach(function (k) {
      motivos.appendChild(el('label', {classe: 'd-flex gap-2 py-2 fc-radio-linha'}, [
        el('input', {type: 'radio', name: 'motivo', value: k}), el('span', {texto: dados.motivos[k]})]));
    });
    form.appendChild(motivos);
    form.appendChild(el('div', {classe: 'fc-cartao mb-2'}, [
      el('label', {classe: 'form-label small fw-semibold', for: 'nrtexto', texto: 'O que aconteceu'}),
      el('input', {classe: 'form-control form-control-lg', id: 'nrtexto', name: 'texto', maxlength: '300'}),
      el('label', {classe: 'd-flex gap-2 mt-2 fc-radio-linha'}, [el('input', {type: 'checkbox', name: 'chamado'}),
        el('span', {texto: 'Abrir chamado para resolver'})])]));
    var botao = el('button', {type: 'submit', classe: 'btn btn-primary btn-lg w-100 fc-app-acao', texto: 'Registrar'});
    form.appendChild(botao);
    form.appendChild(el('button', {type: 'button', classe: 'btn btn-link w-100',
      onclick: function () { leitura ? telaPonto(leitura.ponto) : mostrarLocais(); }}, ['Cancelar']));
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
          leitura ? telaPonto(leitura.ponto) : mostrarLocais();
        }, function () {
          botao.disabled = false;
          dizer('Sem sinal: "não realizada" precisa de sinal para avisar a gestão. Tente de novo quando voltar.', 'warning');
        });
    });
    sec.appendChild(form);
  }

  // A fila subiu uma execução guardada: só AQUELA tarefa deixa de ser
  // "guardada no aparelho" — as outras ainda estão na fila.
  window.addEventListener('trino-fila:enviado', function (ev) {
    if (!ev.detail || ev.detail.tipo !== 'execucao') return;
    var f = feitasNoAparelho();
    if (ev.detail.tarefa_id) {
      if (!(ev.detail.tarefa_id in f)) return;
      f[ev.detail.tarefa_id] = 'Enviada';
    } else {
      // Item guardado por uma versão anterior do app, sem tarefa_id: não dá
      // para saber qual foi, então as guardadas viram "Enviada" como antes.
      Object.keys(f).forEach(function (k) { if (f[k] === 'Guardada no aparelho') f[k] = 'Enviada'; });
    }
    gravarJson(CHAVE_LOCAL, f);
  });

  var params = new URLSearchParams(location.search);
  var ponto = params.get('ponto');
  var localParam = params.get('local');
  var comCamera = params.get('lido') === 'camera';
  if (comCamera && window.history && history.replaceState) {
    // Recarregar a tela não vale como uma nova leitura do QR.
    params.delete('lido');
    history.replaceState(null, '', location.pathname + '?' + params.toString());
  }
  window.addEventListener('popstate', function () {
    var q = new URLSearchParams(location.search);
    if (q.get('ponto')) abrirPonto(q.get('ponto'), false);
    else if (q.get('local')) mostrarTurno(q.get('local'));
    else mostrarLocais();
  });
  if (ponto) abrirPonto(ponto, comCamera);
  else if (localParam) mostrarTurno(localParam);
  else mostrarLocais();
})();
