// Conversa com o servidor (Flask, /api/v1). Mesma sessão do site (cookie) e
// o mesmo CSRF, no cabeçalho X-CSRFToken. Sem token novo, sem porta nova.
import { anotar, guardadaEm } from './copia';

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

// Os endereços cuja última resposta veio da cópia do aparelho (sem sinal).
const copiasLidas = new Set<string>();

const SEM_CONEXAO = 'Sem conexão com o servidor. Confira a internet e tente de novo.';

/** Chama a API das telas novas (``/eu`` → ``/api/v1/eu``) ou, com o caminho
 * inteiro, as do aplicativo de campo que já existem (``/app/api/...``).
 * 401 (sessão vencida) leva ao login e volta para esta tela. */
export async function chamar<T>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const url = caminho.startsWith('/app/') ? caminho : `/api/v1${caminho}`;
  const metodo = (opcoes.method || 'GET').toUpperCase();
  const cabecalhos = new Headers(opcoes.headers);
  cabecalhos.set('Accept', 'application/json');
  if (metodo !== 'GET' && csrf) cabecalhos.set('X-CSRFToken', csrf);
  if (opcoes.body && !(opcoes.body instanceof FormData)) {
    cabecalhos.set('Content-Type', 'application/json');
  }
  let resp: Response;
  try {
    resp = await fetch(url, {
      ...opcoes,
      headers: cabecalhos,
      credentials: 'same-origin',
    });
  } catch {
    throw new ErroDaApi(0, SEM_CONEXAO);
  }
  if (metodo === 'GET') anotar(url, resp);
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
  if (metodo === 'GET' && guardadaEm(resp) !== null) copiasLidas.add(url);
  else copiasLidas.delete(url);
  return dados as T;
}

/** Quem está logado. Vindo da cópia do aparelho (sem sinal), confere com o
 * dono da casca (``<meta name="usuario-id">``, a mesma marca da fila): uma
 * cópia que não é da mesma pessoa não aparece. */
export function buscarEu() {
  return chamar<Eu>('/eu').then((eu) => {
    const dono = document.querySelector<HTMLMetaElement>('meta[name="usuario-id"]')?.content;
    if (copiasLidas.has('/api/v1/eu') && dono && dono !== String(eu.id)) {
      throw new ErroDaApi(0, SEM_CONEXAO);
    }
    guardarCsrf(eu.csrf);
    return eu;
  });
}

/** O ``fetch`` como as telas antigas do aplicativo usam (``/app/api/...``):
 * a mesma sessão e o CSRF no cabeçalho, mas a resposta volta crua — quem
 * chama decide o que é falta de sinal (``TrinoFila.ehFalhaDeConexao``) e o
 * que é recusa do servidor. Sem sinal, a promessa falha. */
export function enviarBruto(url: string, opcoes: RequestInit = {}): Promise<Response> {
  const metodo = (opcoes.method || 'GET').toUpperCase();
  const cabecalhos = new Headers(opcoes.headers);
  if (metodo !== 'GET' && csrf) cabecalhos.set('X-CSRFToken', csrf);
  return fetch(url, { ...opcoes, headers: cabecalhos, credentials: 'same-origin' });
}
