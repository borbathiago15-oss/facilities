/* Fila do app sem internet (Fase 3).
 *
 * O encarregado encerra o turno na câmara fria, sem sinal; o auditor fotografa
 * o fundo do galpão, sem sinal. Nos dois casos o que foi escrito não pode se
 * perder. Esta fila guarda no aparelho (IndexedDB) o envio que não subiu e o
 * reenvia sozinho quando a conexão volta.
 *
 * As regras que protegem o dado:
 *
 *  - O envio é de QUEM ESCREVEU. Cada item guarda o id do usuário, e só sobe
 *    com essa pessoa logada neste aparelho (conferido em /app/sessao). Num
 *    celular compartilhado, ninguém envia em nome de outro.
 *  - Cada envio leva uma marca única. Se a resposta se perdeu no caminho e o
 *    app manda de novo, o servidor reconhece a marca e não duplica passagem
 *    nem foto.
 *  - Conflito não é resolvido no escuro. Se alguém encerrou o mesmo turno
 *    pelo computador, ou gravou a mesma auditoria depois, o item fica aqui
 *    marcado como conflito, com o texto guardado, até a pessoa decidir.
 *  - Sair do sistema com envio pendente avisa, e mantém guardado: sobe quando
 *    a mesma pessoa entrar de novo neste aparelho.
 *
 * ATENÇÃO: arquivo estático, fora do Jinja. Toda URL aqui é literal.
 */
(function () {
  'use strict';

  if (!window.indexedDB || !window.fetch || !window.Promise) { return; }

  var BANCO = 'trino-fila';
  var LOJA = 'envios';
  var INTERVALO = 60 * 1000;

  // ── Guarda (IndexedDB) ────────────────────────────────────────────────
  var _banco = null;
  function abrir() {
    if (_banco) { return _banco; }
    _banco = new Promise(function (ok, falha) {
      var pedido = indexedDB.open(BANCO, 1);
      pedido.onupgradeneeded = function () {
        pedido.result.createObjectStore(LOJA, {keyPath: 'id'});
      };
      pedido.onsuccess = function () { ok(pedido.result); };
      pedido.onerror = function () { _banco = null; falha(pedido.error); };
    });
    return _banco;
  }

  function operar(modo, fazer) {
    return abrir().then(function (db) {
      return new Promise(function (ok, falha) {
        var t = db.transaction(LOJA, modo);
        var loja = t.objectStore(LOJA);
        var resultado = fazer(loja);
        t.oncomplete = function () {
          ok(resultado && 'result' in resultado ? resultado.result : resultado);
        };
        t.onerror = function () { falha(t.error); };
        t.onabort = function () { falha(t.error); };
      });
    });
  }

  function todos() { return operar('readonly', function (l) { return l.getAll(); }); }
  function gravar(item) { return operar('readwrite', function (l) { return l.put(item); }); }
  function apagar(id) { return operar('readwrite', function (l) { return l.delete(id); }); }

  function novoId() {
    if (window.crypto && crypto.randomUUID) { return crypto.randomUUID(); }
    var b = new Uint8Array(16);
    crypto.getRandomValues(b);
    return Array.prototype.map.call(b, function (x) {
      return ('0' + x.toString(16)).slice(-2);
    }).join('');
  }

  function usuarioDaPagina() {
    var m = document.querySelector('meta[name="usuario-id"]');
    var v = m ? parseInt(m.content, 10) : NaN;
    return isNaN(v) ? null : v;
  }

  function meus(itens) {
    var uid = usuarioDaPagina();
    return itens.filter(function (i) { return uid !== null && i.user_id === uid; });
  }

  // ── Conversa com o servidor ───────────────────────────────────────────
  // Toda resposta vira uma de cinco coisas, e cada uma tem UMA reação:
  //   ok        → sai da fila
  //   rede      → para aqui e tenta de novo depois (sem sinal, servidor fora)
  //   sessao    → para aqui: é preciso entrar no sistema de novo
  //   conflito  → fica guardado, marcado, esperando a pessoa decidir
  //   recusado  → o servidor recusou o conteúdo (ex.: foto grande demais)
  function pedir(url, opcoes) {
    return fetch(url, Object.assign({credentials: 'same-origin'}, opcoes))
      .then(function (r) {
        if (r.status === 401 || (r.redirected && /\/login/.test(r.url))) {
          return {tipo: 'sessao'};
        }
        var tipo = r.headers.get('Content-Type') || '';
        if (tipo.indexOf('application/json') < 0) {
          return {tipo: r.status >= 500 ? 'rede' : 'sessao'};
        }
        return r.json().then(function (dados) {
          if (r.ok) { return {tipo: 'ok', dados: dados}; }
          var msg = (dados && dados.error) || ('O servidor respondeu ' + r.status + '.');
          if (r.status === 409 || r.status === 403 || r.status === 404) {
            return {tipo: 'conflito', mensagem: msg, dados: dados};
          }
          if (r.status === 400 || r.status === 413) {
            return {tipo: 'recusado', mensagem: msg, dados: dados};
          }
          return {tipo: 'rede'};
        }, function () { return {tipo: 'rede'}; });
      }, function () { return {tipo: 'rede'}; });
  }

  // Quem está logado — e, quando ninguém está, POR QUÊ não se sabe.
  //
  // Antes isto devolvia `null` tanto para "o servidor disse que não há
  // sessão" quanto para "a rede caiu e o servidor nem respondeu". A fila
  // tratava os dois como sessão vencida, e sem sinal na câmara fria o item
  // aparecia "Aguardando você entrar no sistema" — mandando a pessoa fazer
  // login de novo quando o que faltava era internet.
  //
  // Agora são três respostas, e só a do SERVIDOR vira 'sessao':
  //   {situacao: 'ok', dados}  → logado; `dados` traz user_id e csrf
  //   {situacao: 'sessao'}     → o servidor respondeu, em JSON, que não há
  //                              sessão (401 / autenticado: false)
  //   {situacao: 'rede'}       → não houve resposta do sistema: sem sinal,
  //                              servidor fora, ou uma página no meio do
  //                              caminho (portal de Wi-Fi, proxy) que não é
  //                              o JSON do /app/sessao
  function sessao() {
    return fetch('/app/sessao', {method: 'GET', cache: 'no-store',
                                 credentials: 'same-origin'})
      .then(function (r) {
        var tipo = r.headers.get('Content-Type') || '';
        if (tipo.indexOf('application/json') < 0) { return {situacao: 'rede'}; }
        return r.json().then(function (d) {
          if (r.ok && d && d.autenticado) { return {situacao: 'ok', dados: d}; }
          if (r.status === 401 || (d && d.autenticado === false)) {
            return {situacao: 'sessao'};
          }
          return {situacao: 'rede'};
        }, function () { return {situacao: 'rede'}; });
      }, function () { return {situacao: 'rede'}; });
  }

  // Avisa a página que um item guardado subiu. A tela que o guardou (a nova
  // passagem, por exemplo) troca o "guardado neste aparelho" por "enviado" —
  // senão ela seguia dizendo que não foi, com a passagem já no sistema.
  function avisarEnviado(it, estado, mensagem) {
    try {
      window.dispatchEvent(new CustomEvent('trino-fila:enviado', {detail: {
        id: it.id, tipo: it.tipo, rotulo: it.rotulo || '',
        turno_id: it.turno_id || null, estado: estado, mensagem: mensagem || ''
      }}));
    } catch (e) { /* navegador sem CustomEvent: só a tela não se atualiza */ }
  }

  // Depois de gravar a auditoria (pela fila ou pela tela), os outros envios
  // guardados dela passam a partir dessa versão — foram escritos por quem
  // acabou de gravar, não por outra pessoa.
  function atualizarVersao(auditId, versao) {
    if (!versao) { return Promise.resolve(); }
    return todos().then(function (itens) {
      return Promise.all(itens.filter(function (i) {
        return i.tipo === 'auditoria' && i.audit_id === auditId && i.estado === 'pendente';
      }).map(function (i) { i.versao_base = versao; return gravar(i); }));
    });
  }

  // ── Como cada tipo sobe ───────────────────────────────────────────────
  var ENVIAR = {
    // Passagem de turno: primeiro o turno, depois as fotos (elas precisam do
    // id do turno). Se cair no meio, o item lembra onde parou.
    turno: function (it, s) {
      var passo = Promise.resolve({tipo: 'ok'});
      if (!it.turno_id) {
        passo = pedir('/passagem-de-turno/api/turnos', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': s.csrf},
          body: JSON.stringify(it.corpo)
        }).then(function (r) {
          if (r.tipo === 'recusado') { r.tipo = 'conflito'; }
          if (r.tipo !== 'ok') { return r; }
          it.turno_id = r.dados.id;
          return gravar(it).then(function () { return {tipo: 'ok'}; });
        });
      }
      return passo.then(function (r) {
        if (r.tipo !== 'ok') { return r; }
        return enviarFotosDoTurno(it, s);
      });
    },

    auditoria: function (it, s) {
      var corpo = Object.assign({}, it.corpo);
      if (it.versao_base && !it.forcar) { corpo.versao_base = it.versao_base; }
      return pedir('/audits/' + it.audit_id, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': s.csrf},
        body: JSON.stringify(corpo)
      }).then(function (r) {
        if (r.tipo === 'recusado') { r.tipo = 'conflito'; }
        if (r.tipo !== 'ok') { return r; }
        return atualizarVersao(it.audit_id, r.dados.versao).then(function () { return r; });
      });
    },

    // Execução de checklist da rota (Fase 4A): um envio só, com as fotos.
    // A marca envio_id faz o servidor devolver a mesma execução se este
    // envio já tinha chegado (resposta perdida no caminho).
    execucao: function (it, s) {
      var fd = new FormData();
      fd.append('corpo', JSON.stringify(it.corpo));
      (it.fotos || []).forEach(function (f) {
        fd.append(f.campo, f.arquivo, (f.arquivo && f.arquivo.name) || 'foto.jpg');
      });
      return pedir('/app/api/execucoes', {
        method: 'POST', headers: {'X-CSRFToken': s.csrf}, body: fd
      }).then(function (r) {
        // Recusa da regra (tarefa já feita por outra pessoa, QR errado):
        // fica para a pessoa ver no painel da fila, não trava os outros.
        if (r.tipo === 'recusado') { r.tipo = 'conflito'; }
        return r;
      });
    },

    'auditoria-foto': function (it, s) {
      var fd = new FormData();
      fd.append('arquivo', it.arquivo, it.nome || it.arquivo.name || 'foto.jpg');
      fd.append('envio', it.envio);
      return pedir('/audits/' + it.audit_id + '/itens/' +
                   encodeURIComponent(it.item_code) + '/anexos', {
        method: 'POST', headers: {'X-CSRFToken': s.csrf}, body: fd
      }).then(function (r) {
        if (r.tipo === 'recusado') { r.tipo = 'conflito'; }
        if (r.tipo !== 'ok') { return r; }
        return atualizarVersao(it.audit_id, r.dados.versao).then(function () { return r; });
      });
    }
  };

  function enviarFotosDoTurno(it, s) {
    var grupos = (it.anexos || []).filter(function (g) { return !g.feito; });
    var cadeia = Promise.resolve({tipo: 'ok'});
    grupos.forEach(function (g) {
      cadeia = cadeia.then(function (r) {
        if (r.tipo !== 'ok') { return r; }
        var fd = new FormData();
        fd.append('atividade', g.atividade || '');
        fd.append('envio', g.envio);
        (g.arquivos || []).forEach(function (f) { fd.append('arquivo', f, f.name || 'foto.jpg'); });
        return pedir('/passagem-de-turno/api/turnos/' + it.turno_id + '/anexos', {
          method: 'POST', headers: {'X-CSRFToken': s.csrf}, body: fd
        }).then(function (r2) {
          if (r2.tipo === 'ok' || r2.tipo === 'recusado' || r2.tipo === 'conflito') {
            // O turno já está gravado: uma foto recusada (grande demais,
            // formato errado) não pode prender o resto na fila para sempre.
            // Fica anotada para a pessoa ver.
            g.feito = true;
            if (r2.tipo !== 'ok') { g.recusa = r2.mensagem; }
            return gravar(it).then(function () { return {tipo: 'ok'}; });
          }
          return r2;
        });
      });
    });
    return cadeia.then(function (r) {
      if (r.tipo !== 'ok') { return r; }
      var recusas = (it.anexos || []).filter(function (g) { return g.recusa; });
      if (recusas.length) {
        return {tipo: 'aviso',
                mensagem: 'A passagem foi enviada, mas ' +
                          (recusas.length === 1 ? '1 grupo de fotos foi recusado: '
                                                : recusas.length + ' grupos de fotos foram recusados: ') +
                          recusas[0].recusa};
      }
      return {tipo: 'ok'};
    });
  }

  // ── A fila em si ──────────────────────────────────────────────────────
  var ocupado = false;
  var ultimaSituacao = '';   // '' | 'sessao' | 'rede'

  function enviarPendentes() {
    if (ocupado) { return Promise.resolve(); }
    var trabalho = function () {
      ocupado = true;
      return todos().then(function (itens) {
        var fila = meus(itens).filter(function (i) { return i.estado === 'pendente'; })
          .sort(function (a, b) { return a.criado_em - b.criado_em; });
        if (!fila.length) { ultimaSituacao = ''; return; }
        return sessao().then(function (quem) {
          var uid = usuarioDaPagina();
          // Sem resposta do sistema é falta de sinal, não de login.
          if (quem.situacao === 'rede') { ultimaSituacao = 'rede'; return; }
          // O servidor respondeu sem sessão — ou com OUTRA pessoa logada
          // neste aparelho (celular do piso, compartilhado). Nos dois casos
          // só sobe quando o autor entrar de novo.
          var s = quem.dados;
          if (quem.situacao !== 'ok' || !s || s.user_id !== uid) {
            ultimaSituacao = 'sessao'; return;
          }
          ultimaSituacao = '';
          var cadeia = Promise.resolve(true);
          fila.forEach(function (it) {
            cadeia = cadeia.then(function (seguir) {
              if (!seguir) { return false; }
              var enviar = ENVIAR[it.tipo];
              if (!enviar) { return true; }
              return enviar(it, s).then(function (r) {
                if (r.tipo === 'ok') {
                  return apagar(it.id).then(function () {
                    avisarEnviado(it, 'enviado');
                    return true;
                  });
                }
                if (r.tipo === 'aviso') {
                  it.estado = 'aviso'; it.mensagem = r.mensagem;
                  return gravar(it).then(function () {
                    avisarEnviado(it, 'aviso', r.mensagem);
                    return true;
                  });
                }
                if (r.tipo === 'conflito') {
                  it.estado = 'conflito'; it.mensagem = r.mensagem;
                  return gravar(it).then(function () { return true; });
                }
                ultimaSituacao = r.tipo;   // rede ou sessão: para e tenta depois
                return false;
              });
            });
          });
          return cadeia;
        });
      }).catch(function () { /* banco do aparelho indisponível: tenta depois */ })
        .then(function () { ocupado = false; desenhar(); });
    };
    // Duas abas abertas não sobem o mesmo item ao mesmo tempo.
    if (navigator.locks && navigator.locks.request) {
      return navigator.locks.request('trino-fila', trabalho);
    }
    return trabalho();
  }

  // ── O que a página vê ─────────────────────────────────────────────────
  var selo = null;

  function descrever(i) {
    var quando = new Date(i.criado_em);
    var hora = quando.toLocaleString('pt-BR', {day: '2-digit', month: '2-digit',
                                                hour: '2-digit', minute: '2-digit'});
    var estado = {
      pendente: ultimaSituacao === 'sessao' ? 'Aguardando você entrar no sistema'
                                             : 'Aguardando conexão',
      conflito: 'Precisa da sua decisão',
      aviso: 'Enviado, com aviso'
    }[i.estado] || i.estado;
    return {rotulo: i.rotulo || 'Envio guardado', hora: hora, estado: estado};
  }

  function esc(s) {
    return String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g, function (m) {
      return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'}[m];
    });
  }

  function textoDoItem(i) {
    // O que foi escrito, em texto corrido, para a pessoa copiar num conflito.
    var c = i.corpo || {};
    var partes = [];
    if (i.tipo === 'turno') {
      partes.push((c.turno || '') + ' de ' + (c.data_turno || ''));
      if (c.observacao) { partes.push('Observação: ' + c.observacao); }
      (c.pendencias || []).forEach(function (p) {
        if (p.titulo) { partes.push('Pendência: ' + p.titulo + (p.descricao ? ' — ' + p.descricao : '')); }
      });
      (c.ocorrencias || []).forEach(function (o) {
        if (o.descricao) { partes.push('Ocorrência (' + (o.tipo || '') + '): ' + o.descricao); }
      });
      Object.keys(c.dados || {}).forEach(function (k) {
        var v = c.dados[k];
        if (v && typeof v === 'object' && v.observacao) {
          partes.push(k.replace('atividade:', '') + ': ' + v.observacao);
        } else if (v && typeof v !== 'object') {
          partes.push(k + ': ' + v);
        }
      });
    } else if (i.tipo === 'auditoria') {
      if (c.general_obs) { partes.push('Observação geral: ' + c.general_obs); }
      Object.keys(c.items || {}).forEach(function (k) {
        var v = c.items[k];
        if (v && (v.result || v.obs)) {
          partes.push(k + ': ' + (v.result || '—') + (v.obs ? ' — ' + v.obs : ''));
        }
      });
    } else if (i.tipo === 'auditoria-foto') {
      partes.push('Foto do item ' + i.item_code + ' (' + (i.nome || 'foto') + ')');
    }
    return partes.join('\n');
  }

  function desenhar() {
    if (usuarioDaPagina() === null) { return; }
    todos().then(function (itens) {
      var lista = meus(itens);
      if (!selo) {
        selo = document.createElement('button');
        selo.type = 'button';
        selo.className = 'fila-selo';
        selo.hidden = true;
        selo.addEventListener('click', abrirPainel);
        document.body.appendChild(selo);
      }
      if (!lista.length) { selo.hidden = true; return; }
      var decidir = lista.filter(function (i) { return i.estado !== 'pendente'; }).length;
      selo.hidden = false;
      selo.classList.toggle('fila-selo-alerta', decidir > 0);
      selo.innerHTML = '<i class="bi ' + (decidir ? 'bi-exclamation-triangle' : 'bi-cloud-arrow-up') +
        '"></i> ' + (decidir ? decidir + (decidir > 1 ? ' envios precisam' : ' envio precisa') +
        ' de você' : lista.length + (lista.length > 1 ? ' envios guardados' : ' envio guardado') +
        ' no aparelho');
      selo.title = 'Toque para ver o que está guardado neste aparelho';
    }).catch(function () {});
  }

  function abrirPainel() {
    todos().then(function (itens) {
      var lista = meus(itens).sort(function (a, b) { return a.criado_em - b.criado_em; });
      var fundo = document.createElement('div');
      fundo.className = 'fila-painel-fundo';
      fundo.innerHTML =
        '<div class="fila-painel" role="dialog" aria-label="Envios guardados neste aparelho">' +
          '<div class="fila-painel-topo"><strong>Guardados neste aparelho</strong>' +
          '<button type="button" class="btn-close" data-fila="fechar" aria-label="Fechar"></button></div>' +
          // Sem envio em segundo plano (o service worker não tem 'sync'): a
          // fila só anda com o sistema aberto em alguma tela do aparelho, e
          // o texto não pode prometer mais do que isso.
          '<p class="fila-painel-nota">O que você escreveu sem internet fica aqui e sobe ' +
          'sozinho quando houver sinal, com o sistema aberto neste aparelho. ' +
          'Nada daqui é apagado sem você mandar.</p>' +
          lista.map(function (i) {
            var d = descrever(i);
            var botoes = '';
            if (i.estado === 'conflito' || i.estado === 'aviso') {
              botoes += '<button type="button" class="btn btn-sm btn-outline-secondary" ' +
                        'data-fila="ver" data-id="' + esc(i.id) + '">Ver o que foi escrito</button>';
            }
            if (i.estado === 'conflito' && i.tipo === 'auditoria') {
              botoes += '<button type="button" class="btn btn-sm btn-outline-primary" ' +
                        'data-fila="forcar" data-id="' + esc(i.id) + '">Enviar mesmo assim</button>';
            }
            if (i.estado === 'conflito') {
              botoes += '<button type="button" class="btn btn-sm btn-outline-secondary" ' +
                        'data-fila="retentar" data-id="' + esc(i.id) + '">Tentar de novo</button>';
            }
            botoes += '<button type="button" class="btn btn-sm btn-outline-danger" ' +
                      'data-fila="descartar" data-id="' + esc(i.id) + '">' +
                      (i.estado === 'aviso' ? 'Dispensar' : 'Descartar') + '</button>';
            return '<div class="fila-item fila-' + esc(i.estado) + '">' +
              '<div class="fila-item-rotulo">' + esc(d.rotulo) + '</div>' +
              '<div class="fila-item-meta">' + esc(d.hora) + ' · ' + esc(d.estado) + '</div>' +
              (i.mensagem ? '<div class="fila-item-msg">' + esc(i.mensagem) + '</div>' : '') +
              '<div class="fila-item-texto" hidden></div>' +
              '<div class="fila-item-acoes">' + botoes + '</div></div>';
          }).join('') +
          '<div class="fila-painel-rodape"><button type="button" class="btn btn-primary btn-sm" ' +
          'data-fila="enviar">Tentar enviar agora</button></div>' +
        '</div>';
      document.body.appendChild(fundo);
      fundo.addEventListener('click', function (ev) {
        var alvo = ev.target.closest('[data-fila]');
        if (ev.target === fundo) { fundo.remove(); return; }
        if (!alvo) { return; }
        var acao = alvo.getAttribute('data-fila');
        var id = alvo.getAttribute('data-id');
        var item = lista.filter(function (i) { return i.id === id; })[0];
        if (acao === 'fechar') { fundo.remove(); return; }
        if (acao === 'enviar') {
          fundo.remove(); enviarPendentes(); return;
        }
        if (!item) { return; }
        if (acao === 'ver') {
          var caixa = alvo.closest('.fila-item').querySelector('.fila-item-texto');
          caixa.hidden = !caixa.hidden;
          caixa.textContent = textoDoItem(item) || '(sem texto)';
          return;
        }
        if (acao === 'descartar') {
          var aviso = item.estado === 'aviso' ? 'Dispensar este aviso?' :
            'Descartar apaga deste aparelho o que foi escrito e NÃO envia. ' +
            'Não dá para desfazer. Descartar mesmo assim?';
          if (!confirm(aviso)) { return; }
          apagar(item.id).then(function () { fundo.remove(); desenhar(); });
          return;
        }
        if (acao === 'retentar' || acao === 'forcar') {
          if (acao === 'forcar' && !confirm(
              'Enviar mesmo assim grava o que você escreveu POR CIMA do que ' +
              'foi salvo depois na auditoria. Continuar?')) { return; }
          item.estado = 'pendente';
          item.mensagem = '';
          if (acao === 'forcar') { item.forcar = true; }
          gravar(item).then(function () { fundo.remove(); enviarPendentes(); });
        }
      });
    });
  }

  // ── Sair do sistema ───────────────────────────────────────────────────
  // Com envio pendente: avisa e mantém guardado. Em qualquer caso, apaga as
  // telas que o app guardou para abrir sem internet (ver static/pwa/sw.js).
  function apagarTelasGuardadas() {
    var feito = [];
    if (window.caches && caches.delete) { feito.push(caches.delete('trino-telas').catch(function () {})); }
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      navigator.serviceWorker.controller.postMessage({tipo: 'apagar-telas'});
    }
    return Promise.all(feito);
  }

  // Avisa dos envios guardados e, se a pessoa confirma, apaga as telas
  // guardadas. → Promise<boolean>: sair ou ficar.
  function conferirSaida() {
    return todos().then(function (itens) { return meus(itens).length; }, function () { return 0; })
      .then(function (n) {
        if (n && !confirm(
            'Há ' + n + (n > 1 ? ' envios guardados' : ' envio guardado') +
            ' neste aparelho, ainda sem subir.\n\nEles continuam guardados e ' +
            'sobem sozinhos quando VOCÊ entrar de novo neste aparelho com ' +
            'conexão. Ninguém mais consegue enviá-los.\n\nSair mesmo assim?')) {
          return false;
        }
        return apagarTelasGuardadas().then(function () { return true; });
      })
      // Falha ao conferir (banco do aparelho bloqueado) não prende ninguém
      // dentro do sistema: sai, e a tela de login apaga as telas guardadas.
      .catch(function () { return true; });
  }

  function ehLogout(endereco) {
    var destino;
    try { destino = new URL(endereco || '', location.href); } catch (e) { return false; }
    return destino.origin === location.origin && /\/logout$/.test(destino.pathname);
  }

  // O link GET /logout, como era no Trino.
  document.addEventListener('click', function (ev) {
    var link = ev.target.closest ? ev.target.closest('a[href]') : null;
    if (!link || !ehLogout(link.href)) { return; }
    ev.preventDefault();
    conferirSaida().then(function (sair) { if (sair) { location.href = link.href; } });
  }, true);

  // O "Sair" do Facilities é um FORMULÁRIO (POST /logout, com o token CSRF),
  // não um link — e o clique no botão passava direto pelo interceptador de
  // cima: sem o aviso dos envios guardados e sem apagar as telas guardadas
  // (num celular compartilhado, a passagem do contrato ficava no aparelho).
  // `submit` pega o botão, o Enter e qualquer outro jeito de enviar. O
  // `submit()` nativo do fim não dispara o evento de novo: não há laço.
  document.addEventListener('submit', function (ev) {
    var form = ev.target;
    if (!form || form.tagName !== 'FORM' || !ehLogout(form.getAttribute('action'))) { return; }
    ev.preventDefault();
    conferirSaida().then(function (sair) {
      if (sair) { HTMLFormElement.prototype.submit.call(form); }
    });
  }, true);

  // ── API para as telas ─────────────────────────────────────────────────
  function guardar(item) {
    var uid = usuarioDaPagina();
    if (uid === null) { return Promise.reject(new Error('sem usuário')); }
    item.id = item.id || novoId();
    item.user_id = uid;
    item.criado_em = Date.now();
    item.estado = 'pendente';
    return gravar(item).then(function () {
      desenhar();
      setTimeout(enviarPendentes, 1500);
      return item;
    });
  }

  // O estado mais novo de uma mesma coisa (a auditoria inteira) substitui o
  // anterior ainda não enviado — mandar os dois seria gravar o velho e em
  // seguida o novo.
  function substituir(chave, item) {
    return todos().then(function (itens) {
      return Promise.all(itens.filter(function (i) {
        return i.chave === chave && i.estado === 'pendente';
      }).map(function (i) { return apagar(i.id); }));
    }).then(function () {
      item.chave = chave;
      return guardar(item);
    });
  }

  function removerPorChave(chave) {
    return todos().then(function (itens) {
      return Promise.all(itens.filter(function (i) {
        return i.chave === chave && i.estado === 'pendente';
      }).map(function (i) { return apagar(i.id); }));
    }).then(desenhar).catch(function () {});
  }

  window.TrinoFila = {
    novoId: novoId,
    guardar: guardar,
    substituir: substituir,
    removerPorChave: removerPorChave,
    atualizarVersao: atualizarVersao,
    enviarAgora: enviarPendentes,
    // Um envio que falhou por falta de rede ou sessão vencida — e não por
    // recusa do servidor — é o que a tela deve guardar na fila.
    ehFalhaDeConexao: function (resposta) {
      if (!resposta) { return true; }
      if (resposta.status === 401) { return true; }
      if (resposta.redirected && /\/login/.test(resposta.url)) { return true; }
      return resposta.status >= 500;
    }
  };

  // ── Quando tentar ─────────────────────────────────────────────────────
  window.addEventListener('online', function () { enviarPendentes(); });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') { enviarPendentes(); }
  });
  setInterval(function () { if (navigator.onLine !== false) { enviarPendentes(); } }, INTERVALO);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { desenhar(); setTimeout(enviarPendentes, 2000); });
  } else {
    desenhar(); setTimeout(enviarPendentes, 2000);
  }
})();
