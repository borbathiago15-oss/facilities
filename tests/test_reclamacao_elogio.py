"""Reclamação e elogio pelo QR (decisões do dono, 27/10/2026).

* O QR pergunta: avisar um problema ou fazer um elogio.
* A reclamação vira a tarefa "Checar aviso" de quem está ESCALADO no ponto
  no dia — mesmo com a passada já feita —; sem escalado, vai ao supervisor
  (e ao coordenador). O que foi marcado aparece em palavras, não "Itens do
  checklist".
* A tela de cobranças ganha a aba "Avisos pelo QR" (equipe e cliente; o
  cliente só vê os locais dele).
* Elogio: 1 a 5 estrelas e comentário opcional; avisa quem cuida do ponto,
  entra no painel (fora da nota) e no relatório do cliente.
"""
import io
from datetime import datetime, timedelta

import pytest

from facilities import tempo
from tests import fabrica
from tests.test_portal_cliente import liberado  # noqa: F401  (fixture)


@pytest.fixture()
def cena(app_module):
    """Shopping Centro com um ponto no checklist, a Ana escalada nele hoje
    (tarefa às 00:01, já passada), supervisor e coordenador; e o Hospital
    Norte de outro cliente, com um aviso que o cliente GL não pode ver."""
    from app import db
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        ids['ana'] = fabrica.pessoa(app_module, 'ana.el@trino.com', 'encarregado',
                                    locais=['Shopping Centro'], nome='Ana Técnica')
        ids['sup'] = fabrica.pessoa(app_module, 'sup.el@trino.com', 'supervisor',
                                    locais=['Shopping Centro'])
        ids['coord'] = fabrica.pessoa(app_module, 'coord.el@trino.com', 'pleno',
                                      locais=['Shopping Centro'])
        ids['cli'] = fabrica.cliente(app_module, 'cliente.el@gl.com', ids['cliente'])
        loc = fabrica.local()
        m = s.criar_modelo(loc.id, {'nome': 'Banheiro'}, None)
        s.publicar(m, s.normalizar_itens([{'texto': 'Lixeiras esvaziadas?', 'tipo': 'sim_nao',
                                           'problema_se': 'nao'}]), {}, None)
        rota = s.salvar_rota(loc, None, {
            'nome': 'R', 'turno': 'T', 'hora_inicio': '00:00', 'hora_fim': '23:59',
            'dias_semana': '1234567', 'presencas_por_turno': '0'})
        s.salvar_item(rota, None, {'ponto_id': ids['ponto'], 'modelo_id': m.id,
                                   'horarios': '00:01'})
        ids['rota'] = rota.id
        db.session.commit()
    return ids


def _escalar_ana(app_module, cena):
    from app import db
    from facilities.rotas import servico as s
    from facilities.rotas.models import Rota
    with app_module.app.app_context():
        rota = db.session.get(Rota, cena['rota'])
        s.salvar_escala(rota, {'user_id': cena['ana'], 'dias_semana': '1234567',
                               'data_inicio': tempo.hoje().isoformat()})
        s.garantir_hoje([cena['local']])
        db.session.commit()


def _avisos(app_module, uid):
    from facilities.core.models import Notification
    with app_module.app.app_context():
        return [n.title for n in Notification.query.filter_by(user_id=uid)]


def _reclamar(app_module, qr, **campos):
    c = app_module.app.test_client()
    with app_module.app.app_context():
        from facilities.rotas import ocorrencias
        from facilities.cadastros.models import PontoInspecao
        codigo = ocorrencias.itens_reportaveis(
            PontoInspecao.query.filter_by(codigo_qr=qr).one())[0]['codigo']
    dados = {'itens': [codigo]}
    dados.update(campos)
    return c, c.post(f'/q/{qr}/ocorrencia', data=dados, content_type='multipart/form-data')


# ── O QR pergunta ─────────────────────────────────────────────────────────

def test_o_qr_pergunta_reclamar_ou_elogiar(app_module, cena):
    _escalar_ana(app_module, cena)
    html = app_module.app.test_client().get(f"/q/{cena['qr']}").get_data(as_text=True)
    assert 'O que você quer fazer?' in html
    assert 'Avisar um problema' in html and f"/q/{cena['qr']}/elogio" in html


# ── Reclamação: a tarefa de quem cuida do ponto ───────────────────────────

def test_reclamacao_vai_para_o_escalado_mesmo_com_a_passada_feita(app_module, cena):
    from app import db
    from facilities.rotas.models import CONCLUIDA_NO_PRAZO, OcorrenciaPublica, TarefaDia
    _escalar_ana(app_module, cena)
    with app_module.app.app_context():
        # A passada de hoje já foi feita: antes, ninguém "na rota" recebia.
        for t in TarefaDia.query.filter_by(ponto_id=cena['ponto']):
            t.status = CONCLUIDA_NO_PRAZO
        db.session.commit()
    c, r = _reclamar(app_module, cena['qr'])
    assert r.status_code == 302
    with app_module.app.app_context():
        oc = OcorrenciaPublica.query.one()
        assert oc.responsavel_id == cena['ana']
        assert oc.resumo == 'Lixeiras esvaziadas?' and oc.titulo == 'Lixeiras esvaziadas?'
    assert _avisos(app_module, cena['ana']) == ['Checar aviso: Lixeiras esvaziadas?']
    assert _avisos(app_module, cena['sup']) == ['Checar aviso: Lixeiras esvaziadas?']
    assert _avisos(app_module, cena['coord']) == []
    # Quem avisou vê o que marcou, em palavras.
    html = c.get(r.headers['Location']).get_data(as_text=True)
    assert 'Lixeiras esvaziadas?' in html and 'Itens do checklist' not in html


def test_sem_escalado_vai_para_a_supervisao(app_module, cena):
    from facilities.rotas.models import OcorrenciaPublica
    _reclamar(app_module, cena['qr'])
    with app_module.app.app_context():
        assert OcorrenciaPublica.query.one().responsavel_id is None
    assert _avisos(app_module, cena['ana']) == []
    assert _avisos(app_module, cena['sup']) == ['Checar aviso: Lixeiras esvaziadas?']
    assert _avisos(app_module, cena['coord']) == ['Checar aviso: Lixeiras esvaziadas?']


def test_no_turno_o_aviso_e_tarefa_sua(app_module, cena):
    _escalar_ana(app_module, cena)
    _reclamar(app_module, cena['qr'])
    ana = fabrica.entrar(app_module, 'ana.el@trino.com')
    dados = ana.get(f"/app/api/turno?local={cena['local']}").get_json()
    if 'ocorrencias' not in dados:            # a API do turno pode ser só o resumo
        html = ana.get('/app/turno').get_data(as_text=True)
        assert 'Lixeiras esvaziadas?' in html
    else:
        [o] = dados['ocorrencias']
        assert o['minha'] is True and o['tipo'] == 'Lixeiras esvaziadas?'
    html = ana.get('/app/').get_data(as_text=True)
    assert 'Checar aviso' in html and 'Sua' in html
    sup = fabrica.entrar(app_module, 'sup.el@trino.com')
    html = sup.get(f"/rotas/locais/{cena['local']}/dia").get_data(as_text=True)
    assert 'Lixeiras esvaziadas?' in html and 'tarefa de Ana Técnica' in html


# ── A aba "Avisos pelo QR" das cobranças ──────────────────────────────────

def test_aba_avisos_pelo_qr_na_equipe_e_no_cliente(app_module, cena, liberado):  # noqa: F811
    from app import db
    from facilities.cadastros import servico
    from facilities.cadastros.models import PontoInspecao
    from facilities.rotas import ocorrencias
    _reclamar(app_module, cena['qr'], texto='SO-DO-SHOPPING')
    with app_module.app.app_context():
        admin = fabrica.pessoa(app_module, 'adm.hn@trino.com', 'master')
        hn = fabrica.local('Hospital Norte')
        setor = servico.salvar_setor(hn, None, {'nome': 'Op'}, admin)
        amb = servico.salvar_ambiente(hn, None, {'nome': 'Copa', 'setor_id': setor.id}, admin)
        p = servico.salvar_ponto(hn, None, {'nome': 'Pia', 'ambiente_id': amb.id}, admin)
        db.session.commit()
        ocorrencias.abrir(db.session.get(PontoInspecao, p.id), 'outro', 'SO-DO-HOSPITAL')
        db.session.commit()
    coord = fabrica.entrar(app_module, 'coord.el@trino.com')
    html = coord.get('/cobrancas/').get_data(as_text=True)
    assert 'Avisos pelo QR' in html
    html = coord.get('/cobrancas/?aba=qr').get_data(as_text=True)
    assert 'Lixeiras esvaziadas?' in html and 'SO-DO-SHOPPING' in html
    assert 'SO-DO-HOSPITAL' not in html               # fora da carteira dele
    assert 'SO-DO-SHOPPING' not in coord.get('/cobrancas/?aba=qr&situacao=resolvida').get_data(
        as_text=True)
    cli = fabrica.entrar_com_codigo(app_module, 'cliente.el@gl.com')
    html = cli.get('/cliente/cobrancas?aba=qr').get_data(as_text=True)
    assert 'SO-DO-SHOPPING' in html and 'SO-DO-HOSPITAL' not in html
    assert 'Ana' not in html                           # nome da equipe não vai ao cliente


# ── Elogio ────────────────────────────────────────────────────────────────

def test_elogio_avisa_quem_cuida_do_ponto(app_module, cena):
    from facilities.rotas.models import ElogioPublico
    _escalar_ana(app_module, cena)
    c = app_module.app.test_client()
    html = c.get(f"/q/{cena['qr']}/elogio").get_data(as_text=True)
    assert 'Toque nas estrelas' in html and html.count('name="nota"') == 5
    r = c.post(f"/q/{cena['qr']}/elogio", data={'nota': '5', 'texto': 'Banheiro impecável'})
    assert r.status_code == 200 and 'Obrigado!' in r.get_data(as_text=True)
    with app_module.app.app_context():
        e = ElogioPublico.query.one()
        assert (e.nota, e.texto, e.responsavel_id, e.autor_id) == \
            (5, 'Banheiro impecável', cena['ana'], None)
        cols = {col.name for col in ElogioPublico.__table__.columns}
        assert not cols & {'nome', 'email', 'telefone', 'contato', 'ip'}
    assert _avisos(app_module, cena['ana']) == ['Elogio: 5 de 5 estrelas']
    assert _avisos(app_module, cena['sup']) == []      # elogio não é demanda


@pytest.mark.parametrize('nota', ['0', '6', 'muito', ''])
def test_elogio_recusa_nota_fora_de_1_a_5(app_module, cena, nota):
    from facilities.rotas.models import ElogioPublico
    r = app_module.app.test_client().post(f"/q/{cena['qr']}/elogio", data={'nota': nota})
    assert r.status_code == 400 and 'de 1 a 5 estrelas' in r.get_data(as_text=True)
    with app_module.app.app_context():
        assert ElogioPublico.query.count() == 0


def test_elogio_de_robo_e_de_ponto_desativado(app_module, cena):
    from app import db
    from facilities.cadastros.models import PontoInspecao
    from facilities.rotas.models import ElogioPublico
    c = app_module.app.test_client()
    assert c.post(f"/q/{cena['qr']}/elogio", data={'nota': '5', 'site': 'x'}).status_code == 400
    assert c.post('/q/naoexiste1234/elogio', data={'nota': '5'}).status_code == 404
    with app_module.app.app_context():
        db.session.get(PontoInspecao, cena['ponto']).is_active = False
        db.session.commit()
    r = c.post(f"/q/{cena['qr']}/elogio", data={'nota': '5'})
    assert r.status_code == 409 and 'não recebe mais' in r.get_data(as_text=True)
    with app_module.app.app_context():
        assert ElogioPublico.query.count() == 0


def test_limite_do_elogio_esta_declarado():
    import inspect
    from facilities.rotas import publico
    fonte = inspect.getsource(publico.elogio)
    assert "@limiter.limit('5 per hour', methods=['POST'])" in fonte
    assert "key_func=_chave_do_qr, methods=['POST']" in fonte


def _elogiar(app_module, cena, nota, texto=None, quando=None):
    from app import db
    from facilities.cadastros.models import PontoInspecao
    from facilities.rotas import ocorrencias
    with app_module.app.app_context():
        ocorrencias.elogiar(db.session.get(PontoInspecao, cena['ponto']), nota, texto,
                            agora_utc=quando)
        db.session.commit()


def test_painel_mostra_a_media_fora_da_nota(app_module, cena):
    _elogiar(app_module, cena, 5)
    _elogiar(app_module, cena, 4)
    coord = fabrica.entrar(app_module, 'coord.el@trino.com')
    html = coord.get('/painel').get_data(as_text=True)
    assert 'Elogios do público' in html and '4,5' in html and '2 avaliação(ões)' in html
    sup = fabrica.entrar(app_module, 'sup.el@trino.com')
    html = sup.get(f"/rotas/locais/{cena['local']}/dia").get_data(as_text=True)
    assert 'Elogios do público' in html and '5 de 5 estrelas' in html


def test_relatorio_do_cliente_traz_os_elogios(app_module, cena):
    from openpyxl import load_workbook
    from app import Client, db
    from facilities.relatorios import arquivos, cliente as rel
    hoje = tempo.hoje()
    primeiro = hoje.replace(day=1)
    meio_dia = tempo.para_utc(hoje, datetime.min.time()) + timedelta(hours=15)
    _elogiar(app_module, cena, 5, '=HYPERLINK("x")', quando=meio_dia)
    _elogiar(app_module, cena, 3, quando=meio_dia)
    with app_module.app.app_context():
        d = rel.dados(db.session.get(Client, cena['local']), primeiro)
        assert d['elogios']['total'] == 2 and d['elogios']['media'] == 4.0
        assert [c['texto'] for c in d['elogios']['comentarios']] == ['=HYPERLINK("x")']
        assert arquivos.pdf(d, [], lambda f: None)[:4] == b'%PDF'
        wb = load_workbook(io.BytesIO(arquivos.excel(d)))
        celulas = [c for linha in wb['Elogios'].iter_rows() for c in linha
                   if c.value == '=HYPERLINK("x")']
        assert celulas and all(c.data_type == 's' for c in celulas)
        # Relatório congelado antes dos elogios existirem: sem a chave, sem erro.
        antigo = dict(d)
        antigo.pop('elogios')
        assert arquivos.pdf(antigo, [], lambda f: None)[:4] == b'%PDF'
        arquivos.excel(antigo)
