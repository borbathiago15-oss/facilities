// A página do painel (Fase 4c): busca os dados na API (o mesmo endereço da
// tela antiga abaixo de /api/v1, com a mesma query string ``?de=&ate=``) e
// desenha a tela. Ponto de entrada do pedaço "paineis" do build.
import { useLocation } from 'react-router';
import { Pagina } from '../cadastros/comum';
import { Painel } from './Painel';
import type { DadosDoPainel } from './tipos';

export function PaginaPainel() {
  const { search } = useLocation();
  return <Pagina<DadosDoPainel> api={`/painel${search}`}>{(d) => <Painel dados={d} />}</Pagina>;
}
