import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DadosDoTurno, Tarefa } from './tipos';
import { Turno } from './Turno';

const MIN = 60000;

function tarefa(id: number, minutos: number, extra: Partial<Tarefa> = {}): Tarefa {
  const agora = Date.now();
  return {
    id, ponto: 'QRCOPA', ponto_nome: 'Copa', ambiente: 'Cozinha', local: 'GL 2', local_id: 2,
    rota: 'Limpeza', hora: '10:00', previsto: new Date(agora + minutos * MIN).toISOString(), tolerancia: 10,
    fim_turno: new Date(agora + 8 * 60 * MIN).toISOString(), versao: 5, minha: true, escalado: 'Ana',
    status: 'prevista', situacao: '', tempo_previsto_min: 1, ...extra,
  };
}

function dados(extra: Partial<DadosDoTurno> = {}): DadosDoTurno {
  return {
    usuario: 7, agora: '',
    tarefas: [tarefa(1, 0), tarefa(2, 120, { ponto: 'QRREF', ponto_nome: 'Refeitório', ambiente: 'Refeitório' })],
    versoes: { 5: { id: 5, modelo: 'Limpeza da copa', numero: 1, procedimento: '', materiais: '', epi: '',
      documentos: [], foto_antes: true, foto_depois: true, itens: [
        { codigo: 'pia', texto: 'Pia limpa?', tipo: 'sim_nao', como_fazer: 'Esponja macia.' },
        { codigo: 'lixo', texto: 'Lixo retirado?', tipo: 'sim_nao', exige_foto: true },
      ] } },
    pontos: {
      QRCOPA: { id: 1, nome: 'Copa', ambiente: 'Cozinha', descricao: '', local: 'GL 2', local_id: 2, entrada: false, extras: [], escopo: [5] },
      QRREF: { id: 2, nome: 'Refeitório', ambiente: 'Refeitório', descricao: '', local: 'GL 2', local_id: 2, entrada: false, extras: [], escopo: [5] },
      QRENT: { id: 3, nome: 'Portaria', ambiente: 'Entrada', descricao: '', local: 'GL 2', local_id: 2, entrada: true, extras: [], escopo: [] },
    },
    preventivas: [], motivos: { acesso: 'Sem acesso' }, motivos_atraso: {},
    motivos_nao_feito: { faltou_material: 'Faltou material', outro: 'Outro' },
    motivos_nao_feito_ordem: ['faltou_material', 'outro'],
    motivos_troca: { pedido_cliente: 'Pedido do cliente', outro: 'Outro' },
    tolerancia_atraso_min: 10,
    locais: [{ id: 2, nome: 'GL 2', entrada: 'QRENT', entrada_nome: 'Portaria', chegada: { id: 1, hora: '07:00' } },
             { id: 9, nome: 'GL 9', entrada: 'QR9', entrada_nome: 'Guarita', chegada: null }],
    situacoes: {}, ocorrencias: [], ...extra,
  };
}

function abrir(url: string, d = dados()) {
  return render(
    <MemoryRouter initialEntries={['/app/turno' + url]}>
      <Routes>
        <Route path="/app/turno" element={<Turno dados={d} />} />
        <Route path="/app/ler-qr" element={<p>leitor</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }));
});
afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); sessionStorage.clear(); });

describe('Meu turno', () => {
  it('um cartão por local: o que já chegou leva ao turno; o outro pede o QR da entrada', async () => {
    abrir('');
    expect(await screen.findByText('Você está no GL 2')).toBeInTheDocument();
    expect(screen.getByText('Chegou às 07:00 · 2 de 2 tarefas por fazer')).toBeInTheDocument();
    const outro = screen.getByText('GL 9').closest('a')!;
    expect(outro).toHaveAttribute('data-situacao', 'sem_chegada');
    expect(outro).toHaveAttribute('href', '/app/ler-qr');
    await userEvent.setup().click(screen.getByText('Você está no GL 2'));
    expect(await screen.findByText('Tarefas de hoje', { exact: false })).toBeInTheDocument();
    expect(document.querySelectorAll('.fc-roteiro-n')).toHaveLength(2);
    expect(document.querySelector('.fc-proxima')).toHaveTextContent('Copa');
  });

  it('local com entrada e sem chegada: só "Confirme a chegada"', async () => {
    abrir('?local=9');
    expect(await screen.findByRole('heading', { name: 'Confirme a chegada' })).toBeInTheDocument();
    expect(screen.getByText('Leia o QR da entrada do GL 9 (Guarita).')).toBeInTheDocument();
    expect(document.querySelectorAll('#turno-ponto button')).toHaveLength(0);
  });

  it('o QR abre direto no checklist da hora; o "Pronto" espera tudo', async () => {
    const u = userEvent.setup();
    abrir('?ponto=QRCOPA');
    expect(await screen.findByRole('heading', { name: 'Copa' })).toBeInTheDocument();
    expect(document.querySelector('.fc-exec-sub')).toHaveTextContent('Limpeza da copa das 10:00 · Previsto: 1 min');
    expect(screen.getByText('Aberto sem ler o QR com a câmera: fica com a hora do celular.')).toBeInTheDocument();
    const pronto = screen.getByRole('button', { name: 'Pronto' });
    expect(pronto).toBeDisabled();
    expect(document.querySelector('.fc-faltam')).toHaveTextContent('Faltam a foto do antes, 2 itens e a foto do depois');
    await u.upload(document.querySelector('[data-foto="antes"]') as HTMLInputElement, new File(['a'], 'a.jpg', { type: 'image/jpeg' }));
    await u.click(screen.getByRole('button', { name: 'Feito: Pia limpa?' }));
    expect(screen.getByText('Pia limpa?').closest('.fc-item')).toHaveClass('fc-item-feito');
    // O "como fazer" fica atrás do (i).
    expect(screen.getByText('Esponja macia.').closest('.fc-item-ajuda')).not.toBeVisible();
    await u.click(screen.getByRole('button', { name: 'Como fazer: Pia limpa?' }));
    expect(screen.getByText('Esponja macia.').closest('.fc-item-ajuda')).toBeVisible();
    // Foto exigida: o check só fica verde com a foto.
    await u.click(screen.getByRole('button', { name: 'Feito: Lixo retirado?' }));
    expect(screen.getByText('Lixo retirado?').closest('.fc-item')).not.toHaveClass('fc-item-feito');
    await u.upload(document.querySelector('[data-foto="item:lixo"]') as HTMLInputElement, new File(['l'], 'l.jpg', { type: 'image/jpeg' }));
    expect(screen.getByText('Lixo retirado?').closest('.fc-item')).toHaveClass('fc-item-feito');
    expect(document.querySelector('.fc-faltam')).toHaveTextContent('Falta a foto do depois');
    await u.upload(document.querySelector('[data-foto="depois"]') as HTMLInputElement, new File(['d'], 'd.jpg', { type: 'image/jpeg' }));
    expect(pronto).toBeEnabled();
  });

  it('"Não deu" com "Outro" pede o texto e marca o item', async () => {
    const u = userEvent.setup();
    abrir('?ponto=QRCOPA');
    const linha = (await screen.findByText('Pia limpa?')).closest('.fc-item') as HTMLElement;
    await u.click(within(linha).getByRole('button', { name: 'Não deu' }));
    const folha = screen.getByRole('dialog');
    expect(document.body).toHaveClass('fc-folha-aberta');
    await u.click(within(folha).getByRole('button', { name: 'Outro' }));
    await u.click(within(folha).getByRole('button', { name: 'Confirmar' }));
    expect(within(folha).getByText('Escreva o que aconteceu.')).toBeVisible();
    await u.type(within(folha).getByLabelText('O que aconteceu'), 'Pia quebrada');
    await u.click(within(folha).getByRole('button', { name: 'Confirmar' }));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.body).not.toHaveClass('fc-folha-aberta');
    expect(linha).toHaveClass('fc-item-naodeu');
    expect(linha).toHaveTextContent('Não deu: Outro — Pia quebrada');
  });

  it('"Ir para outra área" guarda o motivo (a mesma chave da tela antiga) e vai ao leitor', async () => {
    const u = userEvent.setup();
    abrir('?local=2');
    await u.click(await screen.findByRole('button', { name: 'Ir para outra área' }));
    await u.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Pedido do cliente' }));
    expect(await screen.findByText('leitor')).toBeInTheDocument();
    const troca = JSON.parse(sessionStorage.getItem('trino-turno-troca-7')!);
    expect(troca).toMatchObject({ motivo: 'pedido_cliente', rotulo: 'Pedido do cliente' });
  });

  it('o QR da área com o motivo pendente adianta a tarefa da rota', async () => {
    sessionStorage.setItem('trino-turno-troca-7', JSON.stringify({ motivo: 'pedido_cliente', rotulo: 'Pedido do cliente', em: Date.now() }));
    abrir('?ponto=QRREF');
    await waitFor(() => expect(document.querySelector('.fc-exec-sub'))
      .toHaveTextContent('Limpeza da copa das 10:00 · adiantada: Pedido do cliente'));
  });

  it('QR que não é dos locais da pessoa: o aviso e o caminho de volta', async () => {
    abrir('?ponto=OUTRO');
    expect(await screen.findByText(/Este QR não é de um ponto dos seus locais/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Voltar ao meu turno' })).toBeInTheDocument();
  });

  it('a fila subiu: só aquela tarefa vira "Enviada"', async () => {
    localStorage.setItem('trino-turno-feitas-7', JSON.stringify({ 1: 'Guardada no aparelho', 2: 'Guardada no aparelho' }));
    abrir('');
    await screen.findByText('Você está no GL 2');
    window.dispatchEvent(new CustomEvent('trino-fila:enviado', { detail: { tipo: 'execucao', tarefa_id: 1 } }));
    expect(JSON.parse(localStorage.getItem('trino-turno-feitas-7')!))
      .toEqual({ 1: 'Enviada', 2: 'Guardada no aparelho' });
  });
});
