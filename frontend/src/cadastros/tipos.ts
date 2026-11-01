// O que a API das telas dos Cadastros entrega (facilities/telas/cadastros.py).

export type Id = { id: number; nome: string };

// ── Cadastros ────────────────────────────────────────────────────────────

export type DadosDoInicio = {
  locais: { id: number; nome: string; cliente: string | null; estado: string | null }[];
  e_admin: boolean;
  pode_novo_contrato: boolean;
  n_empresas: number;
  n_clientes: number;
  n_estados: number;
  links: { locais_admin: string };
};

export type Empresa = { id: number; nome: string; cnpj: string; ativo: boolean };
export type DadosDasEmpresas = { empresas: Empresa[] };

export type Cliente = {
  id: number; nome: string; centro_custo: string; empresa_id: number; gerente_id: number | null;
  gerente: string | null; ativo: boolean; prazo_pedido_insumo_horas: number | null;
  mostrar_nome_executor: boolean; regua: Record<string, number>; prazos: Record<string, number>;
  locais: { id: number; nome: string; estado: string | null }[];
};
export type DadosDosClientes = {
  clientes: Cliente[];
  empresas: { id: number; nome: string; ativo: boolean }[];
  gerentes: Id[];
  tipos_ocorrencia: [string, string][];
  prioridades: [string, string][];
  regua_padrao: Record<string, number>;
  pode_mostrar_nome: boolean;
};

export type DadosDosEstados = { estados: { id: number; nome: string; sigla: string; ativo: boolean }[] };

export type Ponto = {
  id: number; nome: string; descricao: string; ativo: boolean; equipamento_id: number | null;
  equipamento: string | null;
};
export type Equipamento = {
  id: number; nome: string; patrimonio: string; fabricante: string; modelo: string; ativo: boolean;
};
export type Ambiente = {
  id: number; nome: string; descricao: string; ativo: boolean; pontos: Ponto[]; equipamentos: Equipamento[];
};
export type Setor = { id: number; nome: string; ativo: boolean; ambientes: Ambiente[] };
export type DadosDoLocal = {
  local: { id: number; nome: string; cliente: string | null; estado: string | null; subcentro: string };
  setores: Setor[];
  todos_setores: { id: number; nome: string; ambientes: Id[] }[];
  com_inativos: boolean;
  pode_alterar: boolean;
  links: { etiquetas: string };
};

export type DadosDaTrilha = {
  local: Id | null;
  entidade: string | null;
  entidades: [string, string][];
  eventos: {
    id: number; entidade: string; acao: string; entidade_id: number; quando: string; autor: string;
    com_antes: boolean; mudancas: [string, string, string][];
  }[];
};

// ── Cliente, centro de custo, áreas e rotas ──────────────────────────────

export type DadosDosCentrosClientes = {
  clientes: { id: number; nome: string; centros: { id: number; nome: string; centro_custo: string }[] }[];
  pode_criar: boolean;
};

export type DadosDoCentrosCliente = {
  cliente: Id;
  centros: { id: number; nome: string; centro_custo: string; areas: number; rotas: number }[];
  estados: Id[];
};

export type DadosDoCentro = {
  local: {
    id: number; nome: string; centro_custo: string; cliente: Id | null; marcada: boolean;
    marcada_em: string | null;
  };
  aba: string;
  areas: { id: number; nome: string; numero: number; entrada: boolean; checklist_id: number | null }[];
  checklists: Id[];
  raio: number;
  rotas: { id: number; nome: string; turno: string; inicio: string; fim: string; ativa: boolean; areas: number }[];
  links: { etiquetas: string };
};

export type DadosDaRota = {
  local: Id;
  rota: { id: number; nome: string; turno: string; inicio: string; fim: string; dias: string[] };
  linhas: { hora: string; item_id: number; area: string; checklist: string }[];
  areas: Id[];
  pessoas: Id[];
  escalados: { nome: string; desde: string }[];
  hoje: string;
  vazias: number;
  links: { avancado: string };
};

// ── Novo contrato e convites ─────────────────────────────────────────────

export type Passos = { atual: number; local: Id | null; cliente: Id | null };
export type Andamento = { pontos: number; entrada: boolean; rotas: number; equipe: number; convites: number };

export type DadosDoNovoContrato = {
  clientes: {
    id: number; nome: string; centro_custo: string; logo: string | null;
    locais: { id: number; nome: string; andamento: Andamento }[];
  }[];
  pode_criar: boolean;
  empresas: Id[];
  passos: Passos;
};

export type DadosDoNovoLocal = {
  cliente: { id: number; nome: string; logo: string | null };
  estados: Id[];
  pode_logo: boolean;
  passos: Passos;
};

export type DadosDaEstrutura = {
  local: Id;
  setores: { id: number; nome: string; ambientes: { nome: string; pontos: { numero: number; nome: string; entrada: boolean }[] }[] }[];
  andamento: Andamento;
  passos: Passos;
  links: { importar: string; etiquetas: string; rotas: string };
};

export type DadosDaEquipe = {
  local: { id: number; nome: string; cliente_id: number | null };
  perfis: [string, string][];
  eu: { nome: string; e_admin: boolean };
  superiores: { id: number; nome: string; perfil: string }[];
  locais: Id[];
  clientes: Id[];
  convites: { id: number; nome: string; perfil: string; situacao: string }[];
  equipe: { nome: string; perfil: string }[];
  passos: Passos;
  links: { concluir: string };
};

export type ConviteCriado = {
  convite: { nome: string; email: string };
  perfil: string;
  locais: string[];
  enviado: boolean | null;
  link: string;
  whatsapp: string;
  email: string;
  local: Id | null;
  passos: Passos | null;
};

export type DadosDosConvites = {
  convites: {
    id: number; nome: string; email: string; perfil: string; situacao: string; onde: string;
    criado_por: string; criado_em: string;
  }[];
};
