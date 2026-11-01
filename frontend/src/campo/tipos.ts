// O que /api/v1/campo/inicio entrega (facilities/telas/campo.py).

export type LocalDoTurno = {
  local_id: number;
  local: string;
  situacao: 'sem_chegada' | 'chegou' | 'sem_entrada';
  entrada: string | null;
  chegou_as: string | null;
  tarefas: number;
  abertas: number;
  url: string;
};

export type Ocorrencia = {
  id: number; local: string; ambiente: string; titulo: string; ponto: string;
  hora: string | null; texto: string; sua: boolean; url: string;
};

export type InicioDoCampo = {
  hoje: string;
  tem_locais: boolean;
  turno: LocalDoTurno[];
  material: string | null;
  equipe: string | null;
  visitas: { url: string; abertas: number } | null;
  ocorrencias: Ocorrencia[];
  tarefas: { id: number; titulo: string; turno: string; data: string; url: string }[];
  pendencias: { id: number; titulo: string; desde: string | null; url: string }[];
  chamados: { id: number; titulo: string; prazo: string | null; url: string }[] | null;
  passagem: { nome: string; url: string }[] | null;
  links: { ler_qr: string; site: string; instalar: string; passagem: string | null; chamados: string | null };
};
