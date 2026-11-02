import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { Avisos, InicioDaGestao, TrocarSenha } from './Conta';
import { PaginaSeguranca } from './paginas';
import type { DadosDoInicio } from './tipos';

const SEGREDO = 'JBSWY3DPEHPK3PXPSEGREDO';
const QR = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect width="10" height="10"/></svg>';
let chamadas: { url: string; init?: RequestInit }[] = [];
let respostas: Record<string, { status: number; corpo: unknown }> = {};
let ativo = false;
beforeEach(() => {
  chamadas = [];
  respostas = {};
  ativo = false;
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    chamadas.push({ url: String(url), init });
    if (String(url) === '/api/v1/conta/seguranca') {
      return new Response(JSON.stringify({ ativo }), { status: 200 });
    }
    if (String(url) === '/api/v1/conta/seguranca/codigo-novo') {
      return new Response(JSON.stringify({ novo: { segredo: SEGREDO, qr: QR } }), { status: 200 });
    }
    const r = respostas[String(url)] || { status: 200, corpo: { recados: [], destino: '/novo/conta/seguranca' } };
    return new Response(JSON.stringify(r.corpo), { status: r.status });
  });
});
afterEach(() => vi.restoreAllMocks());

function inicio(extra: Partial<DadosDoInicio> = {}): DadosDoInicio {
  return {
    primeiro_nome: 'Gustavo', data: '02/11/2026', perfil: 'Gerente', locais_na_carteira: 3,
    abrir_chamado: '/novo/chamados/novo',
    numeros: [
      { rotulo: 'Atrasadas', n: 2, tom: 'perigo', icone: 'bi-alarm', url: '/novo/demandas/?situacao=atrasada' },
      { rotulo: 'Vencem hoje', n: 0, tom: 'aviso', icone: 'bi-hourglass-split', url: '/novo/demandas/?situacao=hoje' }],
    primeiro: [{ situacao: 'atrasada', situacao_rotulo: 'Atrasada', tipo_rotulo: 'Chamado', numero: 'CH-0007',
      titulo: 'Lâmpada queimada', local: 'GL Armazém 1', prazo: '01/11 14:00', link: '/novo/chamados/7' }],
    fila: '/novo/demandas/',
    atalhos: [{ nome: 'Chamados', icone: 'bi-tools', url: '/novo/chamados/', texto: 'Abrir, atribuir, acompanhar o prazo e fechar.' }],
    administrador: null, ...extra };
}

function comRotas(inicial: string, elemento: React.ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[inicial]}>
        <Routes>
          <Route path="/conta/seguranca" element={<>{elemento}<Link to="/outra">Sair daqui</Link></>} />
          <Route path="/outra" element={<Link to="/conta/seguranca">Voltar</Link>} />
          <Route path="*" element={elemento} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>);
}

describe('o Início da gestão', () => {
  it('mostra os números, a fila e os atalhos como a antiga', () => {
    render(<MemoryRouter><InicioDaGestao dados={inicio()} /></MemoryRouter>);
    expect(screen.getByRole('heading', { name: 'Olá, Gustavo' })).toBeInTheDocument();
    expect(screen.getByText('02/11/2026 · Gerente · 3 local(is) na sua carteira')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Abrir chamado/ })).toHaveAttribute('href', '/chamados/novo');
    expect(screen.getByRole('link', { name: /Atrasadas/ })).toHaveClass('fc-numero', 'fc-numero-perigo');
    expect(screen.getByRole('link', { name: /Vencem hoje/ })).toHaveClass('zerado');
    expect(screen.getByRole('link', { name: /Lâmpada queimada/ })).toHaveAttribute('href', '/chamados/7');
    expect(screen.getByText('Chamado · CH-0007')).toBeInTheDocument();
    expect(screen.getByText('01/11 14:00')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Ver a fila inteira/ })).toHaveAttribute('href', '/demandas/');
    expect(screen.queryByText('Primeiros passos do administrador')).toBeNull();
  });

  it('sem nada esperando, sem módulo, e os primeiros passos do administrador', () => {
    const { unmount } = render(<MemoryRouter><InicioDaGestao dados={inicio({ primeiro: [] })} /></MemoryRouter>);
    expect(screen.getByText('Nada esperando. Tudo em dia.')).toBeInTheDocument();
    unmount();
    render(<MemoryRouter><InicioDaGestao dados={inicio({
      numeros: [], primeiro: [], atalhos: [], abrir_chamado: null, locais_na_carteira: null,
      administrador: { empresas: '/novo/cadastros/empresas', clientes: '/novo/cadastros/clientes',
        estados: '/novo/cadastros/estados', locais: '/novo/admin/contratos', pessoas: '/novo/admin/usuarios' } })} /></MemoryRouter>);
    expect(screen.getByText('Seu perfil ainda não tem módulo liberado. Fale com o administrador.')).toBeInTheDocument();
    expect(screen.getByText('02/11/2026 · Gerente')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'pessoas' })).toHaveAttribute('href', '/admin/usuarios');
    expect(screen.queryByRole('link', { name: /Abrir chamado/ })).toBeNull();
  });
});

describe('os avisos', () => {
  it('abrir vai ao mesmo caminho da antiga e segue o link do aviso', async () => {
    respostas['/api/v1/avisos/5/abrir'] = { status: 200, corpo: { recados: [], destino: '/passagem-de-turno/' } };
    const ir = vi.fn();
    vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, assign: ir } as Location);
    comRotas('/avisos', <Avisos dados={{ nao_lidos: 1, avisos: [
      { id: 5, titulo: 'Pendência nova', mensagem: 'No turno da noite', nao_lido: true, em: '02/11/2026 08:00' },
      { id: 4, titulo: 'Lido', mensagem: '', nao_lido: false, em: '01/11/2026 08:00' }] }} />);
    expect(screen.getByRole('button', { name: /Pendência nova/ })).toHaveClass('nao-lido');
    expect(screen.getByRole('button', { name: /Lido/ })).toHaveClass('bg-transparent');
    await userEvent.click(screen.getByRole('button', { name: /Pendência nova/ }));
    await waitFor(() => expect(ir).toHaveBeenCalledWith('/passagem-de-turno/'));
    expect(chamadas.some((c) => c.url === '/api/v1/avisos/5/abrir' && c.init?.method === 'POST')).toBe(true);
  });

  it('sem não lidos, sem o "Marcar todos"; vazio, o convite da antiga', () => {
    comRotas('/avisos', <Avisos dados={{ nao_lidos: 0, avisos: [] }} />);
    expect(screen.queryByRole('button', { name: 'Marcar todos como lidos' })).toBeNull();
    expect(screen.getByText('Nenhum aviso por aqui.')).toBeInTheDocument();
  });
});

describe('a segurança da conta', () => {
  it('o segredo vem só do envio que o prepara e fica só na memória da tela', async () => {
    const espiaGuardar = vi.spyOn(Storage.prototype, 'setItem');
    const espiaHistorico = vi.spyOn(window.history, 'pushState');
    const espiaLog = vi.spyOn(console, 'log');
    const cliente = new QueryClient();
    render(
      <QueryClientProvider client={cliente}>
        <MemoryRouter initialEntries={['/conta/seguranca']}>
          <Routes>
            <Route path="/conta/seguranca" element={<><PaginaSeguranca /><Link to="/outra">Sair daqui</Link></>} />
            <Route path="/outra" element={<Link to="/conta/seguranca">Voltar</Link>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>);
    expect(await screen.findByText(SEGREDO)).toBeInTheDocument();
    const qr = screen.getByRole('img', { name: 'QR para o aplicativo autenticador' }).querySelector('img')!;
    expect(qr.getAttribute('src')).toBe(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(QR)}`);
    expect(document.querySelector('[data-tela-pronta="seguranca"]')).not.toBeNull();
    // Um pedido só, por POST (o GET da tela traz só o estado).
    const pedidos = chamadas.filter((c) => c.url === '/api/v1/conta/seguranca/codigo-novo');
    expect(pedidos).toHaveLength(1);
    expect(pedidos[0].init?.method).toBe('POST');
    // Nada guardado no aparelho, no histórico, na cópia dos dados nem no console.
    for (const espia of [espiaGuardar, espiaHistorico, espiaLog]) {
      expect(JSON.stringify(espia.mock.calls)).not.toContain(SEGREDO);
    }
    expect(JSON.stringify(window.history.state)).not.toContain(SEGREDO);
    expect(JSON.stringify(cliente.getQueryCache().getAll().map((q) => q.state.data))).not.toContain(SEGREDO);
    // Saiu da tela: o segredo some (e volta a ser pedido ao servidor).
    await userEvent.click(screen.getByRole('link', { name: 'Sair daqui' }));
    expect(screen.queryByText(SEGREDO)).toBeNull();
    await userEvent.click(await screen.findByRole('link', { name: 'Voltar' }));
    expect(await screen.findByText(SEGREDO)).toBeInTheDocument();
    expect(chamadas.filter((c) => c.url === '/api/v1/conta/seguranca/codigo-novo')).toHaveLength(2);
  });

  it('ativar vai ao mesmo caminho da antiga; com a etapa ativada, nenhum segredo é pedido', async () => {
    respostas['/api/v1/conta/seguranca/ativar'] = { status: 200, corpo: {
      recados: [{ tipo: 'success', texto: 'Segunda etapa ativada. A partir de agora, o login pede a senha e o código do aplicativo.' }],
      destino: '/novo/conta/seguranca' } };
    comRotas('/conta/seguranca', <PaginaSeguranca />);
    await screen.findByText(SEGREDO);
    await userEvent.type(screen.getByLabelText('Código do aplicativo'), '123456');
    ativo = true;
    await userEvent.click(screen.getByRole('button', { name: 'Ativar a segunda etapa' }));
    expect(await screen.findByText(/Segunda etapa ativada. A partir de agora/)).toBeInTheDocument();
    expect(await screen.findByText('Segunda etapa ativada.')).toBeInTheDocument();
    const envio = chamadas.find((c) => c.url === '/api/v1/conta/seguranca/ativar')!;
    expect((envio.init!.body as FormData).get('codigo')).toBe('123456');
    expect(screen.queryByText(SEGREDO)).toBeNull();
    expect(chamadas.filter((c) => c.url === '/api/v1/conta/seguranca/codigo-novo')).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Desativar a segunda etapa' })).toBeInTheDocument();
  });

  it('a senha errada que bloqueia a conta leva ao login', async () => {
    ativo = true;
    respostas['/api/v1/conta/seguranca/desativar'] = { status: 400, corpo: {
      destino: '/login', error: 'E-mail ou senha incorretos.' } };
    const ir = vi.fn();
    vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, assign: ir } as Location);
    comRotas('/conta/seguranca', <PaginaSeguranca />);
    await userEvent.type(await screen.findByLabelText('Senha'), 'errada');
    await userEvent.click(screen.getByRole('button', { name: 'Desativar a segunda etapa' }));
    await waitFor(() => expect(ir).toHaveBeenCalledWith('/login'));
  });
});

describe('trocar a senha', () => {
  it('a recusa fica na tela, com os campos vazios como na antiga', async () => {
    respostas['/api/v1/trocar-senha'] = { status: 400, corpo: {
      error: 'A senha atual não confere.', recados: [{ tipo: 'danger', texto: 'A senha atual não confere.' }], destino: null } };
    comRotas('/trocar-senha', <TrocarSenha dados={{ primeiro_acesso: false, minimo: 8 }} />);
    expect(screen.getByText('A senha nova vale em todos os aparelhos; os outros acessos abertos serão encerrados.')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Senha atual'), 'errada');
    await userEvent.type(screen.getByLabelText('Senha nova (mínimo 8 caracteres)'), 'nova-senha-1');
    await userEvent.type(screen.getByLabelText('Repita a senha nova'), 'nova-senha-1');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar senha' }));
    expect(await screen.findByText('A senha atual não confere.')).toBeInTheDocument();
    expect(screen.getByLabelText('Senha atual')).toHaveValue('');
  });

  it('o primeiro acesso tem o texto da antiga', () => {
    comRotas('/trocar-senha', <TrocarSenha dados={{ primeiro_acesso: true, minimo: 8 }} />);
    expect(screen.getByText(/Este é o seu primeiro acesso/)).toBeInTheDocument();
  });
});

describe('o pedaço do build', () => {
  it('o Início abre dentro da casca', async () => {
    respostas['/api/v1/eu'] = { status: 200, corpo: {
      id: 1, nome: 'Admin', primeiro_nome: 'Admin', perfil: 'Administrador', papel: 'master', cliente: false,
      avisos_nao_lidos: 0, menu: [], csrf: 'x', versao: '1',
      links: { inicio: '/', avisos: '/avisos', trocar_senha: '/t', seguranca: '/s', sair: '/sair' } } };
    respostas['/api/v1/inicio'] = { status: 200, corpo: inicio({ primeiro_nome: 'Admin' }) };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/']}><App /></MemoryRouter>
      </QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: 'Olá, Admin' })).toBeInTheDocument();
    expect(document.querySelector('[data-tela-pronta="inicio"]')).not.toBeNull();
  });
});
