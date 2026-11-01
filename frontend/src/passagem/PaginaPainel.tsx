import { useQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router';
import { chamar } from '../api';
import { Painel } from './Painel';
import type { DadosDoPainel } from './tipos';

/** Uma página por recorte: trocar o filtro troca o endereço (a mesma query
 * string da tela antiga) e a tela se refaz do zero, como a antiga recarrega. */
export function PaginaPainel() {
  const { search } = useLocation();
  const q = useQuery({
    queryKey: ['passagem', 'painel', search],
    queryFn: () => chamar<DadosDoPainel>('/passagem/painel' + search),
    gcTime: 0,
  });
  if (q.isPending) return <p className="text-muted" role="status">Carregando…</p>;
  if (q.isError) {
    return (
      <div role="alert">
        <p>{q.error.message}</p>
        <button className="btn btn-primary" type="button" onClick={() => q.refetch()}>Tentar de novo</button>
      </div>
    );
  }
  return <Painel dados={q.data} key={search} />;
}
