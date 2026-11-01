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
