import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import type { DadosDosAvisos } from '../portal/tipos';
import { CobrancaDaEquipe, ListaDasCobrancas } from './Cobrancas';
import type { DadosDaCobranca, DadosDaLista } from './tipos';

let chamadas: { url: string; init?: RequestInit }[] = [];
let respostas: Record<string, { status: number; corpo: unknown }> = {};
const PADRAO = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Resposta enviada. O cliente confirma ou reabre pelo portal.' }], destino: '/novo/cobrancas/9' } };
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

const ABAS = { cobrancas: '/novo/cobrancas/', qr: '/novo/cobrancas/?aba=qr' };

function lista(extra: Partial<DadosDaLista> = {}): DadosDaLista {
  return {
    aba: 'cobrancas', status: '', abas: ABAS,
    filtros: [['Todas', '/novo/cobrancas/', true], ['Encerrada', '/novo/cobrancas/?status=fechada', false]],
    itens: [{ id: 9, numero: 'CB-00009', titulo: 'Vidros', local: 'CD 1', autor: 'Cliente GL', prazo: '05/11/2026',
      situacao: { classe: 'fc-dem fc-dem-atrasada', texto: 'Atrasada' }, url: '/novo/cobrancas/9' }], ...extra };
}

function cobranca(extra: Partial<DadosDaCobranca> = {}): DadosDaCobranca {
  return {
    id: 9, numero: 'CB-00009', titulo: 'Vidros', local: 'CD 1', autor: 'Cliente GL', situacao: 'Aguardando a coordenação',
    prazo: '05/11/2026', reaberturas: 1, status: 'aberta', pode_responder: true,
    eventos: [{ id: 1, quando: '01/11/2026 08:00', autor: 'Cliente GL', tipo: 'Cobrança aberta', prazo: '05/11/2026', texto: 'Limpar' }],
    links: { lista: '/novo/cobrancas/' }, ...extra };
}

describe('a lista das cobranças da equipe', () => {
  it('mostra os selos e os filtros como a antiga', async () => {
    abrir(<ListaDasCobrancas dados={lista()} />, '/cobrancas/');
    expect(screen.getByText('Atrasada')).toHaveClass('fc-dem-atrasada');
    expect(screen.getByText('CD 1 · Cliente GL')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Todas' })).toHaveClass('btn-primary');
    expect(screen.getByRole('link', { name: /CB-00009/ })).toHaveAttribute('href', '/cobrancas/9');
    await userEvent.click(screen.getByRole('link', { name: 'Encerrada' }));
    expect(screen.getByTestId('onde')).toHaveTextContent('/cobrancas/?status=fechada');
  });

  it('vazia', () => {
    abrir(<ListaDasCobrancas dados={lista({ itens: [] })} />);
    expect(screen.getByText('Nenhuma cobrança aqui.')).toBeInTheDocument();
  });

  it('os avisos pelo QR levam ao dia do local na rotina nova', () => {
    const avisos: DadosDosAvisos = {
      aba: 'qr', situacao: '', abas: ABAS, filtros: [['Todos', '/novo/cobrancas/?aba=qr', true]],
      avisos: [{ id: 1, status: 'aberta', situacao: 'Recebida', titulo: 'Local sujo', onde: 'CD 1 · Banheiro · Pia', texto: null,
        quando: '01/11 08:00', atrasada: true, responsavel: 'Eva', url: '/novo/rotas/locais/3/dia?data=2026-11-01' }] };
    abrir(<ListaDasCobrancas dados={avisos} />);
    expect(screen.getByText('Fora do prazo')).toBeInTheDocument();
    expect(screen.getByText(/tarefa de Eva/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Local sujo/ })).toHaveAttribute('href', '/rotas/locais/3/dia?data=2026-11-01');
  });
});

describe('a cobrança na equipe', () => {
  it('responder vai ao mesmo caminho da antiga', async () => {
    abrir(<CobrancaDaEquipe dados={cobranca()} />, '/cobrancas/9');
    expect(screen.getByText(/CD 1 · pedida por Cliente GL/)).toBeInTheDocument();
    expect(screen.getByText(/reaberta 1 vez\(es\)/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Resposta para o cliente'), 'Limpos.');
    await userEvent.click(screen.getByRole('button', { name: 'Responder' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe('/api/v1/cobrancas/9/responder');
    expect((chamadas[0].init!.body as FormData).get('texto')).toBe('Limpos.');
  });

  it('quem não responde e a respondida: os avisos da antiga', () => {
    const { unmount } = abrir(<CobrancaDaEquipe dados={cobranca({ pode_responder: false })} />);
    expect(screen.getByText('Quem responde é a coordenação ou a supervisão do local.')).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
    unmount();
    abrir(<CobrancaDaEquipe dados={cobranca({ pode_responder: false, status: 'respondida', reaberturas: 0 })} />);
    expect(screen.getByText('Respondida. Esperando o cliente confirmar ou reabrir.')).toBeInTheDocument();
    expect(screen.queryByText(/reaberta/)).toBeNull();
  });
});

describe('as cobranças abrem pelo seu pedaço do build', () => {
  it('dentro da casca', async () => {
    respostas['/api/v1/eu'] = { status: 200, corpo: {
      id: 1, nome: 'Admin', primeiro_nome: 'Admin', perfil: 'Administrador', papel: 'master', cliente: false,
      avisos_nao_lidos: 0, menu: [], csrf: 'x', versao: '1',
      links: { inicio: '/', avisos: '/avisos', trocar_senha: '/t', seguranca: '/s', sair: '/sair' } } };
    respostas['/api/v1/cobrancas/9'] = { status: 200, corpo: cobranca() };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/cobrancas/9']}><App /></MemoryRouter>
      </QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: 'CB-00009 · Vidros' })).toBeInTheDocument();
    expect(document.querySelector('[data-tela-pronta="cobranca"]')).not.toBeNull();
  });
});
