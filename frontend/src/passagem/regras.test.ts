import { describe, expect, it } from 'vitest';
import {
  avisoDoEnvio, chaveDaArea, coletar, confirmacaoDasTarefas, escolherTurno, idadeDaPendencia, jaEncerrado,
  modeloEmUso, modelosDaArea, perguntasDe, rotuloDoTurno, textoDosEscolhidos, turnosDaArea,
} from './regras';
import type { Modelo } from './tipos';

function modelo(id: number, area_id: number | null, turnos: string[], extra: Partial<Modelo> = {}): Modelo {
  return {
    id, client_id: 1, nome: 'Modelo ' + id, area_id, descricao: '', turnos: turnos.map((nome) => ({ nome })),
    campos: [], atividades: [], perguntas: [], tipos_ocorrencia: [], ativo: true, ...extra,
  };
}

// O CD de Simões Filho: cada turno com o seu modelo, na mesma área.
const T1 = modelo(1, 10, ['T1']);
const T2 = modelo(2, 10, ['T2', 'T3']);
const ALMOX = modelo(3, 20, ['Diurno']);
const SEM_AREA = modelo(4, null, ['Geral']);
const configs = [T1, T2, ALMOX, SEM_AREA];

describe('área, turno e modelo', () => {
  it('a área escolhe os modelos; "Geral (sem área)" é o modelo sem área', () => {
    expect(modelosDaArea(configs, '10').map((c) => c.id)).toEqual([1, 2]);
    expect(modelosDaArea(configs, 'sem-area').map((c) => c.id)).toEqual([4]);
    expect(modelosDaArea(configs, '').length).toBe(4);
    // Área sem modelo cai nos modelos sem área (a área é divisão nova).
    expect(modelosDaArea(configs, '99').map((c) => c.id)).toEqual([4]);
  });

  it('os turnos da área são a união dos modelos, sem repetir', () => {
    expect(turnosDaArea(configs, '10')).toEqual(['T1', 'T2', 'T3']);
  });

  it('o modelo é consequência de área + turno', () => {
    const e = { configs, area: '10', dia: '2026-11-01', encerrados: {} };
    expect(modeloEmUso(e, 'T3')?.id).toBe(2);
    expect(modeloEmUso(e, 'T1')?.id).toBe(1);
    expect(chaveDaArea(modeloEmUso(e, 'T1'))).toBe('area-10');
    expect(chaveDaArea(SEM_AREA)).toBe('contrato-0');
    expect(chaveDaArea(null)).toBe('');
  });

  it('abre no primeiro turno ainda em aberto; com todos fechados, no 1º', () => {
    const e = { configs, area: '10', dia: '2026-11-01', encerrados: { 1: { '2026-11-01': ['T1'] } } };
    expect(jaEncerrado(e, 'T1')).toBe(true);
    expect(escolherTurno(e, '', true, false)).toBe('T2');
    const todos = { ...e, encerrados: { 1: { '2026-11-01': ['T1'] }, 2: { '2026-11-01': ['T2', 'T3'] } } };
    expect(escolherTurno(todos, '', true, false)).toBe('T1');
  });

  it('a escolha à mão sobrevive à troca de data, se o turno continua em aberto', () => {
    const e = { configs, area: '10', dia: '2026-11-02', encerrados: { 2: { '2026-11-01': ['T3'] } } };
    expect(escolherTurno(e, 'T3', true, true)).toBe('T3');
    expect(escolherTurno({ ...e, dia: '2026-11-01' }, 'T3', true, true)).toBe('T1');
    // Sem mexer à mão, a troca de data volta ao primeiro em aberto.
    expect(escolherTurno(e, 'T3', true, false)).toBe('T1');
    // A própria pessoa escolhendo: vale o que ela escolheu, mesmo encerrado.
    expect(escolherTurno({ ...e, dia: '2026-11-01' }, 'T3', false, true)).toBe('T3');
  });

  it('área sem modelo com turno: sem turno e sem modelo', () => {
    const e = { configs: [modelo(5, 30, [])], area: '30', dia: '2026-11-01', encerrados: {} };
    expect(escolherTurno(e, '', true, false)).toBe('');
    expect(modeloEmUso(e, '')?.id).toBe(5);
  });
});

describe('perguntas e envio', () => {
  it('lê o par antigo (atividades + campos) quando não vem a lista única', () => {
    const cfg = modelo(1, null, ['T1'], {
      atividades: [{ nome: 'Doca limpa', codigo: 'doca' }, 'Portão'],
      campos: [{ nome: 'Volumes', tipo: 'numero' }],
    });
    expect(perguntasDe(cfg)).toEqual([
      { nome: 'Doca limpa', codigo: 'doca', tipo: 'sim_nao', obrigatorio: true },
      { nome: 'Portão', codigo: 'Portão', tipo: 'sim_nao', obrigatorio: true },
      { nome: 'Volumes', codigo: 'Volumes', tipo: 'numero', obrigatorio: false },
    ]);
  });

  it('coleta como a tela antiga: campo em branco vai vazio, rotina vai com a observação', () => {
    const perguntas = [
      { nome: 'Doca', codigo: 'doca', tipo: 'sim_nao' },
      { nome: 'Volumes', codigo: 'vol', tipo: 'numero' },
      { nome: 'Situação', codigo: 'sit', tipo: 'escolha', opcoes: ['NORMAL'] },
    ];
    expect(coletar(perguntas, { 'atividade:doca': { concluido: true, observacao: 'ok' }, vol: '12' })).toEqual({
      vol: '12', sit: '', 'atividade:doca': { concluido: true, observacao: 'ok' },
    });
    expect(coletar(perguntas, {})['atividade:doca']).toEqual({ concluido: false, observacao: '' });
  });

  it('os textos do envio', () => {
    const corpo = { data_turno: '2026-11-01', turno: '2º Turno', finalizar: true };
    expect(rotuloDoTurno('Expedição', corpo)).toBe('Encerramento — Expedição, 2º Turno de 01/11');
    expect(rotuloDoTurno(null, { ...corpo, finalizar: false })).toBe('Rascunho — Passagem, 2º Turno de 01/11');
    expect(avisoDoEnvio(corpo, { pendencias_deixadas: 2 }))
      .toBe('Passagem do 2º Turno de 01/11 encerrada. 2 pendências ficaram para o próximo turno.');
    expect(avisoDoEnvio(corpo, { pendencias_deixadas: 1 })).toContain('1 pendência ficou');
    expect(avisoDoEnvio({ ...corpo, finalizar: false }, null))
      .toBe('Rascunho do 2º Turno de 01/11 salvo. Ele só conta quando você encerrar a passagem.');
    expect(confirmacaoDasTarefas(1)).toMatch(/^Há 1 tarefa da gestão sem resposta\. Se encerrar assim, ela vira/);
    expect(confirmacaoDasTarefas(3)).toMatch(/^Há 3 tarefas .* cada uma vira pendência/);
  });

  it('a idade da pendência e o resumo dos arquivos', () => {
    expect(idadeDaPendencia({ dias: 2, horas: 50 })).toBe('aberta há 2 dias');
    expect(idadeDaPendencia({ dias: 1, horas: 30 })).toBe('aberta há 1 dia');
    expect(idadeDaPendencia({ dias: 0, horas: 3 })).toBe('aberta há 3h');
    expect(idadeDaPendencia({ dias: 0, horas: 0 })).toBe('aberta agora');
    expect(textoDosEscolhidos(0, [])).toBe('');
    expect(textoDosEscolhidos(2, [])).toBe('2 arquivos escolhidos');
    expect(textoDosEscolhidos(1, ['1 foto · 300 KB'])).toBe('1 foto · 300 KB');
  });
});
