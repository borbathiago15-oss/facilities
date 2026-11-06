import { useQuery } from '@tanstack/react-query';
import { Component, type ComponentType, type ReactNode, Suspense, lazy } from 'react';
import { Route, Routes } from 'react-router';
import { buscarEu } from './api';
import { Casca } from './Casca';
import { NaoEncontrada } from './paginas/NaoEncontrada';

// Cada grupo de telas é um pedaço próprio do build, carregado só quando uma
// tela dele abre: o celular do posto não baixa a gestão. Os pedaços são
// arquivos de /static/app (a mesma CSP ``script-src 'self'``; o service
// worker guarda a cópia deles como a de todo /static/).
const campo = () => import('./campo/paginas');
const passagem = () => import('./passagem/paginas');
const cadastros = () => import('./cadastros/paginas');
const rotas = () => import('./rotas/paginas');
const chamados = () => import('./chamados/paginas');
const equipes = () => import('./equipes/paginas');
const materiais = () => import('./materiais/paginas');
const relatorios = () => import('./relatorios/paginas');
const paineis = () => import('./paineis/paginas');
const integracao = () => import('./integracao/paginas');
const portal = () => import('./portal/paginas');
const cobrancas = () => import('./cobrancas/paginas');
const admin = () => import('./paginas/admin/PaginaArmazenamento');
const conta = () => import('./conta/paginas');
const administracao = () => import('./administracao/paginas');

function pedaco<M extends Record<string, ComponentType<any>>, K extends keyof M>(carregar: () => Promise<M>, nome: K) {
  return lazy(() => carregar().then((m) => ({ default: m[nome] })));
}

const PaginaInicioCampo = pedaco(campo, 'PaginaInicioCampo');
const PaginaTurno = pedaco(campo, 'PaginaTurno');
const PaginaLerQr = pedaco(campo, 'PaginaLerQr');
const PaginaEquipeDoCampo = pedaco(campo, 'PaginaEquipeDoCampo');
const PaginaMateriaisDoCampo = pedaco(campo, 'PaginaMateriaisDoCampo');
const PaginaVisitasDoCampo = pedaco(campo, 'PaginaVisitasDoCampo');
const PaginaVisitaDoCampo = pedaco(campo, 'PaginaVisitaDoCampo');
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
const ChamadosLista = pedaco(chamados, 'PaginaLista');
const ChamadosNovo = pedaco(chamados, 'PaginaNovo');
const ChamadosVer = pedaco(chamados, 'PaginaChamado');
const DemandasPainel = pedaco(chamados, 'PaginaDemandas');
const PreventivaLocal = pedaco(chamados, 'PaginaPreventiva');
const EquipeLocal = pedaco(equipes, 'PaginaEquipe');
const EquipeMes = pedaco(equipes, 'PaginaMes');
const VisitasLocal = pedaco(equipes, 'PaginaVisitas');
const MateriaisCatalogo = pedaco(materiais, 'PaginaCatalogo');
const MateriaisEstoque = pedaco(materiais, 'PaginaEstoque');
const MateriaisMes = pedaco(materiais, 'PaginaConsumoDoMes');
const MateriaisCusto = pedaco(materiais, 'PaginaCusto');
const MateriaisPedidos = pedaco(materiais, 'PaginaPedidos');
const RelatoriosInicio = pedaco(relatorios, 'PaginaInicio');
const RelatoriosCliente = pedaco(relatorios, 'PaginaCliente');
const PainelDosLocais = pedaco(paineis, 'PaginaPainel');
const IntegracaoChaves = pedaco(integracao, 'PaginaIntegracao');
const PortalInicio = pedaco(portal, 'PaginaInicio');
const PortalLocal = pedaco(portal, 'PaginaLocal');
const PortalChamado = pedaco(portal, 'PaginaChamado');
const PortalRelatorios = pedaco(portal, 'PaginaRelatorios');
const PortalRelatorio = pedaco(portal, 'PaginaRelatorio');
const PortalCobrancas = pedaco(portal, 'PaginaCobrancas');
const PortalCobranca = pedaco(portal, 'PaginaCobranca');
const CobrancasLista = pedaco(cobrancas, 'PaginaLista');
const CobrancasVer = pedaco(cobrancas, 'PaginaCobranca');
const PaginaArmazenamento = pedaco(admin, 'PaginaArmazenamento');
const ContaInicio = pedaco(conta, 'PaginaInicio');
const ContaAvisos = pedaco(conta, 'PaginaAvisos');
const ContaSeguranca = pedaco(conta, 'PaginaSeguranca');
const ContaTrocarSenha = pedaco(conta, 'PaginaTrocarSenha');
const AdminPessoas = pedaco(administracao, 'PaginaPessoas');
const AdminLocais = pedaco(administracao, 'PaginaLocais');

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
      <Route path="/app/equipe" element={<Carregar><PaginaEquipeDoCampo eu={eu.data} /></Carregar>} />
      <Route path="/app/materiais" element={<Carregar><PaginaMateriaisDoCampo eu={eu.data} /></Carregar>} />
      <Route path="/app/visitas" element={<Carregar><PaginaVisitasDoCampo eu={eu.data} /></Carregar>} />
      <Route path="/app/visitas/:id" element={<Carregar><PaginaVisitaDoCampo eu={eu.data} /></Carregar>} />
      <Route path="*" element={
        <Casca eu={eu.data}>
          <Carregar>
            <Routes>
              <Route path="/" element={<ContaInicio />} />
              <Route path="/avisos" element={<ContaAvisos />} />
              <Route path="/conta/seguranca" element={<ContaSeguranca />} />
              <Route path="/trocar-senha" element={<ContaTrocarSenha />} />
              <Route path="/admin/armazenamento" element={<PaginaArmazenamento />} />
              <Route path="/admin/usuarios" element={<AdminPessoas />} />
              <Route path="/admin/contratos" element={<AdminLocais />} />
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
              <Route path="/chamados" element={<ChamadosLista />} />
              <Route path="/chamados/novo" element={<ChamadosNovo />} />
              <Route path="/chamados/:id" element={<ChamadosVer />} />
              <Route path="/demandas" element={<DemandasPainel />} />
              <Route path="/preventiva/locais/:id" element={<PreventivaLocal />} />
              <Route path="/equipes/locais/:id" element={<EquipeLocal />} />
              <Route path="/equipes/locais/:id/mes" element={<EquipeMes />} />
              <Route path="/visitas/locais/:id" element={<VisitasLocal />} />
              <Route path="/materiais" element={<MateriaisCatalogo />} />
              <Route path="/materiais/custo" element={<MateriaisCusto />} />
              <Route path="/materiais/pedidos" element={<MateriaisPedidos />} />
              <Route path="/materiais/locais/:id" element={<MateriaisEstoque />} />
              <Route path="/materiais/locais/:id/mes" element={<MateriaisMes />} />
              <Route path="/relatorios" element={<RelatoriosInicio />} />
              <Route path="/relatorios/cliente/:id/:mes" element={<RelatoriosCliente />} />
              <Route path="/painel" element={<PainelDosLocais />} />
              <Route path="/admin/integracao" element={<IntegracaoChaves />} />
              <Route path="/cliente" element={<PortalInicio />} />
              <Route path="/cliente/locais/:id" element={<PortalLocal />} />
              <Route path="/cliente/chamados/:id" element={<PortalChamado />} />
              <Route path="/cliente/relatorios" element={<PortalRelatorios />} />
              <Route path="/cliente/relatorios/:id/:mes" element={<PortalRelatorio />} />
              <Route path="/cliente/cobrancas" element={<PortalCobrancas />} />
              <Route path="/cliente/cobrancas/:id" element={<PortalCobranca />} />
              <Route path="/cobrancas" element={<CobrancasLista />} />
              <Route path="/cobrancas/:id" element={<CobrancasVer />} />
              <Route path="*" element={<NaoEncontrada inicio={eu.data.links.inicio} />} />
            </Routes>
          </Carregar>
        </Casca>
      } />
    </Routes>
  );
}
