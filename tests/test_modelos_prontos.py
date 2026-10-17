"""Modelos prontos de facilities (limpeza, portaria, manutenção predial).

* criam a área e um modelo utilizável de verdade: a nova passagem abre com
  os turnos e as perguntas, e o encerramento conta a aderência pela rotina;
* rodar de novo não duplica nem apaga o que o gestor ajustou;
* o código de cada pergunta é o mesmo que a tela de configuração gera;
* quem não configura a passagem não cria modelo pronto.
"""
import json

from facilities.passagem.models import DiarioArea, DiarioConfiguracao
from facilities.passagem.modelos_prontos import MODELOS, codigo_de


def _cid(app_module):
    with app_module.app.app_context():
        from app import Client
        return Client.query.order_by(Client.id).first().id


def test_o_formulario_cria_area_e_modelo(app_module, auth_client):
    cid = _cid(app_module)
    tela = auth_client.get(f'/passagem-de-turno/configuracao?client_id={cid}').get_data(as_text=True)
    assert 'Começar com um modelo pronto' in tela
    r = auth_client.post('/passagem-de-turno/modelos-prontos',
                         data={'client_id': cid, 'servico': ['limpeza', 'portaria']})
    assert r.status_code == 302
    with app_module.app.app_context():
        areas = {a.nome for a in DiarioArea.query.filter_by(client_id=cid)}
        assert areas == {'Limpeza e conservação', 'Portaria e segurança'}
        cfg = DiarioConfiguracao.query.filter_by(client_id=cid,
                                                 nome=MODELOS['portaria']['nome']).one()
        assert [t['nome'] for t in json.loads(cfg.turnos_json)] == ['Diurno', 'Noturno']
        atividades = json.loads(cfg.atividades_json)
        assert atividades[0]['codigo'] == 'rondas_realizadas_nos_horarios_previstos'
        assert all(a['obrigatorio'] for a in atividades if 'Iluminação' not in a['nome'])
        campos = json.loads(cfg.campos_json)
        assert any(c['tipo'] == 'escolha' and c['opcoes'] for c in campos)


def test_rodar_de_novo_nao_duplica(app_module, auth_client):
    cid = _cid(app_module)
    for _ in range(2):
        auth_client.post('/passagem-de-turno/modelos-prontos',
                         data={'client_id': cid, 'servico': ['manutencao']})
    with app_module.app.app_context():
        assert DiarioArea.query.filter_by(client_id=cid).count() == 1
        assert DiarioConfiguracao.query.filter_by(client_id=cid).count() == 1


def test_o_modelo_pronto_serve_para_passar_o_turno(app_module, auth_client):
    cid = _cid(app_module)
    auth_client.post('/passagem-de-turno/modelos-prontos',
                     data={'client_id': cid, 'servico': ['limpeza']})
    with app_module.app.app_context():
        cfg = DiarioConfiguracao.query.filter_by(client_id=cid).one()
        atividades = json.loads(cfg.atividades_json)
        cfg_id = cfg.id
    tela = auth_client.get(f'/passagem-de-turno/turno?client_id={cid}').get_data(as_text=True)
    # As perguntas vão no JSON da tela (o navegador desenha o formulário).
    assert 'sanitarios_limpos_e_abastecidos' in tela
    dados = {f'atividade:{a["codigo"]}': {'concluido': True} for a in atividades}
    from facilities import tempo
    r = auth_client.post('/passagem-de-turno/api/turnos', json={
        'client_id': cid, 'configuracao_id': cfg_id, 'data_turno': tempo.hoje().isoformat(),
        'turno': '1º Turno', 'dados': dados, 'pendencias': [], 'ocorrencias': [],
        'finalizar': True})
    assert r.status_code == 201, r.get_data(as_text=True)


def test_codigo_igual_ao_da_tela():
    assert codigo_de('Bombas, caixas d’água e reservatórios verificados') == \
        'bombas_caixas_d_agua_e_reservatorios_verificados'
    assert codigo_de('  Situação geral do turno ') == 'situacao_geral_do_turno'


def test_sem_permissao_de_configurar_nao_cria(app_module):
    from tests.test_authz import _cleanup_users, _login, _make_user
    cid = _cid(app_module)
    with app_module.app.app_context():
        _uid, email = _make_user(app_module, role='encarregado', client_ids=[cid])
    c = app_module.app.test_client()
    _login(c, email)
    r = c.post('/passagem-de-turno/modelos-prontos', data={'client_id': cid, 'servico': ['limpeza']})
    assert r.status_code == 403
    with app_module.app.app_context():
        assert DiarioConfiguracao.query.filter_by(client_id=cid).count() == 0
        _cleanup_users(app_module, email)
