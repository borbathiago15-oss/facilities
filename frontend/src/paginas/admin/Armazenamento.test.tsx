import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Armazenamento } from './Armazenamento';
import { barras, diasValidos, porQueNaoComeca, progresso, resumoDoPrazo, tamanho } from './regras';
import type { PainelDoArmazenamento } from './tipos';

const BASE: PainelDoArmazenamento = {
  dias: 60, dias_min: 1, dias_max: 3650, corte: '02/09/2026',
  destino: { disponivel: true, tipo: 'r2', rotulo: 'Cloudflare R2, bucket arquivo', mesmo_disco: false, problema: null },
  total: { fotos: 10, bytes: 5 * 1024 * 1024, sem_tamanho: 0 },
  por_mes: [{ mes: '10/2026', fotos: 4, bytes: 2048 }, { mes: '11/2026', fotos: 1, bytes: 1024 }],
  locais: [{ local: 'GL 1', bytes: 3 * 1024 * 1024 }],
  arquivadas: { fotos: 0, bytes: 0, fora_do_principal: 0, bytes_fora_do_principal: 0 },
  no_principal_bytes: 5 * 1024 * 1024,
  pendentes: { fotos: 3, bytes: 1536 * 1024, sem_tamanho: 0 },
  nao_sairam: 0, em_andamento: null, lotes: [],
};

function montar(d: Partial<PainelDoArmazenamento> = {}) {
  const salvarDias = vi.fn().mockResolvedValue(undefined);
  const arquivar = vi.fn().mockResolvedValue(undefined);
  render(<Armazenamento dados={{ ...BASE, ...d }} salvarDias={salvarDias} arquivar={arquivar} />);
  return { salvarDias, arquivar };
}

describe('contas da tela', () => {
  it('tamanho em pt-BR', () => {
    expect(tamanho(0)).toBe('0 KB');
    expect(tamanho(1536)).toBe('1,5 KB');
    expect(tamanho(3.5 * 1024 * 1024)).toBe('3,5 MB');
    expect(tamanho(2 * 1024 ** 3)).toBe('2,0 GB');
  });
  it('prazo, barras, progresso e dias', () => {
    expect(resumoDoPrazo({ fotos: 0, bytes: 0, sem_tamanho: 0 })).toBe('nenhuma foto passou do prazo');
    expect(resumoDoPrazo({ fotos: 2, bytes: 2048, sem_tamanho: 1 })).toBe('2 fotos (pelo menos 2,0 KB)');
    expect(barras([{ bytes: 50 }, { bytes: 100 }, { bytes: 0 }])).toEqual([50, 100, 0]);
    expect(barras([{ bytes: 0 }])).toEqual([0]);
    expect(progresso(120, 300)).toBe('120 de 300 fotos (40%)');
    expect(diasValidos(' 90 ', 1, 3650)).toBe(90);
    expect(diasValidos('0', 1, 3650)).toBeNull();
    expect(diasValidos('1,5', 1, 3650)).toBeNull();
  });
  it('o que impede começar', () => {
    expect(porQueNaoComeca(BASE)).toBeNull();
    expect(porQueNaoComeca({ ...BASE, pendentes: { fotos: 0, bytes: 0, sem_tamanho: 0 } }))
      .toBe('Nenhuma foto com mais de 60 dias.');
    expect(porQueNaoComeca({ ...BASE, destino: { ...BASE.destino, disponivel: false } }))
      .toMatch(/não está configurado/);
  });
});

describe('Armazenamento de fotos', () => {
  it('mostra os números e pede confirmação antes de arquivar', async () => {
    const { arquivar } = montar();
    expect(screen.getAllByText('5,0 MB', { selector: '.fs-4' })).toHaveLength(2);
    expect(screen.getByText('GL 1')).toBeInTheDocument();
    const u = userEvent.setup();
    await u.click(screen.getByRole('button', { name: 'Arquivar 3 fotos' }));
    expect(arquivar).not.toHaveBeenCalled();
    expect(screen.getByRole('alertdialog')).toHaveTextContent('3 fotos (1,5 MB)');
    await u.click(screen.getByRole('button', { name: 'Confirmar e começar' }));
    await waitFor(() => expect(arquivar).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Arquivamento começou/)).toBeInTheDocument();
  });

  it('sem foto no prazo, a frase termina com um ponto só', () => {
    montar({ pendentes: { fotos: 0, bytes: 0, sem_tamanho: 0 } });
    const ajuda = document.getElementById('arquivo-dias-ajuda')!;
    expect(ajuda).toHaveTextContent('Hoje entram as fotos tiradas antes de 02/09/2026: nenhuma foto passou do prazo.');
    expect(ajuda.textContent).not.toMatch(/\.\.\s*$/);
  });

  it('salva o prazo e recusa o que não é número', async () => {
    const { salvarDias } = montar();
    const u = userEvent.setup();
    const campo = screen.getByLabelText('Arquivar fotos com mais de');
    await u.clear(campo);
    await u.type(campo, 'abc');
    await u.click(screen.getByRole('button', { name: 'Salvar prazo' }));
    expect(salvarDias).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('de 1 a 3650');
    await u.clear(campo);
    await u.type(campo, '90');
    await u.click(screen.getByRole('button', { name: 'Salvar prazo' }));
    await waitFor(() => expect(salvarDias).toHaveBeenCalledWith(90));
  });

  it('sem destino: explica como configurar e não deixa começar', () => {
    montar({ destino: { disponivel: false, tipo: null, rotulo: '', mesmo_disco: false, problema: null },
      arquivadas: { fotos: 2, bytes: 10, fora_do_principal: 2, bytes_fora_do_principal: 10 } });
    expect(screen.getByText('O arquivo ainda não está ligado neste servidor.')).toBeInTheDocument();
    expect(screen.getByText('ARQUIVO_FOTOS_PASTA')).toBeInTheDocument();
    expect(screen.getByText(/2 fotos já estão no arquivo e não abrem/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Arquivar 3 fotos' })).toBeDisabled();
  });

  it('pasta no mesmo disco: avisa que não libera espaço', () => {
    montar({ destino: { disponivel: true, tipo: 'pasta', rotulo: 'Pasta /data/arquivo-fotos no servidor',
      mesmo_disco: true, problema: null } });
    expect(screen.getByText(/não libera espaço nenhum/)).toBeInTheDocument();
  });

  it('em andamento e histórico', () => {
    const lote = { id: 1, situacao: 'em_andamento' as const, situacao_rotulo: 'Em andamento', quem: 'Ana',
      iniciado_em: '01/11/2026 10:00', concluido_em: null, corte: '02/09/2026', dias: 60,
      destino: 'Cloudflare R2, bucket arquivo', previstas: 4, arquivadas: 1, bytes: 1024,
      nao_arquivadas: 0, tentativas_com_erro: 1, ultimo_erro: 'chamado_anexos #3: OSError: fora',
      ultima_rodada_em: null };
    montar({ em_andamento: lote, lotes: [lote] });
    expect(screen.getByText('Arquivamento em andamento')).toBeInTheDocument();
    expect(screen.getByText(/Ainda não houve rodada/)).toBeInTheDocument();
    expect(screen.getByText('Último erro: chamado_anexos #3: OSError: fora')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Arquivar 3 fotos' })).toBeDisabled();
    expect(screen.getByText('Já há um arquivamento em andamento.')).toBeInTheDocument();
  });
});
