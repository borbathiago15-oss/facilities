import { useQuery } from '@tanstack/react-query';
import { Route, Routes } from 'react-router';
import { buscarEu } from './api';
import { Casca } from './Casca';
import { PaginaInicioCampo } from './campo/PaginaInicioCampo';
import { Inicio } from './paginas/Inicio';
import { NaoEncontrada } from './paginas/NaoEncontrada';

export function App() {
  const eu = useQuery({ queryKey: ['eu'], queryFn: buscarEu, staleTime: 60_000 });
  if (eu.isPending) {
    return <p className="p-4 text-muted" role="status">Carregando…</p>;
  }
  if (eu.isError) {
    return (
      <div className="p-4" role="alert">
        <p>{eu.error.message}</p>
        <button className="btn btn-primary" type="button" onClick={() => eu.refetch()}>
          Tentar de novo
        </button>
      </div>
    );
  }
  return (
    <Routes>
      {/* O aplicativo de campo tem a moldura própria (topo curto, navegação embaixo). */}
      <Route path="/app" element={<PaginaInicioCampo eu={eu.data} />} />
      <Route path="*" element={
        <Casca eu={eu.data}>
          <Routes>
            <Route path="/" element={<Inicio eu={eu.data} />} />
            <Route path="*" element={<NaoEncontrada inicio={eu.data.links.inicio} />} />
          </Routes>
        </Casca>
      } />
    </Routes>
  );
}
