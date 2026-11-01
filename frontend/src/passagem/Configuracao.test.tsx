import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Configuracao } from './Configuracao';
import type { DadosDaConfiguracao, Modelo } from './tipos';

const MODELO: Modelo = {
  id: 7, client_id: 1, nome: 'Expedição — rotina', area_id: 10, descricao: 'Do turno',
  turnos: [{ nome: '1º Turno' }], campos: [], atividades: [],
  perguntas: [{ nome: 'Doca limpa', codigo: 'doca', tipo: 'sim_nao', obrigatorio: true },
    { nome: 'Situação', codigo: 'sit', tipo: 'escolha', obrigatorio: false, opcoes: ['Normal', 'Crítico'] }],
  tipos_ocorrencia: [{ nome: 'Avaria' }], ativo: true,
};

function dados(extra: Partial<DadosDaConfiguracao> = {}): DadosDaConfiguracao {
  return {
    clients: [{ id: 1, nome: 'GL Armazém 1' }], client_id: 1, configs: [MODELO],
    areas: [{ id: 10, nome: 'Expedição', ativo: true, modelos: 1 }, { id: 11, nome: 'Velha', ativo: false, modelos: 0 }],
    usos: { 7: 3 }, editar: null,
    modelos_prontos: [{ chave: 'limpeza', area: 'Limpeza e conservação', turnos: ['Diurno', 'Noturno'] }],
    recados: [],
    links: { painel: '/novo/passagem-de-turno/?client_id=1', aqui: '/novo/passagem-de-turno/configuracao',
      modelos_prontos: '/passagem-de-turno/modelos-prontos' },
    ...extra,
  };
}

let chamadas: { url: string; init?: RequestInit }[] = [];
let ir: ReturnType<typeof vi.fn>;
beforeEach(() => {
  chamadas = [];
  ir = vi.fn();
  vi.spyOn(window, 'alert').mockImplementation(() => {});
  vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, assign: ir, reload: vi.fn() } as Location);
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    chamadas.push({ url: String(url), init });
    return new Response('{"id": 7, "nome": "Expedição — rotina"}', { status: 200 });
  });
});
afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

function abrir(d = dados()) {
  return render(<MemoryRouter><Configuracao dados={d} /></MemoryRouter>);
}

describe('configuração dos modelos', () => {
  it('abre o primeiro modelo, com o aviso de uso, e só as áreas ativas', () => {
    abrir();
    expect(screen.getByLabelText('Nome do modelo')).toHaveValue('Expedição — rotina');
    expect(document.getElementById('cfg-aviso-uso')!.textContent).toMatch(/já foi usado em 3 turnos/);
    expect(document.querySelector('.cf-item.ativo-sel')).toHaveAttribute('data-usos', '3');
    expect(screen.getByLabelText('Área')).toHaveValue('10');
    expect(screen.queryByRole('option', { name: 'Velha' })).toBeNull();
    expect(screen.getByText('reativar')).toBeInTheDocument();
    // As opções da escolha só na pergunta de escolha.
    const caixas = document.querySelectorAll<HTMLElement>('.cfg-p-opcoes-caixa');
    expect([...caixas].map((c) => c.hidden)).toEqual([true, false]);
    expect(document.getElementById('cfg-prontos')).not.toHaveAttribute('open');
  });

  it('salvar sem mexer devolve o modelo igual e volta com o recado', async () => {
    abrir();
    await userEvent.click(screen.getByRole('button', { name: 'Salvar modelo' }));
    await waitFor(() => expect(ir).toHaveBeenCalledWith('/novo/passagem-de-turno/configuracao?client_id=1&editar=7'));
    expect(chamadas[0].url).toBe('/passagem-de-turno/api/configuracoes/7');
    expect(chamadas[0].init!.method).toBe('PUT');
    expect(JSON.parse(String(chamadas[0].init!.body))).toEqual({
      client_id: 1, nome: 'Expedição — rotina', area_id: 10, descricao: 'Do turno', ativo: true,
      turnos: [{ nome: '1º Turno' }],
      perguntas: [{ nome: 'Doca limpa', codigo: 'doca', tipo: 'sim_nao', obrigatorio: true },
        { nome: 'Situação', codigo: 'sit', tipo: 'escolha', obrigatorio: false, opcoes: ['Normal', 'Crítico'] }],
      tipos_ocorrencia: [{ nome: 'Avaria' }],
    });
    expect(JSON.parse(sessionStorage.getItem('fc-aviso')!).texto).toMatch(/^Modelo "Expedição — rotina" salvo\./);
  });

  it('novo modelo: turno, pergunta movida e POST', async () => {
    abrir();
    await userEvent.click(screen.getByRole('button', { name: /Novo$/ }));
    expect(document.getElementById('cfg-editando')!.textContent).toBe('Novo modelo — ainda não salvo.');
    await userEvent.type(screen.getByLabelText('Nome do modelo'), 'Portaria');
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar turno' }));
    await userEvent.type(document.querySelector('.cfg-shift') as HTMLElement, 'Diurno');
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar pergunta' }));
    await userEvent.click(screen.getByRole('button', { name: 'Adicionar pergunta' }));
    const nomes = document.querySelectorAll<HTMLInputElement>('.cfg-p-nome');
    await userEvent.type(nomes[0], 'Portão fechado?');
    await userEvent.type(nomes[1], 'Rondas feitas');
    await userEvent.click(screen.getAllByRole('button', { name: 'Subir' })[1]);
    await userEvent.click(screen.getByRole('button', { name: 'Salvar modelo' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe('/passagem-de-turno/api/configuracoes');
    expect(chamadas[0].init!.method).toBe('POST');
    const corpo = JSON.parse(String(chamadas[0].init!.body));
    expect(corpo.area_id).toBe(10);
    expect(corpo.turnos).toEqual([{ nome: 'Diurno' }]);
    expect(corpo.perguntas.map((p: { codigo: string }) => p.codigo)).toEqual(['rondas_feitas', 'portao_fechado']);
  });

  it('escolha sem opção não salva', async () => {
    abrir();
    await userEvent.clear(document.querySelectorAll<HTMLTextAreaElement>('.cfg-p-opcoes')[1]);
    await userEvent.click(screen.getByRole('button', { name: 'Salvar modelo' }));
    expect(window.alert).toHaveBeenCalledWith(expect.stringMatching(/"Situação" é de escolha, mas está sem opções/));
    expect(chamadas).toHaveLength(0);
  });

  it('contrato sem modelo abre os prontos; o recado do servidor aparece', () => {
    abrir(dados({ configs: [], recados: [{ tipo: 'info', texto: 'Esses modelos já existiam neste contrato — nada foi duplicado.' }] }));
    expect(document.getElementById('cfg-prontos')).toHaveAttribute('open');
    expect(screen.getByRole('alert')).toHaveTextContent('nada foi duplicado');
    expect(screen.getByText('Nenhum modelo cadastrado.', { exact: false })).toBeInTheDocument();
  });

  it('criar modelos prontos usa o formulário de sempre', async () => {
    abrir();
    await userEvent.click(screen.getByLabelText(/Limpeza e conservação/));
    await userEvent.click(screen.getByRole('button', { name: 'Criar modelos' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe('/passagem-de-turno/modelos-prontos');
    const corpo = chamadas[0].init!.body as FormData;
    expect(corpo.get('client_id')).toBe('1');
    expect(corpo.getAll('servico')).toEqual(['limpeza']);
  });
});
