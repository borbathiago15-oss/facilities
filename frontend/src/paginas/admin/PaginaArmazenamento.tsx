import { useQuery, useQueryClient } from '@tanstack/react-query';
import { chamar } from '../../api';
import { Armazenamento } from './Armazenamento';
import type { PainelDoArmazenamento } from './tipos';

const CHAVE = ['admin', 'armazenamento'];

export function PaginaArmazenamento() {
  const cliente = useQueryClient();
  const q = useQuery({
    queryKey: CHAVE,
    queryFn: () => chamar<PainelDoArmazenamento>('/admin/armazenamento'),
  });
  // O servidor devolve o painel atualizado depois de cada envio.
  const enviar = (caminho: string, corpo: object) =>
    chamar<PainelDoArmazenamento>(caminho, { method: 'POST', body: JSON.stringify(corpo) })
      .then((d) => cliente.setQueryData(CHAVE, d));

  if (q.isPending) return <p className="text-muted" role="status">Carregando…</p>;
  if (q.isError) {
    return (
      <div role="alert">
        <p>{q.error.message}</p>
        <button className="btn btn-primary" type="button" onClick={() => q.refetch()}>Tentar de novo</button>
      </div>
    );
  }
  return (
    <Armazenamento dados={q.data}
      salvarDias={(dias) => enviar('/admin/armazenamento/prazo', { dias })}
      arquivar={() => enviar('/admin/armazenamento/arquivar', { confirmar: true })} />
  );
}
