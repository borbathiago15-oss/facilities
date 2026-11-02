// Os dados das telas da conta, dos avisos e do Início (Fase 6a), como a API
// /api/v1 entrega. As datas e as horas já vêm escritas como a tela antiga
// escreve.

export type Numero = { rotulo: string; n: number; tom: string; icone: string; url: string };

export type ItemDaFila = {
  situacao: string; situacao_rotulo: string; tipo_rotulo: string; numero: string;
  titulo: string; local: string; prazo: string; link: string;
};

export type Atalho = { nome: string; icone: string; url: string; texto: string };

export type DadosDoInicio = {
  primeiro_nome: string; data: string; perfil: string; locais_na_carteira: number | null;
  abrir_chamado: string | null; numeros: Numero[]; primeiro: ItemDaFila[]; fila: string;
  atalhos: Atalho[];
  administrador: { empresas: string; clientes: string; estados: string; locais: string; pessoas: string } | null;
};

export type Aviso = { id: number; titulo: string; mensagem: string; nao_lido: boolean; em: string };

export type DadosDosAvisos = { avisos: Aviso[]; nao_lidos: number };

export type DadosDaSeguranca = { ativo: boolean };

/** O segredo da segunda etapa: só na memória da tela, até ativar ou sair. */
export type CodigoNovo = { segredo: string; qr: string };

export type DadosDaTrocaDeSenha = { primeiro_acesso: boolean; minimo: number };
