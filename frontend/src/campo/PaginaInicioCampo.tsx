import { useQuery } from '@tanstack/react-query';
import { chamar, type Eu } from '../api';
import { CascaCampo } from './CascaCampo';
import { InicioCampo } from './InicioCampo';
import type { InicioDoCampo } from './tipos';

export function PaginaInicioCampo({ eu }: { eu: Eu }) {
  const q = useQuery({
    queryKey: ['campo', 'inicio'],
    queryFn: () => chamar<InicioDoCampo>('/campo/inicio'),
  });
  return (
    <CascaCampo eu={eu} links={q.data?.links ?? null}>
      {q.isPending && <p className="text-muted" role="status">Carregando…</p>}
      {q.isError && (
        <div className="fc-cartao" role="alert">
          <p>{q.error.message}</p>
          <button className="btn btn-primary" type="button" onClick={() => q.refetch()}>Tentar de novo</button>
        </div>
      )}
      {q.data && <InicioCampo eu={eu} dados={q.data} />}
    </CascaCampo>
  );
}
