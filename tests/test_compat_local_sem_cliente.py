"""Fase 1 — o que já existia continua igual num local com e sem cliente.

A Passagem de Turno e os Chamados não sabem nada de cliente, setor ou
ambiente nesta fase: as telas abrem do mesmo jeito nos dois casos.
"""
from tests import fabrica


def test_passagem_e_chamados_abrem_igual_com_e_sem_cliente(app_module, auth_client):
    with app_module.app.app_context():
        com = fabrica.estrutura(app_module)['local']
        sem = fabrica.local('Hospital Norte').id
    for cid in (com, sem):
        assert auth_client.get(f'/passagem-de-turno/configuracao?client_id={cid}').status_code \
            in (200, 302)
    assert auth_client.get('/chamados/').status_code == 200
    r = auth_client.post('/chamados/', data={'client_id': sem, 'titulo': 'Lâmpada',
                                                 'prioridade': 'media', 'categoria': 'eletrica'})
    assert r.status_code in (200, 302)
    r = auth_client.post('/chamados/', data={'client_id': com, 'titulo': 'Torneira',
                                                 'prioridade': 'media',
                                                 'categoria': 'hidraulica'})
    assert r.status_code in (200, 302)
    with app_module.app.app_context():
        from facilities.chamados.models import Chamado
        assert {c.client_id for c in Chamado.query} == {com, sem}
