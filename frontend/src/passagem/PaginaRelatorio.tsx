import { useQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router';
import { chamar } from '../api';
import { Relatorio } from './Relatorio';
import type { DadosDoRelatorio } from './tipos';

/** Um relatório por competência e área (a mesma query string da antiga). */
export function PaginaRelatorio() {
  const { search } = useLocation();
  const q = useQuery({
    queryKey: ['passagem', 'relatorio', search],
    queryFn: () => chamar<DadosDoRelatorio>('/passagem/relatorio-mensal' + search),
    gcTime: 0,
    retry: false,
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
  return <Relatorio dados={q.data} key={search} />;
}
