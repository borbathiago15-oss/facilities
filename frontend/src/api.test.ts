import { afterEach, describe, expect, it, vi } from 'vitest';
import { chamar, ErroDaApi, guardarCsrf } from './api';

function resposta(status: number, corpo: unknown) {
  return Promise.resolve(new Response(JSON.stringify(corpo), { status }));
}

afterEach(() => vi.restoreAllMocks());

describe('chamar', () => {
  it('usa a mesma sessão e manda o CSRF só nos envios', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockImplementation(() => resposta(200, { ok: 1 }));
    guardarCsrf('tok');
    await chamar('/x');
    await chamar('/y', { method: 'POST', body: JSON.stringify({ a: 1 }) });
    const [, leitura] = f.mock.calls[0];
    const [url, envio] = f.mock.calls[1];
    expect(url).toBe('/api/v1/y');
    expect(leitura?.credentials).toBe('same-origin');
    expect(new Headers(leitura?.headers).get('X-CSRFToken')).toBeNull();
    expect(new Headers(envio?.headers).get('X-CSRFToken')).toBe('tok');
    expect(new Headers(envio?.headers).get('Content-Type')).toBe('application/json');
  });

  it('erro do servidor vira mensagem em português', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
      resposta(403, { error: 'Você não tem acesso.' }));
    await expect(chamar('/x')).rejects.toMatchObject({ status: 403, message: 'Você não tem acesso.' });
  });

  it('sem internet diz isso, sem travar', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    const erro = (await chamar("/x").catch((e: unknown) => e)) as ErroDaApi;
    expect(erro).toBeInstanceOf(ErroDaApi);
    expect(erro.status).toBe(0);
    expect(erro.message).toMatch(/Sem conexão/);
  });

  it('sessão vencida leva ao login e volta para a tela', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => resposta(401, {}));
    const ir = vi.fn();
    vi.spyOn(window, 'location', 'get').mockReturnValue({
      ...window.location, pathname: '/novo/x', search: '?a=1', assign: ir,
    } as Location);
    await expect(chamar('/x')).rejects.toMatchObject({ status: 401 });
    expect(ir).toHaveBeenCalledWith('/login?next=%2Fnovo%2Fx%3Fa%3D1');
  });
});
