// Os dados das telas do portal do cliente (Fase 5), como a API
// /api/v1/cliente/... entrega: as datas, as horas e as notas já escritas
// como a tela antiga escreve, e só o que a antiga mostra ao cliente.
import type { CorpoDoRelatorio } from '../relatorios/tipos';

export type Selo = { classe: string; texto: string };
export type Nota = { texto: string; faixa: string } | null;
export type Abas = { cobrancas: string; qr: string };
/** [rótulo, endereço, ativo] — os botões de filtro das telas antigas. */
export type Filtro = [string, string, boolean];

export type CobrancaNaLista = {
  id: number; numero: string; titulo: string; local: string; prazo: string; situacao: Selo; url: string;
};

export type DadosDoInicio = {
  de: string; ate: string; de_br: string; ate_br: string;
  cobrancas: CobrancaNaLista[];
  linhas: { id: number; nome: string; nota: Nota; abertos: number; url: string }[];
  links: { cobrancas: string };
};

export type Foto = { id: number; url: string; alt: string };

export type DadosDoLocal = {
  local: { id: number; nome: string }; de: string; ate: string; nota: Nota;
  indicadores: { chave: string; rotulo: string; pct: string; base: string }[];
  chamados: { id: number; numero: string; titulo: string; situacao: string; atrasado: boolean; fotos: number; quando: string; url: string }[];
  execucoes: { id: number; onde: string; detalhe: string; nao_conformes: number; fotos: Foto[] }[];
  visitas: { id: number; nome: string; detalhe: string; nao_conformes: number; fotos: Foto[] }[];
  documentos: { id: number; modelo: string; nome: string; url: string }[];
  links: { inicio: string; cobrar: string };
};

export type DadosDoChamado = {
  id: number; numero: string; titulo: string; situacao: string; categoria: string; onde: string | null;
  aberto_em: string; prazo: string; aguardando: boolean; resolvido_em: string | null; solucao: string | null;
  fotos: (Foto & { legenda: string })[];
  local: { id: number; nome: string };
  links: { inicio: string; local: string; cobrar: string };
};

export type DadosDosRelatorios = {
  relatorios: { id: number; mes: string; local: string; url: string; pdf: string }[];
};

export type DadosDoRelatorio = {
  local: { id: number; nome: string }; mes: string; nome_do_mes: string; recado: string;
  corpo: CorpoDoRelatorio;
  links: { inicio: string; pdf: string; xlsx: string };
};

export type AvisoPeloQr = {
  id: number; status: string; situacao: string; titulo: string; onde: string; texto: string | null; quando: string;
  // Do cliente:
  resolvido?: string | null; resolucao?: string | null;
  // Da equipe:
  atrasada?: boolean; responsavel?: string | null; url?: string;
};

export type DadosDosAvisos = {
  aba: 'qr'; situacao: string; filtros: Filtro[]; avisos: AvisoPeloQr[]; abas: Abas;
};

export type DadosDasCobrancas = {
  aba: 'cobrancas';
  locais: { id: number; nome: string }[];
  cobrancas: CobrancaNaLista[];
  minimo: string; minimo_br: string; local_escolhido: number | null; abrir_aberto: boolean;
  abas: Abas;
};

export type Evento = { id: number; quando: string; autor: string; tipo: string; prazo: string | null; texto: string | null };

export type DadosDaCobranca = {
  id: number; numero: string; titulo: string; local: string; situacao: Selo; prazo: string;
  respondida: boolean; aberta: boolean; minimo: string; minimo_br: string;
  eventos: Evento[];
  links: { cobrancas: string };
};
