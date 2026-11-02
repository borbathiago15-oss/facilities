// As páginas do portal do cliente (Fase 5): cada uma busca os dados na API
// (o mesmo endereço da tela antiga abaixo de /api/v1, com a mesma query
// string) e desenha a tela. Este arquivo é o ponto de entrada do pedaço
// "portal" do build (carregado só quando uma destas telas abre).
import { useLocation, useParams } from 'react-router';
import { Pagina } from '../cadastros/comum';
import {
  ChamadoDoPortal, CobrancaDoPortal, CobrancasDoPortal, InicioDoPortal, LocalDoPortal, RelatorioDoPortal,
  RelatoriosDoPortal,
} from './Portal';
import type {
  DadosDaCobranca, DadosDasCobrancas, DadosDoChamado, DadosDoInicio, DadosDoLocal, DadosDoRelatorio,
  DadosDosAvisos, DadosDosRelatorios,
} from './tipos';

export function PaginaInicio() {
  const { search } = useLocation();
  return <Pagina<DadosDoInicio> api={`/cliente/${search}`}>{(d) => <InicioDoPortal dados={d} />}</Pagina>;
}

export function PaginaLocal() {
  const { id } = useParams();
  const { search } = useLocation();
  return <Pagina<DadosDoLocal> api={`/cliente/locais/${id}${search}`}>{(d) => <LocalDoPortal dados={d} />}</Pagina>;
}

export function PaginaChamado() {
  const { id } = useParams();
  return <Pagina<DadosDoChamado> api={`/cliente/chamados/${id}`}>{(d) => <ChamadoDoPortal dados={d} />}</Pagina>;
}

export function PaginaRelatorios() {
  return <Pagina<DadosDosRelatorios> api="/cliente/relatorios">{(d) => <RelatoriosDoPortal dados={d} />}</Pagina>;
}

export function PaginaRelatorio() {
  const { id, mes } = useParams();
  return <Pagina<DadosDoRelatorio> api={`/cliente/relatorios/${id}/${encodeURIComponent(mes || '')}`}>{(d) => <RelatorioDoPortal dados={d} />}</Pagina>;
}

export function PaginaCobrancas() {
  const { search } = useLocation();
  return <Pagina<DadosDasCobrancas | DadosDosAvisos> api={`/cliente/cobrancas${search}`}>{(d) => <CobrancasDoPortal dados={d} />}</Pagina>;
}

export function PaginaCobranca() {
  const { id } = useParams();
  return <Pagina<DadosDaCobranca> api={`/cliente/cobrancas/${id}`}>{(d) => <CobrancaDoPortal dados={d} />}</Pagina>;
}
