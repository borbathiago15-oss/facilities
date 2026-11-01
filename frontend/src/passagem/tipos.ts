// O que /api/v1/passagem/... devolve: o mesmo contexto das telas antigas
// (facilities/passagem/rotas.py: contexto_turno e contexto_ver_turno) em JSON.

export type TipoDePergunta = 'sim_nao' | 'numero' | 'texto' | 'texto_longo' | 'escolha';

export type Pergunta = {
  nome: string;
  codigo: string;
  tipo?: TipoDePergunta | string;
  obrigatorio?: boolean;
  opcoes?: string[];
  ordem?: number;
};

export type Modelo = {
  id: number;
  client_id: number;
  nome: string;
  area_id: number | null;
  descricao: string;
  turnos: ({ nome?: string } | string)[];
  campos: { nome: string; codigo?: string; tipo?: string; obrigatorio?: boolean }[];
  atividades: ({ nome?: string; codigo?: string; obrigatorio?: boolean } | string)[];
  perguntas: Pergunta[];
  tipos_ocorrencia: ({ nome?: string } | string)[];
  ativo: boolean;
};

export type Anexo = { id: number; nome: string; mime: string; url: string; anexado_por: string | null };

export type Ocorrencia = { tipo: string; referencia: string; gravidade: string; descricao: string };

export type Anterior =
  | { chave: string; turno: null }
  | {
      chave: string;
      turno: { turno: string; data: string; observacao: string };
      area: string;
      autor: string;
      tem_o_que_ler: boolean;
      ocorrencias: Ocorrencia[];
      anexos: Anexo[];
    };

export type Pendencia = {
  id: number;
  titulo: string;
  referencia: string;
  descricao: string;
  origem_turno: string;
  origem_data: string | null;
  horas: number;
  dias: number;
  vencida: boolean;
  alta: boolean;
  passagens: number;
  ultima_tentativa: { texto: string; quem: string; quando: string } | null;
};

/** ``{'<modelo>': {'<AAAA-MM-DD>': ['1º Turno', ...]}}`` — o que já fechou. */
export type Encerrados = Record<string, Record<string, string[]>>;

export type DadosDaPassagem = {
  usuario: { nome: string; perfil: string };
  clients: { id: number; nome: string }[];
  client_id: number | null;
  centro_custo: string;
  configs: Modelo[];
  areas: { id: number | string; nome: string }[];
  hoje: string;
  encerrados: Encerrados;
  anterior_inicial: string;
  anteriores: Anterior[];
  pendencias: Pendencia[];
  links: { painel: string; trocar_contrato: string; ver_turno: string };
};

export type TarefaDaGestao = {
  id: number;
  titulo: string;
  descricao?: string;
  forma_resposta: string;
  status: string;
  resposta?: string;
};

export type Linha = {
  codigo: string; nome: string; feito: boolean; observacao: string; opcional: boolean; anexos: Anexo[];
};

export type DadosDaLeitura = {
  turno: {
    id: number; client_id: number; turno: string; data: string; data_longa: string; data_iso: string;
    status: string; observacao: string; encerrado_em: string | null;
  };
  cliente: string | null;
  configuracao: string | null;
  autor: string | null;
  no_aparelho: { prep: string; aparelho: string; chegada: string } | null;
  congelada: boolean;
  pode_corrigir: boolean;
  correcoes: { quem: string; quando: string; campos: string; motivo: string }[];
  campos: { nome: string; valor: string; anexos: Anexo[] }[];
  linhas: Linha[];
  anexos_gerais: Anexo[];
  pendencias: {
    titulo: string; referencia: string; status: string; descricao: string;
    trilha: { tipo: string; quem: string; turno: string; data: string | null; quando: string; texto: string }[];
  }[];
  ocorrencias: Ocorrencia[];
  links: { painel: string; corrigir: string };
};

// ── Fase 2b: o painel, o relatório mensal e a configuração ─────────────
// (contexto_painel, contexto_relatorio_mensal e contexto_configuracao)

export type Faixa = 'ok' | 'alerta' | 'critico' | 'neutro' | string;

export type LinhaDoPareto = { tipo: string; qtd: number; pct: number; acumulado: number; vital: boolean };
export type LinhaDoComparativo = {
  turno: string; turnos: number; pct: number | null; cumpridas: number; exigidas: number;
  ocorrencias: number; faixa: Faixa;
};
export type Burndown = { labels: string[]; criadas: number[]; resolvidas: number[] };
export type Rotina = { codigo: string; nome: string; exigida: number; cumprida: number; pct: number | null; faixa: Faixa };

export type DadosDoPainel = {
  clients: { id: number; nome: string }[];
  client_id: number | null;
  periodo: string;
  turno_sel: string;
  periodos: [string, string][];
  area_sel: number;
  todas_as_areas: number;
  de: string;
  ate: string;
  hoje: string;
  dados: null | {
    periodo_label: string; inicio: string; fim: string; turno: string; n_turnos: number;
    turnos_disponiveis: string[];
    areas_disponiveis: { id: number; nome: string }[];
    aderencia: { pct: number | null; cumpridas: number; exigidas: number; faixa: Faixa; meta: number };
    resolucao: { pct: number | null; abertas: number; resolvidas: number; faixa: Faixa };
    n_criticas: number;
    indice_ocorrencias: { valor: number | null; delta: number | null; turnos: number; ocorrencias: number };
    pareto: LinhaDoPareto[];
    turnos_comparativo: LinhaDoComparativo[];
    burndown: Burndown;
    rotinas: Rotina[];
    ocorrencias: {
      id: number; tipo: string; referencia: string; descricao: string; gravidade: string;
      quando: { dia: string | null; turno: string | null };
      chamado: { id: number; numero: string; status_rotulo: string; url: string } | null;
    }[];
    criticas: {
      id: number; titulo: string; descricao: string; prioridade: string;
      alta: boolean; vencida: boolean; horas: number; dias: number;
    }[];
  };
  turnos: { id: number; data: string; area: string; turno: string; status: string }[];
  modelos: { id: number; nome: string; turnos: ({ nome?: string; codigo?: string } | string)[] }[];
  pode_gravar: boolean;
  pode_chamado: boolean;
  pode_ver_chamado: boolean;
  e_gestao: boolean;
  pode_configurar: boolean;
  nome_do_sistema: string;
  links: { nova_passagem: string; relatorio: string | null; configurar: string; ver_turno: string };
};

export type OcorrenciaDoMes = {
  data: string | null; dia: string | null; turno: string; tipo: string; referencia: string;
  descricao: string; gravidade: string;
};

export type DadosDoRelatorio = {
  cliente: { id: number; nome: string };
  meses: [number, string][];
  anos: number[];
  mes: number;
  ano: number;
  areas: { id: number; nome: string }[];
  area_sel: number;
  todas_as_areas: number;
  nome_do_sistema: string;
  rel: {
    area: string; competencia: string; emitido_em: string; emitido_por: string;
    inicio: string; fim_apurado: string | null; em_andamento: boolean;
    turnos: { total: number; por_turno: [string, number][] };
    aderencia: { pct: number | null; cumpridas: number; exigidas: number; faixa: Faixa; meta: number };
    pendencias: {
      abertas: number; resolvidas: number; pct: number | null; faixa: Faixa;
      lista_resolvidas: {
        titulo: string; referencia: string; prioridade: string; resolucao: string; turno: string;
        passagens: number; encerrada: string; resolvida_por: string;
      }[];
      lista_em_aberto: {
        titulo: string; referencia: string; prioridade: string; descricao: string; anterior: boolean;
        ultima_tentativa: string; turno: string; passagens: number; dias: number;
      }[];
    };
    ocorrencias: {
      total: number; mais_frequente: { tipo: string; qtd: number } | null;
      lista: OcorrenciaDoMes[]; atencao: OcorrenciaDoMes[];
    };
    rotinas: Rotina[];
    bordo: { data: string; turno: string; texto: string }[];
  };
  links: { painel: string; pdf: string };
};

export type AreaDoContrato = { id: number; nome: string; ativo: boolean; modelos: number };

export type DadosDaConfiguracao = {
  clients: { id: number; nome: string }[];
  client_id: number | null;
  configs: Modelo[];
  areas: AreaDoContrato[];
  usos: Record<string, number>;
  editar: number | null;
  modelos_prontos: { chave: string; area: string; turnos: string[] }[];
  recados: { tipo: string; texto: string }[];
  links: { painel: string; aqui: string; modelos_prontos: string };
};
