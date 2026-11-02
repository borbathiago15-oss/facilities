import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import type { CorpoDoRelatorio } from '../relatorios/tipos';
import {
  ChamadoDoPortal, CobrancaDoPortal, CobrancasDoPortal, InicioDoPortal, LocalDoPortal, RelatorioDoPortal,
  RelatoriosDoPortal,
} from './Portal';
import type {
  DadosDaCobranca, DadosDasCobrancas, DadosDoChamado, DadosDoInicio, DadosDoLocal, DadosDosAvisos,
} from './tipos';

let chamadas: { url: string; init?: RequestInit }[] = [];
let respostas: Record<string, { status: number; corpo: unknown }> = {};
const PADRAO = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Cobrança CB-00009 enviada à coordenação do contrato.' }], destino: '/novo/cliente/cobrancas/9' } };
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

const SELO = { classe: 'text-bg-primary', texto: 'Respondida — confirme ou reabra' };
const COB = { id: 9, numero: 'CB-00009', titulo: 'Vidros', local: 'CD 1', prazo: '05/11/2026', situacao: SELO, url: '/novo/cliente/cobrancas/9' };

function inicio(extra: Partial<DadosDoInicio> = {}): DadosDoInicio {
  return {
    de: '2026-10-04', ate: '2026-11-02', de_br: '04/10/2026', ate_br: '02/11/2026', cobrancas: [COB],
    linhas: [{ id: 3, nome: 'CD 1', nota: { texto: '85,3 · Boa', faixa: 'boa' }, abertos: 2, url: '/novo/cliente/locais/3?de=2026-10-04&ate=2026-11-02' },
      { id: 4, nome: 'CD 2', nota: null, abertos: 0, url: '/novo/cliente/locais/4?de=2026-10-04&ate=2026-11-02' }],
    links: { cobrancas: '/novo/cliente/cobrancas' }, ...extra };
}

function local(extra: Partial<DadosDoLocal> = {}): DadosDoLocal {
  return {
    local: { id: 3, nome: 'CD 1' }, de: '2026-10-04', ate: '2026-11-02', nota: { texto: '85,3 · Boa', faixa: 'boa' },
    indicadores: [{ chave: 'aderencia', rotulo: 'Aderência à rota', pct: '50,0%', base: '1 de 2' },
      { chave: 'visitas', rotulo: 'Visitas conformes', pct: '—', base: 'sem movimento' }],
    chamados: [{ id: 7, numero: 'CH-00007', titulo: 'Lâmpada', situacao: 'Atrasado', atrasado: true, fotos: 2, quando: 'prazo 01/11 10:00', url: '/novo/cliente/chamados/7' }],
    execucoes: [{ id: 5, onde: 'Banheiro · Pia', detalhe: 'Checklist · 01/11/2026 08:00 · Encarregado / ASG', nao_conformes: 1,
      fotos: [{ id: 11, url: '/cliente/fotos/checklist/11', alt: 'Foto depois do checklist' }] }],
    visitas: [], documentos: [{ id: 2, modelo: 'Checklist', nome: 'POP.pdf', url: '/cliente/documentos/2' }],
    links: { inicio: '/novo/cliente/', cobrar: '/novo/cliente/cobrancas?local=3' }, ...extra };
}

describe('seus locais', () => {
  it('mostra as cobranças em andamento, a nota e o período', async () => {
    abrir(<InicioDoPortal dados={inicio()} />, '/cliente/');
    expect(screen.getByRole('heading', { name: 'Seus locais' })).toBeInTheDocument();
    expect(screen.getByText('Respondida — confirme ou reabra')).toHaveClass('text-bg-primary');
    expect(screen.getByText('85,3 · Boa')).toHaveClass('fc-nota-boa');
    expect(screen.getByText('sem dado no período')).toBeInTheDocument();
    expect(screen.getByText('2 chamado(s) em aberto')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Abrir uma cobrança/ })).toHaveAttribute('href', '/cliente/cobrancas');
    expect(screen.getByText(/Período de 04\/10\/2026 a 02\/11\/2026\./)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Ver o período' }));
    expect(screen.getByTestId('onde')).toHaveTextContent('/cliente/?de=2026-10-04&ate=2026-11-02');
  });

  it('sem local nem cobrança', () => {
    abrir(<InicioDoPortal dados={inicio({ linhas: [], cobrancas: [] })} />);
    expect(screen.getByText('Nenhum local ligado à sua conta ainda. Fale com o seu gerente na Trino.')).toBeInTheDocument();
    expect(screen.queryByText('Cobranças em andamento')).toBeNull();
  });
});

describe('o local', () => {
  it('mostra os indicadores, os chamados, os checklists e os POP/FIT do servidor', () => {
    abrir(<LocalDoPortal dados={local()} />, '/cliente/locais/3');
    expect(screen.getByText('50,0%')).toBeInTheDocument();
    expect(screen.getByText('sem movimento')).toBeInTheDocument();
    expect(screen.getByText('Atrasado')).toHaveClass('fc-dem-atrasada');
    expect(screen.getByText('2 foto(s)')).toBeInTheDocument();
    expect(screen.getByText('1 item(ns) não conforme(s)')).toBeInTheDocument();
    expect(screen.getByAltText('Foto depois do checklist')).toHaveAttribute('src', '/cliente/fotos/checklist/11');
    expect(screen.getByRole('link', { name: /POP\.pdf/ })).toHaveAttribute('href', '/cliente/documentos/2');
    expect(screen.getByText('Nenhuma visita de supervisão feita nos últimos 30 dias.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Cobrar algo deste local/ })).toHaveAttribute('href', '/cliente/cobrancas?local=3');
    expect(screen.getByRole('link', { name: 'Seus locais' })).toHaveAttribute('href', '/cliente/');
  });

  it('sem nada: os vazios e sem a seção dos POP/FIT', () => {
    abrir(<LocalDoPortal dados={local({ nota: null, chamados: [], execucoes: [], documentos: [] })} />);
    expect(screen.getByText('Nenhum chamado neste período.')).toBeInTheDocument();
    expect(screen.getByText('Nenhum checklist feito nos últimos 30 dias.')).toBeInTheDocument();
    expect(screen.queryByText('Procedimentos (POP/FIT)')).toBeNull();
  });
});

describe('o chamado', () => {
  const ch: DadosDoChamado = {
    id: 7, numero: 'CH-00007', titulo: 'Lâmpada', situacao: 'Aguardando peça', categoria: 'Elétrica', onde: null,
    aberto_em: '01/11/2026 08:00', prazo: '03/11/2026 08:00', aguardando: true, resolvido_em: null, solucao: null,
    fotos: [{ id: 4, url: '/cliente/fotos/chamado/4', alt: 'Foto do problema', legenda: 'Antes' }],
    local: { id: 3, nome: 'CD 1' }, links: { inicio: '/novo/cliente/', local: '/novo/cliente/locais/3', cobrar: '/novo/cliente/cobrancas?local=3' } };

  it('mostra só o que a antiga mostra', () => {
    abrir(<ChamadoDoPortal dados={ch} />);
    expect(screen.getByRole('heading', { name: 'CH-00007 · Lâmpada' })).toBeInTheDocument();
    expect(screen.getByText('(parado enquanto aguarda peça ou terceiro)')).toBeInTheDocument();
    expect(screen.queryByText('Onde')).toBeNull();
    expect(screen.queryByText('O que foi feito')).toBeNull();
    expect(screen.getByAltText('Foto do problema')).toHaveAttribute('src', '/cliente/fotos/chamado/4');
    expect(screen.getByRole('link', { name: 'CD 1' })).toHaveAttribute('href', '/cliente/locais/3');
    expect(screen.getByRole('link', { name: /Cobrar este assunto/ })).toHaveAttribute('href', '/cliente/cobrancas?local=3');
  });
});

describe('os relatórios', () => {
  it('a lista abre na tela nova e o PDF fica no servidor', () => {
    abrir(<RelatoriosDoPortal dados={{ relatorios: [{ id: 1, mes: 'Setembro de 2026', local: 'CD 1', url: '/novo/cliente/relatorios/3/2026-09', pdf: '/cliente/relatorios/3/2026-09/arquivo.pdf' }] }} />);
    expect(screen.getByRole('link', { name: 'Abrir' })).toHaveAttribute('href', '/cliente/relatorios/3/2026-09');
    expect(screen.getByRole('link', { name: /PDF/ })).toHaveAttribute('href', '/cliente/relatorios/3/2026-09/arquivo.pdf');
  });

  it('sem relatório liberado', () => {
    abrir(<RelatoriosDoPortal dados={{ relatorios: [] }} />);
    expect(screen.getByText('Nenhum relatório liberado ainda. Eles chegam no começo de cada mês.')).toBeInTheDocument();
  });

  it('o relatório: o corpo e o recado, sem nada da gestão', () => {
    const corpo: CorpoDoRelatorio = {
      nota: null, variacao: 'sem comparação com o mês anterior', indicadores: [], rotinas: [],
      chamados: { abertos: 0, resolvidos: 0, pct_no_prazo: '—', tempo_medio: '—', pendentes_no_fim: 0, lista: [], lista_cortada: false },
      ncs: { total: 0, corrigidas: 0, itens: [] }, ocorrencias: { total: 0, resolvidas: 0, pct_no_prazo: '—', tempo_medio: '—' },
      visitas: { programadas: 0, feitas: 0, conformes: 0 }, cobrancas: { abertas: 0, respondidas: 0, no_prazo: 0, encerradas: 0 },
      elogios: null, fotos: [] };
    abrir(<RelatorioDoPortal dados={{ local: { id: 3, nome: 'CD 1' }, mes: '2026-09', nome_do_mes: 'Setembro de 2026', recado: 'Oi, GL',
      corpo, links: { inicio: '/novo/cliente/relatorios', pdf: '/cliente/relatorios/3/2026-09/arquivo.pdf', xlsx: '/cliente/relatorios/3/2026-09/arquivo.xlsx' } }} />);
    expect(screen.getByText('Recado da coordenação')).toBeInTheDocument();
    expect(screen.getByText('Oi, GL')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Baixar PDF/ })).toHaveAttribute('href', '/cliente/relatorios/3/2026-09/arquivo.pdf');
    expect(screen.queryByText('Antes de liberar')).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });
});

function cobrancas(extra: Partial<DadosDasCobrancas> = {}): DadosDasCobrancas {
  return {
    aba: 'cobrancas', locais: [{ id: 3, nome: 'CD 1' }, { id: 4, nome: 'CD 2' }], cobrancas: [COB],
    minimo: '2026-11-04', minimo_br: '04/11/2026', local_escolhido: null, abrir_aberto: false,
    abas: { cobrancas: '/novo/cliente/cobrancas', qr: '/novo/cliente/cobrancas?aba=qr' }, ...extra };
}

describe('as cobranças', () => {
  it('abre uma cobrança pelo mesmo caminho da antiga e vai à cobrança nova', async () => {
    abrir(<CobrancasDoPortal dados={cobrancas({ local_escolhido: 4, abrir_aberto: true })} />, '/cliente/cobrancas?local=4');
    expect(document.querySelector('details')).toHaveAttribute('open');
    expect(screen.getByLabelText('Local')).toHaveValue('4');
    expect(screen.getByLabelText('Quero a resposta até')).toHaveAttribute('min', '2026-11-04');
    expect(screen.getByText('A partir de 04/11/2026.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Cobranças' })).toHaveClass('active');
    await userEvent.type(screen.getByLabelText('Quero a resposta até'), '2026-11-10');
    await userEvent.type(screen.getByLabelText('Assunto'), 'Vidros');
    await userEvent.type(screen.getByLabelText('O que precisa ser feito'), 'Limpar');
    await userEvent.click(screen.getByRole('button', { name: 'Enviar à coordenação' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe('/api/v1/cliente/cobrancas');
    const corpo = chamadas[0].init!.body as FormData;
    expect([corpo.get('client_id'), corpo.get('prazo'), corpo.get('titulo'), corpo.get('texto')]).toEqual(['4', '2026-11-10', 'Vidros', 'Limpar']);
    await waitFor(() => expect(screen.getByTestId('onde')).toHaveTextContent('/cliente/cobrancas/9'));
  });

  it('um local só: já escolhido; dois sem escolha: "Escolha"; sem cobrança', () => {
    const { unmount } = abrir(<CobrancasDoPortal dados={cobrancas({ locais: [{ id: 3, nome: 'CD 1' }] })} />);
    expect(screen.getByLabelText('Local')).toHaveValue('3');
    expect(screen.queryByText('Escolha')).toBeNull();
    expect(document.querySelector('details')).not.toHaveAttribute('open');
    unmount();
    abrir(<CobrancasDoPortal dados={cobrancas({ cobrancas: [], abrir_aberto: true })} />);
    expect(screen.getByLabelText('Local')).toHaveValue('');
    expect(screen.getByText('Nenhuma cobrança ainda.')).toBeInTheDocument();
  });

  it('a recusa do servidor volta à mesma tela (com o recado no estado da navegação)', async () => {
    respostas['/api/v1/cliente/cobrancas'] = { status: 400, corpo: { recados: [{ tipo: 'danger', texto: 'Escolha um dos seus locais.' }], destino: '/novo/cliente/cobrancas', error: 'Escolha um dos seus locais.' } };
    abrir(<CobrancasDoPortal dados={cobrancas({ abrir_aberto: true, local_escolhido: 3 })} />, '/cliente/cobrancas');
    await userEvent.type(screen.getByLabelText('Quero a resposta até'), '2026-11-10');
    await userEvent.type(screen.getByLabelText('Assunto'), 'x');
    await userEvent.type(screen.getByLabelText('O que precisa ser feito'), 'x');
    await userEvent.click(screen.getByRole('button', { name: 'Enviar à coordenação' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    await waitFor(() => expect(screen.getByTestId('onde')).toHaveTextContent('/cliente/cobrancas'));
  });

  it('a aba dos avisos pelo QR, com os filtros', async () => {
    const avisos: DadosDosAvisos = {
      aba: 'qr', situacao: '', abas: cobrancas().abas,
      filtros: [['Todos', '/novo/cliente/cobrancas?aba=qr', true], ['Resolvida', '/novo/cliente/cobrancas?aba=qr&situacao=resolvida', false]],
      avisos: [{ id: 1, status: 'resolvida', situacao: 'Resolvida', titulo: 'Local sujo', onde: 'CD 1 · Banheiro · Pia', texto: 'Pia entupida', quando: '01/11 08:00', resolvido: '01/11 09:00', resolucao: 'Desentupida' }] };
    abrir(<CobrancasDoPortal dados={avisos} />, '/cliente/cobrancas?aba=qr');
    expect(screen.getByRole('link', { name: /Avisos pelo QR/ })).toHaveClass('active');
    expect(screen.getByText('Resolvida', { selector: '.badge' })).toHaveClass('fc-ocor-resolvida');
    expect(screen.getByText('CD 1 · Banheiro · Pia · "Pia entupida"')).toBeInTheDocument();
    expect(screen.getByText(/resolvido 01\/11 09:00: Desentupida/)).toBeInTheDocument();
    expect(screen.queryByText(/tarefa de/)).toBeNull();
    expect(screen.getByRole('link', { name: 'Todos' })).toHaveClass('btn-primary');
    await userEvent.click(screen.getByRole('link', { name: 'Resolvida' }));
    expect(screen.getByTestId('onde')).toHaveTextContent('/cliente/cobrancas?aba=qr&situacao=resolvida');
  });
});

function cobranca(extra: Partial<DadosDaCobranca> = {}): DadosDaCobranca {
  return {
    id: 9, numero: 'CB-00009', titulo: 'Vidros', local: 'CD 1', situacao: SELO, prazo: '05/11/2026',
    respondida: true, aberta: false, minimo: '2026-11-04', minimo_br: '04/11/2026',
    eventos: [{ id: 1, quando: '01/11/2026 08:00', autor: 'Cliente GL', tipo: 'Cobrança aberta', prazo: '05/11/2026', texto: 'Limpar' },
      { id: 2, quando: '01/11/2026 10:00', autor: 'Coordenação', tipo: 'Resposta da coordenação', prazo: null, texto: 'Limpos.' }],
    links: { cobrancas: '/novo/cliente/cobrancas' }, ...extra };
}

describe('a cobrança', () => {
  it('respondida: confirmar e reabrir vão ao mesmo caminho da antiga', async () => {
    abrir(<CobrancaDoPortal dados={cobranca()} />, '/cliente/cobrancas/9');
    expect(screen.getByText('01/11/2026 10:00 · Coordenação ·', { exact: false })).toBeInTheDocument();
    expect(screen.getByText(/· prazo 05\/11\/2026/, { selector: 'div' })).toBeInTheDocument();
    expect(screen.getByLabelText('Novo prazo (a partir de 04/11/2026)')).toHaveAttribute('min', '2026-11-04');
    await userEvent.type(screen.getByLabelText('Comentário (opcional)'), 'Agora sim');
    await userEvent.click(screen.getByRole('button', { name: 'Confirmar e encerrar' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe('/api/v1/cliente/cobrancas/9/confirmar');
    expect((chamadas[0].init!.body as FormData).get('texto')).toBe('Agora sim');
  });

  it('aberta: o aviso do prazo; encerrada: só a trilha', () => {
    const { unmount } = abrir(<CobrancaDoPortal dados={cobranca({ respondida: false, aberta: true })} />);
    expect(screen.getByText('A coordenação do contrato foi avisada e responde até 05/11/2026.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
    unmount();
    abrir(<CobrancaDoPortal dados={cobranca({ respondida: false, aberta: false })} />);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByText('Histórico')).toBeInTheDocument();
  });
});

describe('o portal abre pelo seu pedaço do build', () => {
  it('dentro da casca do cliente', async () => {
    respostas['/api/v1/eu'] = { status: 200, corpo: {
      id: 2, nome: 'Cliente GL', primeiro_nome: 'Cliente', perfil: 'Cliente', papel: 'cliente', cliente: true,
      avisos_nao_lidos: 0, menu: [], csrf: 'x', versao: '1',
      links: { inicio: '/cliente/', avisos: '/avisos', trocar_senha: '/t', seguranca: '/s', sair: '/sair' } } };
    respostas['/api/v1/cliente/locais/3'] = { status: 200, corpo: local() };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/cliente/locais/3']}><App /></MemoryRouter>
      </QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: 'CD 1' })).toBeInTheDocument();
    expect(document.querySelector('[data-tela-pronta="portal-local"]')).not.toBeNull();
    expect(screen.getAllByText('Portal do cliente').length).toBeGreaterThan(0);
  });
});
