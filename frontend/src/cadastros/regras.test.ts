import { describe, expect, it } from 'vitest';
import { dentroDoRoteador, tresDigitos } from './comum';
import { camposDaFuncao, continuar, erroDoGps, etapas, mudanca, situacao } from './regras';

describe('os passos do novo contrato', () => {
  it('no passo 1, só o cliente: nenhum link (os outros ainda não têm endereço)', () => {
    const e = etapas({ atual: 1, local: null, cliente: null });
    expect(e.map((x) => [x.n, x.classe, x.url])).toEqual([
      [1, 'atual', null], [2, '', null], [3, '', null], [4, '', null]]);
  });

  it('com o cliente, o passo 2 tem endereço; com o local, 3 e 4 (e o 2 não)', () => {
    expect(etapas({ atual: 2, local: null, cliente: { id: 5, nome: 'GL' } }).map((x) => x.url)).toEqual([
      '/novo/novo-contrato', null, null, null]);
    const e = etapas({ atual: 3, local: { id: 9, nome: 'CD' }, cliente: { id: 5, nome: 'GL' } });
    expect(e.map((x) => x.url)).toEqual(['/novo/novo-contrato', null, null, '/novo/novo-contrato/9/equipe']);
    expect(e.map((x) => x.classe)).toEqual(['feito', 'feito', 'atual', '']);
    expect(e[2].atual).toBe(true);
  });
});

describe('o que falta em cada local', () => {
  const a = { pontos: 0, entrada: false, rotas: 0, equipe: 0, convites: 0 };
  it('sem QR, a estrutura; sem equipe nem convite, a equipe; senão, abrir', () => {
    expect(continuar(3, a)).toEqual({ rotulo: 'Continuar: estrutura e QR', url: '/novo/novo-contrato/3/estrutura' });
    expect(continuar(3, { ...a, pontos: 2 })).toEqual({ rotulo: 'Continuar: equipe', url: '/novo/novo-contrato/3/equipe' });
    expect(continuar(3, { ...a, pontos: 2, convites: 1 })).toEqual({ rotulo: 'Abrir', url: '/novo/novo-contrato/3/estrutura' });
  });
});

describe('convites, campos por função e textos', () => {
  it('a situação do convite', () => {
    expect(situacao('pendente')).toEqual({ rotulo: 'aguardando', classe: 'text-bg-warning' });
    expect(situacao('aceito')).toEqual({ rotulo: 'aceito', classe: 'text-bg-success' });
    expect(situacao('vencido').classe).toBe('text-bg-secondary');
  });

  it('cada função mostra só os seus campos', () => {
    expect(camposDaFuncao('cliente')).toEqual({ cliente: true, equipe: false });
    expect(camposDaFuncao('visualizador')).toEqual({ cliente: false, equipe: false });
    expect(camposDaFuncao('encarregado')).toEqual({ cliente: false, equipe: true });
  });

  it('o GPS, a trilha, o número da etiqueta e os endereços', () => {
    expect(erroDoGps(1)).toMatch(/não deixou usar a localização/);
    expect(erroDoGps(3)).toMatch(/perto de uma janela/);
    expect(mudanca(true, '—', 'Copa')).toBe('— → Copa');
    expect(mudanca(false, '—', 'Copa')).toBe('Copa');
    expect(tresDigitos(7)).toBe('007');
    expect(tresDigitos(1234)).toBe('1234');
    expect(dentroDoRoteador('/novo/centros/3?aba=rotas')).toBe('/centros/3?aba=rotas');
    expect(dentroDoRoteador('/cadastros/locais/1/etiquetas.pdf')).toBeNull();
  });
});
