import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Locais } from './Administracao';
import { PaginaPessoas } from './paginas';
import type { DadosDasPessoas, DadosDosLocais } from './tipos';

const SENHA = 'Qx7mPa9KwZ2e';
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
    if (String(url) === '/api/v1/admin/usuarios' && (!init || !init.method || init.method === 'GET')) {
      leituras += 1;
      return new Response(JSON.stringify(pessoas()), { status: 200 });
    }
    const r = respostas[String(url)] || { status: 200, corpo: { recados: [], destino: '/novo/admin/usuarios' } };
    return new Response(JSON.stringify(r.corpo), { status: r.status });
  });
});
afterEach(() => vi.restoreAllMocks());

function pessoas(): DadosDasPessoas {
  return {
    pessoas: [
      { id: 1, nome: 'Administrador', email: 'admin@x.com', perfil: 'master', perfil_rotulo: 'Administrador',
        ativo: true, todos_os_locais: false, superior_id: null, cliente_id: null, locais: [], permissoes: [],
        segunda_etapa: true, alcance: 'todos os locais', cadeia: [] },
      { id: 2, nome: 'Ana', email: 'ana@x.com', perfil: 'encarregado', perfil_rotulo: 'Encarregado / ASG',
        ativo: false, todos_os_locais: false, superior_id: 3, cliente_id: null, locais: [7], permissoes: [],
        segunda_etapa: false, alcance: '1 local(is) direto(s)',
        cadeia: [{ nome: 'Gustavo', perfil: 'Gerente' }, { nome: 'Sueli', perfil: 'Supervisor' }] }],
    locais: [{ id: 7, nome: 'CD 1', ativo: true }, { id: 8, nome: 'CD 2', ativo: false }],
    perfis: [['master', 'Administrador'], ['encarregado', 'Encarregado / ASG']],
    permissoes: [['diario_config', 'Configurar o modelo de passagem de turno']],
    superiores: [{ id: 3, nome: 'Sueli', perfil: 'Supervisor' }],
    clientes: [{ id: 9, nome: 'Grupo GL' }],
  };
}

function abrirPessoas() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/admin/usuarios']}>
        <Routes>
          <Route path="/admin/usuarios" element={<><PaginaPessoas /><Link to="/outra">Sair daqui</Link></>} />
          <Route path="/outra" element={<Link to="/admin/usuarios">Voltar</Link>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>);
}

describe('as pessoas', () => {
  it('mostra a lista como a antiga, sem senha nenhuma', async () => {
    abrirPessoas();
    expect(await screen.findByText('Ana')).toBeInTheDocument();
    expect(screen.getByText('Cadeia: Gustavo (Gerente) › Sueli (Supervisor) › Ana')).toBeInTheDocument();
    expect(screen.getByText('inativo')).toBeInTheDocument();
    expect(screen.getByText('1 local(is) direto(s)')).toBeInTheDocument();
    expect(screen.getAllByText(/2 etapas/)).toHaveLength(1);
    expect(screen.getAllByRole('button', { name: /Desligar a segunda etapa/ })).toHaveLength(1);
    expect(screen.getAllByText('(inativo)', { exact: false }).length).toBeGreaterThan(0);
    expect(document.querySelector('[data-tela-pronta="pessoas"]')).not.toBeNull();
  });

  it('a senha temporária aparece uma vez, só na memória da tela, e some ao sair', async () => {
    respostas['/api/v1/admin/usuarios'] = { status: 200, corpo: {
      recados: [], destino: '/novo/admin/usuarios', senha: { senha: SENHA,
        texto: `Cadastro de Zé criado. Senha temporária: ${SENHA} — entregue pessoalmente; no primeiro acesso o sistema pede uma senha nova.` } } };
    const espiaGuardar = vi.spyOn(Storage.prototype, 'setItem');
    const espiaHistorico = vi.spyOn(window.history, 'pushState');
    const espiaLog = vi.spyOn(console, 'log');
    abrirPessoas();
    await screen.findByText('Ana');
    await userEvent.click(screen.getByText('Cadastrar pessoa', { selector: 'summary' }));
    await userEvent.type(screen.getByLabelText('Nome', { selector: '#nomenovo' }), 'Zé');
    await userEvent.type(screen.getByLabelText('E-mail (login)', { selector: '#emailnovo' }), 'ze@x.com');
    await userEvent.click(screen.getByRole('button', { name: 'Cadastrar' }));
    expect(await screen.findByText(SENHA)).toBeInTheDocument();
    expect(screen.getByText(/Cadastro de Zé criado. Senha temporária:/)).toBeInTheDocument();
    const envio = chamadas.find((c) => c.init?.method === 'POST')!;
    expect((envio.init!.body as FormData).get('role')).toBe('encarregado');
    await waitFor(() => expect(leituras).toBe(2));
    for (const espia of [espiaGuardar, espiaHistorico, espiaLog]) {
      expect(JSON.stringify(espia.mock.calls)).not.toContain(SENHA);
    }
    expect(JSON.stringify(window.history.state)).not.toContain(SENHA);
    await userEvent.click(screen.getByRole('link', { name: 'Sair daqui' }));
    await userEvent.click(await screen.findByRole('link', { name: 'Voltar' }));
    await screen.findByText('Ana');
    expect(screen.queryByText(SENHA)).toBeNull();
  });

  it('"Gerar senha temporária" pede a confirmação da antiga', async () => {
    respostas['/api/v1/admin/usuarios/2/nova-senha'] = { status: 200, corpo: {
      recados: [], destino: '/novo/admin/usuarios', senha: { senha: SENHA, texto: `Senha temporária de Ana: ${SENHA}` } } };
    const confirmar = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    abrirPessoas();
    await screen.findByText('Ana');
    const botoes = screen.getAllByRole('button', { name: /Gerar senha temporária/ });
    await userEvent.click(botoes[1]);
    expect(confirmar).toHaveBeenLastCalledWith('Gerar uma senha temporária nova para Ana? A atual deixa de valer.');
    expect(chamadas.some((c) => c.url.endsWith('/nova-senha'))).toBe(false);
    await userEvent.click(botoes[1]);
    expect(await screen.findByText(SENHA)).toBeInTheDocument();
  });

  it('salvar vai ao mesmo caminho da antiga, com as caixas marcadas', async () => {
    respostas['/api/v1/admin/usuarios/2'] = { status: 200, corpo: {
      recados: [{ tipo: 'success', texto: 'Cadastro de Ana atualizado.' }], destino: '/novo/admin/usuarios' } };
    abrirPessoas();
    await screen.findByText('Ana');
    const form = screen.getByDisplayValue('ana@x.com').closest('form')!;
    await userEvent.click(within(form).getByRole('button', { name: 'Salvar' }));
    expect(await screen.findByText('Cadastro de Ana atualizado.')).toBeInTheDocument();
    const corpo = chamadas.find((c) => c.url === '/api/v1/admin/usuarios/2')!.init!.body as FormData;
    expect(corpo.getAll('clients')).toEqual(['7']);
    expect(corpo.get('superior_id')).toBe('3');
    expect(corpo.get('is_active')).toBeNull();
  });
});

describe('os locais', () => {
  const dados: DadosDosLocais = {
    locais: [{ id: 5, nome: 'GL Armazém 1', centro_de_custo: '123', endereco: '', responsavel_id: null,
      responsavel: null, cliente_id: 9, cliente: 'Grupo GL', estado_id: 1, estado: 'BA', ativo: false,
      links: { estrutura: '/novo/cadastros/locais/5', passagem: '/passagem-de-turno/configuracao?client_id=5' } }],
    gestores: [{ id: 2, nome: 'Gustavo' }],
    clientes: [{ id: 9, nome: 'Grupo GL', ativo: false }, { id: 10, nome: 'Outro', ativo: true }],
    estados: [{ id: 1, nome: 'Bahia', ativo: true }, { id: 2, nome: 'Acre', ativo: false }],
    links: { empresas: '/novo/cadastros/empresas', clientes: '/novo/cadastros/clientes', estados: '/novo/cadastros/estados' },
  };

  it('mostra a lista como a antiga', () => {
    render(<MemoryRouter><Locais dados={dados} /></MemoryRouter>);
    expect(screen.getByText('CC 123')).toBeInTheDocument();
    expect(screen.getByText('sem gestor responsável')).toBeInTheDocument();
    expect(screen.getByText('inativo')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Estrutura/ })).toHaveAttribute('href', '/cadastros/locais/5');
    expect(screen.getByRole('link', { name: /Configurar a passagem/ })).toHaveAttribute('href', '/passagem-de-turno/configuracao?client_id=5');
    // O cliente inativo só aparece no local que já está ligado a ele.
    const novo = screen.getByLabelText('Cliente', { selector: '#lclinovo' });
    expect(within(novo).queryByText('Grupo GL')).toBeNull();
    expect(within(screen.getByLabelText('Cliente', { selector: '#lcli5' })).getByText('Grupo GL')).toBeInTheDocument();
    expect(within(screen.getByLabelText('Estado', { selector: '#lestnovo' })).queryByText('Acre')).toBeNull();
  });

  it('sem cliente, o aviso da antiga; sem local, o cadastro aberto', () => {
    render(<MemoryRouter><Locais dados={{ ...dados, locais: [], clientes: [] }} /></MemoryRouter>);
    expect(screen.getByText(/Para ligar os locais a um cliente/)).toBeInTheDocument();
    expect(screen.getByText('Cadastrar local', { selector: 'summary' }).closest('details')).toHaveAttribute('open');
    expect(screen.getByText('Nenhum local ainda.')).toBeInTheDocument();
  });
});
