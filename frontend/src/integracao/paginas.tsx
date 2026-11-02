// A página das chaves da integração (Fase 4c): busca a lista na API (o mesmo
// endereço da tela antiga abaixo de /api/v1) e desenha a tela. Ponto de
// entrada do pedaço "integracao" do build.
//
// A chave recém-criada mora só aqui, no estado da página (acima da busca:
// recarregar a lista, mesmo com erro, não a perde) e some em qualquer
// navegação — ``location.key`` muda — ou ao sair da tela.
import { useEffect, useState } from 'react';
import { useLocation } from 'react-router';
import { useDados } from '../cadastros/comum';
import { Integracao } from './Integracao';
import type { ChaveNova, DadosDaIntegracao } from './tipos';

export function PaginaIntegracao() {
  const local = useLocation();
  const q = useDados<DadosDaIntegracao>('/admin/integracao/');
  const [nova, setNova] = useState<ChaveNova | null>(null);
  useEffect(() => { setNova(null); }, [local.key]);
  if (q.data === undefined) {
    if (q.isError) {
      return (
        <div role="alert">
          <p>{q.error.message}</p>
          <button className="btn btn-primary" type="button" onClick={() => q.refetch()}>Tentar de novo</button>
        </div>
      );
    }
    return <p className="text-muted" role="status">Carregando…</p>;
  }
  return <Integracao dados={q.data} nova={nova}
    aoCriar={(c) => { setNova(c); q.refetch(); }} />;
}
