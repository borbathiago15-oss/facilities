import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router';
import { chamar } from '../api';
import { horaDaCopia, useCopiaEmUso } from '../copia';
import { Passagem } from './Passagem';
import type { DadosDaPassagem } from './tipos';

/** O aviso da cópia do aparelho (sem sinal, a tela abre da cópia: sw.js). */
export function AvisoDeCopia() {
  const copia = useCopiaEmUso();
  if (copia === null) return null;
  return (
    <div className="alert alert-warning py-2 small" role="status" data-testid="aviso-de-copia">
      Sem sinal: esta é a cópia guardada neste aparelho às {horaDaCopia(copia)}. O que você
      fizer fica guardado no aparelho e sobe sozinho quando o sinal voltar.
    </div>
  );
}

export function PaginaPassagem() {
  const [busca] = useSearchParams();
  const cliente = busca.get('client_id') || '';
  // Uma busca por abertura, como a página antiga: o formulário não é trocado
  // por baixo de quem está preenchendo.
  const q = useQuery({
    queryKey: ['passagem', 'turno', cliente],
    queryFn: () => chamar<DadosDaPassagem>('/passagem/turno' + (cliente
      ? '?client_id=' + encodeURIComponent(cliente) : '')),
    gcTime: 0,
    staleTime: Infinity,
    refetchOnReconnect: false,
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
  return (
    <>
      <AvisoDeCopia />
      <Passagem dados={q.data} key={cliente} />
    </>
  );
}
