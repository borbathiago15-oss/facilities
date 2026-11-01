// O que /api/v1/admin/armazenamento devolve (facilities/arquivo_fotos/servico.py).

export type Lote = {
  id: number;
  situacao: 'em_andamento' | 'concluido' | 'concluido_com_falhas';
  situacao_rotulo: string;
  quem: string;
  iniciado_em: string;
  concluido_em: string | null;
  corte: string;
  dias: number;
  destino: string;
  previstas: number;
  arquivadas: number;
  bytes: number;
  nao_arquivadas: number;
  tentativas_com_erro: number;
  ultimo_erro: string | null;
  ultima_rodada_em: string | null;
};

export type PainelDoArmazenamento = {
  dias: number;
  dias_min: number;
  dias_max: number;
  corte: string;
  destino: {
    disponivel: boolean;
    tipo: 'r2' | 'pasta' | null;
    rotulo: string;
    mesmo_disco: boolean;
    problema: string | null;
  };
  total: { fotos: number; bytes: number; sem_tamanho: number };
  por_mes: { mes: string; fotos: number; bytes: number }[];
  locais: { local: string; bytes: number }[];
  arquivadas: { fotos: number; bytes: number; fora_do_principal: number; bytes_fora_do_principal: number };
  no_principal_bytes: number;
  pendentes: { fotos: number; bytes: number; sem_tamanho: number };
  nao_sairam: number;
  em_andamento: Lote | null;
  lotes: Lote[];
};
