import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { describe, expect, it } from 'vitest';
import { Relatorio } from './Relatorio';
import type { DadosDoRelatorio } from './tipos';

const DADOS: DadosDoRelatorio = {
  cliente: { id: 1, nome: 'GL Armazém 1' },
  meses: [[10, 'Outubro'], [11, 'Novembro']], anos: [2025, 2026], mes: 11, ano: 2026,
  areas: [{ id: 10, nome: 'Expedição' }], area_sel: 10, todas_as_areas: 0, nome_do_sistema: 'Trino Facilities',
  rel: {
    area: 'Expedição', competencia: 'Novembro/2026', emitido_em: '01/11/2026 14:00', emitido_por: 'Gestor',
    inicio: '01/11/2026', fim_apurado: '01/11/2026', em_andamento: true,
    turnos: { total: 2, por_turno: [['1º Turno', 1], ['2º Turno', 1]] },
    aderencia: { pct: 100, cumpridas: 2, exigidas: 2, faixa: 'ok', meta: 95 },
    pendencias: { abertas: 1, resolvidas: 0, pct: 0, faixa: 'critico', lista_resolvidas: [],
      lista_em_aberto: [{ titulo: 'Devolução', referencia: 'NF 10', prioridade: 'alta', descricao: '', anterior: false,
        ultima_tentativa: 'Liguei', turno: '1º Turno', passagens: 1, dias: 0 }] },
    ocorrencias: { total: 1, mais_frequente: { tipo: 'Avaria', qtd: 1 },
      lista: [{ data: '01/11/2026', dia: '01/11', turno: '1º Turno', tipo: 'Avaria', referencia: '', descricao: 'Pallet', gravidade: 'critica' }],
      atencao: [{ data: '01/11/2026', dia: '01/11', turno: '1º Turno', tipo: 'Avaria', referencia: '', descricao: 'Pallet', gravidade: 'critica' }] },
    rotinas: [], bordo: [],
  },
  links: { painel: '/novo/passagem-de-turno/?client_id=1',
    pdf: '/passagem-de-turno/relatorio-mensal?client_id=1&mes=11&ano=2026&format=pdf&area_id=10' },
};

function Endereco() {
  return <output data-testid="endereco">{useLocation().search}</output>;
}

describe('relatório mensal', () => {
  it('mostra o fechamento e leva ao PDF do servidor', async () => {
    render(<MemoryRouter><Routes><Route path="*" element={<><Relatorio dados={DADOS} /><Endereco /></>} /></Routes></MemoryRouter>);
    expect(screen.getByText(/Competência Novembro\/2026/)).toBeInTheDocument();
    expect(screen.getByText('1º Turno: 1 | 2º Turno: 1')).toBeInTheDocument();
    expect(screen.getByText(/Período apurado: 01\/11\/2026 a 01\/11\/2026 \(competência em andamento\)/)).toBeInTheDocument();
    expect(screen.getByText('Mais frequente: Avaria (1)')).toBeInTheDocument();
    expect(screen.getByText('Pontos de atenção da competência (1)')).toBeInTheDocument();
    expect(screen.getByText('Última tentativa: Liguei')).toBeInTheDocument();
    expect(screen.getByText('passou por 1 turno')).toBeInTheDocument();
    expect(screen.getByText('hoje')).toBeInTheDocument();
    expect(screen.getByText(/Nenhum fato relevante registrado/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Baixar PDF/ })).toHaveAttribute('href', DADOS.links.pdf);
    expect(screen.getByRole('link', { name: 'Voltar' })).toHaveAttribute('href', '/novo/passagem-de-turno/?client_id=1');
    await userEvent.selectOptions(screen.getByLabelText('Mês'), '10');
    expect(screen.getByTestId('endereco').textContent).toBe('?client_id=1&area_id=10&mes=10&ano=2026');
  });
});
