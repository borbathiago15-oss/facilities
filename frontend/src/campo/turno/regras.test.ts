import { afterEach, describe, expect, it } from 'vitest';
import { destino } from '../qr';
import {
  chaveChegada, chaveFeitas, chaveTroca, chegadaDe, exigeChegada, faltantes, fraseDoQueFalta, hojeLocal,
  lerTroca, marcarFeita, regrasDoTurno, respostaFeito, situacao, VALIDADE_TROCA_MS, visivel,
  apagarMarcasVencidas, feitasNoAparelho,
} from './regras';
import type { DadosDoTurno, ItemDoChecklist, Tarefa, Versao } from './tipos';

const MIN = 60000;
const AGORA = Date.parse('2026-11-02T13:00:00Z');
const SITUACOES = { concluida_no_prazo: 'Feita no horário', nao_realizada: 'Não realizada' };

function tarefa(id: number, minutos: number, extra: Partial<Tarefa> = {}): Tarefa {
  return {
    id, ponto: 'QR' + id, ponto_nome: 'Ponto ' + id, ambiente: 'Área ' + id, local: 'GL 1', local_id: 1,
    rota: 'Limpeza', hora: '10:00', previsto: new Date(AGORA + minutos * MIN).toISOString(), tolerancia: 10,
    fim_turno: new Date(AGORA + 8 * 60 * MIN).toISOString(), versao: 1, minha: true, escalado: 'Ana',
    status: 'prevista', situacao: '', tempo_previsto_min: null, ...extra,
  };
}

function dados(tarefas: Tarefa[], extra: Partial<DadosDoTurno> = {}): DadosDoTurno {
  return {
    usuario: 7, agora: '', tarefas, versoes: {}, pontos: {}, preventivas: [], motivos: {},
    motivos_atraso: {}, motivos_nao_feito: {}, motivos_troca: {}, tolerancia_atraso_min: 10,
    locais: [], situacoes: SITUACOES, ocorrencias: [], ...extra,
  };
}

afterEach(() => { localStorage.clear(); sessionStorage.clear(); });

describe('situação da tarefa agora', () => {
  it('prevista, no horário, atrasada e turno encerrado, pela hora', () => {
    const s = (min: number, fim?: number) => situacao(
      tarefa(1, min, fim === undefined ? {} : { fim_turno: new Date(AGORA + fim * MIN).toISOString() }),
      SITUACOES, {}, AGORA).cod;
    expect(s(30)).toBe('prevista');
    expect(s(10)).toBe('no_horario');            // a tolerância vale para os dois lados
    expect(s(-10)).toBe('no_horario');
    expect(s(-11)).toBe('atrasada');
    expect(s(-120, -1)).toBe('perdida');
  });

  it('o servidor é a verdade; a marca do aparelho só vale enquanto ele não registrou', () => {
    expect(situacao(tarefa(1, 0, { status: 'concluida_no_prazo' }), SITUACOES, { 1: 'Enviada' }, AGORA))
      .toEqual({ cod: 'concluida_no_prazo', rotulo: 'Feita no horário' });
    expect(situacao(tarefa(1, 0), SITUACOES, { 1: 'Guardada no aparelho' }, AGORA))
      .toEqual({ cod: 'guardada', rotulo: 'Guardada no aparelho' });
    marcarFeita(7, 1, 'Enviada');
    marcarFeita(7, 2, 'Guardada no aparelho');
    apagarMarcasVencidas(dados([tarefa(1, 0, { status: 'concluida_no_prazo' }), tarefa(2, 0)]));
    expect(feitasNoAparelho(7)).toEqual({ 2: 'Guardada no aparelho' });
  });
});

describe('a próxima tarefa e o que aparece', () => {
  const r = (ts: Tarefa[]) => regrasDoTurno(dados(ts), () => AGORA);

  it('a atrasada ou a da hora primeiro, senão a primeira que ainda vai chegar', () => {
    const futura = tarefa(1, 60), daHora = tarefa(2, 5), atrasada = tarefa(3, -30);
    expect(r([futura, daHora, atrasada]).proximaTarefa(1, null)?.id).toBe(3);
    expect(r([futura, daHora, atrasada]).proximaTarefa(1, atrasada)?.id).toBe(2);
    expect(r([futura]).proximaTarefa(1, null)?.id).toBe(1);
    expect(r([tarefa(1, 0, { status: 'concluida_no_prazo' })]).proximaTarefa(1, null)).toBeNull();
  });

  it('só as minhas; as dos colegas num toque; sem nenhuma minha, todas', () => {
    const minha = tarefa(1, 0), colega = tarefa(2, 10, { minha: false, escalado: 'Bia' });
    expect(r([colega, minha]).tarefasVisiveis(1, false)).toEqual({ lista: [minha], minhas: 1, todas: 2 });
    expect(r([colega, minha]).tarefasVisiveis(1, true).lista).toEqual([minha, colega]);
    expect(r([colega]).tarefasVisiveis(1, false).lista).toEqual([colega]);
  });

  it('o QR abre direto a tarefa da hora desta pessoa (ou sem dono), nunca a de outra', () => {
    const daOutra = tarefa(1, 0, { minha: false, escalado: 'Bia', ponto: 'X' });
    const semDono = tarefa(2, 5, { minha: false, escalado: '', ponto: 'X' });
    expect(r([daOutra]).tarefaDaHora('X')).toBeUndefined();
    expect(r([daOutra, semDono]).tarefaDaHora('X')?.id).toBe(2);
  });

  it('adiantar: a próxima ainda fora do horário, que não está guardada no aparelho', () => {
    const cedo = tarefa(1, 120, { ponto: 'X' }), depois = tarefa(2, 240, { ponto: 'X' });
    expect(r([depois, cedo]).tarefaParaAdiantar('X')?.id).toBe(1);
    marcarFeita(7, 1, 'Guardada no aparelho');
    expect(r([depois, cedo]).tarefaParaAdiantar('X')?.id).toBe(2);
    expect(r([tarefa(3, 0, { ponto: 'X' })]).tarefaParaAdiantar('X')).toBeNull();
  });
});

describe('chegada e troca de área no aparelho', () => {
  it('as chaves são as mesmas da tela antiga', () => {
    expect([chaveFeitas(7), chaveChegada(7), chaveTroca(7)])
      .toEqual(['trino-turno-feitas-7', 'trino-turno-chegada-7', 'trino-turno-troca-7']);
  });

  it('a chegada guardada sem sinal só vale no mesmo dia', () => {
    const local = { id: 3, nome: 'GL 3', entrada: 'QRE', entrada_nome: 'Portaria', chegada: null };
    expect(exigeChegada(7, local)).toBe(true);
    localStorage.setItem(chaveChegada(7), JSON.stringify({ 3: { hora: '07:10', data: hojeLocal(), guardada: true } }));
    expect(chegadaDe(7, local)?.hora).toBe('07:10');
    expect(exigeChegada(7, local)).toBe(false);
    localStorage.setItem(chaveChegada(7), JSON.stringify({ 3: { hora: '07:10', data: '2020-01-01' } }));
    expect(exigeChegada(7, local)).toBe(true);
    expect(exigeChegada(7, { ...local, entrada: null })).toBe(false);
  });

  it('o motivo da troca vale por 30 minutos', () => {
    sessionStorage.setItem(chaveTroca(7), JSON.stringify({ motivo: 'pedido_cliente', rotulo: 'Pedido do cliente', em: AGORA }));
    expect(lerTroca(7, AGORA + 5 * MIN)?.motivo).toBe('pedido_cliente');
    expect(lerTroca(7, AGORA + VALIDADE_TROCA_MS)).toBeNull();
  });
});

describe('o checklist', () => {
  const it_ = (codigo: string, extra: Partial<ItemDoChecklist> = {}): ItemDoChecklist =>
    ({ codigo, texto: codigo, tipo: 'sim_nao', ...extra });
  const versao = (itens: ItemDoChecklist[], antes = true, depois = true) =>
    ({ itens, foto_antes: antes, foto_depois: depois } as Versao);

  it('o check verde é a resposta boa do item', () => {
    expect(respostaFeito(it_('a'))).toBe('sim');
    expect(respostaFeito(it_('a', { problema_se: 'sim' }))).toBe('nao');
    expect(respostaFeito(it_('a', { tipo: 'conforme' }))).toBe('conforme');
  });

  it('o que falta, na ordem da tela, e a frase', () => {
    const v = versao([it_('pia'), it_('lixo', { exige_foto: true })]);
    const f = faltantes(v, { respostas: {}, fotos: {} });
    expect(fraseDoQueFalta(f)).toBe('Faltam a foto do antes, 2 itens e a foto do depois');
    // Item com foto exigida: sem a foto, ainda falta; "não deu" dispensa a foto.
    expect(fraseDoQueFalta(faltantes(v, { respostas: { pia: 'sim', lixo: 'sim' }, fotos: {} })))
      .toBe('Faltam a foto do antes, 1 item e a foto do depois');
    const tudo = { antes: new File([], 'a'), depois: new File([], 'd') };
    expect(fraseDoQueFalta(faltantes(v, { respostas: { pia: 'sim', lixo: 'nao_feito' }, fotos: tudo })))
      .toBe('Tudo respondido.');
    expect(fraseDoQueFalta(faltantes(v, { respostas: { pia: 'sim' }, fotos: tudo }))).toBe('Falta 1 item');
    expect(fraseDoQueFalta(faltantes(versao([it_('a'), it_('b')], false, false), { respostas: {}, fotos: {} })))
      .toBe('Faltam 2 itens');
  });

  it('item condicional só conta quando a condição se cumpre', () => {
    const cond = it_('qual', { tipo: 'texto', mostrar_se: { codigo: 'vazou', valor: 'Sim' } });
    expect(visivel(cond, { vazou: 'nao' })).toBe(false);
    expect(visivel(cond, { vazou: 'sim' })).toBe(true);
    const v = versao([it_('vazou'), cond], false, false);
    expect(faltantes(v, { respostas: { vazou: 'nao' }, fotos: {} })).toEqual([]);
    expect(faltantes(v, { respostas: { vazou: 'sim' }, fotos: {} })).toEqual(['1 item']);
  });
});

describe('leitor de QR: só abre QR do próprio sistema', () => {
  it('como o destino() da tela antiga', () => {
    const aqui = 'https://facilities.trino.com/novo/app/ler-qr';
    const d = (t: string) => destino(t, aqui);
    expect([
      d('https://facilities.trino.com/q/yKRZYpIynxphxvqui581Iw'),
      d('/q/yKRZYpIynxphxvqui581Iw'),
      d('https://outro.site/q/yKRZYpIynxphxvqui581Iw'),
      d('https://facilities.trino.com.golpe.io/q/yKRZYpIynxphxvqui581Iw'),
      d('https://facilities.trino.com/admin/usuarios'),
      d('javascript:alert(1)'),
      d('https://facilities.trino.com/q/../admin'),
    ]).toEqual(['/q/yKRZYpIynxphxvqui581Iw', '/q/yKRZYpIynxphxvqui581Iw', null, null, null, null, null]);
  });
});
