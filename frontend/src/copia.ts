// Sem sinal, as telas do campo abrem da cópia guardada no aparelho (o
// service worker, static/pwa/sw.js, Fase 1c). A resposta que veio da cópia
// traz o cabeçalho ``x-guardada-em`` (quando foi guardada); a que veio da
// rede, não. Aqui fica, por endereço, o que a tela está mostrando da cópia —
// para o aviso "é a cópia das HH:MM".
import { useSyncExternalStore } from 'react';

const CABECALHO = 'x-guardada-em';

const daCopia = new Map<string, number>();
const ouvintes = new Set<() => void>();
let instantaneo: number | null = null;

/** A cópia mais antiga em uso (a tela vale o que a parte mais velha vale). */
export function maisAntiga(horas: Iterable<number>): number | null {
  let menor: number | null = null;
  for (const h of horas) if (menor === null || h < menor) menor = h;
  return menor;
}

/** ``HH:MM`` no horário de Brasília (o que o sistema exibe em toda tela). */
export function horaDaCopia(ms: number): string {
  return new Intl.DateTimeFormat('pt-BR', {
    hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'America/Sao_Paulo',
  }).format(new Date(ms));
}

/** Quando a resposta foi guardada (ms), ou ``null`` se veio da rede. */
export function guardadaEm(resp: Response): number | null {
  const valor = Number(resp.headers.get(CABECALHO) || 0);
  return valor > 0 ? valor : null;
}

/** Anota de onde veio a resposta de ``caminho``: a da rede apaga a anotação. */
export function anotar(caminho: string, resp: Response) {
  const quando = guardadaEm(resp);
  if (quando === null && !daCopia.has(caminho)) return;
  if (quando === null) daCopia.delete(caminho);
  else daCopia.set(caminho, quando);
  instantaneo = maisAntiga(daCopia.values());
  ouvintes.forEach((f) => f());
}

function assinar(f: () => void) {
  ouvintes.add(f);
  return () => { ouvintes.delete(f); };
}

/** A hora (ms) da cópia que a tela mostra, ou ``null`` se tudo veio da rede. */
export function useCopiaEmUso(): number | null {
  return useSyncExternalStore(assinar, () => instantaneo, () => null);
}

/** Só para os testes. */
export function esquecerCopias() {
  daCopia.clear();
  instantaneo = null;
}
