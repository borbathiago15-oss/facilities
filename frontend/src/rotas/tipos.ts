// Os dados das telas da rotina dos locais (Fase 3b), como a API os entrega
// (facilities/telas/rotas.py). Saem das MESMAS funções das telas antigas
// (rotas.telas.contexto_*).

export type Dias = [string, string][];

export type LinksDoLocal = { preventiva: string; equipe: string; visitas: string; estrutura: string };

export type DadosDoInicio = {
  locais: { id: number; nome: string; cliente: string | null; links: LinksDoLocal }[];
  pode_montar: boolean;
};

export type DadosDoLocal = {
  local: { id: number; nome: string };
  modelos: { id: number; nome: string; versao: number | null; copia: boolean }[];
  biblioteca: { id: number; nome: string }[];
  rotas: { id: number; nome: string; turno: string; inicio: string; fim: string; atividades: number; ativa: boolean }[];
  pode_montar: boolean;
  ve_estrutura: boolean;
  dias: Dias;
  links: LinksDoLocal;
};

export type DadosDaBiblioteca = {
  modelos: { id: number; nome: string; versao: number | null }[];
  rotas_prontas: { id: number; segmento: string; nome: string; ambientes: number; inicio: string; fim: string; ativa: boolean }[];
  pode_montar: boolean;
};

export type RotaModelo = {
  id: number; nome: string; segmento: string; descricao: string; turno: string; inicio: string;
  fim: string; tolerancia_min: number; dias_semana: string; ativa: boolean;
};

export type DadosDaRotaPronta = {
  modelo: RotaModelo | null;
  linhas: { setor: string; ambiente: string; checklist_id: number | null; horarios: string; quantidade: number }[];
  checklists: { id: number; nome: string }[];
  dias: Dias;
  pode_montar: boolean;
};

export type DadosDeAplicar = {
  local: { id: number; nome: string };
  opcoes: { id: number; segmento: string; nome: string }[];
  modelo: RotaModelo | null;
  linhas: { setor: string; ambiente: string; checklist_id: number; checklist: string; horarios: string }[];
  dias: Dias;
};

export type DadosDoPlano = { local: { id: number; nome: string }; dias: Dias };

export type Previa = {
  avisos: string[];
  blocos: { setor: string; nome: string; atividades: number; existe: boolean }[];
  checklists: { nome: string; itens: string[]; materiais: string; epi: string; existe: boolean }[];
  rotas: {
    nome: string; existe: boolean; turno: string; hora_inicio: string; hora_fim: string;
    intervalo_inicio: string; intervalo_fim: string; dias_semana: string; tolerancia_min: number;
    responsavel: string; observacoes: string;
    itens: { ordem: number; horario: string; tempo_previsto_min: number | null; bloco: string;
      checklist: string; dias_semana: string; horarios_por_dia: [string, string][] }[];
  }[];
};

export type RespostaDaPrevia = { previa: Previa; chave: string; ja_existem: string[] };

export type ItemDoChecklist = {
  codigo: string; texto: string; tipo: string; obrigatorio: boolean; exige_foto: boolean;
  opcoes: string; minimo: string; maximo: string; problema_se: string; mostrar_se: string;
  como_fazer: string; referencia: string | null; foto_ref?: string;
};

export type DadosDoModelo = {
  modelo: { id: number; nome: string; descricao: string; local: { id: number; nome: string } | null;
    exige_foto_antes: boolean; exige_foto_depois: boolean };
  versao: { numero: number; publicada_em: string; materiais: string; epi: string } | null;
  itens: ItemDoChecklist[];
  linhas_em_branco: number;
  tipos: [string, string][];
  pode_montar: boolean;
  documentos: { id: number; nome: string; url: string; enviado_em: string; visivel_cliente: boolean }[];
  limite_docs: number;
};

export type DadosDosFeriados = {
  local: { id: number; nome: string };
  ano: number;
  lista: { data: string; passou: boolean; nome: string; id: number | null }[];
  rotas_param: string[];
  pode_montar: boolean;
};

export type Rota = {
  id: number; nome: string; turno: string; inicio: string; fim: string; intervalo_inicio: string;
  intervalo_fim: string; tolerancia_min: number; dias_semana: string; ativa: boolean;
  observacoes: string; presencas_por_turno: number; presenca_prazo_min: number;
  funciona_em_feriado: boolean; local: { id: number; nome: string };
};

export type ItemDaRota = {
  id: number; ativo: boolean; ponto_id: number; ponto: string; modelo_id: number; modelo: string;
  ordem: number; horarios: string; frequencia_min: number | null; tempo_previsto_min: number | null;
  dias_semana: string; horarios_por_dia: [string, string][]; hoje: string[];
};

export type DadosDaRota = {
  rota: Rota;
  itens: ItemDaRota[];
  pontos: { id: number; setor: string; ambiente: string; nome: string }[];
  modelos: { id: number; nome: string }[];
  pessoas: { id: number; nome: string; perfil: string }[];
  escalas: { id: number; nome: string; dias_semana: string; desde: string; ate: string | null }[];
  pode_montar: boolean;
  dias: Dias;
  hoje: string;
  links: { estrutura: string };
};

export type Gps = { situacao: string | null; texto: string; precisao: number | null };

export type DadosDoDia = {
  local: { id: number; nome: string };
  data: string; data_br: string; data_curta: string;
  aderencia: { no_prazo: number; base: number; pct: number | null };
  tarefas: {
    id: number; hora: string; ambiente: string; ponto: string; modelo: string; rota: string;
    situacao: string; situacao_rotulo: string;
    execucao: { id: number; pessoa: string; inicio: string; fim: string; sem_sinal: boolean;
      nao_conformes: number; gps: Gps; adiantada: boolean; motivo_troca: string; motivo_troca_texto: string } | null;
    nao_realizada: { motivo: string; texto: string; chamado: string | null } | null;
    pessoa: string | null;
  }[];
  ocorrencias: {
    id: number; hora: string; ambiente: string; ponto: string; titulo: string; responsavel: string | null;
    texto: string; foto: string | null; status: string; situacao: string; atrasada: boolean;
    prazo: string | null; resolvida: { quem: string; hora: string; resolucao: string } | null;
  }[];
  elogios: { id: number; hora: string; ambiente: string; ponto: string; nota: number; texto: string; responsavel: string | null }[];
  chegadas: { id: number; hora: string; pessoa: string; com_camera: boolean; gps: Gps }[];
  presencas: { id: number; hora: string; pessoa: string; rota: string; status: string; respondida: string | null }[];
  extras: { id: number; hora: string; ponto: string; modelo: string; pessoa: string; gps: Gps;
    motivo_troca: string; motivo_troca_texto: string }[];
  pode_atender: boolean;
};

export type DadosDaExecucao = {
  execucao: {
    id: number; client_id: number; ambiente: string; ponto: string; modelo: string; versao: number;
    extra: boolean; pessoa: string; lido_em: string; concluida_em: string; sem_sinal: boolean;
    recebida_em: string; gps: Gps | null; tarefa: { hora: string; rota: string } | null;
    adiantada: boolean; motivo_troca: string; motivo_troca_texto: string; observacao: string; dia: string;
  };
  respostas: { codigo: string; texto: string; resposta: string; corrigida: boolean; original: string }[];
  itens: { codigo: string; texto: string; valor: string }[];
  fotos: { id: number; url: string; momento: string; rotulo: string }[];
  nao_conformidades: { id: number; item_texto: string; resposta: string; chamado: string | null }[];
  correcoes: { quando: string; autor: string; motivo: string }[];
  pode_corrigir: boolean;
};
