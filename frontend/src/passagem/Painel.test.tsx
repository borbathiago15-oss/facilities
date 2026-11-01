import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Painel } from './Painel';
import type { DadosDoPainel } from './tipos';

function dados(extra: Partial<DadosDoPainel> = {}): DadosDoPainel {
  return {
    clients: [{ id: 1, nome: 'GL Armazém 1' }, { id: 2, nome: 'CD Norte' }], client_id: 1,
    periodo: '7d', turno_sel: 'todos', periodos: [['hoje', 'Hoje'], ['7d', 'Últimos 7 dias'], ['custom', 'Personalizado']],
    area_sel: 0, todas_as_areas: 0, de: '', ate: '', hoje: '2026-11-01',
    dados: {
      periodo_label: 'Últimos 7 dias', inicio: '26/10/2026', fim: '01/11/2026', turno: 'todos', n_turnos: 1,
      turnos_disponiveis: ['1º Turno', '2º Turno'], areas_disponiveis: [{ id: 10, nome: 'Expedição' }],
      aderencia: { pct: 94.7, cumpridas: 18, exigidas: 19, faixa: 'alerta', meta: 95 },
      resolucao: { pct: null, abertas: 0, resolvidas: 0, faixa: 'neutro' },
      n_criticas: 1,
      indice_ocorrencias: { valor: 2, delta: 0.5, turnos: 1, ocorrencias: 2 },
      pareto: [], turnos_comparativo: [], burndown: { labels: ['31/10', '01/11'], criadas: [0, 1], resolvidas: [0, 0] },
      rotinas: [{ codigo: 'doca', nome: 'Doca limpa', exigida: 19, cumprida: 18, pct: 94.7, faixa: 'alerta' }],
      ocorrencias: [
        { id: 5, tipo: 'Avaria', referencia: 'NF 9', descricao: 'Pallet caído', gravidade: 'critica',
          quando: { dia: '01/11', turno: '1º Turno' }, chamado: null },
        { id: 6, tipo: 'Atraso', referencia: '', descricao: 'Caminhão', gravidade: 'normal',
          quando: { dia: '01/11', turno: '1º Turno' }, chamado: { id: 3, numero: 'OS-00003', status_rotulo: 'Aberto', url: '/chamados/3' } },
      ],
      criticas: [{ id: 31, titulo: 'Devolução', descricao: '', prioridade: 'alta', alta: true, vencida: false, horas: 0, dias: 0 }],
    },
    turnos: [{ id: 9, data: '01/11/2026', area: 'Expedição', turno: '1º Turno', status: 'encerrado' }],
    modelos: [{ id: 7, nome: 'Expedição — rotina', turnos: [{ nome: '1º Turno' }, { nome: '2º Turno' }] }],
    pode_gravar: true, pode_chamado: true, pode_ver_chamado: true, e_gestao: true, pode_configurar: true,
    nome_do_sistema: 'Trino Facilities',
    links: { nova_passagem: '/novo/passagem-de-turno/turno?client_id=1', relatorio: '/novo/passagem-de-turno/relatorio-mensal?client_id=1',
      configurar: '/novo/passagem-de-turno/configuracao?client_id=1', ver_turno: '/novo/passagem-de-turno/turno/' },
    ...extra,
  };
}

function Endereco() {
  const l = useLocation();
  return <output data-testid="endereco">{l.search}</output>;
}

function abrir(d = dados()) {
  return render(<MemoryRouter initialEntries={['/passagem-de-turno']}><Routes>
    <Route path="*" element={<><Painel dados={d} /><Endereco /></>} />
  </Routes></MemoryRouter>);
}

let chamadas: { url: string; init?: RequestInit }[] = [];
let recarregar: ReturnType<typeof vi.fn>;
beforeEach(() => {
  chamadas = [];
  recarregar = vi.fn();
  vi.spyOn(window, 'alert').mockImplementation(() => {});
  vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, reload: recarregar, assign: vi.fn() } as Location);
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    chamadas.push({ url: String(url), init });
    return new Response('{"id": 1}', { status: 201 });
  });
});
afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

describe('painel', () => {
  it('mostra os números como a tela antiga', () => {
    abrir();
    expect(document.querySelector('[data-tela-pronta="painel"]')).toBeInTheDocument();
    expect(screen.getByText('TRINO FACILITIES')).toBeInTheDocument();
    expect(document.querySelector('#dopHero')!.textContent).toContain('94,7%');
    expect(screen.getByText('Atenção', { selector: '.dop-tag' })).toBeInTheDocument();
    expect(screen.getByText(/18 de 19 atividades/)).toBeInTheDocument();
    expect(screen.getByText(/▲ 0,50 vs. janela anterior/)).toBeInTheDocument();
    expect(screen.getByText('agora')).toBeInTheDocument();
    expect(screen.getByText('últimos 2 dias')).toBeInTheDocument();
    expect(document.querySelector('.pg-recorte')!.textContent).toContain('GL Armazém 1 · últimos 7 dias');
    // A ocorrência que já virou chamado mostra a OS; a outra, o botão.
    expect(screen.getByRole('link', { name: /Ver OS-00003/ })).toHaveAttribute('href', '/chamados/3');
    expect(screen.getAllByRole('button', { name: /Abrir chamado/ })).toHaveLength(1);
    expect(screen.getByRole('link', { name: 'abrir' })).toHaveAttribute('href', '/novo/passagem-de-turno/turno/9');
    expect(screen.getByRole('link', { name: /Nova passagem/ })).toHaveAttribute('href', '/novo/passagem-de-turno/turno?client_id=1');
  });

  it('quem só lê não recebe as ações', () => {
    abrir(dados({ pode_gravar: false, pode_chamado: false, e_gestao: false, pode_configurar: false }));
    expect(screen.queryByRole('link', { name: /Nova passagem/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Abrir chamado/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Deixar pendência/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'marcar resolvida' })).toBeNull();
    expect(screen.queryByRole('link', { name: /Configurar/ })).toBeNull();
    // A OS já aberta continua à vista (é leitura).
    expect(screen.getByRole('link', { name: /Ver OS-00003/ })).toBeInTheDocument();
  });

  it('o filtro aplica na troca, com os campos da tela antiga; o personalizado espera o Aplicar', async () => {
    abrir();
    await userEvent.selectOptions(screen.getByLabelText('Turno'), '2º Turno');
    expect(screen.getByTestId('endereco').textContent)
      .toBe('?client_id=1&periodo=7d&de=&ate=&area_id=0&turno=2%C2%BA+Turno');
    await userEvent.selectOptions(screen.getByLabelText('Período'), 'custom');
    expect(document.querySelector<HTMLElement>('.dop-custom')!.hidden).toBe(false);
    expect(screen.getByTestId('endereco').textContent).toContain('turno=2%C2%BA+Turno');
    await userEvent.type(screen.getByLabelText('De'), '2026-10-01');
    await userEvent.type(screen.getByLabelText('Até'), '2026-10-15');
    await userEvent.click(screen.getByRole('button', { name: 'Aplicar' }));
    expect(screen.getByTestId('endereco').textContent)
      .toBe('?client_id=1&periodo=custom&de=2026-10-01&ate=2026-10-15&area_id=0&turno=todos');
  });

  it('a tarefa para um turno vai para a API de sempre', async () => {
    abrir();
    await userEvent.click(screen.getByRole('button', { name: /Tarefa para um turno/ }));
    expect(screen.getByLabelText('Turno', { selector: '#tt-turno' })).toHaveValue('1º Turno');
    await userEvent.click(screen.getByRole('button', { name: 'Atribuir ao turno' }));
    expect(chamadas).toHaveLength(0);
    await userEvent.type(screen.getByLabelText('O que precisa ser feito'), 'Conferir a câmara');
    await userEvent.selectOptions(screen.getByLabelText('Como o turno deve responder'), 'numero');
    await userEvent.click(screen.getByRole('button', { name: 'Atribuir ao turno' }));
    await waitFor(() => expect(recarregar).toHaveBeenCalled());
    expect(chamadas[0].url).toBe('/passagem-de-turno/api/tarefas-turno');
    expect(JSON.parse(String(chamadas[0].init!.body))).toEqual({ client_id: 1, configuracao_id: '7',
      data_turno: '2026-11-01', turno: '1º Turno', titulo: 'Conferir a câmara', descricao: '', forma_resposta: 'numero' });
  });

  it('mostra o recado deixado pela passagem encerrada', () => {
    sessionStorage.setItem('fc-aviso', JSON.stringify({ texto: 'Passagem encerrada.', tipo: 'success' }));
    abrir();
    expect(document.querySelector('#fc-aviso-js .alert-success')!.textContent).toBe('Passagem encerrada.');
  });
});
