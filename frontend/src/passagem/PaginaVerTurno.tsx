import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router';
import { chamar } from '../api';
import type { DadosDaLeitura } from './tipos';
import { VerTurno } from './VerTurno';

export function PaginaVerTurno() {
  const { id = '' } = useParams();
  const q = useQuery({
    queryKey: ['passagem', 'leitura', id],
    queryFn: () => chamar<DadosDaLeitura>('/passagem/turno/' + encodeURIComponent(id)),
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
  return <VerTurno dados={q.data} />;
}
