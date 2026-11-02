// As páginas das cobranças do cliente na equipe (Fase 5): buscam os dados
// na API (o mesmo endereço da tela antiga abaixo de /api/v1, com a mesma
// query string) e desenham a tela. Ponto de entrada do pedaço "cobrancas".
import { useLocation, useParams } from 'react-router';
import { Pagina } from '../cadastros/comum';
import { CobrancaDaEquipe, ListaDasCobrancas } from './Cobrancas';
import type { DadosDaCobranca, DadosDaListaOuAvisos } from './tipos';

export function PaginaLista() {
  const { search } = useLocation();
  return <Pagina<DadosDaListaOuAvisos> api={`/cobrancas/${search}`}>{(d) => <ListaDasCobrancas dados={d} />}</Pagina>;
}

export function PaginaCobranca() {
  const { id } = useParams();
  return <Pagina<DadosDaCobranca> api={`/cobrancas/${id}`}>{(d) => <CobrancaDaEquipe dados={d} />}</Pagina>;
}
