// As páginas da equipe e das visitas de supervisão do local (Fase 4b): cada
// uma busca os dados na API (o mesmo endereço da tela antiga abaixo de
// /api/v1, com a mesma query string) e desenha a tela. Este arquivo é o
// ponto de entrada do pedaço "equipes" do build (carregado só quando uma
// destas telas abre).
import { useLocation, useParams } from 'react-router';
import { Pagina } from '../cadastros/comum';
import { Equipe, Mes } from './Equipe';
import { Visitas } from './Visitas';
import type { DadosDaEquipe, DadosDasVisitas, DadosDoMes } from './tipos';

export function PaginaEquipe() {
  const { id } = useParams();
  return <Pagina<DadosDaEquipe> api={`/equipes/locais/${id}`}>{(d) => <Equipe dados={d} />}</Pagina>;
}

export function PaginaMes() {
  const { id } = useParams();
  const { search } = useLocation();
  return <Pagina<DadosDoMes> api={`/equipes/locais/${id}/mes${search}`}>{(d) => <Mes dados={d} />}</Pagina>;
}

export function PaginaVisitas() {
  const { id } = useParams();
  return <Pagina<DadosDasVisitas> api={`/visitas/locais/${id}`}>{(d) => <Visitas dados={d} />}</Pagina>;
}
