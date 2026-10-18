/* Painel da Passagem de Turno (era embutido no dashboard.html; Fase 9A).
   O contrato vem de <body data-cliente>, os modelos de #tt-modelos e os
   dados dos gráficos de #dop-graficos. */
(function () {
  if (!document.getElementById('tt-area')) return;
  var TT_MODELOS = JSON.parse((document.getElementById('tt-modelos') || {}).textContent || '[]');

  function ttTrocouArea() {
    var sel = document.getElementById('tt-area');
    var alvo = document.getElementById('tt-turno');
    var m = TT_MODELOS.filter(function (x) { return String(x.id) === sel.value; })[0];
    alvo.innerHTML = '';
    var turnos = (m && m.turnos && m.turnos.length) ? m.turnos : [];
    if (!turnos.length) {
      // Modelo sem turno cadastrado: em vez de um select vazio, que não
      // explica nada, a tela diz onde se resolve isso.
      alvo.innerHTML = '<option value="">— nenhum turno no modelo —</option>';
      return;
    }
    turnos.forEach(function (t) {
      var nome = (typeof t === 'string') ? t : (t.nome || t.codigo || '');
      if (!nome) { return; }
      var o = document.createElement('option');
      o.value = nome; o.textContent = nome;
      alvo.appendChild(o);
    });
  }
  document.addEventListener('DOMContentLoaded', ttTrocouArea);

  function ttCriarTarefa() {
    var v = function (id) { return document.getElementById(id).value; };
    // A mensagem tem de dizer o que RESOLVE. "Escolha a área" num contrato
    // que não tem área nenhuma manda a pessoa procurar o que não existe.
    if (!v('tt-area')) {
      alert('Este contrato ainda não tem modelo de passagem ativo. ' +
            'Cadastre um em Configurar e volte aqui.'); return;
    }
    if (!v('tt-turno')) {
      alert('Este modelo não tem turno cadastrado. Cadastre os turnos dele ' +
            'em Configurar.'); return;
    }
    if (!v('tt-titulo').trim()) { alert('Escreva o que precisa ser feito.'); return; }
    var botao = document.getElementById('tt-enviar');
    botao.disabled = true;
    fetch('/passagem-de-turno/api/tarefas-turno', {
      method: 'POST',
      headers: {'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
      body: JSON.stringify({
        client_id: Number(document.body.dataset.cliente || 0), configuracao_id: v('tt-area'),
        data_turno: v('tt-data'), turno: v('tt-turno'),
        titulo: v('tt-titulo'), descricao: v('tt-desc'),
        forma_resposta: v('tt-forma')})
    }).then(function (r) { return r.json().then(function (x) { return {ok: r.ok, x: x}; }); })
      .then(function (res) {
        if (!res.ok) { alert(res.x.error || 'Não foi possível atribuir.'); botao.disabled = false; return; }
        location.reload();
      }).catch(function () { alert('Falha de rede.'); botao.disabled = false; });
  }
  window.ttTrocouArea = ttTrocouArea;
  window.ttCriarTarefa = ttCriarTarefa;
})();
(function () {
  'use strict';
  var CSRF = function () {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : '';
  };
  var CLIENTE = Number(document.body.dataset.cliente || 0);

  // O par de datas só aparece em "Personalizado" — e o formulário não pode
  // auto-submeter enquanto a pessoa ainda está escolhendo De/Até.
  window.dopPeriodoMudou = function (valor) {
    var campos = document.querySelectorAll('.dop-custom');
    for (var i = 0; i < campos.length; i++) { campos[i].hidden = (valor !== 'custom'); }
    if (valor !== 'custom') { document.getElementById('dopFiltros').submit(); }
  };

  window.criarPendenciaGestor = function () {
    var corpo = {
      client_id: CLIENTE,
      titulo: document.getElementById('gestor-p-title').value,
      descricao: document.getElementById('gestor-p-desc').value,
      prioridade: document.getElementById('gestor-p-priority').value
    };
    fetch('/passagem-de-turno/api/pendencias', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF()},
      body: JSON.stringify(corpo)
    }).then(function (r) {
      return r.json().then(function (x) { return {ok: r.ok, x: x}; });
    }).then(function (res) {
      if (!res.ok) { alert(res.x.error || 'Não foi possível salvar.'); return; }
      location.reload();
    });
  };

  // A nota é obrigatória aqui também: o gestor que baixa a pendência pelo
  // painel deve a mesma frase que se pede ao encarregado. Se o caminho curto
  // continuasse existindo no dashboard, ele viraria O caminho.
  window.resolverPendenciaDop = function (id) {
    var texto = prompt('O que foi feito para resolver?');
    if (texto === null) { return; }
    texto = texto.trim();
    if (!texto) { alert('Diga em uma linha o que foi feito.'); return; }
    fetch('/passagem-de-turno/api/pendencias/' + id + '/resolver', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF()},
      body: JSON.stringify({resolucao: texto})
    }).then(function (r) {
      return r.json().then(function (x) { return {ok: r.ok, x: x}; });
    }).then(function (res) {
      if (!res.ok) { alert(res.x.error || 'Não foi possível resolver.'); return; }
      location.reload();
    });
  };

  // Ocorrência → chamado de manutenção. O botão é desabilitado no clique:
  // a rota é idempotente, mas o retorno visual evita a dúvida de "clicou?".
  // Resposta que não é JSON (sem sinal, sessão vencida) também devolve o
  // botão e diz o que houve: antes a promessa quebrava em silêncio e o botão
  // ficava travado, sem mensagem nenhuma.
  window.dopAbrirChamado = function (id, botao) {
    if (botao) { botao.disabled = true; }
    function falhou(msg) {
      if (botao) { botao.disabled = false; }
      alert(msg);
    }
    fetch('/passagem-de-turno/api/ocorrencias/' + id + '/chamado', {
      method: 'POST', headers: {'X-CSRFToken': CSRF()}
    }).then(function (r) {
      return r.json().then(function (x) { return {ok: r.ok, x: x}; },
                           function () { return {ok: false, x: {}}; });
    }).then(function (res) {
      if (!res.ok) {
        falhou(res.x.error || 'Não foi possível abrir o chamado. Recarregue a ' +
               'página e tente de novo.');
        return;
      }
      window.location = res.x.url;
    }, function () {
      falhou('Sem conexão: o chamado não foi aberto. Tente de novo quando o ' +
             'sinal voltar.');
    });
  };

  if (typeof Chart === 'undefined' || !CLIENTE) { return; }

  var NAVY = '#0c2340', BLUE = '#1a5fb4', RED = '#ef4444',
      GREEN = '#22c55e', GREY = '#9ca3af';
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = '#6b7280';

  var graficos = JSON.parse((document.getElementById('dop-graficos') || {}).textContent || '{}');
  var pareto = graficos.pareto || [];
  var comparativo = graficos.comparativo || [];
  var burndown = graficos.burndown || {labels: [], criadas: [], resolvidas: []};

  // "1 ocorrência(s)" no tooltip é o mesmo defeito do texto da tela.
  function plural(n, um, varios) { return n + ' ' + (n === 1 ? um : varios); }

  // ── Pareto: barras horizontais, vitais em vermelho ───────────────────
  // O nome da categoria mora no eixo da esquerda. Em 390px ele saía cortado
  // na borda do cartão, e o eixo largo esmagava as barras.
  // O eixo mostra o nome abreviado com reticências — limite medido pela
  // largura do gráfico — e o tooltip mostra o nome inteiro.
  var elPareto = document.getElementById('dopPareto');
  function rotuloCurto(nome) {
    nome = String(nome || '');
    var largura = elPareto ? elPareto.clientWidth : 600;
    var max = largura < 420 ? 16 : (largura < 640 ? 22 : 34);
    return nome.length > max ? nome.slice(0, max - 1).trim() + '…' : nome;
  }
  if (elPareto && pareto.length) {
    new Chart(elPareto, {
      type: 'bar',
      data: {
        labels: pareto.map(function (p) { return p.tipo; }),
        datasets: [{
          label: 'Ocorrências',
          data: pareto.map(function (p) { return p.qtd; }),
          backgroundColor: pareto.map(function (p) { return p.vital ? RED : GREY; }),
          borderRadius: 4, barThickness: 18
        }]
      },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: {display: false},
          tooltip: {callbacks: {
            title: function (itens) { return pareto[itens[0].dataIndex].tipo; },
            label: function (ctx) {
              var p = pareto[ctx.dataIndex];
              return plural(p.qtd, 'ocorrência', 'ocorrências') + ' · ' +
                     String(p.pct).replace('.', ',') + '% do total · acumulado ' +
                     String(p.acumulado).replace('.', ',') + '%';
            }}}
        },
        scales: {
          x: {beginAtZero: true, ticks: {precision: 0}, grid: {color: '#f3f4f6'}},
          y: {grid: {display: false},
              ticks: {callback: function (valor) {
                return rotuloCurto(this.getLabelForValue(valor));
              }}}
        }
      }
    });
  }

  // ── Turnos: aderência (%) em barra, ocorrências em linha no 2º eixo ──
  var elTurnos = document.getElementById('dopTurnos');
  if (elTurnos && comparativo.length) {
    var cor = {ok: GREEN, alerta: '#f59e0b', critico: RED, neutro: GREY};
    new Chart(elTurnos, {
      data: {
        labels: comparativo.map(function (t) { return t.turno; }),
        datasets: [
          {
            type: 'bar', label: 'Aderência (%)', yAxisID: 'y',
            data: comparativo.map(function (t) { return t.pct; }),
            backgroundColor: comparativo.map(function (t) { return cor[t.faixa] || GREY; }),
            borderRadius: 4, maxBarThickness: 46, order: 2
          },
          {
            type: 'line', label: 'Ocorrências', yAxisID: 'y2',
            data: comparativo.map(function (t) { return t.ocorrencias; }),
            // Reta entre os turnos: são categorias, não uma série contínua,
            // e a curva sugeria valores entre um turno e outro.
            borderColor: NAVY, backgroundColor: NAVY, tension: 0,
            pointRadius: 4, borderWidth: 2, order: 1
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: {position: 'bottom', labels: {boxWidth: 12, usePointStyle: true}},
          tooltip: {callbacks: {afterBody: function (itens) {
            var t = comparativo[itens[0].dataIndex];
            return plural(t.turnos, 'turno encerrado', 'turnos encerrados') + ' · ' +
                   t.cumpridas + '/' + plural(t.exigidas, 'atividade', 'atividades');
          }}}
        },
        scales: {
          y: {beginAtZero: true, max: 100, position: 'left',
              title: {display: true, text: 'Aderência (%)'}, grid: {color: '#f3f4f6'}},
          y2: {beginAtZero: true, position: 'right', ticks: {precision: 0},
               title: {display: true, text: 'Ocorrências'}, grid: {display: false}},
          x: {grid: {display: false}}
        }
      }
    });
  }

  // ── Burn-down: o que entra (vermelho) contra o que sai (verde) ───────
  // `monotone` no lugar da curva livre (tension .3): a curva livre passava
  // do valor entre dois pontos — num dia de 0 seguido de um de 3, a linha
  // descia abaixo de zero e subia acima de 3, desenhando pendência que não
  // existiu. A monótona suaviza sem nunca ultrapassar os pontos.
  var elBurn = document.getElementById('dopBurndown');
  if (elBurn) {
    new Chart(elBurn, {
      type: 'line',
      data: {
        labels: burndown.labels,
        datasets: [
          {label: 'Novas pendências', data: burndown.criadas, borderColor: RED,
           backgroundColor: 'rgba(239,68,68,.12)', fill: true,
           cubicInterpolationMode: 'monotone',
           pointRadius: 2, borderWidth: 2},
          {label: 'Pendências baixadas', data: burndown.resolvidas, borderColor: GREEN,
           backgroundColor: 'rgba(34,197,94,.12)', fill: true,
           cubicInterpolationMode: 'monotone',
           pointRadius: 2, borderWidth: 2}
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: {mode: 'index', intersect: false},
        plugins: {legend: {position: 'bottom', labels: {boxWidth: 12, usePointStyle: true}}},
        scales: {
          y: {beginAtZero: true, ticks: {precision: 0}, grid: {color: '#f3f4f6'}},
          x: {grid: {display: false}}
        }
      }
    });
  }
}());
window.FC_ACOES = Object.assign(window.FC_ACOES || {}, {
  dopPeriodoMudou: window.dopPeriodoMudou, criarPendenciaGestor: window.criarPendenciaGestor,
  resolverPendenciaDop: window.resolverPendenciaDop, dopAbrirChamado: window.dopAbrirChamado,
  ttTrocouArea: function () { if (window.ttTrocouArea) window.ttTrocouArea(); },
  ttCriarTarefa: function () { if (window.ttCriarTarefa) window.ttCriarTarefa(); }
});
