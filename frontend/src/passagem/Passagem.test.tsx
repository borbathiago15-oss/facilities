import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Passagem } from './Passagem';
import type { DadosDaPassagem, Modelo } from './tipos';

function modelo(id: number, area_id: number, nome: string, turnos: string[], perguntas: Modelo['perguntas']): Modelo {
  return { id, client_id: 1, nome, area_id, descricao: '', turnos: turnos.map((n) => ({ nome: n })), campos: [],
    atividades: [], perguntas, tipos_ocorrencia: [{ nome: 'Avaria' }], ativo: true };
}

function dados(extra: Partial<DadosDaPassagem> = {}): DadosDaPassagem {
  return {
    usuario: { nome: 'Ana Souza', perfil: 'Encarregado' },
    clients: [{ id: 1, nome: 'GL Armazém 1' }], client_id: 1, centro_custo: 'GL-01',
    configs: [
      modelo(7, 10, 'Expedição — rotina', ['1º Turno', '2º Turno'], [
        { nome: 'Doca limpa', codigo: 'doca', tipo: 'sim_nao', obrigatorio: true },
        { nome: 'Situação', codigo: 'sit', tipo: 'escolha', opcoes: ['NORMAL', 'CRÍTICO'] },
      ]),
      modelo(8, 20, 'Almoxarifado — rotina', ['Diurno'], [{ nome: 'Estoque contado', codigo: 'est', tipo: 'numero' }]),
    ],
    areas: [{ id: 10, nome: 'Expedição' }, { id: 20, nome: 'Almoxarifado' }],
    hoje: '2026-11-01',
    encerrados: { 7: { '2026-11-01': ['1º Turno'] } },
    anterior_inicial: 'area-10',
    anteriores: [
      { chave: 'area-10', turno: { turno: '1º Turno', data: '01/11', observacao: 'Doca travada' }, area: 'Expedição',
        autor: 'Mariana', tem_o_que_ler: true, ocorrencias: [], anexos: [] },
      { chave: 'area-20', turno: null },
    ],
    pendencias: [
      { id: 31, titulo: 'Devolução da NF 123', referencia: 'NF 123', descricao: '', origem_turno: '1º Turno',
        origem_data: '30/10', horas: 50, dias: 2, vencida: true, alta: true, passagens: 3, ultima_tentativa: null },
    ],
    links: { painel: '/passagem-de-turno/?client_id=1', trocar_contrato: '/novo/passagem-de-turno/turno?client_id=',
      ver_turno: '/novo/passagem-de-turno/turno/' },
    ...extra,
  };
}

function abrir(d = dados()) {
  return render(<MemoryRouter><Passagem dados={d} /></MemoryRouter>);
}

let chamadas: { url: string; init?: RequestInit }[] = [];
beforeEach(() => {
  chamadas = [];
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    chamadas.push({ url: String(url), init });
    if (String(url).includes('/api/tarefas-turno?')) return new Response('{"tarefas": []}', { status: 200 });
    if (String(url).endsWith('/api/turnos')) return new Response('{"id": 99, "pendencias_deixadas": 1}', { status: 201 });
    return new Response('{}', { status: 200 });
  });
});
afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

describe('nova passagem', () => {
  it('abre nas pendências, com o turno anterior da área e o turno ainda em aberto', () => {
    abrir();
    const aba = screen.getByRole('tab', { name: /Pendências/ });
    expect(aba).toHaveClass('ativa');
    expect(within(aba).getByText('1')).toHaveClass('dt-aba-n', 'ruim');
    expect(screen.getByText('aberta há 2 dias')).toBeVisible();
    expect(screen.getByText('passou por 3 turnos')).toBeVisible();
    expect(document.querySelector('[data-area="area-10"]')).not.toHaveAttribute('hidden');
    expect(document.querySelector('[data-area="area-20"]')).toHaveAttribute('hidden');
    // O 1º Turno já fechou hoje: abre no 2º, e o 1º diz que está encerrado.
    const turno = document.getElementById('diario-shift') as HTMLSelectElement;
    expect(turno.value).toBe('2º Turno');
    expect(screen.getByRole('option', { name: '1º Turno — já encerrado' })).toBeInTheDocument();
  });

  it('a área troca as perguntas e o bloco do turno anterior', async () => {
    abrir();
    await userEvent.click(screen.getByRole('tab', { name: /Passagem de turno/ }));
    expect(screen.getByText('Doca limpa')).toBeVisible();
    await userEvent.selectOptions(screen.getByLabelText('Área'), '20');
    expect(screen.queryByText('Doca limpa')).toBeNull();
    expect(screen.getByText('Estoque contado')).toBeVisible();
    expect(document.querySelector('[data-area="area-20"]')).not.toHaveAttribute('hidden');
    expect((document.getElementById('diario-shift') as HTMLSelectElement).value).toBe('Diurno');
  });

  it('linhas de pendência entram e saem; o semáforo escolhe com um toque', async () => {
    abrir(dados({ pendencias: [] }));
    expect(screen.getByText('Nenhuma pendência aberta neste contrato.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Nova pendência/ }));
    expect(document.querySelectorAll('.pending-row').length).toBe(1);
    await userEvent.click(document.querySelector('.pending-row button[data-remover]') as HTMLElement);
    expect(document.querySelectorAll('.pending-row').length).toBe(0);
    await userEvent.click(screen.getByRole('button', { name: 'CRÍTICO' }));
    expect(screen.getByRole('button', { name: 'CRÍTICO' })).toHaveClass('sel');
  });

  it('encerra com o corpo da tela antiga e leva ao painel com o recado', async () => {
    const ir = vi.fn();
    vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, assign: ir } as Location);
    abrir(dados({ pendencias: [] }));
    await userEvent.click(screen.getByLabelText('Concluído'));
    await userEvent.type(document.getElementById('diario-observacao')!, 'Tudo certo');
    await userEvent.click(screen.getByRole('button', { name: /Nova ocorrência/ }));
    await userEvent.type(document.querySelector('.o-desc') as HTMLElement, 'Pallet caído');
    await userEvent.click(screen.getByRole('button', { name: 'Encerrar turno' }));
    await waitFor(() => expect(ir).toHaveBeenCalledWith('/passagem-de-turno/?client_id=1'));
    const envio = chamadas.find((c) => c.url === '/passagem-de-turno/api/turnos')!;
    const corpo = JSON.parse(String(envio.init!.body));
    expect(corpo).toMatchObject({
      client_id: 1, configuracao_id: 7, data_turno: '2026-11-01', turno: '2º Turno', finalizar: true,
      observacao: 'Tudo certo', pendencias: [],
      dados: { sit: '', 'atividade:doca': { concluido: true, observacao: '' } },
      ocorrencias: [{ tipo: 'Avaria', referencia: '', descricao: 'Pallet caído', gravidade: 'normal' }],
    });
    expect(corpo.envio_id).toBeTruthy();
    expect(corpo.encerrado_no_aparelho).toBeTruthy();
    expect(JSON.parse(sessionStorage.getItem('fc-aviso')!).texto)
      .toBe('Passagem do 2º Turno de 01/11 encerrada. 1 pendência ficou para o próximo turno.');
  });

  it('sem sinal, guarda na fila do aparelho e diz que ainda não foi enviado', async () => {
    const guardar = vi.fn().mockResolvedValue({ id: 'f1' });
    window.TrinoFila = { novoId: () => 'id1', guardar, enviarAgora: () => {}, ehFalhaDeConexao: () => true };
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    try {
      abrir(dados({ pendencias: [] }));
      await userEvent.click(screen.getByRole('button', { name: 'Salvar rascunho' }));
      await screen.findByText(/Guardado neste aparelho\./);
      expect(guardar.mock.calls[0][0]).toMatchObject({ tipo: 'turno', turno_id: null,
        rotulo: 'Rascunho — Expedição — rotina, 2º Turno de 01/11' });
      expect(chamadas.find((c) => c.url === '/passagem-de-turno/api/turnos')).toBeUndefined();
      // A fila subiu o item: a caixa diz "Enviado" e leva à passagem (tela nova).
      window.dispatchEvent(new CustomEvent('trino-fila:enviado', { detail: { id: 'f1', turno_id: 42 } }));
      await screen.findByText(/Enviado\./);
      expect(screen.getByRole('link', { name: 'Ver a passagem' })).toHaveAttribute('href',
        '/passagem-de-turno/turno/42');
    } finally {
      delete window.TrinoFila;
    }
  });

  it('resolver a última pendência leva à aba da passagem', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('Liguei e resolvi');
    abrir();
    await userEvent.click(screen.getByRole('button', { name: 'Resolver' }));
    await waitFor(() => expect(screen.getByRole('tab', { name: /Passagem de turno/ })).toHaveClass('ativa'));
    const envio = chamadas.find((c) => c.url === '/passagem-de-turno/api/pendencias/31/resolver')!;
    expect(JSON.parse(String(envio.init!.body))).toEqual({ resolucao: 'Liguei e resolvi', data_turno: '2026-11-01',
      turno: '2º Turno', configuracao_id: 7 });
    expect(screen.getByText('Todas as pendências recebidas foram baixadas.')).toBeInTheDocument();
  });

  it('"Continua" mostra na hora o que se tentou, com o nome de quem tentou', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('Liguei para o CD');
    abrir();
    await userEvent.click(screen.getByRole('button', { name: 'Continua' }));
    await screen.findByText('Liguei para o CD');
    expect(screen.getByText('— Ana Souza, agora')).toBeInTheDocument();
  });

  it('a tarefa da gestão aparece antes das perguntas e pede confirmação ao encerrar', async () => {
    vi.mocked(globalThis.fetch).mockImplementation(async (url, init) => {
      chamadas.push({ url: String(url), init });
      return new Response(JSON.stringify({ tarefas: [{ id: 5, titulo: 'Conferir a câmara', forma_resposta: 'numero',
        status: 'pendente', descricao: '' }] }), { status: 200 });
    });
    const confirmar = vi.spyOn(window, 'confirm').mockReturnValue(false);
    abrir(dados({ pendencias: [] }));
    await screen.findByText('Conferir a câmara');
    expect(chamadas[0].url).toBe('/passagem-de-turno/api/tarefas-turno?client_id=1&configuracao_id=7' +
      '&data_turno=2026-11-01&turno=2%C2%BA%20Turno');
    await userEvent.click(screen.getByRole('button', { name: 'Encerrar turno' }));
    expect(confirmar).toHaveBeenCalledWith(expect.stringMatching(/^Há 1 tarefa da gestão sem resposta/));
    expect(chamadas.some((c) => c.url === '/passagem-de-turno/api/turnos')).toBe(false);
  });
});
