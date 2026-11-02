import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { Catalogo, ConsumoDoMes, Custo, Estoque, Pedidos, classeDoPedido } from './Materiais';
import type { DadosDoCatalogo, DadosDoConsumoDoMes, DadosDoCusto, DadosDoEstoque, DadosDosPedidos, Pedido } from './tipos';

let chamadas: { url: string; init?: RequestInit }[] = [];
let respostas: Record<string, { status: number; corpo: unknown }> = {};
const PADRAO = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Feito.' }], destino: '/novo/materiais/locais/3' } };
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

const LINKS = { catalogo: '/novo/materiais/', custo: '/novo/materiais/custo', pedidos: '/novo/materiais/pedidos' };

function catalogo(extra: Partial<DadosDoCatalogo> = {}): DadosDoCatalogo {
  return {
    materiais: [
      { id: 1, nome: 'Detergente', unidade: 'L', preco: 'R$ 1.234,50', preco_campo: '1.234,50', ativo: true },
      { id: 2, nome: 'Pano', unidade: 'un', preco: null, preco_campo: '', ativo: false }],
    locais: [{ id: 3, nome: 'CD 1', url: '/novo/materiais/locais/3' }], pode_montar: true, links: LINKS, ...extra };
}

describe('o catálogo', () => {
  it('mostra os preços como a antiga e leva ao estoque novo', () => {
    abrir(<Catalogo dados={catalogo()} />);
    expect(screen.getByText('R$ 1.234,50 / L')).toBeInTheDocument();
    expect(screen.getByText('sem preço')).toHaveClass('text-muted');
    expect(screen.getByText('desativado')).toBeInTheDocument();
    expect(document.getElementById('mp1')).toHaveValue('1.234,50');
    expect(document.getElementById('mp2')).toHaveValue('');
    expect(screen.getByText('CD 1').closest('a')).toHaveAttribute('href', '/materiais/locais/3');
    expect(screen.getByRole('link', { name: /Custo operacional/ })).toHaveAttribute('href', '/materiais/custo');
    expect(screen.getByRole('button', { name: 'Desativar' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reativar' })).toBeInTheDocument();
  });

  it('quem só vê não recebe os formulários', () => {
    abrir(<Catalogo dados={catalogo({ pode_montar: false, locais: [] })} />);
    expect(screen.queryByText('Cadastrar material')).toBeNull();
    expect(screen.queryByText('Editar')).toBeNull();
    expect(screen.getByText('Nenhum local na sua carteira.')).toBeInTheDocument();
  });

  it('cadastrar envia ao mesmo caminho da antiga', async () => {
    respostas['/api/v1/materiais/'] = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Material "Cera" cadastrado.' }], destino: '/novo/materiais/' } };
    abrir(<Catalogo dados={catalogo()} />, '/materiais/custo');
    await userEvent.type(document.getElementById('nmn')!, 'Cera');
    await userEvent.type(document.getElementById('nmu')!, 'L');
    await userEvent.click(screen.getByRole('button', { name: 'Cadastrar' }));
    await waitFor(() => expect(screen.getByTestId('onde')).toHaveTextContent('/materiais/'));
    const corpo = chamadas.find((c) => c.url === '/api/v1/materiais/')!.init!.body as FormData;
    expect([corpo.get('nome'), corpo.get('unidade'), corpo.get('preco_unitario')]).toEqual(['Cera', 'L', '']);
  });
});

function estoque(extra: Partial<DadosDoEstoque> = {}): DadosDoEstoque {
  return {
    local: { id: 3, nome: 'CD 1' }, materiais: [{ id: 1, nome: 'Detergente', unidade: 'L' }],
    com_saldo: [{ id: 1, nome: 'Detergente', unidade: 'L', saldo: '8,5', negativo: false },
      { id: 2, nome: 'Pano', unidade: 'un', saldo: '-3', negativo: true }],
    movimentos: [{ dia: '02/11', tipo_rotulo: 'Consumo', material: 'Pano', quantidade: '-5 un', valor: '—', pessoa: 'Ana',
      motivo: 'Acabou', autorizou: 'Gestor' }],
    rotas: [{ id: 4, nome: 'Manhã' }], tipos: [['entrada', 'Entrada'], ['saida', 'Saída'], ['ajuste', 'Ajuste de inventário']],
    pode_montar: true, gestor_do_contrato: true, links: { ...LINKS, mes: '/novo/materiais/locais/3/mes' }, ...extra };
}

describe('o estoque do local', () => {
  it('mostra o saldo, o negativo e os lançamentos como a antiga', () => {
    abrir(<Estoque dados={estoque()} />);
    expect(screen.getByText('8,5 L')).not.toHaveClass('text-danger');
    expect(screen.getByText('-3 un')).toHaveClass('ms-auto', 'fw-bold', 'text-danger');
    expect(screen.getByText('saldo negativo autorizado por Gestor').tagName).toBe('B');
    expect(screen.getByText(/Ana · Acabou ·/)).toBeInTheDocument();
    expect([...document.querySelectorAll('#mvt option')].map((o) => o.getAttribute('value'))).toEqual(['entrada', 'saida', 'ajuste']);
    expect(document.querySelectorAll('input[name=autorizar_negativo]')).toHaveLength(2);
    expect(screen.getByRole('link', { name: 'Materiais' })).toHaveAttribute('href', '/materiais/');
  });

  it('sem ser gestor do contrato, sem a autorização do negativo; sem montar, só o consumo', () => {
    abrir(<Estoque dados={estoque({ gestor_do_contrato: false, pode_montar: false, movimentos: [] })} />);
    expect(document.querySelectorAll('input[name=autorizar_negativo]')).toHaveLength(0);
    expect(screen.queryByText('Lançar entrada, saída ou ajuste')).toBeNull();
    expect(screen.getByRole('heading', { name: 'Lançar consumo' })).toBeInTheDocument();
    expect(screen.getByText('Nenhum lançamento ainda.')).toHaveAttribute('colspan', '6');
  });

  it('o consumo vai à mesma ação do chamado e do formulário antigo', async () => {
    abrir(<Estoque dados={estoque()} />, '/materiais/locais/3');
    await userEvent.type(document.getElementById('csq')!, '1,5');
    await userEvent.selectOptions(document.getElementById('csr')!, '4');
    await userEvent.click(screen.getByRole('button', { name: 'Lançar consumo' }));
    await waitFor(() => expect(chamadas.map((c) => c.url)).toContain('/api/v1/materiais/locais/3/consumo'));
    const corpo = chamadas.find((c) => c.url.endsWith('/consumo'))!.init!.body as FormData;
    expect([corpo.get('material_id'), corpo.get('quantidade'), corpo.get('rota_id'), corpo.get('voltar')]).toEqual(['1', '1,5', '4', null]);
  });
});

describe('o consumo do mês e o custo', () => {
  const mes = (extra: Partial<DadosDoConsumoDoMes> = {}): DadosDoConsumoDoMes => ({
    local: { id: 3, nome: 'CD 1' }, mes: '11/2026', anterior: '2026-10', seguinte: '2026-12', total: 'R$ 18,00',
    sem_preco: ['Pano', 'Cera'], linhas: [{ material: 'Detergente', quantidade: '1,5 L', vezes: 2, valor: 'R$ 18,00' }],
    links: { local: '/novo/materiais/locais/3' }, ...extra });

  it('o mês: o total, o que ficou de fora e a navegação', async () => {
    abrir(<ConsumoDoMes dados={mes()} />, '/materiais/locais/3/mes');
    expect(screen.getByText('Fora do custo (material sem preço): Pano, Cera.')).toBeInTheDocument();
    expect(screen.getAllByText('R$ 18,00')).toHaveLength(2);
    await userEvent.click(screen.getByRole('link', { name: /Mês seguinte/ }));
    expect(screen.getByTestId('onde')).toHaveTextContent('/materiais/locais/3/mes?m=2026-12');
  });

  it('o mês vazio', () => {
    abrir(<ConsumoDoMes dados={mes({ linhas: [], sem_preco: [] })} />);
    expect(screen.getByText('Nenhum consumo neste mês.')).toBeInTheDocument();
    expect(screen.queryByText(/Fora do custo/)).toBeNull();
  });

  const custo = (extra: Partial<DadosDoCusto> = {}): DadosDoCusto => ({
    de: '2026-11-01', ate: '2026-11-02', de_br: '01/11/2026', ate_br: '02/11/2026', total: 'R$ 18,00', sem_preco: 1,
    clientes: [['Grupo GL', 'R$ 18,00']], estados: [['BA', 'R$ 18,00']],
    locais: [{ url: '/novo/materiais/locais/3', nome: 'CD 1', cliente: 'Grupo GL', estado: 'BA', consumos: 2, sem_preco: 1, valor: 'R$ 18,00' }],
    links: LINKS, ...extra });

  it('o custo: as somas, o aviso e o filtro do período', async () => {
    abrir(<Custo dados={custo()} />, '/materiais/custo');
    expect(screen.getByText('Total de 01/11/2026 a 02/11/2026')).toBeInTheDocument();
    expect(screen.getByText('1 consumo(s) de material sem preço ficaram fora do total.')).toBeInTheDocument();
    expect(screen.getByText('Grupo GL · BA · 2 lançamento(s), 1 sem preço')).toBeInTheDocument();
    expect(screen.getByText('CD 1').closest('a')).toHaveAttribute('href', '/materiais/locais/3');
    await userEvent.clear(document.getElementById('cde')!);
    await userEvent.type(document.getElementById('cde')!, '2026-10-01');
    await userEvent.click(screen.getByRole('button', { name: 'Ver' }));
    expect(screen.getByTestId('onde')).toHaveTextContent('/materiais/custo?de=2026-10-01&ate=2026-11-02');
  });

  it('o custo sem nada no período', () => {
    abrir(<Custo dados={custo({ clientes: [], estados: [], locais: [], sem_preco: 0, total: 'R$ 0,00' })} />);
    expect(screen.getAllByText('Nada no período.')).toHaveLength(3);
    expect(screen.queryByText(/ficaram fora do total/)).toBeNull();
  });
});

function pedido(extra: Partial<Pedido> = {}): Pedido {
  return { id: 8, resumo: '5 un de Pano · acabou', status: 'aberto', situacao_rotulo: 'Aberto', selo: 'no_prazo', atrasado: false,
    local: 'CD 1', pessoa: 'Ana', criado_em: '02/11/2026 08:00', prazo: '03/11 08:00', quem_viu: null, visto_em: null,
    foto: '/materiais/pedidos/8/foto', pode_marcar: true, ...extra };
}

describe('os pedidos de insumo', () => {
  it('mostra o selo, o prazo, a foto e o "visto" como a antiga', async () => {
    const dados: DadosDosPedidos = { pedidos: [pedido(), pedido({ id: 9, status: 'visto', situacao_rotulo: 'Visto', selo: 'visto',
      prazo: null, quem_viu: 'Gestor', visto_em: '02/11/2026 09:00', foto: null, pode_marcar: false }),
    pedido({ id: 10, selo: 'atrasada', atrasado: true, pode_marcar: false, foto: null })], links: LINKS };
    abrir(<Pedidos dados={dados} />, '/materiais/pedidos');
    expect(screen.getByText('Aberto', { selector: '.fc-dem-no_prazo' })).toBeInTheDocument();
    expect(screen.getByText('Aberto · atrasado')).toHaveClass('badge', 'fc-dem', 'fc-dem-atrasada');
    expect(screen.getByText('Visto')).toHaveClass('badge', 'text-bg-light');
    expect(screen.getAllByText('CD 1 · Ana · 02/11/2026 08:00 · prazo 03/11 08:00')).toHaveLength(2);
    expect(screen.getByText('CD 1 · Ana · 02/11/2026 08:00 · visto por Gestor em 02/11/2026 09:00')).toBeInTheDocument();
    // A foto continua servida pelo servidor (link normal).
    expect(screen.getByRole('link', { name: 'Ver foto' })).toHaveAttribute('href', '/materiais/pedidos/8/foto');
    expect(screen.getAllByRole('button', { name: /Marcar como visto/ })).toHaveLength(1);
    await userEvent.click(screen.getByRole('button', { name: /Marcar como visto/ }));
    await waitFor(() => expect(chamadas.map((c) => c.url)).toContain('/api/v1/materiais/pedidos/8/visto'));
  });

  it('sem pedido nenhum; a classe do selo', () => {
    abrir(<Pedidos dados={{ pedidos: [], links: LINKS }} />);
    expect(screen.getByText('Nenhum pedido de insumo.')).toBeInTheDocument();
    expect(classeDoPedido(pedido({ selo: 'visto' }))).toBe('text-bg-light');
    expect(classeDoPedido(pedido({ selo: 'atrasada' }))).toBe('fc-dem fc-dem-atrasada');
  });
});

describe('as telas abrem pelo seu pedaço do build', () => {
  it('o catálogo carrega sob demanda, dentro da casca', async () => {
    respostas['/api/v1/eu'] = { status: 200, corpo: {
      id: 1, nome: 'Admin', primeiro_nome: 'Admin', perfil: 'Administrador', papel: 'master', cliente: false,
      avisos_nao_lidos: 0, menu: [], csrf: 'x', versao: '1',
      links: { inicio: '/', avisos: '/avisos', trocar_senha: '/t', seguranca: '/s', sair: '/sair' } } };
    respostas['/api/v1/materiais/'] = { status: 200, corpo: catalogo() };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/materiais/']}><App /></MemoryRouter>
      </QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: 'Materiais e insumos' })).toBeInTheDocument();
    expect(document.querySelector('[data-tela-pronta="materiais"]')).not.toBeNull();
  });
});
