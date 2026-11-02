// As páginas dos relatórios do cliente (Fase 4c): cada uma busca os dados na
// API (o mesmo endereço da tela antiga abaixo de /api/v1, com a mesma query
// string) e desenha a tela. Este arquivo é o ponto de entrada do pedaço
// "relatorios" do build (carregado só quando uma destas telas abre).
import { useLocation, useParams } from 'react-router';
import { Pagina } from '../cadastros/comum';
import { InicioDosRelatorios, RelatorioDoCliente } from './Relatorios';
import type { DadosDoInicio, DadosDoRelatorio } from './tipos';

export function PaginaInicio() {
  const { search } = useLocation();
  return <Pagina<DadosDoInicio> api={`/relatorios/${search}`}>{(d) => <InicioDosRelatorios dados={d} />}</Pagina>;
}

export function PaginaCliente() {
  const { id, mes } = useParams();
  return <Pagina<DadosDoRelatorio> api={`/relatorios/cliente/${id}/${encodeURIComponent(mes || '')}`}>{(d) => <RelatorioDoCliente dados={d} />}</Pagina>;
}
