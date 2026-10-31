// Conversa com o servidor (Flask, /api/v1). Mesma sessão do site (cookie) e
// o mesmo CSRF, no cabeçalho X-CSRFToken. Sem token novo, sem porta nova.

export type ItemDoMenu = {
  endpoint: string;
  rotulo: string;
  icone: string;
  url: string;
};

export type GrupoDoMenu = {
  titulo: string;
  fixo: boolean;
  aberto: boolean;
  itens: ItemDoMenu[];
};

export type Eu = {
  id: number;
  nome: string;
  primeiro_nome: string;
  perfil: string;
  papel: string;
  cliente: boolean;
  avisos_nao_lidos: number;
  menu: GrupoDoMenu[];
  csrf: string;
  versao: string;
  links: { inicio: string; avisos: string; trocar_senha: string; seguranca: string; sair: string };
};

export class ErroDaApi extends Error {
  status: number;
  constructor(status: number, mensagem: string) {
    super(mensagem);
    this.status = status;
  }
}

let csrf = '';

export function guardarCsrf(token: string) {
  csrf = token;
}

const SEM_CONEXAO = 'Sem conexão com o servidor. Confira a internet e tente de novo.';

/** Chama a API. 401 (sessão vencida) leva ao login e volta para esta tela. */
export async function chamar<T>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const metodo = (opcoes.method || 'GET').toUpperCase();
  const cabecalhos = new Headers(opcoes.headers);
  cabecalhos.set('Accept', 'application/json');
  if (metodo !== 'GET' && csrf) cabecalhos.set('X-CSRFToken', csrf);
  if (opcoes.body && !(opcoes.body instanceof FormData)) {
    cabecalhos.set('Content-Type', 'application/json');
  }
  let resp: Response;
  try {
    resp = await fetch(`/api/v1${caminho}`, {
      ...opcoes,
      headers: cabecalhos,
      credentials: 'same-origin',
    });
  } catch {
    throw new ErroDaApi(0, SEM_CONEXAO);
  }
  if (resp.status === 401) {
    const volta = window.location.pathname + window.location.search;
    window.location.assign(`/login?next=${encodeURIComponent(volta)}`);
    throw new ErroDaApi(401, 'Sessão expirada. Entre de novo.');
  }
  const dados = await resp.json().catch(() => null);
  if (!resp.ok) {
    const msg = (dados && (dados.error || dados.erro)) || 'Algo deu errado. Tente de novo.';
    throw new ErroDaApi(resp.status, msg);
  }
  return dados as T;
}

export function buscarEu() {
  return chamar<Eu>('/eu').then((eu) => {
    guardarCsrf(eu.csrf);
    return eu;
  });
}
