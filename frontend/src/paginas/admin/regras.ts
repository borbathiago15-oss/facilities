// As contas da tela "Armazenamento de fotos" (sem React, para testar sozinhas).
import type { PainelDoArmazenamento } from './tipos';

/** 0 → "0 KB"; 1536 → "1,5 KB"; 3_500_000 → "3,3 MB"; em pt-BR. */
export function tamanho(bytes: number): string {
  const unidades = ['KB', 'MB', 'GB', 'TB'];
  let v = bytes / 1024;
  let i = 0;
  while (v >= 1024 && i < unidades.length - 1) {
    v /= 1024;
    i += 1;
  }
  const casas = v >= 100 || v === 0 ? 0 : 1;
  return `${v.toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas })} ${unidades[i]}`;
}

export function fotos(n: number): string {
  return `${n.toLocaleString('pt-BR')} ${n === 1 ? 'foto' : 'fotos'}`;
}

/** Quantas fotos passaram do prazo, e quanto pesam (as sem tamanho
 * registrado entram como "pelo menos"). */
export function resumoDoPrazo(p: PainelDoArmazenamento['pendentes']): string {
  if (!p.fotos) return 'Nenhuma foto passou do prazo.';
  const peso = p.sem_tamanho ? `pelo menos ${tamanho(p.bytes)}` : tamanho(p.bytes);
  return `${fotos(p.fotos)} (${peso})`;
}

/** Largura da barra de cada mês, em % do maior mês (o maior = 100). */
export function barras(meses: { bytes: number }[]): number[] {
  const maior = Math.max(0, ...meses.map((m) => m.bytes));
  return meses.map((m) => (maior ? Math.round((m.bytes / maior) * 100) : 0));
}

/** O que impede começar agora, ou null se pode. */
export function porQueNaoComeca(d: PainelDoArmazenamento): string | null {
  if (!d.destino.disponivel) return 'O destino do arquivo não está configurado neste servidor.';
  if (d.em_andamento) return 'Já há um arquivamento em andamento.';
  if (!d.pendentes.fotos) return `Nenhuma foto com mais de ${d.dias} dias.`;
  return null;
}

/** "120 de 300 fotos (40%)". */
export function progresso(arquivadas: number, previstas: number): string {
  const pct = previstas ? Math.min(100, Math.round((arquivadas / previstas) * 100)) : 100;
  return `${arquivadas.toLocaleString('pt-BR')} de ${fotos(previstas)} (${pct}%)`;
}

export function diasValidos(texto: string, min: number, max: number): number | null {
  if (!/^\d+$/.test(texto.trim())) return null;
  const n = Number(texto.trim());
  return n >= min && n <= max ? n : null;
}
