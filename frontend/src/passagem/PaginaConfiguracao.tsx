import { useQuery } from '@tanstack/react-query';
import { useLocation } from 'react-router';
import { chamar } from '../api';
import { Configuracao } from './Configuracao';
import type { DadosDaConfiguracao } from './tipos';

/** Uma busca por abertura (e por contrato): o editor não é trocado por
 * baixo de quem está editando. */
export function PaginaConfiguracao() {
  const { search } = useLocation();
  const q = useQuery({
    queryKey: ['passagem', 'configuracao', search],
    queryFn: () => chamar<DadosDaConfiguracao>('/passagem/configuracao' + search),
    gcTime: 0,
    staleTime: Infinity,
    refetchOnReconnect: false,
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
  return <Configuracao dados={q.data} key={search} />;
}
