import { useQuery } from '@tanstack/react-query';
import { chamar, type Eu } from '../../api';
import { CascaCampo } from '../CascaCampo';
import type { RespostaDoTurno } from './tipos';
import { Turno } from './Turno';

export function PaginaTurno({ eu }: { eu: Eu }) {
  // Uma busca por abertura da tela, como a página antiga: os dados mudam com
  // a tela aberta (a tarefa feita, a chegada) e não são trocados por baixo.
  const q = useQuery({
    queryKey: ['campo', 'turno'],
    queryFn: () => chamar<RespostaDoTurno>('/campo/turno'),
    gcTime: 0,
    staleTime: Infinity,
    refetchOnReconnect: false,
  });
  return (
    <CascaCampo eu={eu} links={q.data?.links ?? null}>
      {q.isPending && (
        <>
          <h1 className="fc-titulo">Meu turno</h1>
          <p className="fc-sub" role="status">Carregando…</p>
        </>
      )}
      {q.isError && (
        <div className="fc-cartao" role="alert">
          <p>{q.error.message}</p>
          <button className="btn btn-primary" type="button" onClick={() => q.refetch()}>Tentar de novo</button>
        </div>
      )}
      {q.data && <Turno dados={q.data.dados} />}
    </CascaCampo>
  );
}
