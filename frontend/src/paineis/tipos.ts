// Os dados do painel (Fase 4c), como a API /api/v1/painel entrega: as notas
// e as porcentagens já escritas como a tela antiga escreve (``85,3``).

export type LinhaDoPainel = {
  local_id: number; local: string; nota: string | null; faixa: string | null;
  indicadores: ({ pct: string; base: string } | null)[];
  elogios: { media: string; total: number } | null;
  atrasadas: number; atrasadas_url: string;
};

export type DadosDoPainel = {
  de: string; ate: string; de_br: string; ate_br: string;
  faixa_critica: number; faixa_boa: number;
  indicadores: string[];
  resumo: { media: string; faixas: [string, number][]; sem_dado: number };
  linhas: LinhaDoPainel[];
  grupos: { cliente: string; media: string; linhas: LinhaDoPainel[] }[] | null;
};
