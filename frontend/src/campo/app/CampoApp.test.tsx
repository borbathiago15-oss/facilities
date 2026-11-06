import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Equipe } from './Equipe';
import { Materiais } from './Materiais';
import type { DadosDaEquipe, DadosDaVisita, DadosDasVisitas, DadosDosMateriais, ItemDaVisita } from './tipos';
import { ListaDeVisitas, Visita, aceitavel } from './Visitas';

let chamadas: { url: string; init?: RequestInit }[] = [];
let respostas: Record<string, { status: number; corpo: unknown }> = {};
const PADRAO = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Feito.' }], destino: '/novo/app/materiais' } };
beforeEach(() => {
  chamadas = [];
  respostas = {};
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    chamadas.push({ url: String(url), init });
    const r = respostas[String(url)] || PADRAO;
    return new Response(JSON.stringify(r.corpo), { status: r.status });
  });
});
afterEach(() => vi.restoreAllMocks());

function Onde() {
  const l = useLocation();
  return <span data-testid="onde">{l.pathname + l.search + l.hash}</span>;
}

function abrir(no: React.ReactNode, url = '/app') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes><Route path="*" element={<>{no}<Onde /></>} /></Routes>
    </MemoryRouter>);
}

const LINKS = { ler_qr: '/novo/app/ler-qr', site: '/', instalar: '/app/instalar', passagem: null, chamados: null };

function corpo(url: string) {
  return chamadas.find((c) => c.url === url)!.init!.body as FormData;
}

// ── Equipe ────────────────────────────────────────────────────────────────

function equipe(extra: Partial<DadosDaEquipe> = {}): DadosDaEquipe {
  return {
    dia: '04/11/2026', data: '2026-11-04', ontem: '/novo/app/equipe?data=2026-11-03',
    amanha: '/novo/app/equipe?data=2026-11-05',
    situacoes: [['veio', 'Veio'], ['faltou', 'Faltou'], ['atrasou', 'Atrasou']],
    locais: [{ id: 1, nome: 'GL Armazém 1', cobridores: [{ id: 10, nome: 'Ana Souza' }, { id: 11, nome: 'Mariana Lima' }],
      linhas: [
        { escala_id: 5, funcionario_id: 10, funcionario: 'Ana Souza', detalhe: 'Limpeza · 07:00 às 15:00 · ASG',
          presenca: { id: 7, situacao: 'faltou', rotulo: 'Faltou', cobertura: null } },
        { escala_id: 6, funcionario_id: 11, funcionario: 'Mariana Lima', detalhe: 'Portaria · 06:00 às 18:00',
          presenca: { id: 8, situacao: 'faltou', rotulo: 'Faltou', cobertura: { funcionario: 'Ana Souza', motivo: 'folga trocada' } } },
      ] }],
    links: LINKS, ...extra };
}

describe('a equipe do dia', () => {
  it('mostra o dia, a situação marcada e a cobertura como a antiga', () => {
    abrir(<Equipe dados={equipe()} />);
    expect(screen.getByRole('heading', { name: 'Equipe · 04/11/2026' })).toBeInTheDocument();
    expect(screen.getByText('Limpeza · 07:00 às 15:00 · ASG')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Faltou' })[0]).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getAllByRole('button', { name: 'Veio' })[0]).not.toHaveAttribute('aria-pressed');
    expect(screen.getByText('Ana Souza', { selector: 'b' })).toBeInTheDocument();
    expect(screen.getByText(/folga trocada/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Dia anterior/ })).toHaveAttribute('href', '/app/equipe?data=2026-11-03');
    // Quem faltou não aparece entre quem pode cobrir.
    const opcoes = [...document.getElementById('cq7')!.querySelectorAll('option')].map((o) => o.textContent);
    expect(opcoes).toEqual(['Mariana Lima']);
  });

  it('hoje não tem "Dia seguinte"; sem escala, diz onde se lança', () => {
    abrir(<Equipe dados={equipe({ amanha: null, locais: [] })} />);
    expect(screen.queryByText(/Dia seguinte/)).toBeNull();
    expect(screen.getByText(/A escala é lançada no site/)).toBeInTheDocument();
  });

  it('marcar envia a escala, o dia e a situação e volta à pessoa', async () => {
    respostas['/api/v1/campo/equipe/presenca'] = { status: 200, corpo: {
      recados: [{ tipo: 'success', texto: 'Ana Souza: veio.' }], destino: '/novo/app/equipe?data=2026-11-04#escala-5' } };
    abrir(<Equipe dados={equipe()} />);
    await userEvent.click(screen.getAllByRole('button', { name: 'Veio' })[0]);
    await waitFor(() => expect(screen.getByTestId('onde')).toHaveTextContent('/app/equipe?data=2026-11-04#escala-5'));
    const fd = corpo('/api/v1/campo/equipe/presenca');
    expect([fd.get('escala_id'), fd.get('data'), fd.get('situacao')]).toEqual(['5', '2026-11-04', 'veio']);
  });

  it('a cobertura vai ao caminho da presença; a recusa aparece na tela', async () => {
    respostas['/api/v1/campo/equipe/presencas/7/cobertura'] = { status: 400, corpo: {
      error: 'Diga o motivo da cobertura (ex.: atestado, folga trocada).' } };
    abrir(<Equipe dados={equipe()} />);
    await userEvent.click(screen.getByText('Alguém cobriu esta falta?'));
    await userEvent.type(screen.getByLabelText('Motivo'), 'atestado');
    await userEvent.click(screen.getByRole('button', { name: 'Registrar cobertura' }));
    expect(await screen.findByText('Diga o motivo da cobertura (ex.: atestado, folga trocada).')).toBeInTheDocument();
    const fd = corpo('/api/v1/campo/equipe/presencas/7/cobertura');
    expect([fd.get('funcionario_id'), fd.get('motivo')]).toEqual(['11', 'atestado']);
  });
});

// ── Materiais ─────────────────────────────────────────────────────────────

function materiais(extra: Partial<DadosDosMateriais> = {}): DadosDosMateriais {
  return {
    locais: [{ id: 1, nome: 'GL Armazém 1' }], materiais: [{ id: 3, nome: 'Detergente neutro', unidade: 'L' }],
    chamados: [{ id: 9, rotulo: 'OS-0009 · Vazamento' }], rotas: [{ id: 4, rotulo: 'GL Armazém 1 · Rota A' }],
    meus: [{ id: 2, resumo: 'Pano de chão · 5', detalhe: 'GL Armazém 1 · 04/11 10:00 · Aberto' }],
    links: LINKS, ...extra };
}

describe('o material', () => {
  it('os mesmos campos da antiga, sem preço', () => {
    abrir(<Materiais dados={materiais()} />);
    expect(screen.getAllByRole('option', { name: 'Detergente neutro (L)' })).toHaveLength(2);
    expect(screen.getByRole('option', { name: 'OS-0009 · Vazamento' })).toBeInTheDocument();
    expect(screen.getByText('GL Armazém 1 · 04/11 10:00 · Aberto')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/R\$/);
  });

  it('sem local liberado e com o catálogo vazio, diz o que fazer', () => {
    const { unmount } = abrir(<Materiais dados={materiais({ locais: [] })} />);
    expect(screen.getByText('Você ainda não tem local liberado.')).toBeInTheDocument();
    unmount();
    abrir(<Materiais dados={materiais({ materiais: [] })} />);
    expect(screen.getByText(/catálogo de materiais ainda está vazio/)).toBeInTheDocument();
  });

  it('o consumo e o pedido com foto vão ao caminho do campo', async () => {
    abrir(<Materiais dados={materiais()} />, '/app/materiais');
    await userEvent.type(screen.getByLabelText('Quantidade'), '1,5');
    await userEvent.click(screen.getByRole('button', { name: /Registrar consumo/ }));
    await waitFor(() => expect(chamadas.some((c) => c.url === '/api/v1/campo/materiais/consumo')).toBe(true));
    const fd = corpo('/api/v1/campo/materiais/consumo');
    expect([fd.get('client_id'), fd.get('material_id'), fd.get('quantidade'), fd.get('chamado_id')]).toEqual(['1', '3', '1,5', '']);
    const foto = new File(['x'], 'f.jpg', { type: 'image/jpeg' });
    await userEvent.upload(screen.getByLabelText('Foto (opcional)'), foto);
    await userEvent.type(screen.getByLabelText('O que precisa'), 'saco de lixo');
    await userEvent.click(screen.getByRole('button', { name: /Avisar o gestor/ }));
    await waitFor(() => expect(chamadas.some((c) => c.url === '/api/v1/campo/materiais/pedido')).toBe(true));
    const p = corpo('/api/v1/campo/materiais/pedido');
    expect(p.get('texto')).toBe('saco de lixo');
    // (o jsdom não põe no FormData o arquivo do ``upload``: basta o campo ir)
    expect(p.has('foto')).toBe(true);
  });
});

// ── Visitas ───────────────────────────────────────────────────────────────

describe('as visitas', () => {
  it('a lista com os selos e o link da visita nova', () => {
    const d: DadosDasVisitas = { links: LINKS, visitas: [
      { id: 1, nome: 'Visita semanal', local: 'GL 1', ate: '04/11', selo: 'hoje', url: '/novo/app/visitas/1' },
      { id: 2, nome: 'Visita mensal', local: 'GL 2', ate: '01/11', selo: 'atrasada', url: '/novo/app/visitas/2' }] };
    abrir(<ListaDeVisitas dados={d} />);
    expect(screen.getByText('Hoje')).toHaveClass('fc-sit-no_horario');
    expect(screen.getByText('Atrasada')).toHaveClass('fc-sit-atrasada');
    expect(screen.getByText('Visita semanal').closest('a')).toHaveAttribute('href', '/app/visitas/1');
  });

  it('sem visita, a frase da antiga', () => {
    abrir(<ListaDeVisitas dados={{ links: LINKS, visitas: [] }} />);
    expect(screen.getByText('Nenhuma visita esperando você.')).toBeInTheDocument();
  });

  const item = (x: Partial<ItemDaVisita>): ItemDaVisita => ({
    codigo: 'q', texto: 'Pergunta', tipo: 'texto', obrigatorio: false, mostrar_se: null,
    minimo: null, maximo: null, opcoes: [], exige_foto: false, ...x });

  function aberta(extra: Partial<DadosDaVisita> = {}): DadosDaVisita {
    return {
      visita: { id: 31, nome: 'Visita semanal', local: 'GL 1', status: 'prevista', situacao_rotulo: 'A fazer',
        ate: '04/11/2026', quem_fez: null, feita_em: null, n_nao_conformes: 0, chamado: null, observacao: '', supervisor: 'Sueli' },
      fotos: [], respostas: [], pode_fazer: true, exige_foto_antes: true, exige_foto_depois: false, links: LINKS,
      itens: [
        item({ codigo: 'uniforme', texto: 'Uniforme completo?', tipo: 'sim_nao', obrigatorio: true }),
        item({ codigo: 'peca', texto: 'Qual peça?', exige_foto: true,
          mostrar_se: { codigo: 'uniforme', valor: 'nao', texto: 'Uniforme completo?' } }),
        item({ codigo: 'temp', texto: 'Temperatura', tipo: 'numero', minimo: '0.0', maximo: '8.0' }),
        item({ codigo: 'piso', texto: 'Piso', tipo: 'escolha', opcoes: ['Limpo', 'Sujo'] }),
      ], ...extra };
  }

  it('o checklist com os campos da antiga, a condição e as fotos reduzidas', () => {
    abrir(<Visita dados={aberta()} />);
    expect(screen.getByText('GL 1 · A fazer · até 04/11/2026')).toBeInTheDocument();
    expect(screen.getByText('Responda só se "Uniforme completo?" for "nao".')).toBeInTheDocument();
    expect(screen.getByText('Aceitável: de 0.0 até 8.0')).toBeInTheDocument();
    const nomes = [...document.querySelectorAll('form [name]')].map((e) => e.getAttribute('name'));
    expect(new Set(nomes)).toEqual(new Set(['f_antes', 'r_uniforme', 'r_peca', 'f_item:peca', 'r_temp', 'r_piso', 'f_livre', 'observacao']));
    // A foto do item condicional não é obrigatória; a de antes, sim. Todas são reduzidas no aparelho.
    expect(document.getElementById('f_item:peca')).not.toBeRequired();
    expect(document.getElementById('f_antes')).toBeRequired();
    expect(document.getElementById('f_livre')).toHaveAttribute('multiple');
    expect(document.querySelectorAll('input[type=file][data-foto-leve]')).toHaveLength(3);
    expect(screen.getByText(/Esta tela precisa de sinal/)).toBeInTheDocument();
  });

  it('o registro envia o formulário inteiro com as fotos', async () => {
    respostas['/api/v1/campo/visitas/31'] = { status: 200, corpo: {
      recados: [{ tipo: 'success', texto: 'Visita registrada. Tudo conforme.' }], destino: '/novo/app/visitas/31' } };
    abrir(<Visita dados={aberta({ exige_foto_antes: false })} />, '/app/visitas/31');
    await userEvent.click(screen.getByText('Sim'));
    await userEvent.upload(document.getElementById('f_livre') as HTMLInputElement,
      [new File(['a'], 'a.jpg', { type: 'image/jpeg' }), new File(['b'], 'b.jpg', { type: 'image/jpeg' })]);
    await userEvent.click(screen.getByRole('button', { name: /Registrar a visita/ }));
    await waitFor(() => expect(chamadas.some((c) => c.url === '/api/v1/campo/visitas/31')).toBe(true));
    const fd = corpo('/api/v1/campo/visitas/31');
    expect(fd.get('r_uniforme')).toBe('sim');
    expect((document.getElementById('f_livre') as HTMLInputElement).files).toHaveLength(2);
    expect(fd.has('f_livre') && fd.has('observacao')).toBe(true);
  });

  it('a recusa do servidor aparece e o preenchido fica na tela', async () => {
    respostas['/api/v1/campo/visitas/31'] = { status: 400, corpo: { error: 'Responda: "Uniforme completo?".' } };
    abrir(<Visita dados={aberta({ exige_foto_antes: false })} />, '/app/visitas/31');
    await userEvent.type(document.getElementById('obs')!, 'tudo certo');
    await userEvent.click(screen.getByRole('button', { name: /Registrar a visita/ }));
    expect(await screen.findByText('Responda: "Uniforme completo?".')).toBeInTheDocument();
    expect(document.getElementById('obs')).toHaveValue('tudo certo');
    expect(screen.getByTestId('onde')).toHaveTextContent('/app/visitas/31');
  });

  it('a visita de outra pessoa e a visita feita', () => {
    const { unmount } = abrir(<Visita dados={aberta({ pode_fazer: false, itens: [] })} />);
    expect(screen.getByText('Esta visita é de Sueli.')).toBeInTheDocument();
    unmount();
    abrir(<Visita dados={aberta({
      pode_fazer: false, itens: [],
      visita: { ...aberta().visita, status: 'feita', situacao_rotulo: 'Feita', ate: null, quem_fez: 'Sueli',
        feita_em: '04/11/2026 10:00', n_nao_conformes: 1, observacao: 'Bota rasgada',
        chamado: { numero: 'OS-0012', status_rotulo: 'Aberto', url: '/novo/chamados/12' } },
      fotos: [{ id: 3, url: '/app/visitas/fotos/3', alt: 'Foto livre', legenda: 'Livre' }],
      respostas: [{ codigo: 'uniforme', texto: 'Uniforme completo?', valor: 'nao' }] })} />);
    expect(screen.getByText('OS-0012').closest('a')).toHaveAttribute('href', '/chamados/12');
    expect(screen.getByAltText('Foto livre')).toHaveAttribute('src', '/app/visitas/fotos/3');
    expect(screen.getByText('Bota rasgada')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Registrar a visita/ })).toBeNull();
  });

  it('o "Aceitável" só com o que o item tem', () => {
    expect(aceitavel(item({ minimo: '2' }))).toBe('Aceitável: de 2');
    expect(aceitavel(item({ maximo: '9' }))).toBe('Aceitável:  até 9');
    expect(aceitavel(item({}))).toBeNull();
  });
});
