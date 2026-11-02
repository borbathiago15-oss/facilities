// Os dados que as telas dos chamados, das demandas e da preventiva recebem
// (facilities/telas/chamados.py): os mesmos das telas antigas, com as horas,
// as datas e os números já escritos como elas escrevem.

export type Pares = [string, string][];

/** O selo do prazo (templates/chamados/_selo.html). */
export type SeloDoPrazo = { tipo: 'ok' | 'atrasado' | 'vence' | 'parado'; perto: boolean; texto: string } | null;

export type ResumoDoChamado = {
  id: number; numero: string; titulo: string;
  prioridade: string; prioridade_rotulo: string; status: string; status_rotulo: string;
  prazo_selo: SeloDoPrazo; atrasado: boolean;
  contrato: string; area: string | null; local: string; categoria_rotulo: string;
  responsavel: string | null;
};

export type Numeros = {
  em_aberto: number; atrasados: number; aguardando_confirmacao: number; dias: number;
  pct_no_prazo: string; tempo_medio: string;
};

export type DadosDaLista = {
  chamados: ResumoDoChamado[]; cortada: boolean; por_pagina: number;
  contratos: { id: number; nome: string }[]; client_id: number | null;
  visao: string; visoes: Pares; prioridade: string; categoria: string;
  prioridades: Pares; categorias: Pares; numeros: Numeros; pode_abrir: boolean;
};

export type DadosDoNovo = {
  contratos: { id: number; nome: string }[];
  areas: Record<string, { id: number; nome: string }[]>;
  client_id: number | null; prioridades: Pares; categorias: Pares;
};

export type DadosDoChamado = {
  chamado: ResumoDoChamado & {
    client_id: number; solicitante: string; aberto_em: string; responsavel_id: number | null;
    prazo: string; origem: string; visita: string | null; pausa: string | null;
    descricao: string; motivo_espera: string; solucao: string;
  };
  acoes: string[];
  tecnicos: { id: number; nome: string; perfil: string }[];
  prioridades: Pares;
  eventos: { tipo: string; autor: string; rotulo: string; quando: string; texto: string }[];
  anexos: { id: number; nome: string; momento: string; imagem: boolean; url: string }[];
  pode_anexar: boolean;
  consumos: { quantidade: string; unidade: string; material: string; pessoa: string; quando: string; valor: string | null }[];
  ve_custo: boolean;
  materiais: { id: number; nome: string; unidade: string }[];
};

export type ItemDaDemanda = {
  tipo: string; tipo_rotulo: string; situacao: string; situacao_rotulo: string;
  numero: string; titulo: string; local: string; estado: string; responsavel: string;
  prazo: string | null; link: string;
};

export type DadosDasDemandas = {
  itens: ItemDaDemanda[]; locais: { id: number; nome: string }[];
  local: number | null; tipo: string; situacao: string;
  tipos: Pares; situacoes: Pares; contagem: Record<string, number>;
  links: { cobrancas: string };
};

export type PlanoPreventivo = {
  id: number; nome: string; ativo: boolean; ponto_id: number; ponto: string;
  equipamento_id: number | null; equipamento: string | null; modelo_id: number; modelo: string;
  intervalo_dias: number; antecedencia_dias: number; proxima_em: string; proxima_em_iso: string;
  prioridade: string; prioridade_rotulo: string; responsavel_id: number | null; responsavel: string | null;
  ciclos: { vencimento: string; chamado: { url: string; numero: string; status_rotulo: string } | null }[];
};

export type DadosDaPreventiva = {
  local: { id: number; nome: string };
  planos: PlanoPreventivo[];
  // Com o item desativado que um plano ainda usa (só no "Editar" dele).
  modelos: { id: number; nome: string; ativo: boolean }[];
  pontos: { id: number; rotulo: string; ativo: boolean }[];
  equipamentos: { id: number; nome: string; ativo: boolean }[];
  tecnicos: { id: number; nome: string }[];
  prioridades: Pares; hoje: string; pode_montar: boolean;
  links: { pontos: string; checklists: string };
};
