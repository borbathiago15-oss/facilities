// As páginas da Fase 1d do aplicativo de campo: cada uma busca os dados em
// /api/v1/campo/... (com a mesma query string da antiga) e desenha a tela na
// moldura do campo. Entram no pedaço "campo" do build (campo/paginas.ts).
import { useLocation, useParams } from 'react-router';
import type { Eu } from '../../api';
import { PaginaDoCampo } from './comum';
import { Equipe } from './Equipe';
import { Materiais } from './Materiais';
import type { DadosDaEquipe, DadosDaVisita, DadosDasVisitas, DadosDosMateriais } from './tipos';
import { ListaDeVisitas, Visita } from './Visitas';

export function PaginaEquipeDoCampo({ eu }: { eu: Eu }) {
  const { search } = useLocation();
  return (
    <PaginaDoCampo<DadosDaEquipe> eu={eu} api={`/campo/equipe${search}`} titulo="Equipe de hoje">
      {(d) => <Equipe dados={d} />}
    </PaginaDoCampo>
  );
}

export function PaginaMateriaisDoCampo({ eu }: { eu: Eu }) {
  return (
    <PaginaDoCampo<DadosDosMateriais> eu={eu} api="/campo/materiais" titulo="Material">
      {(d) => <Materiais dados={d} />}
    </PaginaDoCampo>
  );
}

export function PaginaVisitasDoCampo({ eu }: { eu: Eu }) {
  return (
    <PaginaDoCampo<DadosDasVisitas> eu={eu} api="/campo/visitas" titulo="Visitas de supervisão">
      {(d) => <ListaDeVisitas dados={d} />}
    </PaginaDoCampo>
  );
}

export function PaginaVisitaDoCampo({ eu }: { eu: Eu }) {
  const { id } = useParams();
  return (
    <PaginaDoCampo<DadosDaVisita> eu={eu} api={`/campo/visitas/${id}`} titulo="Visita de supervisão">
      {(d) => <Visita dados={d} />}
    </PaginaDoCampo>
  );
}
