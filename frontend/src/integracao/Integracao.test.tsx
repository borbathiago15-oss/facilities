import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { Integracao } from './Integracao';
import { PaginaIntegracao } from './paginas';
import type { DadosDaIntegracao } from './tipos';

const SEGREDO = 'fac_1a2b3c4d_SEGREDO-que-so-aparece-uma-vez';
let chamadas: { url: string; init?: RequestInit }[] = [];
let respostas: Record<string, { status: number; corpo: unknown }> = {};
let leituras = 0;
beforeEach(() => {
  chamadas = [];
  respostas = {};
  leituras = 0;
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    chamadas.push({ url: String(url), init });
    if (String(url) === '/api/v1/admin/integracao/' && (!init || !init.method || init.method === 'GET')) {
      leituras += 1;
      return new Response(JSON.stringify(dados()), { status: 200 });
    }
    const r = respostas[String(url)] || { status: 200, corpo: { recados: [], destino: '/novo/admin/integracao/' } };
    return new Response(JSON.stringify(r.corpo), { status: r.status });
  });
});
afterEach(() => vi.restoreAllMocks());

function dados(extra: Partial<DadosDaIntegracao> = {}): DadosDaIntegracao {
  return {
    chaves: [
      { id: 1, nome: 'Produção', prefixo: 'fac_1a2b3c4d_…', locais: 'todos os locais', criada_em: '01/10/2026', ultimo_uso_em: '02/11/2026 08:00', ativa: true },
      { id: 2, nome: 'Teste', prefixo: 'fac_9f9f9f9f_…', locais: 'CD 1, CD 2', criada_em: '02/09/2026', ultimo_uso_em: null, ativa: false }],
    acessos: [{ id: 7, em: '02/11/2026 08:00', chave: 'chave inválida', rota: 'locais', parametros: '', status: 401, itens: '' }],
    locais: [{ id: 3, nome: 'CD 1' }, { id: 4, nome: 'CD 2' }], ...extra };
}

function abrirPagina() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/admin/integracao/']}>
        <Routes>
          <Route path="/admin/integracao" element={<><PaginaIntegracao /><Link to="/outra">Sair daqui</Link></>} />
          <Route path="/outra" element={<Link to="/admin/integracao/">Voltar</Link>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>);
}

describe('as chaves da integração', () => {
  it('mostra a lista como a antiga, sem o texto de chave nenhuma', () => {
    render(<MemoryRouter><Integracao dados={dados()} nova={null} aoCriar={() => {}} /></MemoryRouter>);
    expect(screen.getByText('fac_1a2b3c4d_…')).toBeInTheDocument();
    expect(screen.getByText('todos os locais · criada 01/10/2026 · último uso 02/11/2026 08:00')).toBeInTheDocument();
    expect(screen.getByText('CD 1, CD 2 · criada 02/09/2026')).toBeInTheDocument();
    expect(screen.getByText('revogada')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Revogar' })).toHaveLength(1);
    expect(screen.getByText('chave inválida')).toBeInTheDocument();
    expect(screen.queryByText(/Copie agora/)).toBeNull();
  });

  it('vazia', () => {
    render(<MemoryRouter><Integracao dados={dados({ chaves: [], acessos: [] })} nova={null} aoCriar={() => {}} /></MemoryRouter>);
    expect(screen.getByText('Nenhuma chave ainda.')).toBeInTheDocument();
    expect(screen.getByText('Nenhum acesso ainda.')).toBeInTheDocument();
  });

  it('a chave nova aparece uma vez, só na memória da tela, e some ao sair', async () => {
    respostas['/api/v1/admin/integracao/'] = { status: 200, corpo: {
      recados: [], destino: '/novo/admin/integracao/', chave: { nome: 'Nova', texto: SEGREDO } } };
    const espiaGuardar = vi.spyOn(Storage.prototype, 'setItem');
    const espiaHistorico = vi.spyOn(window.history, 'pushState');
    const espiaLog = vi.spyOn(console, 'log');
    abrirPagina();
    await screen.findByText('Produção');
    await userEvent.click(screen.getByText('Criar chave', { selector: 'summary' }));
    await userEvent.type(screen.getByLabelText('Nome'), 'Nova');
    await userEvent.click(screen.getByLabelText(/Todos os locais/));
    await userEvent.click(screen.getByRole('button', { name: 'Criar chave' }));
    expect(await screen.findByText(SEGREDO)).toBeInTheDocument();
    expect(screen.getByText('Chave "Nova" criada. Copie agora: ela não aparece de novo.')).toBeInTheDocument();
    const envio = chamadas.find((c) => c.init?.method === 'POST')!;
    expect(envio.url).toBe('/api/v1/admin/integracao/');
    expect((envio.init!.body as FormData).get('todos')).toBe('1');
    // A lista é lida de novo (a chave nova entra nela, só com o prefixo).
    await waitFor(() => expect(leituras).toBe(2));
    expect(screen.getByText(SEGREDO)).toBeInTheDocument();
    // Nada guardado no aparelho, no histórico nem no console.
    for (const espia of [espiaGuardar, espiaHistorico, espiaLog]) {
      expect(JSON.stringify(espia.mock.calls)).not.toContain(SEGREDO);
    }
    expect(JSON.stringify(window.history.state)).not.toContain(SEGREDO);
    // Saiu e voltou: a chave não aparece de novo.
    await userEvent.click(screen.getByRole('link', { name: 'Sair daqui' }));
    await userEvent.click(await screen.findByRole('link', { name: 'Voltar' }));
    await screen.findByText('Produção');
    expect(screen.queryByText(SEGREDO)).toBeNull();
    expect(screen.queryByText(/Copie agora/)).toBeNull();
  });

  it('a recusa volta à tela com o recado, sem chave', async () => {
    respostas['/api/v1/admin/integracao/'] = { status: 400, corpo: {
      error: 'Dê um nome à chave (ex.: Trino Intelligence — produção).',
      recados: [{ tipo: 'danger', texto: 'Dê um nome à chave (ex.: Trino Intelligence — produção).' }],
      destino: '/novo/admin/integracao/' } };
    abrirPagina();
    await screen.findByText('Produção');
    await userEvent.click(screen.getByText('Criar chave', { selector: 'summary' }));
    await userEvent.type(screen.getByLabelText('Nome'), ' ');
    await userEvent.click(screen.getByRole('button', { name: 'Criar chave' }));
    expect(await screen.findByText('Dê um nome à chave (ex.: Trino Intelligence — produção).')).toBeInTheDocument();
    expect(screen.queryByText(/Copie agora/)).toBeNull();
  });

  it('revogar vai ao mesmo caminho da antiga e esquece a chave mostrada', async () => {
    respostas['/api/v1/admin/integracao/'] = { status: 200, corpo: {
      recados: [], destino: '/novo/admin/integracao/', chave: { nome: 'Nova', texto: SEGREDO } } };
    respostas['/api/v1/admin/integracao/1/revogar'] = { status: 200, corpo: {
      recados: [{ tipo: 'success', texto: 'Chave "Produção" revogada: deixa de funcionar agora.' }], destino: '/novo/admin/integracao/' } };
    abrirPagina();
    await screen.findByText('Produção');
    await userEvent.click(screen.getByText('Criar chave', { selector: 'summary' }));
    await userEvent.type(screen.getByLabelText('Nome'), 'Nova');
    await userEvent.click(screen.getByRole('button', { name: 'Criar chave' }));
    await screen.findByText(SEGREDO);
    await userEvent.click(screen.getByRole('button', { name: 'Revogar' }));
    expect(await screen.findByText('Chave "Produção" revogada: deixa de funcionar agora.')).toBeInTheDocument();
    expect(chamadas.some((c) => c.url === '/api/v1/admin/integracao/1/revogar' && c.init?.method === 'POST')).toBe(true);
    expect(screen.queryByText(SEGREDO)).toBeNull();
  });

  it('abre pelo seu pedaço do build, dentro da casca', async () => {
    respostas['/api/v1/eu'] = { status: 200, corpo: {
      id: 1, nome: 'Admin', primeiro_nome: 'Admin', perfil: 'Administrador', papel: 'master', cliente: false,
      avisos_nao_lidos: 0, menu: [], csrf: 'x', versao: '1',
      links: { inicio: '/', avisos: '/avisos', trocar_senha: '/t', seguranca: '/s', sair: '/sair' } } };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/admin/integracao/']}><App /></MemoryRouter>
      </QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: 'Integração com o Trino Intelligence' })).toBeInTheDocument();
    expect(document.querySelector('[data-tela-pronta="integracao"]')).not.toBeNull();
  });
});
