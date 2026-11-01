import { describe, expect, it } from 'vitest';
import {
  avisoDeUso, codigoDe, decimal, faixaDoPainel, faixaDoRelatorio, faltaNaTarefa, idade, linhaDaPergunta, mover,
  nModelos, opcoesDoTipo, parada, pct, perguntasParaSalvar, plural, prioridadeDoPainel, prioridadeDoRelatorio,
  recorte, turnosDoModelo,
} from './gestao';
import { configDoPareto, rotuloCurto } from './graficos';
import type { DadosDoPainel } from './tipos';

describe('números e textos do painel e do relatório', () => {
  it('escreve como o Jinja: vírgula, "—" e o plural certo', () => {
    expect(decimal(94.7, 1)).toBe('94,7');
    expect(decimal(0.5, 2)).toBe('0,50');
    expect(pct(100)).toBe('100,0%');
    expect(pct(null)).toBe('—');
    expect(plural(1, 'turno', 'turnos')).toBe('1 turno');
    expect(plural(0, 'turno', 'turnos')).toBe('0 turnos');
  });

  it('as faixas e as prioridades', () => {
    expect(faixaDoPainel('ok')).toBe('No alvo');
    expect(faixaDoPainel('neutro')).toBe('Sem rotina cadastrada');
    expect(faixaDoRelatorio('neutro')).toBe('Sem base');
    expect(faixaDoRelatorio('critico')).toBe('Crítico');
    expect(prioridadeDoPainel('MEDIA')).toBe('Média');
    expect(prioridadeDoPainel('urgente')).toBe('urgente');
    expect(prioridadeDoRelatorio('')).toBe('—');
  });

  it('a idade da pendência e o tempo parada', () => {
    expect(idade(2, 50)).toBe('há 2d');
    expect(idade(0, 5)).toBe('há 5h');
    expect(idade(0, 0)).toBe('agora');
    expect(parada(0)).toBe('hoje');
    expect(parada(1)).toBe('há 1 dia');
    expect(parada(3)).toBe('há 3 dias');
  });

  it('o resumo do filtro recolhido diz o recorte', () => {
    const d = {
      clients: [{ id: 1, nome: 'GL Armazém 1' }], client_id: 1, periodo: '7d',
      periodos: [['hoje', 'Hoje'], ['7d', 'Últimos 7 dias']], area_sel: 10, todas_as_areas: 0, turno_sel: '2º Turno',
      dados: { areas_disponiveis: [{ id: 10, nome: 'Expedição' }] },
    } as unknown as DadosDoPainel;
    expect(recorte(d)).toBe('· GL Armazém 1 · últimos 7 dias · Expedição · 2º Turno');
    expect(recorte({ ...d, client_id: null, area_sel: 0, turno_sel: 'todos' })).toBe('· sem contrato · últimos 7 dias');
  });
});

describe('a tarefa para um turno', () => {
  const modelos = [{ id: 7, nome: 'Expedição', turnos: [{ nome: '1º Turno' }, 'Noturno', { codigo: 't3' }, {}] },
    { id: 8, nome: 'Vazio', turnos: [] }];
  it('os turnos do modelo escolhido', () => {
    expect(turnosDoModelo(modelos, '7')).toEqual(['1º Turno', 'Noturno', 't3']);
    expect(turnosDoModelo(modelos, '8')).toEqual([]);
    expect(turnosDoModelo(modelos, '')).toEqual([]);
  });
  it('a mensagem diz o que resolve', () => {
    expect(faltaNaTarefa('', '', '')).toMatch(/ainda não tem modelo de passagem ativo/);
    expect(faltaNaTarefa('7', '', 'x')).toMatch(/não tem turno cadastrado/);
    expect(faltaNaTarefa('7', '1º Turno', '  ')).toBe('Escreva o que precisa ser feito.');
    expect(faltaNaTarefa('7', '1º Turno', 'Conferir')).toBeNull();
  });
});

describe('a configuração dos modelos', () => {
  it('o código sai do nome, sem acento', () => {
    expect(codigoDe('  Sanitários limpos?  ')).toBe('sanitarios_limpos');
    expect(codigoDe('Situação geral do turno')).toBe('situacao_geral_do_turno');
  });

  it('tipo desconhecido ganha a sua opção', () => {
    expect(opcoesDoTipo('sim_nao').length).toBe(5);
    expect(opcoesDoTipo('foto').at(-1)).toEqual(['foto', 'foto']);
  });

  it('salvar sem mexer devolve a pergunta igual; renomear refaz o código', () => {
    const l = linhaDaPergunta(1, { nome: 'Doca limpa', codigo: 'doca', tipo: 'sim_nao', obrigatorio: false });
    expect(perguntasParaSalvar([l]).perguntas).toEqual([
      { nome: 'Doca limpa', codigo: 'doca', tipo: 'sim_nao', obrigatorio: false }]);
    expect(perguntasParaSalvar([{ ...l, nome: 'Doca varrida' }]).perguntas[0].codigo).toBe('doca_varrida');
    const esc = linhaDaPergunta(2, { nome: 'Situação', codigo: 'sit', tipo: 'escolha', opcoes: ['A', 'B'] });
    expect(esc.opcoes).toBe('A\nB');
    expect(perguntasParaSalvar([{ ...esc, opcoes: ' A \n\nB ' }]).perguntas[0].opcoes).toEqual(['A', 'B']);
    // Linha sem nome é descartada.
    expect(perguntasParaSalvar([linhaDaPergunta(3)]).perguntas).toEqual([]);
  });

  it('escolha sem opção e nomes repetidos não salvam', () => {
    const esc = { ...linhaDaPergunta(1), nome: 'Situação', tipo: 'escolha' };
    expect(perguntasParaSalvar([esc]).erro).toMatch(/"Situação" é de escolha, mas está sem opções/);
    const a = { ...linhaDaPergunta(1), nome: 'Doca' };
    expect(perguntasParaSalvar([a, { ...a, n: 2, nome: 'doca' }]).erro).toMatch(/duas perguntas com o mesmo nome \("doca"\)/);
  });

  it('as setas mudam a ordem; nas pontas, nada', () => {
    const l = [{ n: 1 }, { n: 2 }, { n: 3 }];
    expect(mover(l, 2, -1).map((x) => x.n)).toEqual([2, 1, 3]);
    expect(mover(l, 2, 1).map((x) => x.n)).toEqual([1, 3, 2]);
    expect(mover(l, 1, -1)).toBe(l);
    expect(mover(l, 3, 1)).toBe(l);
  });

  it('o aviso do modelo já usado e a contagem de modelos', () => {
    expect(avisoDeUso(0)).toBe('');
    expect(avisoDeUso(1)).toMatch(/^Este modelo já foi usado em 1 turno\. /);
    expect(avisoDeUso(3)).toMatch(/em 3 turnos\./);
    expect(nModelos(1)).toBe('1 modelo');
    expect(nModelos(2)).toBe('2 modelos');
  });
});

describe('os gráficos', () => {
  it('o nome da categoria encolhe com a largura do gráfico', () => {
    const nome = 'Avaria de palete na doca de expedição';
    expect(rotuloCurto(nome, 390)).toBe('Avaria de palet…');
    expect(rotuloCurto(nome, 1000)).toBe('Avaria de palete na doca de exped…');
    expect(rotuloCurto(nome, 500)).toBe('Avaria de palete na d…');
    expect(rotuloCurto('Avaria', 300)).toBe('Avaria');
  });
  it('o Pareto pinta as vitais de vermelho e diz o acumulado', () => {
    const c = configDoPareto([{ tipo: 'Avaria', qtd: 3, pct: 75, acumulado: 75, vital: true },
      { tipo: 'Atraso', qtd: 1, pct: 25, acumulado: 100, vital: false }], () => 600);
    expect(c.data.datasets[0].backgroundColor).toEqual(['#ef4444', '#9ca3af']);
    expect(c.options.plugins.tooltip.callbacks.label({ dataIndex: 0 }))
      .toBe('3 ocorrências · 75% do total · acumulado 75%');
  });
});
