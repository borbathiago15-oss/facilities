// Os três gráficos do painel da passagem, com a MESMA configuração da tela
// antiga (static/js/diario_dashboard.js) e a mesma biblioteca, do arquivo de
// sempre (static/vendor/chart/chart.umd.min.js: a CSP só aceita script
// deste site). As funções que montam a configuração são puras (testadas).
import { plural } from './gestao';
import type { Burndown, LinhaDoComparativo, LinhaDoPareto } from './tipos';

let carregando: Promise<void> | null = null;

/** O Chart.js, carregado só no painel. Sem ele, a tela segue sem gráficos. */
export function carregarChart(): Promise<void> {
  if (window.Chart) return Promise.resolve();
  if (!carregando) {
    carregando = new Promise((ok) => {
      const s = document.createElement('script');
      s.src = '/static/vendor/chart/chart.umd.min.js';
      s.onload = () => ok();
      s.onerror = () => { carregando = null; ok(); };
      document.head.appendChild(s);
    });
  }
  return carregando;
}

const NAVY = '#0c2340', RED = '#ef4444', GREEN = '#22c55e', GREY = '#9ca3af';

/** O nome da categoria no eixo, abreviado pela largura do gráfico (em 390px
 * ele saía cortado na borda do cartão); o tooltip mostra o nome inteiro. */
export function rotuloCurto(nome: string, largura: number): string {
  nome = String(nome || '');
  const max = largura < 420 ? 16 : (largura < 640 ? 22 : 34);
  return nome.length > max ? nome.slice(0, max - 1).trim() + '…' : nome;
}

// ── Pareto: barras horizontais, vitais em vermelho ───────────────────────
export function configDoPareto(pareto: LinhaDoPareto[], largura: () => number) {
  return {
    type: 'bar',
    data: {
      labels: pareto.map((p) => p.tipo),
      datasets: [{
        label: 'Ocorrências',
        data: pareto.map((p) => p.qtd),
        backgroundColor: pareto.map((p) => (p.vital ? RED : GREY)),
        borderRadius: 4, barThickness: 18,
      }],
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          title: (itens: { dataIndex: number }[]) => pareto[itens[0].dataIndex].tipo,
          label: (ctx: { dataIndex: number }) => {
            const p = pareto[ctx.dataIndex];
            return plural(p.qtd, 'ocorrência', 'ocorrências') + ' · ' +
              String(p.pct).replace('.', ',') + '% do total · acumulado ' +
              String(p.acumulado).replace('.', ',') + '%';
          } } },
      },
      scales: {
        x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#f3f4f6' } },
        y: { grid: { display: false },
          ticks: { callback(this: { getLabelForValue(v: unknown): string }, valor: unknown) {
            return rotuloCurto(this.getLabelForValue(valor), largura());
          } } },
      },
    },
  };
}

// ── Turnos: aderência (%) em barra, ocorrências em linha no 2º eixo ─────
export function configDosTurnos(comparativo: LinhaDoComparativo[]) {
  const cor: Record<string, string> = { ok: GREEN, alerta: '#f59e0b', critico: RED, neutro: GREY };
  return {
    data: {
      labels: comparativo.map((t) => t.turno),
      datasets: [
        {
          type: 'bar', label: 'Aderência (%)', yAxisID: 'y',
          data: comparativo.map((t) => t.pct),
          backgroundColor: comparativo.map((t) => cor[t.faixa] || GREY),
          borderRadius: 4, maxBarThickness: 46, order: 2,
        },
        {
          type: 'line', label: 'Ocorrências', yAxisID: 'y2',
          data: comparativo.map((t) => t.ocorrencias),
          // Reta entre os turnos: são categorias, não uma série contínua.
          borderColor: NAVY, backgroundColor: NAVY, tension: 0,
          pointRadius: 4, borderWidth: 2, order: 1,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, usePointStyle: true } },
        tooltip: { callbacks: { afterBody: (itens: { dataIndex: number }[]) => {
          const t = comparativo[itens[0].dataIndex];
          return plural(t.turnos, 'turno encerrado', 'turnos encerrados') + ' · ' +
            t.cumpridas + '/' + plural(t.exigidas, 'atividade', 'atividades');
        } } },
      },
      scales: {
        y: { beginAtZero: true, max: 100, position: 'left',
          title: { display: true, text: 'Aderência (%)' }, grid: { color: '#f3f4f6' } },
        y2: { beginAtZero: true, position: 'right', ticks: { precision: 0 },
          title: { display: true, text: 'Ocorrências' }, grid: { display: false } },
        x: { grid: { display: false } },
      },
    },
  };
}

// ── Burn-down: o que entra (vermelho) contra o que sai (verde) ──────────
// `monotone`: a curva livre passava do valor entre dois pontos e desenhava
// pendência que não existiu.
export function configDoBurndown(b: Burndown) {
  return {
    type: 'line',
    data: {
      labels: b.labels,
      datasets: [
        { label: 'Novas pendências', data: b.criadas, borderColor: RED,
          backgroundColor: 'rgba(239,68,68,.12)', fill: true, cubicInterpolationMode: 'monotone',
          pointRadius: 2, borderWidth: 2 },
        { label: 'Pendências baixadas', data: b.resolvidas, borderColor: GREEN,
          backgroundColor: 'rgba(34,197,94,.12)', fill: true, cubicInterpolationMode: 'monotone',
          pointRadius: 2, borderWidth: 2 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, usePointStyle: true } } },
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#f3f4f6' } },
        x: { grid: { display: false } },
      },
    },
  };
}

/** Os padrões da tela antiga: a fonte do site e o cinza dos textos. */
export function padroes() {
  if (!window.Chart) return;
  window.Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  window.Chart.defaults.color = '#6b7280';
}
