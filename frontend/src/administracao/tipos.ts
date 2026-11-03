// Os dados das telas das pessoas e dos locais do administrador (Fase 6a),
// como a API /api/v1/admin/... entrega. A leitura nunca traz senha nem hash.

export type Pessoa = {
  id: number; nome: string; email: string; perfil: string; perfil_rotulo: string;
  ativo: boolean; todos_os_locais: boolean; superior_id: number | null;
  cliente_id: number | null; locais: number[]; permissoes: string[];
  segunda_etapa: boolean; propria: boolean; alcance: string; cadeia: { nome: string; perfil: string }[];
};

export type DadosDasPessoas = {
  pessoas: Pessoa[];
  locais: { id: number; nome: string; ativo: boolean }[];
  perfis: [string, string][];
  permissoes: [string, string][];
  superiores: { id: number; nome: string; perfil: string }[];
  clientes: { id: number; nome: string }[];
};

/** A senha temporária recém-criada: só na memória da tela, até sair dela. */
export type SenhaNova = { texto: string; senha: string };

export type Local = {
  id: number; nome: string; centro_de_custo: string; endereco: string;
  responsavel_id: number | null; responsavel: string | null;
  cliente_id: number | null; cliente: string | null;
  estado_id: number | null; estado: string | null; ativo: boolean;
  links: { estrutura: string; passagem: string };
};

export type DadosDosLocais = {
  locais: Local[];
  gestores: { id: number; nome: string }[];
  clientes: { id: number; nome: string; ativo: boolean }[];
  estados: { id: number; nome: string; ativo: boolean }[];
  links: { empresas: string; clientes: string; estados: string };
};
