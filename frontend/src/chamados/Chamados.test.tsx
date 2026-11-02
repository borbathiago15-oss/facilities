import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { Lista, Novo, SeloPrazo, Ver, urlDaLista } from './Chamados';
import { Demandas, urlDaSituacao } from './Demandas';
import { Preventiva } from './Preventiva';
import type { DadosDaLista, DadosDaPreventiva, DadosDasDemandas, DadosDoChamado, ResumoDoChamado } from './tipos';

let chamadas: { url: string; init?: RequestInit }[] = [];
let respostas: Record<string, { status: number; corpo: unknown }> = {};
const PADRAO = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Feito.' }], destino: '/novo/chamados/7' } };
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

const PRI: [string, string][] = [['urgente', 'Urgente'], ['alta', 'Alta'], ['media', 'Média'], ['baixa', 'Baixa']];
const CAT: [string, string][] = [['eletrica', 'Elétrica'], ['outro', 'Outro']];

function resumo(extra: Partial<ResumoDoChamado> = {}): ResumoDoChamado {
  return { id: 7, numero: 'OS-00007', titulo: 'Torneira vazando', prioridade: 'alta', prioridade_rotulo: 'Alta',
    status: 'aberto', status_rotulo: 'Aberto', prazo_selo: { tipo: 'atrasado', perto: false, texto: 'atrasado há 2h' },
    atrasado: true, contrato: 'CD 1', area: 'Limpeza', local: 'Copa', categoria_rotulo: 'Hidráulica', responsavel: null, ...extra };
}

function lista(extra: Partial<DadosDaLista> = {}): DadosDaLista {
  return { chamados: [resumo()], cortada: false, por_pagina: 100, contratos: [{ id: 3, nome: 'CD 1' }, { id: 4, nome: 'CD 2' }],
    client_id: 3, visao: 'abertos', visoes: [['abertos', 'Em aberto'], ['todos', 'Todos']], prioridade: 'alta', categoria: '',
    prioridades: PRI, categorias: CAT, pode_abrir: true,
    numeros: { em_aberto: 4, atrasados: 1, aguardando_confirmacao: 0, dias: 30, pct_no_prazo: '66,7%', tempo_medio: '2,5 dias' }, ...extra };
}

function chamado(extra: Partial<DadosDoChamado> = {}): DadosDoChamado {
  return {
    chamado: { ...resumo(), client_id: 3, solicitante: 'Ana', aberto_em: '01/11/2026 08:00', responsavel_id: null,
      prazo: '02/11/2026 08:00', origem: 'manual', visita: null, pausa: null, descricao: 'Pinga', motivo_espera: '', solucao: '' },
    acoes: ['comentar', 'atribuir', 'prioridade', 'cancelar', 'iniciar'],
    tecnicos: [{ id: 11, nome: 'Caio', perfil: 'Técnico' }], prioridades: PRI,
    eventos: [{ tipo: 'aberto', autor: 'Ana', rotulo: 'abriu o chamado', quando: '01/11/2026 08:00', texto: '' }],
    anexos: [{ id: 5, nome: 'f.png', momento: 'antes', imagem: true, url: '/chamados/anexos/5' }],
    pode_anexar: true, consumos: [], ve_custo: true, materiais: [{ id: 2, nome: 'Fita', unidade: 'un' }], ...extra };
}

describe('a lista', () => {
  it('mostra os números, os selos e os links como a tela antiga', () => {
    abrir(<Lista dados={lista()} />, '/chamados/');
    expect(screen.getByText('66,7%')).toBeInTheDocument();
    expect(screen.getByText('2,5 dias')).toBeInTheDocument();
    expect(screen.getByText('atrasado').closest('a')).toHaveClass('ch-num', 'alerta');
    expect(screen.getByText('atrasado há 2h')).toHaveClass('ch-prazo', 'atrasado');
    expect(screen.getByText('Torneira vazando').closest('a')).toHaveAttribute('href', '/chamados/7');
    expect(screen.getByText('Torneira vazando').closest('a')).toHaveClass('ch-item', 'atrasado');
    expect(screen.getByText('sem responsável').tagName).toBe('EM');
    // As abas guardam o filtro; os números do topo só o contrato.
    expect(screen.getByRole('link', { name: 'Todos' })).toHaveAttribute('href', '/chamados/?client_id=3&visao=todos&prioridade=alta');
    expect(screen.getByRole('link', { name: 'Em aberto' })).toHaveClass('ativo');
    expect(screen.getByText('em aberto').closest('a')).toHaveAttribute('href', '/chamados/?client_id=3&visao=abertos');
    expect(screen.getByRole('link', { name: /Abrir chamado/ })).toHaveAttribute('href', '/chamados/novo?client_id=3');
  });

  it('o filtro vai ao endereço com o formulário inteiro, como o GET da antiga', async () => {
    abrir(<Lista dados={lista()} />, '/chamados/');
    await userEvent.selectOptions(screen.getByLabelText('Categoria'), 'eletrica');
    expect(screen.getByTestId('onde')).toHaveTextContent('/chamados/?client_id=3&prioridade=alta&categoria=eletrica&visao=abertos');
  });

  it('sem chamado, o texto de cada aba; quem só lê não vê "Abrir chamado"', () => {
    abrir(<Lista dados={lista({ chamados: [], visao: 'atrasados', pode_abrir: false })} />);
    expect(screen.getByText('Nenhum chamado atrasado.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Abrir chamado/ })).toBeNull();
  });

  it('a lista cortada avisa como a antiga', () => {
    abrir(<Lista dados={lista({ cortada: true })} />);
    expect(screen.getByText(/Mostrando os 100 chamados mais recentes/)).toBeInTheDocument();
  });

  it('o endereço da lista deixa de fora o vazio', () => {
    expect(urlDaLista([['client_id', null], ['visao', 'todos'], ['prioridade', '']])).toBe('/novo/chamados/?visao=todos');
  });
});

describe('os selos', () => {
  it('cada tipo de prazo tem a classe da antiga', () => {
    const { rerender } = render(<SeloPrazo selo={{ tipo: 'vence', perto: true, texto: 'vence em 2h' }} />);
    expect(screen.getByText('vence em 2h')).toHaveClass('ch-prazo', 'perto');
    rerender(<SeloPrazo selo={{ tipo: 'vence', perto: false, texto: 'vence 05/11 10:00' }} />);
    expect(screen.getByText('vence 05/11 10:00').className).toBe('ch-prazo');
    rerender(<SeloPrazo selo={{ tipo: 'ok', perto: false, texto: 'resolvido 01/11 10:00' }} />);
    expect(screen.getByText('resolvido 01/11 10:00')).toHaveClass('ch-prazo', 'ok');
    // "Aguardando": o relógio do prazo está parado (D8), sem vermelho nem ícone.
    rerender(<SeloPrazo selo={{ tipo: 'parado', perto: false, texto: 'prazo parado' }} />);
    expect(screen.getByText('prazo parado').className).toBe('ch-prazo');
    expect(document.querySelector('.ch-prazo i')).toBeNull();
    rerender(<SeloPrazo selo={null} />);
    expect(document.querySelector('.ch-prazo')).toBeNull();
  });
});

describe('abrir', () => {
  const dados = { contratos: [{ id: 3, nome: 'CD 1' }, { id: 4, nome: 'CD 2' }], client_id: null,
    areas: { 3: [{ id: 8, nome: 'Limpeza' }] }, prioridades: PRI, categorias: CAT };

  it('as áreas seguem o contrato escolhido; sem área, a caixa fica desligada', async () => {
    abrir(<Novo dados={dados} />, '/chamados/novo');
    const area = screen.getByLabelText(/Área \/ serviço/) as HTMLSelectElement;
    expect(screen.getByLabelText('Contrato')).toHaveValue('');
    expect(area).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText('Contrato'), '3');
    expect(screen.getByLabelText(/Área \/ serviço/)).not.toBeDisabled();
    expect(screen.getByRole('option', { name: 'Limpeza' })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Contrato'), '4');
    expect(screen.getByLabelText(/Área \/ serviço/)).toBeDisabled();
    expect(screen.getByLabelText('Categoria')).toHaveValue('outro');
    expect(screen.getByLabelText('Prioridade')).toHaveValue('media');
  });

  it('um contrato só já vem escolhido, sem "Escolha…"', () => {
    abrir(<Novo dados={{ ...dados, contratos: [{ id: 3, nome: 'CD 1' }] }} />);
    expect(screen.getByLabelText('Contrato')).toHaveValue('3');
    expect(screen.queryByRole('option', { name: 'Escolha…' })).toBeNull();
  });

  it('envia o formulário (com as fotos) e vai ao chamado com o recado', async () => {
    respostas['/api/v1/chamados/'] = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Chamado OS-00009 aberto.' }], destino: '/novo/chamados/9' } };
    abrir(<Novo dados={{ ...dados, client_id: 3 }} />, '/chamados/novo');
    await userEvent.type(screen.getByLabelText('O que está errado?'), 'Lâmpada');
    await userEvent.upload(screen.getByLabelText(/Fotos/), new File(['x'], 'a.png', { type: 'image/png' }));
    await userEvent.click(screen.getByRole('button', { name: 'Abrir chamado' }));
    await waitFor(() => expect(screen.getByTestId('onde')).toHaveTextContent('/chamados/9'));
    const corpo = chamadas[0].init!.body as FormData;
    expect(chamadas[0].url).toBe('/api/v1/chamados/');
    expect(corpo.get('client_id')).toBe('3');
    expect(corpo.get('titulo')).toBe('Lâmpada');
    // (o jsdom não põe no FormData o arquivo do ``upload``: basta o campo ir)
    expect(corpo.has('arquivo')).toBe(true);
  });
});

describe('o chamado', () => {
  it('mostra só as ações disponíveis, abertas como na antiga', () => {
    abrir(<Ver dados={chamado()} />);
    expect(screen.getByRole('button', { name: /Iniciar atendimento/ })).toBeInTheDocument();
    expect(screen.queryByText('Resolver')).toBeNull();
    expect(screen.getByText('Atribuir a um técnico').closest('details')).toHaveAttribute('open');
    expect(screen.getByText('Mudar prioridade').closest('details')).not.toHaveAttribute('open');
    expect(screen.getByRole('link', { name: 'Chamados' })).toHaveAttribute('href', '/chamados/?client_id=3');
    expect(screen.getByAltText('f.png').closest('a')).toHaveAttribute('href', '/chamados/anexos/5');
    expect(screen.getByText('Pinga')).toHaveClass('ch-desc');
  });

  it('sem ação, sem o cartão "O que fazer agora"', () => {
    abrir(<Ver dados={chamado({ acoes: [], pode_anexar: false, materiais: [] })} />);
    expect(screen.queryByText('O que fazer agora')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Anexar' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Lançar material' })).toBeNull();
  });

  it('a ação vai ao mesmo caminho da antiga, com o mesmo campo "acao"', async () => {
    respostas['/api/v1/chamados/7/acao'] = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Atribuído.' }], destino: '/novo/chamados/7' } };
    abrir(<Ver dados={chamado()} />, '/chamados/7');
    await userEvent.selectOptions(screen.getByLabelText('Responsável'), '11');
    await userEvent.click(screen.getByRole('button', { name: 'Atribuir' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    const corpo = chamadas[0].init!.body as FormData;
    expect(corpo.get('acao')).toBe('atribuir');
    expect(corpo.get('responsavel_id')).toBe('11');
  });

  it('a recusa do servidor aparece no topo', async () => {
    respostas['/api/v1/chamados/7/acao'] = { status: 400, corpo: { error: 'Escreva o comentário.' } };
    abrir(<Ver dados={chamado()} />, '/chamados/7');
    fireEvent.submit(screen.getByRole('button', { name: 'Comentar' }).closest('form')!);
    expect(await screen.findByText('Escreva o comentário.')).toBeInTheDocument();
  });

  it('o material vai à mesma ação do formulário antigo, de volta ao chamado', async () => {
    abrir(<Ver dados={chamado()} />, '/chamados/7');
    await userEvent.type(screen.getByLabelText('Quantidade'), '1,5');
    await userEvent.click(screen.getByRole('button', { name: 'Lançar material' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe('/api/v1/materiais/locais/3/consumo');
    const corpo = chamadas[0].init!.body as FormData;
    expect([corpo.get('material_id'), corpo.get('quantidade'), corpo.get('chamado_id'), corpo.get('voltar')]).toEqual(['2', '1,5', '7', 'chamado']);
  });

  it('a espera, a solução e o tempo parado como a antiga escreve', () => {
    const d = chamado({ acoes: ['retomar', 'resolver'] });
    d.chamado = { ...d.chamado, status: 'aguardando', motivo_espera: 'Peça', pausa: '1 h 5 min aguardando (somado ao prazo)', origem: 'preventiva' };
    abrir(<Ver dados={d} />);
    expect(screen.getByText('Aguardando:').parentElement).toHaveTextContent('Aguardando: Peça');
    expect(screen.getByText('1 h 5 min aguardando (somado ao prazo)')).toBeInTheDocument();
    expect(screen.getByText('Manutenção preventiva programada')).toBeInTheDocument();
    expect(screen.queryByText(/Para fazer esta preventiva/)).toBeNull();      // só aberta ou em atendimento
    expect(screen.getByText('Resolver').closest('details')).toHaveAttribute('open');
  });
});

describe('as demandas', () => {
  const dados: DadosDasDemandas = {
    itens: [{ tipo: 'chamado', tipo_rotulo: 'Chamado', situacao: 'atrasada', situacao_rotulo: 'Atrasada', numero: 'OS-00007',
      titulo: 'Torneira', local: 'CD 1', estado: 'Aberto', responsavel: 'Caio', prazo: '01/11 08:00', link: '/novo/chamados/7' },
    { tipo: 'insumo', tipo_rotulo: 'Pedido de insumo', situacao: 'sem_prazo', situacao_rotulo: 'Sem prazo', numero: '',
      titulo: 'Papel', local: 'CD 1', estado: 'Novo', responsavel: '', prazo: null, link: '/materiais/pedidos' }],
    locais: [{ id: 3, nome: 'CD 1' }], local: null, tipo: '', situacao: 'atrasada',
    tipos: [['chamado', 'Chamado'], ['insumo', 'Pedido de insumo']],
    situacoes: [['atrasada', 'Atrasada'], ['sem_prazo', 'Sem prazo']], contagem: { atrasada: 1, sem_prazo: 1 },
    links: { cobrancas: '/cobrancas/' } };

  it('os itens levam à tela nova onde já existe, e às antigas nas outras', () => {
    abrir(<Demandas dados={dados} />);
    expect(screen.getByText('Torneira').closest('a')).toHaveAttribute('href', '/chamados/7');
    expect(screen.getByText('Papel').closest('a')).toHaveAttribute('href', '/materiais/pedidos');
    expect(screen.getByText('prazo 01/11 08:00')).toBeInTheDocument();
    expect(screen.getByText('CD 1 · Aberto · Caio')).toBeInTheDocument();
    expect(screen.getAllByText('Atrasada')[0].closest('a')).toHaveClass('border-primary');
  });

  it('os cartões e o filtro vão aos endereços da antiga', async () => {
    expect(urlDaSituacao('hoje', null, '')).toBe('/novo/demandas/?situacao=hoje&tipo=');
    expect(urlDaSituacao('hoje', 3, 'chamado')).toBe('/novo/demandas/?situacao=hoje&local=3&tipo=chamado');
    abrir(<Demandas dados={dados} />, '/demandas/');
    await userEvent.selectOptions(screen.getByLabelText('Tipo'), 'insumo');
    await userEvent.click(screen.getByRole('button', { name: 'Filtrar' }));
    expect(screen.getByTestId('onde')).toHaveTextContent('/demandas/?local=&tipo=insumo&situacao=atrasada');
  });
});

describe('a preventiva', () => {
  function prev(extra: Partial<DadosDaPreventiva> = {}): DadosDaPreventiva {
    return {
      local: { id: 3, nome: 'CD 1' },
      planos: [{ id: 5, nome: 'Filtro', ativo: true, ponto_id: 2, ponto: 'Copa · Pia', equipamento_id: null, equipamento: null,
        modelo_id: 9, modelo: 'Limpeza', intervalo_dias: 30, antecedencia_dias: 2, proxima_em: '10/11/2026',
        proxima_em_iso: '2026-11-10', prioridade: 'alta', prioridade_rotulo: 'Alta', responsavel_id: 11, responsavel: 'Caio',
        ciclos: [{ vencimento: '10/10/2026', chamado: { url: '/novo/chamados/7', numero: 'OS-00007', status_rotulo: 'Fechado' } },
          { vencimento: '10/09/2026', chamado: null }] }],
      modelos: [{ id: 9, nome: 'Limpeza' }], pontos: [{ id: 1, rotulo: 'Hall · Porta' }, { id: 2, rotulo: 'Copa · Pia' }],
      equipamentos: [], tecnicos: [{ id: 11, nome: 'Caio' }], prioridades: PRI, hoje: '2026-11-02', pode_montar: true,
      links: { pontos: '/novo/cadastros/locais/3', checklists: '/novo/rotas/locais/3' }, ...extra };
  }

  it('mostra o plano como a antiga e os campos de editar já preenchidos', () => {
    abrir(<Preventiva dados={prev()} />);
    expect(screen.getByText('Copa · Pia · a cada 30 dia(s)')).toBeInTheDocument();
    expect(screen.getByText('10/11/2026').tagName).toBe('STRONG');
    expect(screen.getByText('Checklist: Limpeza · Alta · Caio')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'OS-00007' })).toHaveAttribute('href', '/chamados/7');
    expect(screen.getByText(/sem ordem/)).toBeInTheDocument();
    expect(document.getElementById('ponto5')).toHaveValue('2');
    expect(document.getElementById('prox5')).toHaveValue('2026-11-10');
    expect(document.getElementById('pri5')).toHaveValue('alta');
    expect(document.getElementById('proxnovo')).toHaveValue('2026-11-02');
    expect(document.getElementById('prinovo')).toHaveValue('media');
    expect(document.getElementById('intnovo')).toHaveValue(30);
  });

  it('desativar manda o mesmo campo "ativo" da antiga', async () => {
    abrir(<Preventiva dados={prev()} />, '/preventiva/locais/3');
    fireEvent.submit(screen.getByRole('button', { name: 'Desativar plano' }).closest('form')!);
    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe('/api/v1/preventiva/5');
    expect((chamadas[0].init!.body as FormData).get('ativo')).toBe('0');
  });

  it('sem ponto ou sem checklist publicado, o aviso no lugar do "Novo plano"', () => {
    abrir(<Preventiva dados={prev({ modelos: [], planos: [] })} />);
    expect(screen.getByText(/precisa de pelo menos um ponto com QR/)).toBeInTheDocument();
    expect(screen.queryByText('Novo plano')).toBeNull();
    expect(screen.getByText('Nenhum plano preventivo ainda.')).toBeInTheDocument();
  });
});

describe('as telas abrem pelo seu pedaço do build', () => {
  it('"/chamados/novo" é a tela de abrir (e não um chamado de id "novo")', async () => {
    respostas['/api/v1/eu'] = { status: 200, corpo: {
      id: 1, nome: 'Admin', primeiro_nome: 'Admin', perfil: 'Administrador', papel: 'master', cliente: false,
      avisos_nao_lidos: 0, menu: [], csrf: 'x', versao: '1',
      links: { inicio: '/', avisos: '/avisos', trocar_senha: '/t', seguranca: '/s', sair: '/sair' } } };
    respostas['/api/v1/chamados/novo?client_id=3'] = { status: 200, corpo: { contratos: [{ id: 3, nome: 'CD 1' }], areas: {},
      client_id: 3, prioridades: PRI, categorias: CAT } };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/chamados/novo?client_id=3']}><App /></MemoryRouter>
      </QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: 'Abrir chamado' })).toBeInTheDocument();
    expect(chamadas.map((c) => c.url)).toContain('/api/v1/chamados/novo?client_id=3');
  });
});
