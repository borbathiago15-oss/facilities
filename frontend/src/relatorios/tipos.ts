// Os dados das telas dos relatórios do cliente (Fase 4c), como a API
// /api/v1/relatorios/... entrega: os números já escritos como a tela antiga
// escreve (``85,3``, ``85,3%``, ``24,0 h``, "—").

export type LocalDoMes = {
  id: number; nome: string; cliente: string; liberado: boolean; liberado_em: string | null; url: string;
};

export type DadosDoInicio = {
  mes: string; nome_do_mes: string; locais: LocalDoMes[];
  links: { anterior: string; seguinte: string };
};

export type Foto = { ref: string; legenda: string; url: string };

export type CorpoDoRelatorio = {
  nota: { texto: string; faixa: string } | null;
  variacao: string;
  indicadores: { chave: string; rotulo: string; pct: string; base: string }[];
  rotinas: { ambiente: string; previstas: number; no_prazo: number; com_atraso: number; nao_feitas: number; pct: string }[];
  chamados: {
    abertos: number; resolvidos: number; pct_no_prazo: string; tempo_medio: string; pendentes_no_fim: number;
    lista: { numero: string; titulo: string; categoria: string; aberto_em: string; resolvido_em: string; situacao: string }[];
    lista_cortada: boolean;
  };
  ncs: { total: number; corrigidas: number; itens: [string, number][] };
  ocorrencias: { total: number; resolvidas: number; pct_no_prazo: string; tempo_medio: string };
  visitas: { programadas: number; feitas: number; conformes: number };
  cobrancas: { abertas: number; respondidas: number; no_prazo: number; encerradas: number };
  elogios: {
    total: number; media: string;
    comentarios: { texto: string; nota: number; estrelas: string; onde: string; quando: string }[];
  } | null;
  fotos: Foto[];
};

export type DadosDoRelatorio = {
  local: { id: number; nome: string }; cliente: string | null; mes: string; nome_do_mes: string;
  liberado_em: string | null; recado: string; pode_gerir: boolean; mes_fechado: boolean;
  mudou: [string, string, string][];
  corpo: CorpoDoRelatorio;
  escolha: { todas: (Foto & { escolhida: boolean })[]; automatica: boolean; fotos_max: number } | null;
  links: { inicio: string; pdf: string; xlsx: string };
};
