import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { Painel } from '../paineis/Painel';
import type { DadosDoPainel, LinhaDoPainel } from '../paineis/tipos';
import { InicioDosRelatorios, RelatorioDoCliente } from './Relatorios';
import type { CorpoDoRelatorio, DadosDoInicio, DadosDoRelatorio } from './tipos';

let chamadas: { url: string; init?: RequestInit }[] = [];
let respostas: Record<string, { status: number; corpo: unknown }> = {};
const PADRAO = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Recado salvo.' }], destino: '/novo/relatorios/cliente/3/2026-09' } };
beforeEach(() => {
  chamadas = [];
  respostas = {};
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    chamadas.push({ url: String(url), init });
    const r = respostas[String(url)] || PADRAO;
    return new Response(JSON.stringify(r.corpo), { status: r.status });
  });
});
afterEach(() => vi.restoreAllMocks());

function Onde() {
  const l = useLocation();
  return <span data-testid="onde">{l.pathname + l.search}</span>;
}

function abrir(no: React.ReactNode, url = '/') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes><Route path="*" element={<>{no}<Onde /></>} /></Routes>
    </MemoryRouter>);
}

const EU = {
  id: 1, nome: 'Admin', primeiro_nome: 'Admin', perfil: 'Administrador', papel: 'master', cliente: false,
  avisos_nao_lidos: 0, menu: [], csrf: 'x', versao: '1',
  links: { inicio: '/', avisos: '/avisos', trocar_senha: '/t', seguranca: '/s', sair: '/sair' } };

function inicio(extra: Partial<DadosDoInicio> = {}): DadosDoInicio {
  return {
    mes: '2026-09', nome_do_mes: 'Setembro de 2026',
    locais: [
      { id: 3, nome: 'CD 1', cliente: 'Grupo GL', liberado: true, liberado_em: '02/10 09:15', url: '/novo/relatorios/cliente/3/2026-09' },
      { id: 4, nome: 'CD 2', cliente: 'Sem cliente', liberado: false, liberado_em: null, url: '/novo/relatorios/cliente/4/2026-09' }],
    links: { anterior: '/novo/relatorios/?mes=2026-08', seguinte: '/novo/relatorios/?mes=2026-10' }, ...extra };
}

function corpo(extra: Partial<CorpoDoRelatorio> = {}): CorpoDoRelatorio {
  return {
    nota: { texto: '85,3 · Boa', faixa: 'boa' }, variacao: '+2,5 ponto(s) sobre o mês anterior',
    indicadores: [
      { chave: 'aderencia', rotulo: 'Aderência à rota', pct: '50,0%', base: '1 de 2' },
      { chave: 'visitas', rotulo: 'Visitas conformes', pct: '—', base: 'sem movimento' }],
    rotinas: [{ ambiente: 'Banheiro', previstas: 2, no_prazo: 1, com_atraso: 0, nao_feitas: 1, pct: '50,0%' }],
    chamados: { abertos: 1, resolvidos: 1, pct_no_prazo: '100,0%', tempo_medio: '24,0 h', pendentes_no_fim: 0,
      lista: [{ numero: 'CH-1', titulo: 'Lâmpada', categoria: 'Elétrica', aberto_em: '10/09 05:00', resolvido_em: '—', situacao: 'Aberto' }],
      lista_cortada: true },
    ncs: { total: 1, corrigidas: 0, itens: [['Piso limpo?', 1]] },
    ocorrencias: { total: 2, resolvidas: 1, pct_no_prazo: '—', tempo_medio: '35 min' },
    visitas: { programadas: 4, feitas: 3, conformes: 2 },
    cobrancas: { abertas: 1, respondidas: 1, no_prazo: 1, encerradas: 0 },
    elogios: { total: 2, media: '4,5', comentarios: [{ texto: 'Muito limpo', nota: 5, estrelas: 'estrelas', onde: 'Hall · Porta', quando: '12/09' }] },
    fotos: [{ ref: 'chamado:9', legenda: 'CH-1 · Lâmpada · depois', url: '/chamados/anexos/9' }],
    ...extra };
}

function relatorio(extra: Partial<DadosDoRelatorio> = {}): DadosDoRelatorio {
  return {
    local: { id: 3, nome: 'CD 1' }, cliente: 'Grupo GL', mes: '2026-09', nome_do_mes: 'Setembro de 2026',
    liberado_em: null, recado: '', pode_gerir: true, mes_fechado: true, mudou: [], corpo: corpo(),
    escolha: { todas: [
      { ref: 'chamado:9', legenda: 'CH-1 · Lâmpada · depois', url: '/chamados/anexos/9', escolhida: true },
      { ref: 'execucao:5', legenda: 'Banheiro · Pia', url: '/rotas/fotos/5', escolhida: false }], automatica: true, fotos_max: 12 },
    links: { inicio: '/novo/relatorios/?mes=2026-09', pdf: '/relatorios/cliente/3/2026-09/arquivo.pdf', xlsx: '/relatorios/cliente/3/2026-09/arquivo.xlsx' },
    ...extra };
}

describe('o início dos relatórios', () => {
  it('mostra um por local, liberado ou não, e navega pelos meses', async () => {
    abrir(<InicioDosRelatorios dados={inicio()} />);
    expect(screen.getByText('Setembro de 2026')).toBeInTheDocument();
    expect(screen.getByText('Liberado')).toHaveClass('text-bg-success');
    expect(screen.getByText('Não liberado')).toHaveClass('text-bg-light');
    expect(screen.getByText('em 02/10 09:15')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /CD 2/ })).toHaveAttribute('href', '/relatorios/cliente/4/2026-09');
    await userEvent.click(screen.getByRole('link', { name: 'Mês anterior' }));
    expect(screen.getByTestId('onde')).toHaveTextContent('/relatorios/?mes=2026-08');
  });

  it('sem local na carteira', () => {
    abrir(<InicioDosRelatorios dados={inicio({ locais: [] })} />);
    expect(screen.getByText('Nenhum local na sua carteira.')).toBeInTheDocument();
  });
});

describe('o relatório do mês', () => {
  it('mostra o corpo como a antiga, com o PDF e o Excel do servidor', () => {
    abrir(<RelatorioDoCliente dados={relatorio()} />);
    expect(screen.getByText('85,3 · Boa')).toHaveClass('fc-nota-boa');
    expect(screen.getByText('+2,5 ponto(s) sobre o mês anterior')).toBeInTheDocument();
    expect(screen.getByText('1 de 2')).toBeInTheDocument();
    expect(screen.getByText('sem movimento')).toBeInTheDocument();
    expect(screen.getByText('A lista mostra os primeiros chamados; o Excel traz os mesmos números.')).toBeInTheDocument();
    expect(screen.getByText(/Avisos pelo QR: 2 recebido\(s\), 1 resolvido\(s\), — no prazo, tempo médio 35 min\./)).toBeInTheDocument();
    expect(screen.getByText('(5 estrelas · Hall · Porta · 12/09)')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /PDF/ })).toHaveAttribute('href', '/relatorios/cliente/3/2026-09/arquivo.pdf');
    expect(screen.getByRole('link', { name: /Excel/ })).toHaveAttribute('href', '/relatorios/cliente/3/2026-09/arquivo.xlsx');
    expect(screen.getByRole('link', { name: 'Relatórios' })).toHaveAttribute('href', '/relatorios/?mes=2026-09');
    expect(screen.getByText('ainda não liberado ao cliente', { exact: false })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Liberar para o cliente/ })).toBeInTheDocument();
    expect(screen.queryByText('Recado da coordenação')).toBeNull();
    // A escolha: a amostra automática, sem o "Voltar para a amostra".
    expect([...document.querySelectorAll('input[name=foto]:checked')].map((i) => i.getAttribute('value'))).toEqual(['chamado:9']);
    expect(screen.queryByRole('button', { name: 'Voltar para a amostra automática' })).toBeNull();
  });

  it('liberado e com números novos: o aviso, liberar de novo e recolher', () => {
    abrir(<RelatorioDoCliente dados={relatorio({ liberado_em: '02/10/2026 09:15', recado: 'Reforço no 2º andar',
      mudou: [['Nota do mês', '85.3', '80.1'], ['Visitas feitas', '—', '3']],
      escolha: { ...relatorio().escolha!, automatica: false } })} />);
    expect(screen.getByText('liberado ao cliente em 02/10/2026 09:15')).toHaveClass('text-success');
    expect(screen.getByText('Os números mudaram depois da liberação.')).toBeInTheDocument();
    expect(screen.getByText('Nota do mês: 85.3 → 80.1')).toBeInTheDocument();
    expect(screen.getByText('Visitas feitas: — → 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Liberar a versão atual/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Recolher do portal' })).toBeInTheDocument();
    expect(screen.getByText('Recado da coordenação')).toBeInTheDocument();
    expect(screen.getByLabelText('Recado ao cliente (opcional)')).toHaveValue('Reforço no 2º andar');
    expect(screen.getByRole('button', { name: 'Voltar para a amostra automática' })).toBeInTheDocument();
  });

  it('liberado sem mudança: só o recolher; mês aberto: o aviso do dia 1º', () => {
    const { unmount } = abrir(<RelatorioDoCliente dados={relatorio({ liberado_em: '02/10/2026 09:15' })} />);
    expect(screen.queryByRole('button', { name: /Liberar/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'Recolher do portal' })).toBeInTheDocument();
    unmount();
    abrir(<RelatorioDoCliente dados={relatorio({ mes_fechado: false })} />);
    expect(screen.getByText('O mês ainda não acabou: a liberação abre no dia 1º do mês seguinte.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Liberar/ })).toBeNull();
  });

  it('quem só lê não recebe a gestão nem a escolha das fotos', () => {
    abrir(<RelatorioDoCliente dados={relatorio({ pode_gerir: false, escolha: null })} />);
    expect(screen.queryByText('Antes de liberar')).toBeNull();
    expect(screen.queryByText(/Escolher as fotos/)).toBeNull();
    expect(screen.getByText('Fotos do mês')).toBeInTheDocument();
  });

  it('sem nada no mês', () => {
    abrir(<RelatorioDoCliente dados={relatorio({ corpo: corpo({ nota: null, rotinas: [], fotos: [], elogios: { total: 0, media: '—', comentarios: [] },
      chamados: { ...corpo().chamados, lista: [], lista_cortada: false }, ncs: { total: 0, corrigidas: 0, itens: [] } }), escolha: { todas: [], automatica: true, fotos_max: 12 } })} />);
    expect(screen.getByText('sem movimento no mês')).toBeInTheDocument();
    expect(screen.getByText('Sem rotinas programadas no mês.')).toBeInTheDocument();
    expect(screen.getByText('Nenhuma avaliação pelo QR no mês.')).toBeInTheDocument();
    expect(screen.getByText('Sem fotos no mês.')).toBeInTheDocument();
    expect(screen.queryByText(/Escolher as fotos/)).toBeNull();
  });

  it('as ações vão ao mesmo caminho da antiga, com o formulário', async () => {
    abrir(<RelatorioDoCliente dados={relatorio()} />, '/relatorios/cliente/3/2026-09');
    await userEvent.type(screen.getByLabelText('Recado ao cliente (opcional)'), 'Oi');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar recado' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe('/api/v1/relatorios/cliente/3/2026-09/recado');
    expect((chamadas[0].init!.body as FormData).get('recado')).toBe('Oi');
    await userEvent.click(document.querySelector('input[value="execucao:5"]')!);
    await userEvent.click(screen.getByRole('button', { name: 'Salvar as fotos' }));
    await waitFor(() => expect(chamadas).toHaveLength(2));
    expect(chamadas[1].url).toBe('/api/v1/relatorios/cliente/3/2026-09/fotos');
    expect((chamadas[1].init!.body as FormData).getAll('foto')).toEqual(['chamado:9', 'execucao:5']);
    await userEvent.click(screen.getByRole('button', { name: /Liberar para o cliente/ }));
    await waitFor(() => expect(chamadas).toHaveLength(3));
    expect(chamadas[2].url).toBe('/api/v1/relatorios/cliente/3/2026-09/liberar');
  });
});

function linha(extra: Partial<LinhaDoPainel> = {}): LinhaDoPainel {
  return {
    local_id: 3, local: 'CD 1', nota: '85,3 · Boa', faixa: 'boa',
    indicadores: [{ pct: '50,0%', base: '1 de 2' }, null],
    elogios: { media: '4,5', total: 2 }, atrasadas: 2, atrasadas_url: '/novo/demandas/?local=3&situacao=atrasada', ...extra };
}

function painel(extra: Partial<DadosDoPainel> = {}): DadosDoPainel {
  return {
    de: '2026-10-04', ate: '2026-11-02', de_br: '04/10/2026', ate_br: '02/11/2026', faixa_critica: 70, faixa_boa: 85,
    indicadores: ['Aderência à rota', 'Visitas conformes'],
    resumo: { media: '85,3', faixas: [['Crítica', 0], ['Atenção', 0], ['Boa', 1]], sem_dado: 1 },
    linhas: [linha(), linha({ local_id: 4, local: 'CD 2', nota: null, faixa: null, elogios: null, atrasadas: 0, indicadores: [null, null] })],
    grupos: null, ...extra };
}

describe('o painel', () => {
  it('mostra as notas, os indicadores, os elogios e o atrasado como a antiga', async () => {
    abrir(<Painel dados={painel()} />, '/painel');
    expect(screen.getByText(/Abaixo de 70: crítica; de 70 a 84: atenção; 85 ou mais: boa\./)).toBeInTheDocument();
    expect(screen.getByText('85,3 · Boa')).toHaveClass('fc-nota-boa');
    expect(screen.getByText('sem dado')).toBeInTheDocument();
    expect(screen.getByText('Sem dado')).toBeInTheDocument();
    expect(screen.getByText('2 avaliação(ões)')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '2' })).toHaveAttribute('href', '/demandas/?local=3&situacao=atrasada');
    expect(screen.getByText('O período vai de 04/10/2026 a 02/11/2026.', { exact: false })).toBeInTheDocument();
    expect(document.getElementById('pde')).toHaveValue('2026-10-04');
    await userEvent.click(screen.getByRole('button', { name: 'Ver' }));
    expect(screen.getByTestId('onde')).toHaveTextContent('/painel?de=2026-10-04&ate=2026-11-02');
  });

  it('agrupado por cliente; sem local', () => {
    const { unmount } = abrir(<Painel dados={painel({ grupos: [{ cliente: 'Grupo GL', media: '85,3', linhas: [linha()] }] })} />);
    expect(screen.getByRole('heading', { name: /Grupo GL/ })).toHaveAttribute('id', 'tit-g1');
    expect(screen.getByText('· nota média 85,3')).toBeInTheDocument();
    expect(screen.queryByText('CD 2')).toBeNull();
    unmount();
    abrir(<Painel dados={painel({ linhas: [], resumo: { media: '—', faixas: [['Crítica', 0]], sem_dado: 0 } })} />);
    expect(screen.getByText('Nenhum local na sua carteira.')).toBeInTheDocument();
    expect(screen.queryByText('Sem dado')).toBeNull();
  });
});

describe('as telas abrem pelo seu pedaço do build', () => {
  it('o relatório e o painel carregam sob demanda, dentro da casca', async () => {
    respostas['/api/v1/eu'] = { status: 200, corpo: EU };
    respostas['/api/v1/relatorios/cliente/3/2026-09'] = { status: 200, corpo: relatorio() };
    respostas['/api/v1/painel'] = { status: 200, corpo: painel() };
    const { unmount } = render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/relatorios/cliente/3/2026-09']}><App /></MemoryRouter>
      </QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: 'CD 1' })).toBeInTheDocument();
    expect(document.querySelector('[data-tela-pronta="relatorio-cliente"]')).not.toBeNull();
    unmount();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/painel']}><App /></MemoryRouter>
      </QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: 'Painel' })).toBeInTheDocument();
    expect(document.querySelector('[data-tela-pronta="painel"]')).not.toBeNull();
  });
});
