// Os dados das telas das cobranças do cliente vistas pela equipe (Fase 5),
// como a API /api/v1/cobrancas/... entrega (as datas já escritas como a
// tela antiga escreve).
import type { Abas, DadosDosAvisos, Evento, Filtro, Selo } from '../portal/tipos';

export type DadosDaLista = {
  aba: 'cobrancas'; status: string; filtros: Filtro[];
  itens: { id: number; numero: string; titulo: string; local: string; autor: string; prazo: string; situacao: Selo; url: string }[];
  abas: Abas;
};

export type DadosDaListaOuAvisos = DadosDaLista | DadosDosAvisos;

export type DadosDaCobranca = {
  id: number; numero: string; titulo: string; local: string; autor: string; situacao: string; prazo: string;
  reaberturas: number; status: string; pode_responder: boolean; eventos: Evento[];
  links: { lista: string };
};
