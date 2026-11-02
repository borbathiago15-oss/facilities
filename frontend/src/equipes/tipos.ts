// Os dados que as telas da equipe e das visitas de supervisão recebem
// (facilities/telas/equipes.py): os mesmos das telas antigas, com as horas e
// as datas já escritas como elas escrevem.

export type Pares = [string, string][];
export type Local = { id: number; nome: string };

export type Funcionario = {
  id: number; nome: string; funcao: string; matricula: string; user_id: number | null;
  usa_app: boolean; ativo: boolean;
};

export type Posto = {
  id: number; nome: string; hora_inicio: string; hora_fim: string;
  rota_id: number | null; rota: string | null; ativo: boolean;
};

export type Escala = {
  id: number; funcionario: string; posto: string; dias: string;
  data_inicio: string; data_fim: string | null;
};

export type DadosDaEquipe = {
  local: Local; hoje: string; dias: Pares;
  funcionarios: Funcionario[]; postos: Posto[]; escalas: Escala[];
  rotas: { id: number; nome: string }[];
  logins: { id: number; nome: string; email: string }[];
  pode_montar: boolean;
  links: { local: string; mes: string; visitas: string };
};

/** A célula da grade do mês (a letra, a classe e o ``title`` da antiga). */
export type Celula = { tipo: 'coberta' | 'faltou' | 'atrasou' | 'veio' | 'pendente' | 'previsto'; letra: string; titulo: string } | null;

export type DadosDoMes = {
  local: Local; mes: string; m: string; anterior: string; seguinte: string;
  totais: { previstos: number; lancados: number; faltas: number; cobertas: number };
  dias: number[];
  linhas: { funcionario: string; posto: string; celulas: Celula[] }[];
  links: { equipe: string };
};

export type Programada = {
  id: number; nome: string; ativo: boolean; modelo_id: number; modelo: string;
  intervalo_dias: number; proxima_em: string; proxima_em_iso: string;
  supervisor_id: number | null; supervisor: string | null;
};

export type VisitaRecente = {
  id: number; nome: string; vencimento: string; quem_fez: string | null;
  status: string; situacao_rotulo: string; n_nao_conformes: number; url: string;
};

export type DadosDasVisitas = {
  local: Local;
  modelos: { id: number; nome: string }[];
  programadas: Programada[];
  recentes: VisitaRecente[];
  supervisores: { id: number; nome: string; perfil: string }[];
  hoje: string; pode_montar: boolean;
  links: { checklists: string };
};
