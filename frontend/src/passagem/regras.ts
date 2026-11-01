// As regras da tela da nova passagem, sem tela nenhuma: as mesmas da tela
// antiga (static/js/diario_operacional.js), uma a uma, para poder testar.
import type { Encerrados, Modelo, Pergunta, TarefaDaGestao } from './tipos';

/** O valor da opção "Geral (sem área)" (``AREA_SEM_CADASTRO`` no servidor). */
export const AREA_SEM_CADASTRO = 'sem-area';

export function chaveDe(item: { codigo?: string; nome?: string } | string): string {
  if (typeof item === 'string') return item;
  return item.codigo || item.nome || String(item);
}

/** As perguntas do modelo. O servidor já manda a lista única; o par antigo
 * (atividades + campos) é lido como reserva, como na tela antiga. */
export function perguntasDe(cfg: Modelo): Pergunta[] {
  if (cfg.perguntas && cfg.perguntas.length) return cfg.perguntas;
  const fora: Pergunta[] = (cfg.atividades || []).map((a) => {
    const x = typeof a === 'string' ? { nome: a } : a;
    return {
      nome: x.nome || String(a), codigo: x.codigo || x.nome || String(a),
      tipo: 'sim_nao', obrigatorio: x.obrigatorio !== false,
    };
  });
  return fora.concat((cfg.campos || []).map((c) => ({
    nome: c.nome, codigo: c.codigo || c.nome, tipo: c.tipo || 'texto', obrigatorio: c.obrigatorio === true,
  })));
}

/** Os modelos da área escolhida ('' = contrato sem seletor de área). */
export function modelosDaArea(configs: Modelo[], area: string): Modelo[] {
  if (!area) return configs;
  if (area === AREA_SEM_CADASTRO) return configs.filter((c) => !c.area_id);
  const so = configs.filter((c) => String(c.area_id || '') === area);
  // Contrato sem área cadastrada (ou modelo antigo, sem área) continua
  // vendo os seus modelos.
  return so.length ? so : configs.filter((c) => !c.area_id);
}

export function nomesDeTurno(cfg: Modelo): string[] {
  return (cfg.turnos || []).map((x) => (x && typeof x === 'object' && x.nome) || String(x)).filter(Boolean);
}

/** Os turnos de TODA a área, sem repetir, na ordem dos modelos. */
export function turnosDaArea(configs: Modelo[], area: string): string[] {
  const fora: string[] = [];
  modelosDaArea(configs, area).forEach((c) => {
    nomesDeTurno(c).forEach((n) => { if (!fora.includes(n)) fora.push(n); });
  });
  return fora;
}

/** O modelo é consequência de área + turno. */
export function modeloDe(configs: Modelo[], area: string, turno: string): Modelo | null {
  const lista = modelosDaArea(configs, area);
  for (const c of lista) if (nomesDeTurno(c).includes(turno)) return c;
  return lista[0] || null;
}

export type Escolha = { configs: Modelo[]; area: string; dia: string; encerrados: Encerrados };

export function jaEncerrado(e: Escolha, turno: string): boolean {
  const cfg = modeloDe(e.configs, e.area, turno);
  if (!cfg || !e.dia) return false;
  const doDia = (e.encerrados[String(cfg.id)] || {})[e.dia] || [];
  return doDia.includes(turno);
}

/** O primeiro turno da área ainda em aberto naquela data; todos encerrados → o 1º. */
export function primeiroEmAberto(e: Escolha, disponiveis: string[]): string {
  for (const t of disponiveis) if (!jaEncerrado(e, t)) return t;
  return disponiveis[0];
}

/** O turno do seletor, como a tela antiga decide (``desenhar``):
 * ``preSelecionar`` na abertura e na troca de área ou de data; ``turnoAMao``
 * quando a pessoa já mexeu no seletor. */
export function escolherTurno(e: Escolha, atual: string, preSelecionar: boolean, turnoAMao: boolean): string {
  const disponiveis = turnosDaArea(e.configs, e.area);
  if (!disponiveis.length) return '';
  const existe = disponiveis.includes(atual);
  if (!preSelecionar && existe) return atual;
  if (turnoAMao && existe && !jaEncerrado(e, atual)) return atual;
  return primeiroEmAberto(e, disponiveis);
}

/** O modelo em uso: o da área + turno, ou o primeiro da área sem turno. */
export function modeloEmUso(e: Escolha, turno: string): Modelo | null {
  if (!turnosDaArea(e.configs, e.area).length) return modelosDaArea(e.configs, e.area)[0] || null;
  return modeloDe(e.configs, e.area, turno);
}

/** A mesma regra de ``_chave_da_area`` no servidor. */
export function chaveDaArea(cfg: Modelo | null): string {
  if (!cfg) return '';
  return cfg.area_id ? 'area-' + cfg.area_id : 'contrato-0';
}

export type Resposta = string | { concluido: boolean; observacao: string };

/** O ``dados`` do envio, como ``coletar`` da tela antiga. */
export function coletar(perguntas: Pergunta[], respostas: Record<string, Resposta>) {
  const dados: Record<string, unknown> = {};
  perguntas.forEach((p) => {
    const k = chaveDe(p);
    if ((p.tipo || 'sim_nao') !== 'sim_nao') {
      const v = respostas[k];
      dados[k] = typeof v === 'string' ? v : '';
    }
  });
  perguntas.forEach((p) => {
    const k = chaveDe(p);
    if ((p.tipo || 'sim_nao') === 'sim_nao') {
      const v = respostas['atividade:' + k];
      const r = v && typeof v === 'object' ? v : { concluido: false, observacao: '' };
      dados['atividade:' + k] = { concluido: !!r.concluido, observacao: r.observacao || '' };
    }
  });
  return dados;
}

function diaMes(data: string) {
  const d = (data || '').split('-');
  return d.length === 3 ? d[2] + '/' + d[1] : data;
}

type Corpo = { data_turno: string; turno: string; finalizar: boolean };

/** O rótulo do envio guardado na fila do aparelho. */
export function rotuloDoTurno(nomeDoModelo: string | null, corpo: Corpo): string {
  return (corpo.finalizar ? 'Encerramento' : 'Rascunho') + ' — ' + (nomeDoModelo || 'Passagem') + ', ' +
    corpo.turno + ' de ' + diaMes(corpo.data_turno);
}

/** O recado que o painel mostra depois do envio (``fc-aviso``). */
export function avisoDoEnvio(corpo: Corpo, resposta: { pendencias_deixadas?: number } | null): string {
  const turno = corpo.turno || 'turno';
  const dia = (corpo.data_turno || '').split('-');
  const quando = dia.length === 3 ? ' de ' + dia[2] + '/' + dia[1] : '';
  if (corpo.finalizar) {
    const n = Number((resposta && resposta.pendencias_deixadas) || 0);
    return 'Passagem do ' + turno + quando + ' encerrada.' +
      (n ? ' ' + (n === 1 ? '1 pendência ficou' : n + ' pendências ficaram') + ' para o próximo turno.' : '');
  }
  return 'Rascunho do ' + turno + quando + ' salvo. Ele só conta quando você encerrar a passagem.';
}

/** A pergunta antes de encerrar com tarefa da gestão sem resposta. */
export function confirmacaoDasTarefas(semResposta: number): string {
  return (semResposta === 1
    ? 'Há 1 tarefa da gestão sem resposta. Se encerrar assim, ela vira '
    : 'Há ' + semResposta + ' tarefas da gestão sem resposta. Se encerrar assim, cada uma vira ') +
    'pendência de prioridade alta e quem pediu é avisado. Encerrar mesmo assim?';
}

export function tarefasSemResposta(tarefas: TarefaDaGestao[]): number {
  return tarefas.filter((t) => t.status === 'pendente').length;
}

/** "aberta há 2 dias" / "aberta há 3h" / "aberta agora". */
export function idadeDaPendencia(p: { dias: number; horas: number }): string {
  if (p.dias >= 1) return 'aberta há ' + p.dias + ' dia' + (p.dias > 1 ? 's' : '');
  if (p.horas >= 1) return 'aberta há ' + p.horas + 'h';
  return 'aberta agora';
}

/** O texto de "Tirar foto"/"Anexar arquivo" depois da escolha. */
export function textoDosEscolhidos(arquivos: number, resumos: string[]): string {
  if (!arquivos) return '';
  if (resumos.length) return resumos.join(' + ');
  return arquivos === 1 ? '1 arquivo escolhido' : arquivos + ' arquivos escolhidos';
}
