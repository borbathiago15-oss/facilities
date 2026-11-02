// O que as telas dos Cadastros têm em comum (Fase 3a da migração para
// React): a busca dos dados (uma por abertura: depois de cada envio a tela
// se refaz do zero, como a antiga depois do redirecionamento), o envio dos
// formulários e os recados de uma vez só.
//
// Os formulários são os mesmos das telas antigas (os mesmos nomes de campo):
// o envio leva o próprio formulário (FormData) para o MESMO caminho abaixo de
// /api/v1/cadastros, que chama a MESMA ação da antiga. A resposta traz o
// recado (o flash da antiga) e o endereço de volta, já na tela nova.
import { useQuery } from '@tanstack/react-query';
import { type ReactNode, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { chamar, enviarBruto } from '../api';
import { Recados } from '../passagem/Recados';

export type Recado = { tipo: string; texto: string };
export type Resposta = { recados?: Recado[]; destino?: string; error?: string };

const SEM_CONEXAO = 'Sem conexão com o servidor. Confira a internet e tente de novo.';

/** ``/novo/x`` → ``/x`` (o endereço dentro do roteador); os outros, null. */
export function dentroDoRoteador(url: string): string | null {
  return url.startsWith('/novo/') ? url.slice('/novo'.length) : null;
}

/** Os dados da tela: uma busca por abertura (``location.key``), sem cópia. */
export function useDados<T>(api: string) {
  const local = useLocation();
  return useQuery({
    queryKey: ['cadastros', api, local.key],
    queryFn: () => chamar<T>(api),
    gcTime: 0,
    staleTime: Infinity,
    refetchOnReconnect: false,
    retry: false,
  });
}

/** Espera os dados; erro com "Tentar de novo", como as outras telas novas. */
export function Pagina<T>({ api, children }: { api: string; children: (dados: T) => ReactNode }) {
  const q = useDados<T>(api);
  if (q.isPending) return <p className="text-muted" role="status">Carregando…</p>;
  if (q.isError) {
    return (
      <div role="alert">
        <p>{q.error.message}</p>
        <button className="btn btn-primary" type="button" onClick={() => q.refetch()}>Tentar de novo</button>
      </div>
    );
  }
  return <>{children(q.data)}</>;
}

/** Os recados que o envio deixou (vêm no ``state`` da navegação). Lidos, saem
 * do histórico: recarregar a página não os mostra de novo (como o flash). */
export function RecadosDoEnvio() {
  const local = useLocation();
  const [recados] = useState<Recado[]>(() => (local.state as { recados?: Recado[] } | null)?.recados || []);
  useEffect(() => {
    const h = window.history.state;
    if (h && h.usr) window.history.replaceState({ ...h, usr: null }, '');
  }, []);
  return <Recados servidor={recados} />;
}

/** O caminho de migalhas do topo (o ``breadcrumb`` das telas antigas). */
export function Migalhas({ itens }: { itens: [string, string | null][] }) {
  if (!itens.length) return null;
  return (
    <nav aria-label="breadcrumb"><ol className="breadcrumb">
      {itens.map(([rotulo, url], n) => (url
        ? <li className="breadcrumb-item" key={n}><Ir href={url}>{rotulo}</Ir></li>
        : <li className="breadcrumb-item active" aria-current="page" key={n}>{rotulo}</li>))}
    </ol></nav>
  );
}

/** Link: tela nova navega sem recarregar; tela antiga (ou PDF) abre normal. */
export function Ir({ href, children, ...resto }: { href: string; children: ReactNode } &
  Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>) {
  const dentro = dentroDoRoteador(href);
  if (dentro !== null && !resto.target) return <Link to={dentro} {...resto}>{children}</Link>;
  return <a href={href} {...resto}>{children}</a>;
}

/** Leva ao endereço de volta com os recados; tela antiga, navega normal. */
export function useIr() {
  const navegar = useNavigate();
  return (destino: string, recados: Recado[] = []) => {
    const dentro = dentroDoRoteador(destino);
    if (dentro === null) { window.location.assign(destino); return; }
    navegar(dentro, { state: { recados } });
    window.scrollTo(0, 0);
  };
}

/** Envia o corpo (o formulário, ou um objeto vira JSON) e devolve a resposta
 * do servidor; sem sinal, a resposta é o erro de conexão. */
export async function enviar(url: string, corpo: FormData | Record<string, unknown>): Promise<{ ok: boolean; dados: Resposta }> {
  const opcoes: RequestInit = corpo instanceof FormData
    ? { method: 'POST', body: corpo }
    : { method: 'POST', body: JSON.stringify(corpo), headers: { 'Content-Type': 'application/json' } };
  let r: Response;
  try {
    r = await enviarBruto(url, { ...opcoes, headers: { Accept: 'application/json', ...(opcoes.headers || {}) } });
  } catch {
    return { ok: false, dados: { error: SEM_CONEXAO } };
  }
  if (r.status === 401) {
    const volta = window.location.pathname + window.location.search;
    window.location.assign(`/login?next=${encodeURIComponent(volta)}`);
    return { ok: false, dados: { error: 'Sessão expirada. Entre de novo.' } };
  }
  const dados = (await r.json().catch(() => null)) as Resposta | null;
  if (!dados) return { ok: false, dados: { error: 'Algo deu errado. Tente de novo.' } };
  return { ok: r.ok, dados };
}

/** O envio de formulário das telas dos cadastros: manda, e vai ao endereço
 * de volta com o recado (o mesmo caminho da tela antiga depois do POST).
 * Sem endereço (falta de sinal, erro de servidor), o recado aparece aqui. */
export function useFormulario() {
  const ir = useIr();
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const enviarFormulario = (url: string, form: HTMLFormElement) => {
    if (ocupado) return;
    setOcupado(true);
    setErro(null);
    enviar(url, new FormData(form)).then(({ dados }) => {
      setOcupado(false);
      if (dados.destino) { ir(dados.destino, dados.recados); return; }
      setErro(dados.error || 'Algo deu errado. Tente de novo.');
      window.scrollTo(0, 0);
    });
  };
  const submeter = (url: string) => (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    enviarFormulario(url, ev.currentTarget);
  };
  const aviso = erro
    ? <Recados servidor={[{ tipo: 'danger', texto: erro }]} key={erro} />
    : null;
  return { submeter, enviarFormulario, ocupado, aviso };
}

/** ``%03d`` do número da etiqueta (QR 001). */
export function tresDigitos(n: number): string {
  return String(n).padStart(3, '0');
}

/** A busca de um formulário GET (o ``?de=&ate=`` do custo e do painel). */
export function buscaDoFormulario(form: HTMLFormElement): string {
  const q = new URLSearchParams();
  new FormData(form).forEach((v, k) => q.append(k, typeof v === 'string' ? v : ''));
  return q.toString();
}
