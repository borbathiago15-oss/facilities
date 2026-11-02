// As páginas dos chamados, das demandas e da preventiva (Fase 4a): cada uma
// busca os dados na API (o mesmo endereço da tela antiga abaixo de /api/v1,
// com a mesma query string) e desenha a tela. Este arquivo é o ponto de
// entrada do pedaço "chamados" do build (carregado só quando uma destas
// telas abre).
import { useLocation, useParams } from 'react-router';
import { Pagina } from '../cadastros/comum';
import { Lista, Novo, Ver } from './Chamados';
import { Demandas } from './Demandas';
import { Preventiva } from './Preventiva';
import type { DadosDaLista, DadosDaPreventiva, DadosDasDemandas, DadosDoChamado, DadosDoNovo } from './tipos';

export function PaginaLista() {
  const { search } = useLocation();
  return <Pagina<DadosDaLista> api={`/chamados/${search}`}>{(d) => <Lista dados={d} />}</Pagina>;
}

export function PaginaNovo() {
  const { search } = useLocation();
  return <Pagina<DadosDoNovo> api={`/chamados/novo${search}`}>{(d) => <Novo dados={d} />}</Pagina>;
}

export function PaginaChamado() {
  const { id } = useParams();
  return <Pagina<DadosDoChamado> api={`/chamados/${id}`}>{(d) => <Ver dados={d} />}</Pagina>;
}

export function PaginaDemandas() {
  const { search } = useLocation();
  return <Pagina<DadosDasDemandas> api={`/demandas/${search}`}>{(d) => <Demandas dados={d} />}</Pagina>;
}

export function PaginaPreventiva() {
  const { id } = useParams();
  return <Pagina<DadosDaPreventiva> api={`/preventiva/locais/${id}`}>{(d) => <Preventiva dados={d} />}</Pagina>;
}
