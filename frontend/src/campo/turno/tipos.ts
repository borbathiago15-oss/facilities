// O que /api/v1/campo/turno entrega: o MESMO JSON que a tela antiga leva
// embutido (rotas.telas._dados_do_turno), mais os endereços da moldura.

export type Tarefa = {
  id: number;
  ponto: string;                 // o código do QR
  ponto_nome: string;
  ambiente: string;
  local: string;
  local_id: number;
  rota: string;
  hora: string;
  previsto: string;              // ISO, UTC
  tolerancia: number;            // minutos
  fim_turno: string;
  versao: number;
  minha: boolean;
  escalado: string;
  status: string;                // a situação no servidor ("prevista" = em aberto)
  situacao: string;
  tempo_previsto_min: number | null;
};

export type ItemDoChecklist = {
  codigo: string;
  texto: string;
  tipo: string;                  // sim_nao, conforme, numero, escolha, data_hora, texto
  problema_se?: string;
  exige_foto?: boolean;
  mostrar_se?: { codigo: string; valor: string } | null;
  como_fazer?: string;
  foto_ref_url?: string;
  minimo?: number | null;
  maximo?: number | null;
  opcoes?: string[];
};

export type Versao = {
  id: number;
  modelo: string;
  numero: number;
  procedimento: string;
  itens: ItemDoChecklist[];
  materiais: string;
  epi: string;
  documentos: { nome: string; url: string }[];
  foto_antes: boolean;
  foto_depois: boolean;
};

export type Ponto = {
  id: number;
  nome: string;
  ambiente: string;
  descricao: string;
  local: string;
  local_id: number;
  entrada: boolean;
  extras: number[];
  escopo: number[];
};

export type Preventiva = {
  id: number; numero: string; titulo: string; ponto: string; ponto_nome: string;
  ambiente: string; versao: number; vence: string; atrasada: boolean; minha: boolean;
};

export type OcorrenciaDoPonto = {
  id: number; ponto: string; ponto_nome: string; ambiente: string; tipo: string;
  minha: boolean; responsavel: string; texto: string; hora: string; status: string;
  prazo: string; atrasada: boolean;
};

export type Chegada = { id?: number; hora: string; data?: string; guardada?: boolean };

export type LocalDaCarteira = {
  id: number;
  nome: string;
  entrada: string | null;
  entrada_nome: string | null;
  chegada: Chegada | null;
};

export type Vocabulario = Record<string, string>;

export type DadosDoTurno = {
  usuario: number;
  agora: string;
  tarefas: Tarefa[];
  versoes: Record<string, Versao>;
  pontos: Record<string, Ponto>;
  preventivas: Preventiva[];
  motivos: Vocabulario;
  motivos_atraso: Vocabulario;
  motivos_nao_feito: Vocabulario;
  motivos_atraso_ordem?: string[];
  motivos_nao_feito_ordem?: string[];
  motivos_troca: Vocabulario;
  motivos_troca_ordem?: string[];
  tolerancia_atraso_min: number;
  locais: LocalDaCarteira[];
  situacoes: Vocabulario;
  ocorrencias: OcorrenciaDoPonto[];
};

export type LinksDoCampo = {
  ler_qr: string; site: string; instalar: string; passagem: string | null; chamados: string | null;
};

export type RespostaDoTurno = { dados: DadosDoTurno; links: LinksDoCampo };

/** O motivo de ir a outra área (troca de área, 27/10/2026). */
export type Troca = { motivo: string; rotulo: string; texto?: string; em?: number };

/** O motivo de um item "Não deu". */
export type MotivoNaoDeu = {
  motivo: string; rotulo: string; texto?: string; material_id?: number; material_nome?: string;
};
