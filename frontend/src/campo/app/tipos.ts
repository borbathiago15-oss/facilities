// Os dados das telas novas do aplicativo de campo da Fase 1d
// (facilities/telas/campo_app.py): os mesmos de equipes/app_equipe.html,
// materiais/app.html, visitas/app_lista.html e visitas/app_visita.html.
import type { LinksDoCampo } from '../tipos';

export type PresencaDoDia = {
  id: number;
  situacao: string;
  rotulo: string;
  cobertura: { funcionario: string; motivo: string } | null;
};

export type LinhaDaEquipe = {
  escala_id: number;
  funcionario_id: number;
  funcionario: string;
  /** "Posto · 07:00 às 15:00 · Função", como a antiga escreve. */
  detalhe: string;
  presenca: PresencaDoDia | null;
};

export type DadosDaEquipe = {
  dia: string;
  data: string;
  ontem: string;
  amanha: string | null;
  situacoes: [string, string][];
  locais: { id: number; nome: string; linhas: LinhaDaEquipe[]; cobridores: { id: number; nome: string }[] }[];
  links: LinksDoCampo;
};

export type DadosDosMateriais = {
  locais: { id: number; nome: string }[];
  materiais: { id: number; nome: string; unidade: string }[];
  chamados: { id: number; rotulo: string }[];
  rotas: { id: number; rotulo: string }[];
  meus: { id: number; resumo: string; detalhe: string }[];
  links: LinksDoCampo;
};

export type DadosDasVisitas = {
  visitas: { id: number; nome: string; local: string; ate: string; selo: 'atrasada' | 'hoje' | null; url: string }[];
  links: LinksDoCampo;
};

export type ItemDaVisita = {
  codigo: string;
  texto: string;
  tipo: string;
  obrigatorio: boolean;
  mostrar_se: { codigo: string; valor: string; texto: string } | null;
  minimo: string | null;
  maximo: string | null;
  opcoes: string[];
  exige_foto: boolean;
};

export type DadosDaVisita = {
  visita: {
    id: number; nome: string; local: string; status: string; situacao_rotulo: string;
    ate: string | null; quem_fez: string | null; feita_em: string | null; n_nao_conformes: number;
    chamado: { numero: string; status_rotulo: string; url: string } | null;
    observacao: string; supervisor: string | null;
  };
  fotos: { id: number; url: string; alt: string; legenda: string }[];
  respostas: { codigo: string; texto: string; valor: string }[];
  itens: ItemDaVisita[];
  exige_foto_antes: boolean;
  exige_foto_depois: boolean;
  pode_fazer: boolean;
  links: LinksDoCampo;
};
