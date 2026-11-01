import { useQuery } from '@tanstack/react-query';
import { Route, Routes } from 'react-router';
import { buscarEu } from './api';
import { Casca } from './Casca';
import { PaginaInicioCampo } from './campo/PaginaInicioCampo';
import { PaginaLerQr } from './campo/PaginaLerQr';
import { PaginaTurno } from './campo/turno/PaginaTurno';
import { PaginaConfiguracao } from './passagem/PaginaConfiguracao';
import { PaginaPainel } from './passagem/PaginaPainel';
import { PaginaPassagem } from './passagem/PaginaPassagem';
import { PaginaRelatorio } from './passagem/PaginaRelatorio';
import { PaginaVerTurno } from './passagem/PaginaVerTurno';
import { PaginaArmazenamento } from './paginas/admin/PaginaArmazenamento';
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
      <Route path="/app/turno" element={<PaginaTurno eu={eu.data} />} />
      <Route path="/app/ler-qr" element={<PaginaLerQr eu={eu.data} />} />
      <Route path="*" element={
        <Casca eu={eu.data}>
          <Routes>
            <Route path="/" element={<Inicio eu={eu.data} />} />
            <Route path="/admin/armazenamento" element={<PaginaArmazenamento />} />
            <Route path="/passagem-de-turno" element={<PaginaPainel />} />
            <Route path="/passagem-de-turno/relatorio-mensal" element={<PaginaRelatorio />} />
            <Route path="/passagem-de-turno/configuracao" element={<PaginaConfiguracao />} />
            <Route path="/passagem-de-turno/turno" element={<PaginaPassagem />} />
            <Route path="/passagem-de-turno/turno/:id" element={<PaginaVerTurno />} />
            <Route path="*" element={<NaoEncontrada inicio={eu.data.links.inicio} />} />
          </Routes>
        </Casca>
      } />
    </Routes>
  );
}
