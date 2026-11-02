// Os dados que as telas dos materiais recebem (facilities/telas/materiais.py):
// os mesmos das telas antigas, com as quantidades ("1,5"), os valores
// ("R$ 1.234,56") e as datas já escritos como elas escrevem.

export type Pares = [string, string][];
export type Local = { id: number; nome: string };
export type Links = { catalogo: string; custo: string; pedidos: string };

export type MaterialDoCatalogo = {
  id: number; nome: string; unidade: string; preco: string | null; preco_campo: string; ativo: boolean;
};

export type DadosDoCatalogo = {
  materiais: MaterialDoCatalogo[];
  locais: { id: number; nome: string; url: string }[];
  pode_montar: boolean; links: Links;
};

export type Movimento = {
  dia: string; tipo_rotulo: string; material: string; quantidade: string; valor: string;
  pessoa: string; motivo: string; autorizou: string | null;
};

export type DadosDoEstoque = {
  local: Local;
  materiais: { id: number; nome: string; unidade: string }[];
  com_saldo: { id: number; nome: string; unidade: string; saldo: string; negativo: boolean }[];
  movimentos: Movimento[];
  rotas: { id: number; nome: string }[];
  tipos: Pares;
  pode_montar: boolean; gestor_do_contrato: boolean;
  links: Links & { mes: string };
};

export type DadosDoConsumoDoMes = {
  local: Local; mes: string; anterior: string; seguinte: string; total: string;
  sem_preco: string[];
  linhas: { material: string; quantidade: string; vezes: number; valor: string }[];
  links: { local: string };
};

export type DadosDoCusto = {
  de: string; ate: string; de_br: string; ate_br: string; total: string; sem_preco: number;
  clientes: Pares; estados: Pares;
  locais: { url: string; nome: string; cliente: string; estado: string; consumos: number; sem_preco: number; valor: string }[];
  links: Links;
};

export type Pedido = {
  id: number; resumo: string; status: string; situacao_rotulo: string;
  selo: 'visto' | 'atrasada' | 'no_prazo'; atrasado: boolean;
  local: string; pessoa: string; criado_em: string; prazo: string | null;
  quem_viu: string | null; visto_em: string | null; foto: string | null; pode_marcar: boolean;
};

export type DadosDosPedidos = { pedidos: Pedido[]; links: Links };
