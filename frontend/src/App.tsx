import { useQuery } from '@tanstack/react-query';
import { Component, type ComponentType, type ReactNode, Suspense, lazy } from 'react';
import { Route, Routes } from 'react-router';
import { buscarEu } from './api';
import { Casca } from './Casca';
import { Inicio } from './paginas/Inicio';
import { NaoEncontrada } from './paginas/NaoEncontrada';

// Cada grupo de telas é um pedaço próprio do build, carregado só quando uma
// tela dele abre: o celular do posto não baixa a gestão. Os pedaços são
// arquivos de /static/app (a mesma CSP ``script-src 'self'``; o service
// worker guarda a cópia deles como a de todo /static/).
const campo = () => import('./campo/paginas');
const passagem = () => import('./passagem/paginas');
const cadastros = () => import('./cadastros/paginas');
const rotas = () => import('./rotas/paginas');
const admin = () => import('./paginas/admin/PaginaArmazenamento');

function pedaco<M extends Record<string, ComponentType<any>>, K extends keyof M>(carregar: () => Promise<M>, nome: K) {
  return lazy(() => carregar().then((m) => ({ default: m[nome] })));
}

const PaginaInicioCampo = pedaco(campo, 'PaginaInicioCampo');
const PaginaTurno = pedaco(campo, 'PaginaTurno');
const PaginaLerQr = pedaco(campo, 'PaginaLerQr');
const PaginaPainel = pedaco(passagem, 'PaginaPainel');
const PaginaRelatorio = pedaco(passagem, 'PaginaRelatorio');
const PaginaConfiguracao = pedaco(passagem, 'PaginaConfiguracao');
const PaginaPassagem = pedaco(passagem, 'PaginaPassagem');
const PaginaVerTurno = pedaco(passagem, 'PaginaVerTurno');
const PaginaCadastros = pedaco(cadastros, 'PaginaInicio');
const PaginaEmpresas = pedaco(cadastros, 'PaginaEmpresas');
const PaginaClientes = pedaco(cadastros, 'PaginaClientes');
const PaginaEstados = pedaco(cadastros, 'PaginaEstados');
const PaginaTrilha = pedaco(cadastros, 'PaginaTrilha');
const PaginaLocal = pedaco(cadastros, 'PaginaLocal');
const PaginaTrilhaDoLocal = pedaco(cadastros, 'PaginaTrilhaDoLocal');
const PaginaCentrosClientes = pedaco(cadastros, 'PaginaCentrosClientes');
const PaginaCentrosCliente = pedaco(cadastros, 'PaginaCentrosCliente');
const PaginaCentro = pedaco(cadastros, 'PaginaCentro');
const PaginaRota = pedaco(cadastros, 'PaginaRota');
const PaginaNovoContrato = pedaco(cadastros, 'PaginaNovoContrato');
const PaginaNovoLocal = pedaco(cadastros, 'PaginaNovoLocal');
const PaginaEstrutura = pedaco(cadastros, 'PaginaEstrutura');
const PaginaEquipe = pedaco(cadastros, 'PaginaEquipe');
const PaginaConvites = pedaco(cadastros, 'PaginaConvites');
const RotasInicio = pedaco(rotas, 'PaginaInicio');
const RotasLocal = pedaco(rotas, 'PaginaLocal');
const RotasBiblioteca = pedaco(rotas, 'PaginaBiblioteca');
const RotasRotaPronta = pedaco(rotas, 'PaginaRotaPronta');
const RotasAplicar = pedaco(rotas, 'PaginaAplicar');
const RotasImportarPlano = pedaco(rotas, 'PaginaImportarPlano');
const RotasModelo = pedaco(rotas, 'PaginaModelo');
const RotasRota = pedaco(rotas, 'PaginaRota');
const RotasFeriados = pedaco(rotas, 'PaginaFeriados');
const RotasDia = pedaco(rotas, 'PaginaDia');
const RotasExecucao = pedaco(rotas, 'PaginaExecucao');
const PaginaArmazenamento = pedaco(admin, 'PaginaArmazenamento');

const CARREGANDO = <p className="p-4 text-muted" role="status">Carregando…</p>;

/** O pedaço da tela não chegou (sem sinal e sem cópia no aparelho, ou um
 * deploy no meio): diz o que houve em vez da tela em branco. */
class FalhaAoCarregar extends Component<{ children: ReactNode }, { falhou: boolean }> {
  state = { falhou: false };

  static getDerivedStateFromError() {
    return { falhou: true };
  }

  render() {
    if (!this.state.falhou) return this.props.children;
    return (
      <div className="p-4" role="alert">
        <p>Não foi possível abrir esta tela. Confira a internet e tente de novo.</p>
        <button className="btn btn-primary" type="button" onClick={() => window.location.reload()}>Tentar de novo</button>
      </div>
    );
  }
}

function Carregar({ children }: { children: ReactNode }) {
  return <FalhaAoCarregar><Suspense fallback={CARREGANDO}>{children}</Suspense></FalhaAoCarregar>;
}

export function App() {
  const eu = useQuery({ queryKey: ['eu'], queryFn: buscarEu, staleTime: 60_000 });
  if (eu.isPending) {
    return CARREGANDO;
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
      <Route path="/app" element={<Carregar><PaginaInicioCampo eu={eu.data} /></Carregar>} />
      <Route path="/app/turno" element={<Carregar><PaginaTurno eu={eu.data} /></Carregar>} />
      <Route path="/app/ler-qr" element={<Carregar><PaginaLerQr eu={eu.data} /></Carregar>} />
      <Route path="*" element={
        <Casca eu={eu.data}>
          <Carregar>
            <Routes>
              <Route path="/" element={<Inicio eu={eu.data} />} />
              <Route path="/admin/armazenamento" element={<PaginaArmazenamento />} />
              <Route path="/passagem-de-turno" element={<PaginaPainel />} />
              <Route path="/passagem-de-turno/relatorio-mensal" element={<PaginaRelatorio />} />
              <Route path="/passagem-de-turno/configuracao" element={<PaginaConfiguracao />} />
              <Route path="/passagem-de-turno/turno" element={<PaginaPassagem />} />
              <Route path="/passagem-de-turno/turno/:id" element={<PaginaVerTurno />} />
              <Route path="/cadastros" element={<PaginaCadastros />} />
              <Route path="/cadastros/empresas" element={<PaginaEmpresas />} />
              <Route path="/cadastros/clientes" element={<PaginaClientes />} />
              <Route path="/cadastros/estados" element={<PaginaEstados />} />
              <Route path="/cadastros/trilha" element={<PaginaTrilha />} />
              <Route path="/cadastros/locais/:id" element={<PaginaLocal />} />
              <Route path="/cadastros/locais/:id/trilha" element={<PaginaTrilhaDoLocal />} />
              <Route path="/clientes" element={<PaginaCentrosClientes />} />
              <Route path="/clientes/:id" element={<PaginaCentrosCliente />} />
              <Route path="/centros/:id" element={<PaginaCentro />} />
              <Route path="/centros/:id/rotas/:rota" element={<PaginaRota />} />
              <Route path="/novo-contrato" element={<PaginaNovoContrato />} />
              <Route path="/novo-contrato/cliente/:id/local" element={<PaginaNovoLocal />} />
              <Route path="/novo-contrato/:id/estrutura" element={<PaginaEstrutura />} />
              <Route path="/novo-contrato/:id/equipe" element={<PaginaEquipe />} />
              <Route path="/convites" element={<PaginaConvites />} />
              <Route path="/rotas" element={<RotasInicio />} />
              <Route path="/rotas/biblioteca" element={<RotasBiblioteca />} />
              <Route path="/rotas/biblioteca/rotas/nova" element={<RotasRotaPronta />} />
              <Route path="/rotas/biblioteca/rotas/:id" element={<RotasRotaPronta />} />
              <Route path="/rotas/locais/:id" element={<RotasLocal />} />
              <Route path="/rotas/locais/:id/rota-pronta" element={<RotasAplicar />} />
              <Route path="/rotas/locais/:id/importar-plano" element={<RotasImportarPlano />} />
              <Route path="/rotas/locais/:id/feriados" element={<RotasFeriados />} />
              <Route path="/rotas/locais/:id/dia" element={<RotasDia />} />
              <Route path="/rotas/modelos/:id" element={<RotasModelo />} />
              <Route path="/rotas/execucoes/:id" element={<RotasExecucao />} />
              <Route path="/rotas/:id" element={<RotasRota />} />
              <Route path="*" element={<NaoEncontrada inicio={eu.data.links.inicio} />} />
            </Routes>
          </Carregar>
        </Casca>
      } />
    </Routes>
  );
}
