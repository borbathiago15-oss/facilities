// Os dados da tela das chaves da integração (Fase 4c), como a API
// /api/v1/admin/integracao/ entrega. A leitura nunca traz o texto nem o hash
// de chave nenhuma: só o prefixo (``fac_1a2b3c4d_…``).

export type Chave = {
  id: number; nome: string; prefixo: string; locais: string;
  criada_em: string; ultimo_uso_em: string | null; ativa: boolean;
};

export type Acesso = {
  id: number; em: string; chave: string; rota: string; parametros: string;
  status: number; itens: number | string;
};

export type DadosDaIntegracao = {
  chaves: Chave[]; acessos: Acesso[]; locais: { id: number; nome: string }[];
};

/** A chave recém-criada: só na memória da tela, até sair dela. */
export type ChaveNova = { nome: string; texto: string };
