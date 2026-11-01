// As páginas da rotina dos locais (Fase 3b): cada uma busca os dados na API
// (o mesmo endereço da tela antiga abaixo de /api/v1, com a mesma query
// string) e desenha a tela. Este arquivo é o ponto de entrada do pedaço
// "rotas" do build (carregado só quando uma destas telas abre).
import { useLocation, useParams } from 'react-router';
import { Pagina } from '../cadastros/comum';
import { Dia, Execucao, Feriados } from './Acompanhamento';
import { Biblioteca, Inicio, Local } from './Inicio';
import { Modelo } from './Modelo';
import { ImportarPlano } from './Plano';
import { Aplicar, RotaPronta } from './Prontas';
import { Rota } from './Rota';
import type {
  DadosDaBiblioteca, DadosDaExecucao, DadosDaRota, DadosDaRotaPronta, DadosDeAplicar, DadosDoDia,
  DadosDoInicio, DadosDoLocal, DadosDoModelo, DadosDoPlano, DadosDosFeriados,
} from './tipos';

export function PaginaInicio() {
  return <Pagina<DadosDoInicio> api="/rotas/inicio">{(d) => <Inicio dados={d} />}</Pagina>;
}

export function PaginaLocal() {
  const { id } = useParams();
  return <Pagina<DadosDoLocal> api={`/rotas/locais/${id}`}>{(d) => <Local dados={d} />}</Pagina>;
}

export function PaginaBiblioteca() {
  return <Pagina<DadosDaBiblioteca> api="/rotas/biblioteca">{(d) => <Biblioteca dados={d} />}</Pagina>;
}

export function PaginaRotaPronta() {
  const { id } = useParams();
  return <Pagina<DadosDaRotaPronta> api={`/rotas/biblioteca/rotas/${id || 'nova'}`}>{(d) => <RotaPronta dados={d} />}</Pagina>;
}

export function PaginaAplicar() {
  const { id } = useParams();
  const { search } = useLocation();
  return <Pagina<DadosDeAplicar> api={`/rotas/locais/${id}/rota-pronta${search}`}>{(d) => <Aplicar dados={d} />}</Pagina>;
}

export function PaginaImportarPlano() {
  const { id } = useParams();
  return <Pagina<DadosDoPlano> api={`/rotas/locais/${id}/importar-plano`}>{(d) => <ImportarPlano dados={d} />}</Pagina>;
}

export function PaginaModelo() {
  const { id } = useParams();
  return <Pagina<DadosDoModelo> api={`/rotas/modelos/${id}`}>{(d) => <Modelo dados={d} />}</Pagina>;
}

export function PaginaRota() {
  const { id } = useParams();
  return <Pagina<DadosDaRota> api={`/rotas/${id}`}>{(d) => <Rota dados={d} />}</Pagina>;
}

export function PaginaFeriados() {
  const { id } = useParams();
  const { search } = useLocation();
  return <Pagina<DadosDosFeriados> api={`/rotas/locais/${id}/feriados${search}`}>{(d) => <Feriados dados={d} />}</Pagina>;
}

export function PaginaDia() {
  const { id } = useParams();
  const { search } = useLocation();
  return <Pagina<DadosDoDia> api={`/rotas/locais/${id}/dia${search}`}>{(d) => <Dia dados={d} />}</Pagina>;
}

export function PaginaExecucao() {
  const { id } = useParams();
  return <Pagina<DadosDaExecucao> api={`/rotas/execucoes/${id}`}>{(d) => <Execucao dados={d} />}</Pagina>;
}
