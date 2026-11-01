// As regras de tela dos Cadastros que não dependem do servidor: os passos do
// assistente, o "Continuar" de cada local, o rótulo da situação do convite e
// os campos que cada função mostra (static/js/novo-contrato.js).
import type { Andamento, Passos } from './tipos';

export type Etapa = { n: number; rotulo: string; url: string | null; classe: string; atual: boolean };

/** Os quatro passos do assistente (``_passos.html``): passo com endereço vira
 * link (dá para voltar a qualquer um); o atual fica marcado. */
export function etapas(p: Passos): Etapa[] {
  const loc = p.local;
  const cli = p.cliente;
  const lista: [number, string, string | null][] = [
    [1, 'Cliente', '/novo/novo-contrato'],
    [2, 'Local', cli && !loc ? `/novo/novo-contrato/cliente/${cli.id}/local` : null],
    [3, 'Estrutura e QR', loc ? `/novo/novo-contrato/${loc.id}/estrutura` : null],
    [4, 'Equipe', loc ? `/novo/novo-contrato/${loc.id}/equipe` : null],
  ];
  return lista.map(([n, rotulo, url]) => ({
    n, rotulo, url: url && n !== p.atual ? url : null,
    classe: n === p.atual ? 'atual' : (n < p.atual ? 'feito' : ''),
    atual: n === p.atual,
  }));
}

/** O que falta no local, na lista do passo 1 (``cliente.html``). */
export function continuar(localId: number, a: Andamento): { rotulo: string; url: string } {
  if (!a.pontos) return { rotulo: 'Continuar: estrutura e QR', url: `/novo/novo-contrato/${localId}/estrutura` };
  if (!a.equipe && !a.convites) return { rotulo: 'Continuar: equipe', url: `/novo/novo-contrato/${localId}/equipe` };
  return { rotulo: 'Abrir', url: `/novo/novo-contrato/${localId}/estrutura` };
}

const SITUACOES: Record<string, string> = {
  aceito: 'aceito', pendente: 'aguardando', vencido: 'vencido', cancelado: 'cancelado',
};

/** O rótulo e a cor da situação do convite. */
export function situacao(sit: string): { rotulo: string; classe: string } {
  const classe = sit === 'aceito' ? 'text-bg-success' : (sit === 'pendente' ? 'text-bg-warning' : 'text-bg-secondary');
  return { rotulo: SITUACOES[sit] ?? sit, classe };
}

/** Cada função mostra só os campos dela: o cliente escolhe o cliente (não tem
 * superior nem locais); a equipe escolhe a quem responde e os locais; a
 * diretoria vê tudo e não escolhe nada. */
export function camposDaFuncao(papel: string): { cliente: boolean; equipe: boolean } {
  return { cliente: papel === 'cliente', equipe: papel !== 'cliente' && papel !== 'visualizador' };
}

/** A frase quando o celular não dá a posição (``posicao-local.js``). */
export function erroDoGps(codigo: number | undefined): string {
  return codigo === 1
    ? 'O celular não deixou usar a localização. Libere a localização para este site e tente de novo.'
    : 'Não foi possível pegar a posição. Vá para perto de uma janela ou área aberta e tente de novo.';
}

/** O texto de uma mudança na trilha (``trilha.html``): com "antes", a seta. */
export function mudanca(comAntes: boolean, antes: string, depois: string): string {
  return comAntes ? `${antes} → ${depois}` : depois;
}
