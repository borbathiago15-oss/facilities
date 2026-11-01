import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DadosDaLeitura } from './tipos';
import { VerTurno } from './VerTurno';

function dados(extra: Partial<DadosDaLeitura> = {}): DadosDaLeitura {
  return {
    turno: { id: 9, client_id: 1, turno: '1º Turno', data: '01/11', data_longa: '01/11/2026', data_iso: '2026-11-01',
      status: 'encerrado', observacao: '', encerrado_em: '01/11/2026 18:02' },
    cliente: 'GL Armazém 1', configuracao: 'Limpeza — rotina', autor: 'Ana Souza', no_aparelho: null,
    congelada: true, pode_corrigir: false, correcoes: [], campos: [],
    linhas: [
      { codigo: 'a', nome: 'Banheiros limpos', feito: true, observacao: '', opcional: false, anexos: [
        { id: 3, nome: 'foto.jpg', mime: 'image/jpeg', url: '/passagem-de-turno/api/anexos/3', anexado_por: 'Sueli' }] },
      { codigo: 'b', nome: 'Vidros', feito: false, observacao: 'Sem rodo', opcional: true, anexos: [] },
    ],
    anexos_gerais: [], pendencias: [], ocorrencias: [],
    links: { painel: '/novo/passagem-de-turno/?client_id=1', corrigir: '/passagem-de-turno/api/turnos/9/corrigir' },
    ...extra,
  };
}

afterEach(() => vi.restoreAllMocks());

describe('leitura da passagem', () => {
  it('mostra o checklist, as provas e quem anexou', () => {
    render(<VerTurno dados={dados()} />);
    expect(screen.getByRole('heading', { name: '1º Turno · 01/11' })).toBeVisible();
    expect(screen.getByText('Concluído')).toHaveClass('vt-tag', 'ok');
    expect(screen.getByText('Não feita')).toHaveClass('neutro');
    expect(screen.getByText('anexado por Sueli')).toBeVisible();
    expect(screen.getByText(/encerrado em 01\/11\/2026 18:02/)).toBeVisible();
    expect(screen.getByText('Nenhuma pendência deixada.')).toBeVisible();
    expect(screen.queryByRole('button', { name: /Corrigir/ })).toBeNull();
  });

  it('o autor corrige com o motivo obrigatório', async () => {
    const enviar = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{"error": "Fechou"}', { status: 409 }));
    const alerta = vi.spyOn(window, 'alert').mockImplementation(() => {});
    render(<VerTurno dados={dados({ pode_corrigir: true })} />);
    await userEvent.click(screen.getByRole('button', { name: /Corrigir/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Registrar a correção' }));
    expect(alerta).toHaveBeenCalledWith('Diga em uma linha o que estava errado.');
    expect(enviar).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText(/O que estava errado/), 'Era o 2º');
    await userEvent.click(screen.getByRole('button', { name: 'Registrar a correção' }));
    expect(enviar.mock.calls[0][0]).toBe('/passagem-de-turno/api/turnos/9/corrigir');
    expect(JSON.parse(String(enviar.mock.calls[0][1]!.body))).toEqual({ data_turno: '2026-11-01', turno: '1º Turno',
      observacao: '', motivo: 'Era o 2º' });
    await vi.waitFor(() => expect(alerta).toHaveBeenLastCalledWith('Fechou'));
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(screen.queryByText('Corrigir esta passagem')).toBeNull();
  });
});
