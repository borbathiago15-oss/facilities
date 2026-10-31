import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import type { Eu } from './api';
import { Casca } from './Casca';
import { Inicio } from './paginas/Inicio';

const EU: Eu = {
  id: 1, nome: 'Ana Souza', primeiro_nome: 'Ana', perfil: 'Supervisor', papel: 'supervisor',
  cliente: false, avisos_nao_lidos: 3, csrf: 'tok', versao: 'v1',
  links: { inicio: '/', avisos: '/avisos', trocar_senha: '/trocar-senha', seguranca: '/seguranca', sair: '/logout' },
  menu: [
    { titulo: 'Hoje', fixo: true, aberto: true, itens: [
      { endpoint: 'core.inicio', rotulo: 'Início', icone: 'bi-house-door', url: '/' }] },
    { titulo: 'Operação', fixo: false, aberto: true, itens: [
      { endpoint: 'chamados.index', rotulo: 'Chamados', icone: 'bi-tools', url: '/chamados/' }] },
  ],
};

function montar() {
  return render(
    <MemoryRouter><Casca eu={EU}><Inicio eu={EU} /></Casca></MemoryRouter>,
  );
}

describe('Casca', () => {
  it('mostra o menu do servidor, o sino e a pessoa', () => {
    montar();
    expect(screen.getByRole('navigation', { name: 'Módulos' })).toHaveTextContent('Chamados');
    expect(screen.getByRole('link', { name: 'Avisos: 3 não lido(s)' })).toHaveAttribute('href', '/avisos');
    expect(screen.getByRole('heading', { name: 'Olá, Ana' })).toBeInTheDocument();
  });

  it('a gaveta do celular abre e fecha (botão e Esc)', async () => {
    const u = userEvent.setup();
    montar();
    const botao = screen.getByRole('button', { name: 'Menu' });
    await u.click(botao);
    expect(document.body).toHaveClass('fc-menu-aberto');
    expect(botao).toHaveAttribute('aria-expanded', 'true');
    await u.keyboard('{Escape}');
    expect(document.body).not.toHaveClass('fc-menu-aberto');
    expect(botao).toHaveFocus();
  });

  it('sair é um envio com o CSRF (nunca um link)', () => {
    montar();
    const form = screen.getByRole('button', { name: /Sair/ }).closest('form')!;
    expect(form).toHaveAttribute('method', 'post');
    expect(form.querySelector('input[name="csrf_token"]')).toHaveValue('tok');
  });
});
