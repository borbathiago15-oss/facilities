"""Assistente "Novo contrato" no CELULAR e no PC (decisões do dono, 22/10/2026):
o gerente cadastra o cliente com a logo, o local, um ambiente com o QR da
entrada e convida uma pessoa; a pessoa abre o link, cria a senha e entra.

Com ``E2E_CAPTURAS=<pasta>`` as telas viram PNG (para o dono ver).
"""
import os
import re

from conftest import abrir_contexto, entrar

CAPTURAS = os.environ.get('E2E_CAPTURAS')


def _capturar(pg, perfil, nome):
    if CAPTURAS:
        os.makedirs(CAPTURAS, exist_ok=True)
        pg.screenshot(path=os.path.join(CAPTURAS, f'{perfil}-{nome}.png'), full_page=True)


def _sem_rolagem_lateral(pg):
    assert pg.evaluate('document.documentElement.scrollWidth') <= pg.viewport_size['width']


def _logo(tmp_path):
    from PIL import Image, ImageDraw
    im = Image.new('RGB', (480, 160), (20, 80, 160))
    ImageDraw.Draw(im).text((30, 60), 'TRINO FRIO', fill='white')
    caminho = tmp_path / 'logo.png'
    im.save(caminho)
    return str(caminho)


def test_gerente_monta_o_contrato_e_a_pessoa_aceita_o_convite(servidor, navegador, perfil,
                                                              tmp_path):
    base = servidor['base']
    b, ctx = abrir_contexto(navegador, perfil)
    pg = ctx.new_page()
    entrar(pg, base, 'gerente@e2e.test')
    pg.goto(base + '/novo-contrato')
    assert pg.get_by_text('De qual cliente é o local?').is_visible()
    _sem_rolagem_lateral(pg)
    pg.click('summary:has-text("Cadastrar cliente novo")')
    pg.fill('#nome', 'Trino Frio')
    pg.fill('#centro_custo', 'TF')
    pg.set_input_files('#logo', _logo(tmp_path))
    _capturar(pg, perfil, '1-cliente')
    pg.click('button:has-text("Cadastrar e seguir para o local")')
    pg.wait_for_load_state('networkidle')

    # Passo 2: o local.
    assert pg.get_by_role('heading', name='Novo local').is_visible()
    pg.fill('#name', f'Trino Frio — Armazém {perfil}')
    pg.select_option('#estado_id', label='Bahia')
    _sem_rolagem_lateral(pg)
    _capturar(pg, perfil, '2-local')
    pg.click('button:has-text("Cadastrar e seguir para a estrutura")')
    pg.wait_for_load_state('networkidle')

    # Passo 3: um ambiente com a entrada.
    assert pg.get_by_role('heading', name='Estrutura e QR').is_visible()
    pg.fill('#setor_nome', 'Administrativo')
    pg.fill('#ambiente_nome', 'Recepção')
    pg.fill('#pontos', 'Porta de entrada\nBalcão')
    pg.check('#entrada')
    pg.click('form button:has-text("Cadastrar")')
    pg.wait_for_load_state('networkidle')
    assert pg.get_by_text('QR 001 · Porta de entrada · entrada').is_visible()
    _sem_rolagem_lateral(pg)
    _capturar(pg, perfil, '3-estrutura')
    with pg.expect_popup() as aba:
        pg.click('a:has-text("Imprimir etiquetas")')
    if CAPTURAS:
        # A folha de etiquetas (o PDF, baixado pela sessão do gerente).
        pdf = pg.request.get(aba.value.url)
        assert pdf.ok and pdf.body().startswith(b'%PDF')
        open(os.path.join(CAPTURAS, f'{perfil}-etiquetas.pdf'), 'wb').write(pdf.body())
    aba.value.close()

    # Passo 4: o convite.
    pg.click('a:has-text("Seguir para a equipe")')
    pg.wait_for_load_state('networkidle')
    pg.fill('#nome', 'Joana Encarregada')
    pg.fill('#email', f'joana.{perfil}@e2e.test')
    pg.fill('#telefone', '71 98888-7777')
    # Cada função mostra só os seus campos.
    pg.select_option('#role', label='Cliente (portal do cliente)')
    assert pg.is_visible('#cliente_id') and not pg.is_visible('#superior_id')
    pg.select_option('#role', label='Encarregado / ASG')
    assert not pg.is_visible('#cliente_id') and pg.is_visible('#superior_id')
    _sem_rolagem_lateral(pg)
    _capturar(pg, perfil, '4-equipe')
    pg.click('button:has-text("Criar convite")')
    pg.wait_for_load_state('networkidle')
    assert pg.get_by_role('heading', name='Convite pronto').is_visible()
    whatsapp = pg.get_attribute('a:has-text("Enviar pelo WhatsApp")', 'href')
    assert whatsapp.startswith('https://wa.me/5571988887777?text=')
    link = pg.input_value('#link')
    assert re.search(r'/convite/[A-Za-z0-9_-]{30,}$', link)
    _sem_rolagem_lateral(pg)
    _capturar(pg, perfil, '5-convite-pronto')
    ctx.close()
    b.close()

    # A pessoa convidada, noutro aparelho.
    b, ctx = abrir_contexto(navegador, perfil)
    pg = ctx.new_page()
    pg.goto(link)
    assert pg.get_by_text('Bem-vindo, Joana').is_visible()
    _sem_rolagem_lateral(pg)
    pg.fill('#senha', 'joana-senha-1')
    pg.fill('#confirma', 'joana-senha-1')
    _capturar(pg, perfil, '6-aceitar-convite')
    pg.click('button:has-text("Criar minha conta")')
    pg.wait_for_load_state('networkidle')
    assert '/login' in pg.url
    assert pg.input_value('input[name=email]') == f'joana.{perfil}@e2e.test'
    pg.fill('input[name=password]', 'joana-senha-1')
    pg.click('button[type=submit]')
    pg.wait_for_load_state('networkidle')
    assert '/app' in pg.url, pg.url
    _capturar(pg, perfil, '7-primeiro-acesso')
    linhas = servidor['sql']("SELECT role FROM users WHERE email = ?", f'joana.{perfil}@e2e.test')
    assert linhas == [('encarregado',)]
    ctx.close()
    b.close()
