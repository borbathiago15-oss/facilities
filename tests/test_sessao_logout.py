"""Fase 2 — sair encerra a sessão de verdade.

Antes o "Sair" só apagava o cookie deste navegador: uma cópia dele (ou o
"Manter conectado" de 14 dias) continuava abrindo o sistema.
"""
from tests import fabrica


def test_cookie_antigo_nao_abre_nada_depois_de_sair(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'sair@trino.com', 'pleno', locais=['Shopping Centro'])
    c = fabrica.entrar(app_module, 'sair@trino.com')
    assert c.get('/').status_code == 200
    copia = c.get_cookie('session').value
    lembrar = app_module.app.test_client()
    lembrar.post('/login', data={'email': 'sair@trino.com', 'password': fabrica.SENHA,
                                 'lembrar': '1'})
    assert lembrar.get('/').status_code == 200
    assert c.post('/logout').status_code == 302
    ladrao = app_module.app.test_client()
    ladrao.set_cookie('session', copia)
    assert ladrao.get('/').status_code == 302          # volta para o login
    assert lembrar.get('/').status_code == 302          # o outro aparelho também caiu


def test_entrar_de_novo_depois_de_sair_funciona(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'sair2@trino.com', 'encarregado', locais=['Shopping Centro'])
    c = fabrica.entrar(app_module, 'sair2@trino.com')
    c.post('/logout')
    c = fabrica.entrar(app_module, 'sair2@trino.com')
    assert c.get('/').status_code == 200
