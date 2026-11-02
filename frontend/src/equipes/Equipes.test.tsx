import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { Equipe, Mes } from './Equipe';
import { Visitas, classeDoSelo } from './Visitas';
import type { DadosDaEquipe, DadosDasVisitas, DadosDoMes, VisitaRecente } from './tipos';

let chamadas: { url: string; init?: RequestInit }[] = [];
let respostas: Record<string, { status: number; corpo: unknown }> = {};
const PADRAO = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Feito.' }], destino: '/novo/equipes/locais/3' } };
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

const DIAS: [string, string][] = [['1', 'Seg'], ['2', 'Ter'], ['3', 'Qua'], ['4', 'Qui'], ['5', 'Sex'], ['6', 'Sáb'], ['7', 'Dom']];

function equipe(extra: Partial<DadosDaEquipe> = {}): DadosDaEquipe {
  return {
    local: { id: 3, nome: 'CD 1' }, hoje: '2026-11-02', dias: DIAS,
    funcionarios: [
      { id: 5, nome: 'Ana', funcao: 'ASG', matricula: '123', user_id: 9, usa_app: true, ativo: true },
      { id: 6, nome: 'Zé', funcao: '', matricula: '', user_id: null, usa_app: false, ativo: false }],
    postos: [
      { id: 7, nome: 'Limpeza', hora_inicio: '07:00', hora_fim: '15:00', rota_id: 2, rota: 'Manhã', ativo: true },
      { id: 8, nome: 'Portaria', hora_inicio: '22:00', hora_fim: '06:00', rota_id: null, rota: null, ativo: false }],
    escalas: [{ id: 11, funcionario: 'Ana', posto: 'Limpeza', dias: 'Seg Qua Sex ', data_inicio: '01/10/2026', data_fim: '31/12/2026' }],
    rotas: [{ id: 2, nome: 'Manhã' }], logins: [{ id: 9, nome: 'Ana Souza', email: 'ana@x.com' }],
    pode_montar: true,
    links: { local: '/novo/rotas/locais/3', mes: '/novo/equipes/locais/3/mes', visitas: '/novo/visitas/locais/3' },
    ...extra };
}

describe('a equipe do local', () => {
  it('mostra os funcionários, os postos e a escala como a antiga', () => {
    abrir(<Equipe dados={equipe()} />);
    expect(screen.getByText('matrícula 123')).toBeInTheDocument();
    expect(screen.getByText('usa o aplicativo')).toBeInTheDocument();
    expect(screen.getByText('sem login')).toBeInTheDocument();
    expect(screen.getByText('desligado')).toBeInTheDocument();
    expect(screen.getByText('07:00 às 15:00 · rota "Manhã"')).toBeInTheDocument();
    expect(screen.getByText('22:00 às 06:00')).toBeInTheDocument();
    expect(screen.getByText('Limpeza · Seg Qua Sex · desde 01/10/2026 até 31/12/2026')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Conferir o mês/ })).toHaveAttribute('href', '/equipes/locais/3/mes');
    expect(screen.getByRole('link', { name: 'CD 1' })).toHaveAttribute('href', '/rotas/locais/3');
    // Os campos de editar já preenchidos; os de cadastrar com os padrões.
    expect(document.getElementById('fu5')).toHaveValue('9');
    expect(document.getElementById('fu6')).toHaveValue('');
    expect(document.getElementById('pr7')).toHaveValue('2');
    expect(document.getElementById('pi7')).toHaveValue('07:00');
    expect(document.getElementById('npi')).toHaveValue('07:00');
    expect(document.getElementById('ef11')).toHaveValue('2026-11-02');
    expect(document.getElementById('esi')).toHaveValue('2026-11-02');
    // A escala só oferece quem está ativo; seg a sex já marcados.
    expect([...document.querySelectorAll('#esf option')].map((o) => o.textContent)).toEqual(['Ana']);
    expect([...document.querySelectorAll('#esp option')].map((o) => o.textContent)).toEqual(['Limpeza (07:00–15:00)']);
    expect([...document.querySelectorAll('input[type=checkbox]:checked')].map((i) => i.getAttribute('name')))
      .toEqual(['dia_1', 'dia_2', 'dia_3', 'dia_4', 'dia_5']);
    expect(screen.getByRole('button', { name: 'Desligar' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Reativar' })).toHaveLength(2);   // o Zé e a Portaria
  });

  it('quem só lê não recebe os formulários; vazio, convida a cadastrar', () => {
    const { unmount } = abrir(<Equipe dados={equipe({ pode_montar: false })} />);
    expect(screen.queryByText('Cadastrar funcionário')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Encerrar' })).toBeNull();
    unmount();
    abrir(<Equipe dados={equipe({ funcionarios: [], postos: [], escalas: [] })} />);
    expect(screen.getByText('Nenhum funcionário ainda.')).toBeInTheDocument();
    expect(screen.getByText('Ninguém escalado ainda.')).toBeInTheDocument();
    expect(screen.getByText('Cadastrar funcionário').closest('details')).toHaveAttribute('open');
    expect(screen.queryByText('Lançar escala')).toBeNull();
  });

  it('envia o formulário ao mesmo caminho da antiga e segue o destino com o recado', async () => {
    respostas['/api/v1/equipes/escalas/11/encerrar'] = { status: 200, corpo: {
      recados: [{ tipo: 'success', texto: 'Escala de Ana encerrada em 10/11/2026.' }], destino: '/novo/equipes/locais/3' } };
    abrir(<Equipe dados={equipe()} />, '/equipes/locais/3');
    await userEvent.click(screen.getByRole('button', { name: 'Encerrar' }));
    await waitFor(() => expect(chamadas.map((c) => c.url)).toContain('/api/v1/equipes/escalas/11/encerrar'));
    const corpo = chamadas.find((c) => c.url.endsWith('/encerrar'))!.init!.body as FormData;
    expect(corpo.get('data_fim')).toBe('2026-11-02');
    expect(screen.getByTestId('onde')).toHaveTextContent('/equipes/locais/3');
  });

  it('sem sinal, a frase aparece na própria tela', async () => {
    vi.mocked(globalThis.fetch).mockRejectedValueOnce(new TypeError('falhou'));
    abrir(<Equipe dados={equipe()} />, '/equipes/locais/3');
    await userEvent.type(document.getElementById('npn')!, 'Recepção');
    await userEvent.click(document.getElementById('npn')!.closest('form')!.querySelector('button')!);
    expect(await screen.findByText(/Sem conexão com o servidor/)).toBeInTheDocument();
  });

  it('a recusa volta ao endereço da tela nova (onde o recado aparece)', async () => {
    respostas['/api/v1/equipes/locais/3/funcionarios'] = { status: 400, corpo: {
      recados: [{ tipo: 'danger', texto: 'Informe o nome do funcionário.' }], destino: '/novo/equipes/locais/3',
      error: 'Informe o nome do funcionário.' } };
    abrir(<Equipe dados={equipe()} />, '/equipes/locais/3');
    await userEvent.type(document.getElementById('nfn')!, 'x');
    await userEvent.click(document.getElementById('nfn')!.closest('form')!.querySelector('button')!);
    const corpo = chamadas.find((c) => c.url.endsWith('/funcionarios'))!.init!.body as FormData;
    expect(corpo.get('nome')).toBe('x');
    await waitFor(() => expect(screen.getByTestId('onde')).toHaveTextContent('/equipes/locais/3'));
  });
});

function mes(extra: Partial<DadosDoMes> = {}): DadosDoMes {
  return {
    local: { id: 3, nome: 'CD 1' }, mes: '11/2026', m: '2026-11', anterior: '2026-10', seguinte: '2026-12',
    totais: { previstos: 4, lancados: 2, faltas: 1, cobertas: 1 }, dias: [1, 2, 3],
    linhas: [{ funcionario: 'Ana', posto: 'Limpeza', celulas: [
      { tipo: 'coberta', letra: 'C', titulo: 'Faltou; cobriu Mariana (atestado)' },
      { tipo: 'pendente', letra: '·', titulo: 'Escalado, sem presença lançada' },
      { tipo: 'previsto', letra: '○', titulo: 'Escalado (dia ainda não chegou)' }] }],
    links: { equipe: '/novo/equipes/locais/3' }, ...extra };
}

describe('a grade do mês', () => {
  it('mostra as letras e os títulos da antiga, e navega entre os meses', async () => {
    abrir(<Mes dados={mes()} />, '/equipes/locais/3/mes');
    expect(screen.getByRole('heading', { name: 'Escala e presença · 11/2026' })).toBeInTheDocument();
    expect(screen.getByTitle('Faltou; cobriu Mariana (atestado)')).toHaveClass('fc-pres', 'fc-pres-coberta');
    expect(screen.getByTitle('Escalado (dia ainda não chegou)')).toHaveClass('text-muted', 'small');
    expect(document.querySelectorAll('tbody td')).toHaveLength(3);
    await userEvent.click(screen.getByRole('link', { name: /Mês anterior/ }));
    expect(screen.getByTestId('onde')).toHaveTextContent('/equipes/locais/3/mes?m=2026-10');
  });

  it('sem escala, a linha vazia ocupa a tabela toda', () => {
    abrir(<Mes dados={mes({ linhas: [] })} />);
    expect(screen.getByText('Nenhuma escala neste mês.')).toHaveAttribute('colspan', '4');
  });
});

function visitas(extra: Partial<DadosDasVisitas> = {}): DadosDasVisitas {
  return {
    local: { id: 3, nome: 'CD 1' }, modelos: [{ id: 4, nome: 'Qualidade' }, { id: 5, nome: 'Limpeza' }],
    programadas: [
      { id: 21, nome: 'Semanal', ativo: true, modelo_id: 5, modelo: 'Limpeza', intervalo_dias: 7, proxima_em: '05/11/2026',
        proxima_em_iso: '2026-11-05', supervisor_id: 9, supervisor: 'Sueli' },
      { id: 22, nome: 'Parada', ativo: false, modelo_id: 4, modelo: 'Qualidade', intervalo_dias: 30, proxima_em: '01/12/2026',
        proxima_em_iso: '2026-12-01', supervisor_id: null, supervisor: null }],
    recentes: [{ id: 31, nome: 'Semanal', vencimento: '29/10/2026', quem_fez: 'Sueli', status: 'feita', situacao_rotulo: 'Feita',
      n_nao_conformes: 2, url: '/app/visitas/31' }],
    supervisores: [{ id: 9, nome: 'Sueli', perfil: 'Supervisor' }], hoje: '2026-11-02', pode_montar: true,
    links: { checklists: '/novo/rotas/locais/3' }, ...extra };
}

describe('as visitas do local', () => {
  it('mostra a programação e as recentes como a antiga', () => {
    abrir(<Visitas dados={visitas()} />);
    expect(screen.getByText('Limpeza · a cada 7 dia(s) · Sueli')).toBeInTheDocument();
    expect(screen.getByText('Qualidade · a cada 30 dia(s) · qualquer supervisor')).toBeInTheDocument();
    expect(screen.getByText('05/11/2026').tagName).toBe('STRONG');
    expect(screen.queryByText('01/12/2026')).toBeNull();
    expect(screen.getByText('desativada')).toBeInTheDocument();
    expect(screen.getByText('Feita · 2 não conforme(s)')).toHaveClass('badge', 'text-bg-warning');
    // A visita em si é do aplicativo antigo: link normal, fora do roteador.
    expect(screen.getByText('até 29/10/2026 · Sueli').closest('a')).toHaveAttribute('href', '/app/visitas/31');
    expect(document.getElementById('vm21')).toHaveValue('5');
    expect(document.getElementById('vs21')).toHaveValue('9');
    expect(document.getElementById('vs22')).toHaveValue('');
    expect(document.getElementById('vpnova')).toHaveValue('2026-11-02');
    expect(document.getElementById('vinova')).toHaveValue(7);
  });

  it('sem checklist publicado, avisa e não oferece programar', () => {
    abrir(<Visitas dados={visitas({ modelos: [], programadas: [], recentes: [] })} />);
    expect(screen.getByText(/precisa de um checklist publicado/)).toBeInTheDocument();
    expect(screen.queryByText('Programar visita')).toBeNull();
    expect(screen.getByText('Nenhuma visita ainda.')).toBeInTheDocument();
  });

  it('a cor do selo segue a situação', () => {
    const v = (status: string, n = 0) => ({ status, n_nao_conformes: n } as VisitaRecente);
    expect(classeDoSelo(v('feita', 1))).toBe('text-bg-warning');
    expect(classeDoSelo(v('feita'))).toBe('text-bg-success');
    expect(classeDoSelo(v('perdida'))).toBe('text-bg-danger');
    expect(classeDoSelo(v('prevista'))).toBe('text-bg-light');
  });

  it('desativar envia o "ativo" ao mesmo caminho da antiga', async () => {
    abrir(<Visitas dados={visitas()} />, '/visitas/locais/3');
    await userEvent.click(screen.getByRole('button', { name: 'Desativar' }));
    await waitFor(() => expect(chamadas.map((c) => c.url)).toContain('/api/v1/visitas/programadas/21'));
    expect((chamadas.find((c) => c.url.endsWith('/21'))!.init!.body as FormData).get('ativo')).toBe('0');
  });
});

describe('as telas abrem pelo seu pedaço do build', () => {
  it('a equipe do local carrega sob demanda, dentro da casca', async () => {
    respostas['/api/v1/eu'] = { status: 200, corpo: {
      id: 1, nome: 'Admin', primeiro_nome: 'Admin', perfil: 'Administrador', papel: 'master', cliente: false,
      avisos_nao_lidos: 0, menu: [], csrf: 'x', versao: '1',
      links: { inicio: '/', avisos: '/avisos', trocar_senha: '/t', seguranca: '/s', sair: '/sair' } } };
    respostas['/api/v1/equipes/locais/3'] = { status: 200, corpo: equipe() };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/equipes/locais/3']}><App /></MemoryRouter>
      </QueryClientProvider>);
    expect(await screen.findByRole('heading', { name: 'Equipe · CD 1' })).toBeInTheDocument();
    expect(document.querySelector('[data-tela-pronta="equipe-local"]')).not.toBeNull();
  });
});
