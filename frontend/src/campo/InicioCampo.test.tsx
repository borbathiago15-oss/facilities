import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Eu } from '../api';
import { InicioCampo } from './InicioCampo';
import { Presenca } from './Presenca';
import type { InicioDoCampo } from './tipos';

const EU = { primeiro_nome: 'Ana', perfil: 'Encarregado' } as Eu;

const BASE: InicioDoCampo = {
  hoje: '31/10/2026', tem_locais: true, turno: [], material: null, equipe: null, visitas: null,
  ocorrencias: [], tarefas: [], pendencias: [], chamados: [], passagem: null,
  links: { ler_qr: '/app/ler-qr', site: '/', instalar: '/app/instalar', passagem: null, chamados: null },
};

function montar(d: Partial<InicioDoCampo>) {
  return render(<MemoryRouter><InicioCampo eu={EU} dados={{ ...BASE, ...d }} /></MemoryRouter>);
}

afterEach(() => vi.restoreAllMocks());

describe('Início do campo', () => {
  it('um cartão por local, conforme a chegada', () => {
    montar({ turno: [
      { local_id: 1, local: 'GL 1', situacao: 'sem_chegada', entrada: 'Portaria', chegou_as: null, tarefas: 3, abertas: 3, url: '/app/ler-qr' },
      { local_id: 2, local: 'GL 2', situacao: 'chegou', entrada: 'Portaria', chegou_as: '07:02', tarefas: 4, abertas: 1, url: '/app/turno?local=2' },
      { local_id: 3, local: 'GL 3', situacao: 'sem_entrada', entrada: null, chegou_as: null, tarefas: 0, abertas: 0, url: '/app/turno?local=3' },
    ] });
    expect(screen.getByText('3 tarefas hoje · Ao chegar, leia o QR da entrada (Portaria)')).toBeInTheDocument();
    expect(screen.getByText('Você está no GL 2')).toBeInTheDocument();
    expect(screen.getByText('Chegou às 07:02 · 1 de 4 tarefas por fazer')).toBeInTheDocument();
    expect(screen.getByText('Nenhuma tarefa da rota hoje')).toBeInTheDocument();
    expect(screen.getByText('Você está no GL 2').closest('a')).toHaveAttribute('href', '/app/turno?local=2');
  });

  it('sem local liberado: diz o que fazer', () => {
    montar({ tem_locais: false });
    expect(screen.getByText(/ainda não tem local liberado/)).toBeInTheDocument();
    expect(screen.queryByText('Para hoje')).toBeNull();
  });

  it('listas vazias convidam, chamados só para quem vê chamados', () => {
    montar({ chamados: null });
    expect(screen.getByText('Nenhuma tarefa da gestão esperando você.')).toBeInTheDocument();
    expect(screen.queryByText('Chamados abertos')).toBeNull();
  });

  it('aviso do público mostra o local primeiro', () => {
    montar({ ocorrencias: [{ id: 9, local: 'GL 1', ambiente: 'Banheiro 1', titulo: 'Sem papel', ponto: 'Porta',
      hora: '10:15', texto: 'acabou', sua: true, url: '/app/turno?ponto=X' }] });
    expect(screen.getByText('Avisos do público (1)')).toBeInTheDocument();
    expect(screen.getByText('GL 1 · Banheiro 1 · Sem papel')).toBeInTheDocument();
    expect(screen.getByText('Sua')).toBeInTheDocument();
  });
});

describe('Pedido de presença', () => {
  it('pergunta, confirma e mostra o recado do servidor', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockImplementation((url) => {
      const corpo = String(url).endsWith('/app/api/presenca')
        ? { pedido: { id: 5, rota: 'Limpeza', ate: '10:30' } }
        : { mensagem: 'Presença confirmada às 10:12.' };
      return Promise.resolve(new Response(JSON.stringify(corpo), { status: 200 }));
    });
    render(<Presenca />);
    const botao = await screen.findByRole('button', { name: 'Estou no posto' });
    expect(screen.getByText('Confirme que você está no posto (até 10:30).')).toBeInTheDocument();
    await userEvent.setup().click(botao);
    await waitFor(() => expect(screen.getByText('Presença confirmada às 10:12.')).toBeInTheDocument());
    const [url, envio] = f.mock.calls[1];
    expect(url).toBe('/app/api/presenca/5');
    expect(envio?.method).toBe('POST');
  });
});
