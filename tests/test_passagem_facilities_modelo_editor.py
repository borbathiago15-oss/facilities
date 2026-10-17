"""O editor do modelo de passagem: salvar sem mexer em nada devolve o modelo IGUAL.

O defeito, como apareceu no celular: o administrador criou os modelos
prontos, abriu o de Manutenção em Configurar e tocou em "Salvar modelo" sem
mudar nada. A pergunta "Situação geral do turno" — uma ESCOLHA com o
semáforo 🟢 Normal / 🟡 Atenção / 🔴 Crítico — voltou como Sim/Não
obrigatória, sem as opções. O editor não oferecia o tipo "escolha" (o
seletor ficava em branco), não mandava as opções, e o servidor lia o tipo
vazio como Sim/Não. Daí em diante o encarregado via uma chave "Concluído"
no lugar do semáforo, e a pergunta passava a pesar na aderência.

O que se prova:

* o corpo que o editor manda (``saveConfig`` em diario_config.js), com o
  modelo pronto aberto e nada mudado, devolve tipo, opções, obrigatoriedade
  e código de toda pergunta — e o resto do modelo;
* o editor oferece todo tipo que os modelos prontos usam, manda as opções da
  escolha e o código da pergunta que já existia;
* o corpo da tela ANTIGA (tipo vazio, sem opções — ainda guardada no
  navegador de alguém) não estraga mais a pergunta que já existia;
* pergunta NOVA com tipo inválido é recusada, em vez de virar Sim/Não;
* os exemplos do editor são de facilities, não de armazém;
* salvar deixa o recado "Modelo salvo" para a tela que recarrega.
"""
import json
import os
import re

import pytest

from facilities.passagem.models import DiarioConfiguracao
from facilities.passagem.modelos_prontos import MODELOS, SEMAFORO

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _js(nome):
    """O JS sem as linhas de comentário — que citam o texto antigo de propósito."""
    with open(os.path.join(RAIZ, 'facilities', 'static', 'js', nome), encoding='utf-8') as f:
        return '\n'.join(l for l in f.read().splitlines()
                         if not l.lstrip().startswith('//'))


@pytest.fixture()
def contrato(app_module, auth_client):
    """Um contrato com os três modelos prontos criados pelo formulário."""
    with app_module.app.app_context():
        cid = app_module.Client.query.order_by(app_module.Client.id).first().id
    r = auth_client.post('/passagem-de-turno/modelos-prontos',
                         data={'client_id': cid, 'servico': list(MODELOS)})
    assert r.status_code == 302
    return cid


def _configs_da_tela(html):
    """O que o navegador lê: o ``data-configs`` do editor."""
    m = re.search(r"data-configs='([^']*)'", html)
    assert m, 'data-configs não encontrado na tela de configuração'
    return json.loads(m.group(1))


def _nome(item):
    return item['nome'] if isinstance(item, dict) else item


def _corpo_do_editor(m):
    """O corpo que ``saveConfig`` monta com o modelo ``m`` aberto e nada mudado.

    Linha a linha, como o JS: cada pergunta leva nome, o código que a linha
    guardou (``data-codigo``), o tipo do seletor, a obrigatoriedade e — na
    escolha — as opções da caixa, uma por linha.
    """
    perguntas = []
    for x in m['perguntas']:
        p = {'nome': x['nome'], 'codigo': x['codigo'], 'tipo': x['tipo'],
             'obrigatorio': x['obrigatorio']}
        if x['tipo'] == 'escolha':
            p['opcoes'] = [o.strip() for o in '\n'.join(x['opcoes']).split('\n') if o.strip()]
        perguntas.append(p)
    return {'client_id': m['client_id'], 'nome': m['nome'], 'area_id': m['area_id'],
            'descricao': m['descricao'], 'ativo': m['ativo'],
            'turnos': [{'nome': _nome(t)} for t in m['turnos']],
            'perguntas': perguntas,
            'tipos_ocorrencia': [{'nome': _nome(t)} for t in m['tipos_ocorrencia']]}


def _retrato(cfg):
    """Tudo o que o modelo guarda e a tela do encarregado lê."""
    return {'nome': cfg.nome, 'area_id': cfg.area_id, 'descricao': cfg.descricao,
            'ativo': cfg.ativo, 'turnos': json.loads(cfg.turnos_json),
            'atividades': json.loads(cfg.atividades_json),
            'campos': json.loads(cfg.campos_json),
            'tipos_ocorrencia': json.loads(cfg.tipos_ocorrencia_json)}


def _situacao_geral(cfg):
    campos = json.loads(cfg.campos_json)
    return next((c for c in campos if c['nome'] == 'Situação geral do turno'), None)


# ── Salvar sem mudar nada ────────────────────────────────────────────────

def test_salvar_modelo_pronto_sem_mudar_nada_devolve_o_mesmo_modelo(
        app_module, auth_client, contrato):
    html = auth_client.get(f'/passagem-de-turno/configuracao?client_id={contrato}'
                           ).get_data(as_text=True)
    modelos = _configs_da_tela(html)
    assert len(modelos) == len(MODELOS)
    with app_module.app.app_context():
        antes = {c.id: _retrato(c) for c in
                 DiarioConfiguracao.query.filter_by(client_id=contrato)}

    for m in modelos:
        r = auth_client.put(f'/passagem-de-turno/api/configuracoes/{m["id"]}',
                            json=_corpo_do_editor(m))
        assert r.status_code == 200, r.get_data(as_text=True)

    with app_module.app.app_context():
        for cfg in DiarioConfiguracao.query.filter_by(client_id=contrato):
            assert _retrato(cfg) == antes[cfg.id], cfg.nome
            # O semáforo continua semáforo: escolha, obrigatória, com as três
            # opções — e FORA da rotina que conta na aderência.
            semaforo = _situacao_geral(cfg)
            assert semaforo is not None, cfg.nome
            assert semaforo['tipo'] == 'escolha'
            assert semaforo['opcoes'] == SEMAFORO
            assert semaforo['obrigatorio'] is True
            assert 'Situação geral do turno' not in [
                a['nome'] for a in json.loads(cfg.atividades_json)]


def test_o_editor_oferece_todo_tipo_que_os_modelos_prontos_usam():
    """O seletor de tipo em branco era a raiz do defeito."""
    js = _js('diario_config.js')
    m = re.search(r'var TIPOS = \[(.*?)\];', js, re.S)
    assert m, 'lista TIPOS não encontrada no editor'
    oferecidos = set(re.findall(r"\['([a-z_]+)'", m.group(1)))
    usados = {p['tipo'] for modelo in MODELOS.values() for p in modelo['perguntas']}
    assert usados <= oferecidos
    from facilities.passagem.rotas import TIPOS_DE_PERGUNTA
    assert oferecidos == set(TIPOS_DE_PERGUNTA)


def test_o_editor_manda_as_opcoes_e_o_codigo_da_pergunta():
    js = _js('diario_config.js')
    salvar = js[js.index('function saveConfig'):]
    salvar = salvar[:salvar.index('var caixaAreas')]
    # A escolha leva as opções da caixa, uma por linha.
    assert "tipo === 'escolha'" in salvar
    assert 'p.opcoes =' in salvar and ".cfg-p-opcoes" in salvar
    # O código da pergunta que já existia volta igual (se não foi renomeada).
    assert 'linha.dataset.codigo' in salvar
    # E a linha guarda opções e código ao abrir o modelo.
    assert 'addCfgPergunta(x.nome, x.tipo, x.obrigatorio, x.opcoes, x.codigo)' in js


def test_o_corpo_da_tela_antiga_nao_estraga_a_escolha(app_module, auth_client, contrato):
    """A tela antiga mandava ``tipo: ''`` e nenhuma opção para o semáforo.

    Quem ainda tiver o JS velho no navegador não pode transformar a
    pergunta em Sim/Não: a pergunta que já existe guarda tipo e opções.
    """
    with app_module.app.app_context():
        cfg = DiarioConfiguracao.query.filter_by(
            client_id=contrato, nome=MODELOS['manutencao']['nome']).one()
        cfg_id = cfg.id
        from facilities.passagem.rotas import _config_payload
        m = _config_payload(cfg)
    corpo = _corpo_do_editor(m)
    for p in corpo['perguntas']:
        if p['tipo'] == 'escolha':
            p['tipo'] = ''
            p.pop('opcoes')
    r = auth_client.put(f'/passagem-de-turno/api/configuracoes/{cfg_id}', json=corpo)
    assert r.status_code == 200
    with app_module.app.app_context():
        semaforo = _situacao_geral(DiarioConfiguracao.query.get(cfg_id))
    assert semaforo is not None
    assert (semaforo['tipo'], semaforo['opcoes']) == ('escolha', SEMAFORO)


def test_pergunta_nova_com_tipo_invalido_e_recusada(app_module, auth_client, contrato):
    with app_module.app.app_context():
        cfg = DiarioConfiguracao.query.filter_by(
            client_id=contrato, nome=MODELOS['limpeza']['nome']).one()
        cfg_id, antes = cfg.id, _retrato(cfg)
    for tipo in ('', 'semaforo'):
        r = auth_client.put(f'/passagem-de-turno/api/configuracoes/{cfg_id}', json={
            'perguntas': [{'nome': 'Pergunta nova', 'codigo': 'pergunta_nova',
                           'tipo': tipo, 'obrigatorio': True}]})
        assert r.status_code == 400
        assert r.is_json and 'tipo de resposta' in r.get_json()['error']
    r = auth_client.post('/passagem-de-turno/api/configuracoes', json={
        'client_id': contrato, 'nome': 'Modelo com tipo errado',
        'perguntas': [{'nome': 'X', 'tipo': 'semaforo'}]})
    assert r.status_code == 400
    with app_module.app.app_context():
        # Nada mudou: nem o modelo existente, nem um modelo novo pela metade.
        assert _retrato(DiarioConfiguracao.query.get(cfg_id)) == antes
        assert DiarioConfiguracao.query.filter_by(
            nome='Modelo com tipo errado').count() == 0


def test_pergunta_sem_a_chave_tipo_continua_sendo_sim_nao(auth_client, contrato):
    """O formato antigo — quem nunca mandou tipo — segue valendo."""
    r = auth_client.post('/passagem-de-turno/api/configuracoes', json={
        'client_id': contrato, 'nome': 'Formato antigo',
        'perguntas': [{'nome': 'Portaria aberta no horário', 'obrigatorio': True}]})
    assert r.status_code == 201
    assert r.get_json()['perguntas'][0]['tipo'] == 'sim_nao'


# ── Os exemplos e o recado ───────────────────────────────────────────────

LOGISTICA = ('Expedição', 'Almoxarifado', '5S', 'Devolução', 'Ex.: T1', ', CD')


def test_os_exemplos_do_editor_sao_de_facilities(auth_client, contrato):
    js = _js('diario_config.js')
    for palavra in LOGISTICA:
        assert palavra not in js, palavra
    assert 'Limpeza, Portaria, Manutenção predial' in js
    html = auth_client.get(f'/passagem-de-turno/configuracao?client_id={contrato}'
                           ).get_data(as_text=True)
    assert 'Passagem da Expedição' not in html
    assert 'placeholder="Ex.: Limpeza — rotina do turno"' in html


def test_salvar_o_modelo_deixa_o_recado_para_a_tela_que_recarrega():
    """A tela voltava ao topo sem dizer se tinha salvo."""
    js = _js('diario_config.js')
    salvar = js[js.index('function saveConfig'):]
    salvar = salvar[:salvar.index('var caixaAreas')]
    aviso = salvar.index("sessionStorage.setItem('fc-aviso'")
    assert "tipo: 'success'" in salvar[aviso:]
    assert aviso < salvar.index("window.location = '/passagem-de-turno/configuracao")
