import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { buscarEu, chamar } from './api';
import { anotar, esquecerCopias, horaDaCopia, maisAntiga, useCopiaEmUso } from './copia';

// 14:32 em Brasília (17:32 UTC).
const AS_14_32 = Date.UTC(2026, 10, 1, 17, 32);

function resposta(corpo: unknown, guardada?: number) {
  const cabecalhos: Record<string, string> = {};
  if (guardada) cabecalhos['x-guardada-em'] = String(guardada);
  return new Response(JSON.stringify(corpo), { status: 200, headers: cabecalhos });
}

afterEach(() => {
  vi.restoreAllMocks();
  esquecerCopias();
  document.head.innerHTML = '';
});

describe('a cópia guardada no aparelho', () => {
  it('a hora é a de Brasília, HH:MM', () => {
    expect(horaDaCopia(AS_14_32)).toBe('14:32');
  });

  it('a tela vale a parte mais velha', () => {
    expect(maisAntiga([])).toBeNull();
    expect(maisAntiga([30, 10, 20])).toBe(10);
  });

  it('a resposta da cópia acende o aviso; a da rede apaga', () => {
    const { result } = renderHook(() => useCopiaEmUso());
    expect(result.current).toBeNull();
    act(() => anotar('/api/v1/campo/turno', resposta({}, AS_14_32)));
    act(() => anotar('/api/v1/eu', resposta({}, AS_14_32 + 60_000)));
    expect(result.current).toBe(AS_14_32);
    act(() => anotar('/api/v1/campo/turno', resposta({})));
    expect(result.current).toBe(AS_14_32 + 60_000);
    act(() => anotar('/api/v1/eu', resposta({})));
    expect(result.current).toBeNull();
  });

  it('chamar anota de onde veio a leitura', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(resposta({ ok: 1 }, AS_14_32));
    const { result } = renderHook(() => useCopiaEmUso());
    await act(() => chamar('/campo/inicio'));
    expect(result.current).toBe(AS_14_32);
  });

  it('a cópia de outra pessoa não aparece', async () => {
    document.head.innerHTML = '<meta name="usuario-id" content="7">';
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(resposta({ id: 8, csrf: 'x' }, AS_14_32));
    await expect(buscarEu()).rejects.toMatchObject({ status: 0 });
  });

  it('a cópia da mesma pessoa aparece', async () => {
    document.head.innerHTML = '<meta name="usuario-id" content="7">';
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(resposta({ id: 7, csrf: 'x' }, AS_14_32));
    await expect(buscarEu()).resolves.toMatchObject({ id: 7 });
  });
});
