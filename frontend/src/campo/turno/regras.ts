// As regras da tela "Meu turno", sem tela: a situação de cada tarefa AGORA,
// a próxima da rota, o que falta no checklist. As mesmas da tela antiga
// (static/js/rotas-turno.js); ``agora`` e as marcas do aparelho entram por
// parâmetro, para os testes.
import type { DadosDoTurno, ItemDoChecklist, LocalDaCarteira, Chegada, Tarefa, Troca, Versao } from './tipos';

export type Situacao = { cod: string; rotulo: string };
/** As tarefas que este aparelho já guardou/enviou: id → rótulo. */
export type Feitas = Record<string, string>;

// ── As chaves do aparelho: as MESMAS da tela antiga, para as duas telas
// conviverem no mesmo celular. ───────────────────────────────────────────
export const chaveFeitas = (usuario: number) => `trino-turno-feitas-${usuario}`;
export const chaveChegada = (usuario: number) => `trino-turno-chegada-${usuario}`;
export const chaveTroca = (usuario: number) => `trino-turno-troca-${usuario}`;
// O motivo escolhido antes de ir ler o QR da outra área vale por 30 min.
export const VALIDADE_TROCA_MS = 30 * 60000;

export function lerJson<T = Record<string, unknown>>(chave: string): T {
  try { return JSON.parse(localStorage.getItem(chave) || '{}'); } catch { return {} as T; }
}
export function gravarJson(chave: string, v: unknown) {
  try { localStorage.setItem(chave, JSON.stringify(v)); } catch { /* aparelho sem espaço */ }
}
export function feitasNoAparelho(usuario: number): Feitas { return lerJson<Feitas>(chaveFeitas(usuario)); }
export function marcarFeita(usuario: number, id: number, rotulo: string) {
  const f = feitasNoAparelho(usuario);
  f[id] = rotulo;
  gravarJson(chaveFeitas(usuario), f);
}
export function desmarcarFeita(usuario: number, id: number) {
  const f = feitasNoAparelho(usuario);
  if (!(id in f)) return;
  delete f[id];
  gravarJson(chaveFeitas(usuario), f);
}
/** O servidor é a verdade: tarefa que ele já registrou perde a marca local
 * ("guardada" ou "enviada"). */
export function apagarMarcasVencidas(dados: DadosDoTurno) {
  dados.tarefas.forEach((t) => { if (t.status !== 'prevista') desmarcarFeita(dados.usuario, t.id); });
}

export function lerTroca(usuario: number, agora = Date.now()): Troca | null {
  try {
    const t = JSON.parse(sessionStorage.getItem(chaveTroca(usuario)) || 'null');
    return t && agora - t.em < VALIDADE_TROCA_MS ? t : null;
  } catch { return null; }
}
export function guardarTroca(usuario: number, t: Troca) {
  try { sessionStorage.setItem(chaveTroca(usuario), JSON.stringify(t)); } catch { /* sem espaço */ }
}
export function limparTroca(usuario: number) {
  try { sessionStorage.removeItem(chaveTroca(usuario)); } catch { /* nada a fazer */ }
}

// ── Horas ───────────────────────────────────────────────────────────────
export function hora(iso?: string | null) {
  const d = iso ? new Date(iso) : new Date();
  return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
}
export function hojeLocal(d = new Date()) {
  return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2);
}
/** A partir de quando a tarefa pode ser feita (o previsto menos a tolerância). */
export function desdeQuando(t: Tarefa) {
  return hora(new Date(Date.parse(t.previsto) - t.tolerancia * 60000).toISOString());
}

// ── Locais e chegada ────────────────────────────────────────────────────
export function localDe(dados: DadosDoTurno, id: number | string | null | undefined) {
  return (dados.locais || []).filter((l) => String(l.id) === String(id))[0] || null;
}
/** A chegada de hoje no local: a do servidor ou a guardada no aparelho (sem
 * sinal) no mesmo dia. */
export function chegadaDe(usuario: number, local: LocalDaCarteira | null): Chegada | null {
  if (!local) return null;
  if (local.chegada) return local.chegada;
  const m = lerJson<Record<string, Chegada>>(chaveChegada(usuario))[local.id];
  return m && m.data === hojeLocal() ? m : null;
}
export function marcarChegadaLocal(usuario: number, localId: number, h: string) {
  const c = lerJson<Record<string, Chegada>>(chaveChegada(usuario));
  c[localId] = { hora: h, data: hojeLocal(), guardada: true };
  gravarJson(chaveChegada(usuario), c);
}
export function exigeChegada(usuario: number, local: LocalDaCarteira | null) {
  return !!(local && local.entrada && !chegadaDe(usuario, local));
}

// ── A situação de cada tarefa AGORA (a do servidor envelhece com a tela aberta)
export function situacao(t: Tarefa, situacoes: Record<string, string>, feitas: Feitas,
                         agora = Date.now()): Situacao {
  if (t.status !== 'prevista') return { cod: t.status, rotulo: situacoes[t.status] };
  const guardada = feitas[t.id];
  if (guardada) return { cod: 'guardada', rotulo: guardada };
  const prev = Date.parse(t.previsto);
  const tol = t.tolerancia * 60000;
  if (agora < prev - tol) return { cod: 'prevista', rotulo: 'Prevista' };
  if (agora <= prev + tol) return { cod: 'no_horario', rotulo: 'No horário' };
  if (agora > Date.parse(t.fim_turno)) return { cod: 'perdida', rotulo: 'Turno encerrado' };
  return { cod: 'atrasada', rotulo: 'Atrasada' };
}

/** As regras que dependem dos dados da tela, do aparelho e da hora. */
export function regrasDoTurno(dados: DadosDoTurno, agora = () => Date.now()) {
  const feitas = () => feitasNoAparelho(dados.usuario);
  const sit = (t: Tarefa) => situacao(t, dados.situacoes, feitas(), agora());
  const podeFazer = (t: Tarefa) => { const s = sit(t).cod; return s === 'no_horario' || s === 'atrasada'; };
  const emAberto = (t: Tarefa) => {
    const s = sit(t).cod;
    return s === 'prevista' || s === 'no_horario' || s === 'atrasada';
  };
  const porHora = (a: Tarefa, b: Tarefa) => Date.parse(a.previsto) - Date.parse(b.previsto);
  const tarefasDoLocal = (localId: number | string) =>
    dados.tarefas.filter((t) => String(t.local_id) === String(localId)).sort(porHora);
  return {
    situacao: sit,
    podeFazer,
    emAberto,
    tarefasDoLocal,
    /** Só as minhas tarefas (27/10/2026); as dos colegas, num toque. Sem
     * nenhuma minha no local (o supervisor), todas. */
    tarefasVisiveis(localId: number | string, verColegas: boolean) {
      const doLocal = tarefasDoLocal(localId);
      const minhas = doLocal.filter((t) => t.minha);
      return { lista: minhas.length && !verColegas ? minhas : doLocal, minhas: minhas.length,
               todas: doLocal.length };
    },
    /** A próxima da rota depois de ``feita``: a atrasada ou a da hora
     * primeiro, senão a primeira que ainda vai chegar. */
    proximaTarefa(localId: number | string, feita: Tarefa | null): Tarefa | null {
      const abertas = tarefasDoLocal(localId).filter((t) => emAberto(t) && (!feita || t.id !== feita.id));
      return abertas.filter(podeFazer)[0] || abertas[0] || null;
    },
    /** A tarefa da hora neste ponto, se é desta pessoa (ou sem dono): abre
     * direto no checklist. A de outra pessoa fica na tela do ponto. */
    tarefaDaHora(codigo: string): Tarefa | undefined {
      return dados.tarefas.filter((t) => t.ponto === codigo && podeFazer(t) && (t.minha || !t.escalado))
        .sort(porHora)[0];
    },
    /** A próxima tarefa ainda fora da janela do horário neste ponto (desta
     * pessoa ou sem dono): a que "adiantar" conclui. */
    tarefaParaAdiantar(codigo: string): Tarefa | null {
      return dados.tarefas.filter((t) => t.ponto === codigo && sit(t).cod === 'prevista' && !feitas()[t.id] &&
        (t.minha || !t.escalado)).sort(porHora)[0] || null;
    },
  };
}
export type RegrasDoTurno = ReturnType<typeof regrasDoTurno>;

/** Os checklists (versões) de uma lista de ids, sem os que não vieram. */
export function versoesDe(dados: DadosDoTurno, ids: number[] | undefined): Versao[] {
  return (ids || []).map((vid) => dados.versoes[vid]).filter(Boolean);
}

// ── O checklist ─────────────────────────────────────────────────────────
/** A resposta "boa" de um item de marcar (o check verde). */
export function respostaFeito(it: ItemDoChecklist) {
  if (it.tipo === 'conforme') return 'conforme';
  return it.problema_se === 'sim' ? 'nao' : 'sim';
}
export function ehDeMarcar(it: ItemDoChecklist) { return it.tipo === 'sim_nao' || it.tipo === 'conforme'; }

export type EstadoDoChecklist = {
  respostas: Record<string, string>;
  fotos: Record<string, File | null>;
};

/** O item aparece? (a condição "mostrar se" de outro item) */
export function visivel(it: ItemDoChecklist, respostas: Record<string, string>) {
  const se = it.mostrar_se;
  if (!se) return true;
  return String(respostas[se.codigo] || '').toLowerCase() === String(se.valor || '').toLowerCase();
}

/** O que ainda falta para o "Pronto", na ordem da tela. */
export function faltantes(versao: Versao, e: EstadoDoChecklist) {
  const lista: string[] = [];
  if (versao.foto_antes && !e.fotos.antes) lista.push('a foto do antes');
  let n = 0;
  versao.itens.forEach((it) => {
    if (!visivel(it, e.respostas)) return;
    const r = String(e.respostas[it.codigo] || '').trim();
    if (!r) { n += 1; return; }
    if (it.exige_foto && r !== 'nao_feito' && !e.fotos['item:' + it.codigo]) n += 1;
  });
  if (n) lista.push(n + (n > 1 ? ' itens' : ' item'));
  if (versao.foto_depois && !e.fotos.depois) lista.push('a foto do depois');
  return lista;
}

/** "Faltam a foto do antes, 2 itens e a foto do depois" / "Tudo respondido." */
export function fraseDoQueFalta(f: string[]) {
  if (!f.length) return 'Tudo respondido.';
  const frase = f.length > 1 ? f.slice(0, -1).join(', ') + ' e ' + f[f.length - 1] : f[0];
  return 'Falta' + (f.length > 1 || /itens/.test(f[0]) ? 'm ' : ' ') + frase;
}
