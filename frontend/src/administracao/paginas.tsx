// As páginas das pessoas e dos locais do administrador (Fase 6a): buscam os
// dados na API (o mesmo endereço da tela antiga abaixo de /api/v1) e desenham
// a tela. Ponto de entrada do pedaço "administracao" do build.
//
// A senha temporária recém-criada mora só aqui, no estado da página (acima
// da busca: recarregar a lista não a perde) e some em qualquer navegação —
// ``location.key`` muda — ou ao sair da tela.
import { useEffect, useState } from 'react';
import { useLocation } from 'react-router';
import { Pagina, useDados } from '../cadastros/comum';
import { Locais, Pessoas } from './Administracao';
import type { DadosDasPessoas, DadosDosLocais, SenhaNova } from './tipos';

export function PaginaPessoas() {
  const local = useLocation();
  const q = useDados<DadosDasPessoas>('/admin/usuarios');
  const [senha, setSenha] = useState<SenhaNova | null>(null);
  useEffect(() => { setSenha(null); }, [local.key]);
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
  return <Pessoas dados={q.data} senha={senha} aoGerar={(s) => { setSenha(s); q.refetch(); }} />;
}

export function PaginaLocais() {
  return <Pagina<DadosDosLocais> api="/admin/contratos">{(d) => <Locais dados={d} />}</Pagina>;
}
