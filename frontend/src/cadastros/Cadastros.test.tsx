import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { Estados } from './Cadastros';
import { Local } from './Local';
import { Equipe } from './NovoContrato';
import type { DadosDaEquipe, DadosDoLocal } from './tipos';

let chamadas: { url: string; init?: RequestInit }[] = [];
let resposta: { status: number; corpo: unknown };
beforeEach(() => {
  chamadas = [];
  resposta = { status: 200, corpo: { recados: [{ tipo: 'success', texto: 'Bahia desativado.' }], destino: '/novo/cadastros/estados' } };
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (url, init) => {
    chamadas.push({ url: String(url), init });
    return new Response(JSON.stringify(resposta.corpo), { status: resposta.status });
  });
});
afterEach(() => vi.restoreAllMocks());

function Onde() {
  const l = useLocation();
  return <span data-testid="onde">{l.pathname + l.search}</span>;
}

function abrir(no: React.ReactNode, url = '/') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes><Route path="*" element={<>{no}<Onde /></>} /></Routes>
    </MemoryRouter>);
}

describe('o envio dos formulários', () => {
  it('leva o formulário de sempre ao mesmo caminho da API e volta com o recado', async () => {
    abrir(<Estados dados={{ estados: [{ id: 5, nome: 'Bahia', sigla: 'BA', ativo: true }] }} />, '/cadastros/estados');
    await userEvent.click(screen.getByRole('button', { name: 'Desativar' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe('/api/v1/cadastros/estados/5/ativo');
    const corpo = chamadas[0].init!.body as FormData;
    expect(corpo.get('ativo')).toBe('0');
    expect(screen.getByTestId('onde')).toHaveTextContent('/cadastros/estados');
  });

  it('sem sinal, diz o que houve na própria tela', async () => {
    vi.mocked(globalThis.fetch).mockRejectedValueOnce(new TypeError('offline'));
    abrir(<Estados dados={{ estados: [{ id: 5, nome: 'Bahia', sigla: 'BA', ativo: false }] }} />);
    await userEvent.click(screen.getByRole('button', { name: 'Ativar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Sem conexão com o servidor');
  });
});

function local(extra: Partial<DadosDoLocal> = {}): DadosDoLocal {
  return {
    local: { id: 1, nome: 'CD 1', cliente: 'Grupo GL', estado: 'Bahia', subcentro: 'GL-01' },
    setores: [{ id: 2, nome: 'Administrativo', ativo: true, ambientes: [{
      id: 3, nome: 'Copa', descricao: '', ativo: true,
      pontos: [{ id: 4, nome: 'Pia', descricao: '', ativo: true, equipamento_id: null, equipamento: null },
        { id: 5, nome: 'Velho', descricao: '', ativo: false, equipamento_id: null, equipamento: null }],
      equipamentos: [],
    }] }],
    todos_setores: [{ id: 2, nome: 'Administrativo', ambientes: [{ id: 3, nome: 'Copa' }] }],
    com_inativos: false, pode_alterar: true,
    links: { etiquetas: '/cadastros/locais/1/etiquetas.pdf' },
    ...extra,
  };
}

describe('a estrutura do local', () => {
  it('esconde os desativados como a antiga, e a diretoria não vê as ações', () => {
    const { unmount } = abrir(<Local dados={local()} />);
    expect(screen.getByText('Pia')).toBeInTheDocument();
    expect(screen.queryByText('Velho')).toBeNull();
    expect(screen.getByRole('link', { name: 'Etiqueta' })).toHaveAttribute('href', '/cadastros/locais/1/etiquetas.pdf?ponto=4');
    unmount();
    abrir(<Local dados={local({ com_inativos: true, pode_alterar: false })} />);
    expect(screen.getByText('Velho')).toBeInTheDocument();
    expect(screen.queryByText('Cadastrar setor')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Desativar' })).toBeNull();
  });

  it('com os desativados à mostra, o envio leva a volta (inativos=1)', async () => {
    resposta.corpo = { recados: [], destino: '/novo/cadastros/locais/1?inativos=1' };
    abrir(<Local dados={local({ com_inativos: true })} />);
    await userEvent.type(document.getElementById('snovo')!, 'Armazém');
    await userEvent.click(screen.getByRole('button', { name: 'Cadastrar' }));
    await waitFor(() => expect(chamadas).toHaveLength(1));
    expect(chamadas[0].url).toBe('/api/v1/cadastros/locais/1/setor');
    const corpo = chamadas[0].init!.body as FormData;
    expect(corpo.get('nome')).toBe('Armazém');
    expect(corpo.get('inativos')).toBe('1');
    expect(screen.getByTestId('onde')).toHaveTextContent('/cadastros/locais/1?inativos=1');
  });
});

function equipe(): DadosDaEquipe {
  return {
    local: { id: 9, nome: 'CD 9', cliente_id: 5 },
    perfis: [['pleno', 'Coordenador'], ['encarregado', 'Encarregado / ASG'], ['cliente', 'Cliente (portal do cliente)']],
    eu: { nome: 'Gerente', e_admin: false },
    superiores: [], locais: [{ id: 9, nome: 'CD 9' }, { id: 10, nome: 'CD 10' }],
    clientes: [{ id: 5, nome: 'GL' }], convites: [], equipe: [],
    passos: { atual: 4, local: { id: 9, nome: 'CD 9' }, cliente: { id: 5, nome: 'GL' } },
    links: { concluir: '/rotas/locais/9' },
  };
}

describe('o convite', () => {
  it('cada função mostra os seus campos; o local do passo já vem marcado', async () => {
    abrir(<Equipe dados={equipe()} />);
    expect(screen.getByLabelText('Função')).toHaveValue('encarregado');
    expect(screen.getByLabelText('Responde a').closest('[data-so-equipe]')).not.toHaveAttribute('hidden');
    expect(screen.getByLabelText('De qual cliente').closest('[data-so-cliente]')).toHaveAttribute('hidden');
    expect(screen.getByLabelText('CD 9')).toBeChecked();
    expect(screen.getByLabelText('CD 10')).not.toBeChecked();
    expect(screen.getByRole('option', { name: 'Você (Gerente)' })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Função'), 'cliente');
    expect(screen.getByLabelText('De qual cliente').closest('[data-so-cliente]')).not.toHaveAttribute('hidden');
    expect(screen.getByLabelText('Responde a').closest('[data-so-equipe]')).toHaveAttribute('hidden');
  });

  it('recusado, o recado aparece e o formulário fica como estava; aceito, a página do link', async () => {
    resposta = { status: 400, corpo: { error: 'Informe o nome da pessoa.' } };
    abrir(<Equipe dados={equipe()} />);
    await userEvent.type(screen.getByLabelText('Nome'), 'Joana');
    await userEvent.type(screen.getByLabelText('E-mail (é com ele que a pessoa entra)'), 'a@b.com');
    await userEvent.click(screen.getByRole('button', { name: 'Criar convite' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Informe o nome da pessoa.');
    expect(screen.getByLabelText('E-mail (é com ele que a pessoa entra)')).toHaveValue('a@b.com');
    expect(screen.getByLabelText('Nome')).toHaveValue('Joana');
    resposta = { status: 200, corpo: {
      convite: { nome: 'Joana', email: 'a@b.com' }, perfil: 'Encarregado / ASG', locais: ['CD 9'], enviado: false,
      link: 'http://x/convite/abc', whatsapp: 'https://wa.me/55?text=x', email: 'mailto:a@b.com',
      local: { id: 9, nome: 'CD 9' }, passos: equipe().passos,
    } };
    await userEvent.click(screen.getByRole('button', { name: 'Criar convite' }));
    expect(await screen.findByRole('heading', { name: 'Convite pronto' })).toBeInTheDocument();
    expect(screen.getByLabelText('Ou copie o link')).toHaveValue('http://x/convite/abc');
    expect(screen.getByText(/O e-mail não saiu agora/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Convidar outra pessoa/ })).toHaveAttribute('href', '/novo-contrato/9/equipe');
  });
});
