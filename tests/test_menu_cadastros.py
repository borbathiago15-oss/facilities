"""Menu de Cadastros (pedido do dono, 19/10/2026): um grupo próprio, sempre
aberto, na ordem em que se monta um contrato; cada item só para quem abre a
tela."""
from tests import fabrica


def _menu(app_module, email, papel):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, email, papel, locais=['Shopping Centro'])
    html = fabrica.entrar(app_module, email).get('/').get_data(as_text=True)
    return html[html.index('fc-lat-nav'):html.index('fc-lat-rodape')]


def test_administrador_ve_todos_os_cadastros_em_ordem(app_module):
    menu = _menu(app_module, 'menu.master@trino.com', 'master')
    ordem = ['Empresas do grupo', 'Clientes', 'Estados em uso', 'Locais',
             'Estrutura e QR dos locais', 'Biblioteca de checklists']
    posicoes = [menu.index(t) for t in ordem]
    assert posicoes == sorted(posicoes)
    assert 'Integração' in menu


def test_administracao_do_sistema_so_do_administrador(app_module):
    """Pedido do dono (01/11/2026): "Pessoas e acessos" e "Armazenamento de
    fotos" num grupo próprio, depois dos cadastros, só para o administrador."""
    menu = _menu(app_module, 'menu.master2@trino.com', 'master')
    grupo = menu.index('Administração do sistema')
    assert menu.index('Biblioteca de checklists') < grupo
    assert grupo < menu.index('Pessoas e acessos') < menu.index('Armazenamento de fotos')
    assert 'href="/novo/admin/armazenamento"' in menu
    for papel in ('pleno', 'gerente', 'supervisor'):
        outro = _menu(app_module, f'menu.adm.{papel}@trino.com', papel)
        assert 'Administração do sistema' not in outro
        assert 'Armazenamento de fotos' not in outro


def test_coordenacao_ve_so_o_que_pode_abrir(app_module):
    menu = _menu(app_module, 'menu.pleno@trino.com', 'pleno')
    assert 'Estrutura e QR dos locais' in menu and 'Biblioteca de checklists' in menu
    for so_admin in ('Empresas do grupo', 'Pessoas e acessos', 'Integração'):
        assert so_admin not in menu


def test_campo_nao_ve_cadastros(app_module):
    menu = _menu(app_module, 'menu.asg@trino.com', 'encarregado')
    assert 'Cadastros' not in menu
