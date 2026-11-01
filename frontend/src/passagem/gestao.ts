// As regras das telas da gestão da passagem (Fase 2b), sem tela nenhuma: as
// mesmas das telas antigas (templates/diario_operacional/dashboard.html,
// relatorio_mensal.html e configuracao.html, e static/js/diario_dashboard.js
// e diario_config.js), uma a uma, para poder testar.
import type { DadosDoPainel, Pergunta } from './tipos';

/** ``'%.1f'|format(v)|replace('.', ',')``: o número da tela, com vírgula. */
export function decimal(v: number, casas: number): string {
  return v.toFixed(casas).replace('.', ',');
}

/** A porcentagem dos cartões: "—" quando não se aplica (zero de zero). */
export function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : decimal(v, 1) + '%';
}

/** "1 turno(s) encerrado(s)" é a tela admitindo que não sabe contar. */
export function plural(n: number, um: string, varios: string): string {
  return n + ' ' + (n === 1 ? um : varios);
}

/** O texto da faixa no cartão de aderência do painel. */
export function faixaDoPainel(f: string): string {
  if (f === 'ok') return 'No alvo';
  if (f === 'alerta') return 'Atenção';
  if (f === 'critico') return 'Crítico';
  return 'Sem rotina cadastrada';
}

/** O texto da faixa no relatório (``faixa_txt``). */
export function faixaDoRelatorio(f: string): string {
  if (f === 'ok') return 'No alvo';
  if (f === 'alerta') return 'Atenção';
  if (f === 'critico') return 'Crítico';
  return 'Sem base';
}

const PRIORIDADES: Record<string, string> = { baixa: 'Baixa', media: 'Média', alta: 'Alta' };

/** A prioridade no painel: o valor cru quando não é uma das três. */
export function prioridadeDoPainel(v: string): string {
  return PRIORIDADES[(v || '').toLowerCase()] ?? v;
}

/** A prioridade no relatório (``prioridade``): "—" quando vazia. */
export function prioridadeDoRelatorio(v: string): string {
  return PRIORIDADES[(v || '').toLowerCase()] ?? (v || '—');
}

/** "há 0h" é a pendência que acabou de entrar: diz "agora". */
export function idade(dias: number, horas: number): string {
  if (dias >= 1) return 'há ' + dias + 'd';
  if (horas >= 1) return 'há ' + horas + 'h';
  return 'agora';
}

/** "0 dia(s)" para a pendência aberta hoje lia como erro (``parada``). */
export function parada(dias: number): string {
  return dias ? 'há ' + plural(dias, 'dia', 'dias') : 'hoje';
}

/** O resumo do filtro recolhido: o recorte que se está vendo, sem abrir. */
export function recorte(d: DadosDoPainel): string {
  const cliente = d.clients.find((c) => c.id === d.client_id);
  const rotulo = (d.periodos.find(([k]) => k === d.periodo) || [d.periodo, d.periodo])[1];
  let texto = '· ' + (cliente ? cliente.nome : 'sem contrato') + ' · ' + rotulo.toLowerCase();
  if (d.area_sel && d.area_sel !== d.todas_as_areas) {
    const a = (d.dados ? d.dados.areas_disponiveis : []).find((x) => x.id === d.area_sel);
    if (a) texto += ' · ' + a.nome;
  }
  if (d.turno_sel && d.turno_sel !== 'todos') texto += ' · ' + d.turno_sel;
  return texto;
}

/** Os turnos do modelo escolhido na "Tarefa para um turno" (``ttTrocouArea``). */
export function turnosDoModelo(modelos: DadosDoPainel['modelos'], id: string): string[] {
  const m = modelos.find((x) => String(x.id) === id);
  return ((m && m.turnos) || [])
    .map((t) => (typeof t === 'string' ? t : (t.nome || t.codigo || '')))
    .filter(Boolean);
}

/** O que falta para atribuir a tarefa, ou ``null`` (``ttCriarTarefa``). */
export function faltaNaTarefa(area: string, turno: string, titulo: string): string | null {
  // A mensagem tem de dizer o que RESOLVE. "Escolha a área" num contrato
  // que não tem área nenhuma manda a pessoa procurar o que não existe.
  if (!area) {
    return 'Este contrato ainda não tem modelo de passagem ativo. ' +
      'Cadastre um em Configurar e volte aqui.';
  }
  if (!turno) return 'Este modelo não tem turno cadastrado. Cadastre os turnos dele em Configurar.';
  if (!titulo.trim()) return 'Escreva o que precisa ser feito.';
  return null;
}

// ── A configuração dos modelos (diario_config.js) ───────────────────────

/** Os tipos de resposta que a tela do encarregado sabe desenhar. */
export const TIPOS: [string, string][] = [['sim_nao', 'Sim / Não'], ['numero', 'Número'], ['texto', 'Texto'],
  ['texto_longo', 'Texto longo'], ['escolha', 'Escolha (opções)']];

/** Tipo que esta tela não conhece (de uma versão mais nova) ganha a sua
 * opção: em branco, salvar mudaria a pergunta sem ninguém ter pedido. */
export function opcoesDoTipo(atual: string | undefined): [string, string][] {
  const lista = TIPOS.slice();
  if (atual && !TIPOS.some((t) => t[0] === atual)) lista.push([atual, atual]);
  return lista;
}

export function codigoDe(nome: string): string {
  return String(nome).trim().toLowerCase()
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

/** Uma linha de pergunta na tela: ``codigo``/``nomeOriginal`` são os da
 * pergunta que já existia no modelo. */
export type LinhaDePergunta = {
  n: number; nome: string; tipo: string; obrigatorio: boolean; opcoes: string;
  codigo?: string; nomeOriginal?: string;
};

export function linhaDaPergunta(n: number, p?: Pergunta): LinhaDePergunta {
  if (!p) return { n, nome: '', tipo: 'sim_nao', obrigatorio: true, opcoes: '' };
  return {
    n, nome: p.nome || '', tipo: p.tipo || 'sim_nao', obrigatorio: p.obrigatorio !== false,
    opcoes: (p.opcoes || []).join('\n'), codigo: p.codigo || undefined, nomeOriginal: p.nome || undefined,
  };
}

export type PerguntaSalva = { nome: string; codigo: string; tipo: string; obrigatorio: boolean; opcoes?: string[] };

/** As perguntas para salvar, na ordem da tela, ou o erro que impede.
 *
 * Salvar sem mexer em nada devolve o modelo IGUAL: o tipo, as opções, a
 * obrigatoriedade e o código. O código só é recalculado quando a pergunta é
 * renomeada (ou é nova). */
export function perguntasParaSalvar(linhas: LinhaDePergunta[]): { perguntas: PerguntaSalva[]; erro: string | null } {
  let semOpcoes: string | null = null;
  const perguntas = linhas.map((l) => {
    const nomeP = l.nome.trim();
    const codigo = (l.codigo && l.nomeOriginal === nomeP) ? l.codigo : codigoDe(nomeP);
    const p: PerguntaSalva = { nome: nomeP, codigo, tipo: l.tipo, obrigatorio: l.obrigatorio };
    if (l.tipo === 'escolha') {
      p.opcoes = l.opcoes.split('\n').map((o) => o.trim()).filter((o) => o);
      if (nomeP && !p.opcoes.length && !semOpcoes) semOpcoes = nomeP;
    }
    return p;
  }).filter((x) => x.nome);
  // Escolha sem opção não tem o que o encarregado tocar (o servidor a
  // guardaria como texto): melhor dizer agora do que mudar o tipo calado.
  if (semOpcoes) {
    return { perguntas, erro: 'A pergunta "' + semOpcoes + '" é de escolha, mas está sem opções. ' +
      'Escreva as opções, uma por linha, ou troque o tipo da resposta.' };
  }
  // Dois códigos iguais viram a MESMA linha em dados_json: a segunda
  // pergunta sobrescreveria a primeira e a aderência contaria errado.
  const vistos: Record<string, boolean> = {};
  let repetido: string | null = null;
  perguntas.forEach((x) => {
    if (vistos[x.codigo]) repetido = x.nome;
    vistos[x.codigo] = true;
  });
  if (repetido) {
    return { perguntas, erro: 'Há duas perguntas com o mesmo nome ("' + repetido + '"). ' +
      'Renomeie uma delas: as duas viram a mesma linha no turno.' };
  }
  return { perguntas, erro: null };
}

/** Mover a linha ``n`` uma posição (``passo`` -1 sobe, 1 desce). */
export function mover<T extends { n: number }>(lista: T[], n: number, passo: number): T[] {
  const i = lista.findIndex((x) => x.n === n);
  const j = i + passo;
  if (i < 0 || j < 0 || j >= lista.length) return lista;
  const nova = lista.slice();
  [nova[i], nova[j]] = [nova[j], nova[i]];
  return nova;
}

/** Editar um modelo já usado NÃO reescreve o passado: o aviso diz o que muda. */
export function avisoDeUso(usados: number): string {
  return usados
    ? 'Este modelo já foi usado em ' + usados + (usados === 1 ? ' turno' : ' turnos') + '. Alterar as rotinas ' +
      'vale dos próximos turnos em diante — os já encerrados guardam a régua ' +
      'do dia em que foram fechados.'
    : '';
}

/** "1 modelo(s)" é a tela admitindo que não sabe contar. */
export function nModelos(n: number): string {
  n = Number(n) || 0;
  return n + (n === 1 ? ' modelo' : ' modelos');
}

/** O recado que a configuração mostra depois de salvar (``fc-aviso``). */
export function avisoDoModeloSalvo(nome: string): string {
  return 'Modelo "' + nome + '" salvo. As mudanças valem ' +
    'para as próximas passagens; as já encerradas não mudam.';
}
