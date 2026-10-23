"""Desempenho (23/10/2026): o número de consultas ao banco não pode crescer
com o número de locais, rotas ou itens.

No teste de carga (50 locais, 200 pessoas, um mês de rotas), o app de campo
do gerente fazia 8 mil consultas por tela (7,4 s), o agendador 11 mil por
rodada (20 s) e o painel carregava 48 mil tarefas uma a uma. Estes testes
medem as consultas com 2 e com 5 locais: se alguém voltar a consultar "um
por um", o número cresce e o teste quebra.
"""
import uuid

import pytest
from sqlalchemy import event

from facilities import tempo
from tests import fabrica


class Contador:
    def __init__(self, engine):
        self.engine, self.n = engine, 0

    def _conta(self, *_a):
        self.n += 1

    def __enter__(self):
        self.n = 0
        event.listen(self.engine, 'before_cursor_execute', self._conta)
        return self

    def __exit__(self, *_a):
        event.remove(self.engine, 'before_cursor_execute', self._conta)


def _local_com_rota(app_module, autor):
    """Um local novo com setor, 3 pontos, um checklist e uma rota de 3 itens
    com dois horários cada, escalada para um encarregado do local."""
    from app import Client, db
    from facilities.cadastros import servico as cad
    from facilities.rotas import servico as s
    loc = Client(name=f'Local desempenho {uuid.uuid4().hex[:6]}', is_active=True)
    db.session.add(loc)
    db.session.flush()
    setor = cad.salvar_setor(loc, None, {'nome': 'Operação'}, autor)
    amb = cad.salvar_ambiente(loc, None, {'nome': 'Doca', 'setor_id': setor.id}, autor)
    pontos = [cad.salvar_ponto(loc, None, {'nome': f'Doca {i}', 'ambiente_id': amb.id}, autor)
              for i in range(3)]
    m = s.criar_modelo(loc.id, {'nome': 'Limpeza da doca'}, None)
    s.publicar(m, s.normalizar_itens([{'texto': 'Piso limpo?', 'tipo': 'sim_nao'}]), {}, None)
    rota = s.salvar_rota(loc, None, {'nome': 'Rota da doca', 'turno': 'T1',
                                     'hora_inicio': '00:00', 'hora_fim': '23:59',
                                     'tolerancia_min': '30', 'dias_semana': '1234567'})
    for p in pontos:
        s.salvar_item(rota, None, {'ponto_id': p.id, 'modelo_id': m.id,
                                   'horarios': '08:00, 14:00'})
    enc = fabrica.pessoa(app_module, f'enc.{loc.id}@desempenho.com', 'encarregado',
                         locais=[loc.id])
    s.salvar_escala(rota, {'user_id': enc, 'dias_semana': '1234567',
                           'data_inicio': (tempo.hoje().replace(day=1)).isoformat()})
    db.session.commit()
    return loc.id


@pytest.fixture()
def gerente(app_module):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'gerente.desempenho@trino.com', 'gerente', all_clients=True)
    return 'gerente.desempenho@trino.com'


def _medir(app_module, cliente, url):
    from app import db
    cliente.get(url)        # a primeira gera as tarefas; mede a segunda
    with app_module.app.app_context():
        engine = db.engine
    with Contador(engine) as c:
        r = cliente.get(url)
    assert r.status_code == 200, r.status_code
    return c.n


@pytest.mark.parametrize('url', ['/app/turno', '/app/', '/painel'])
def test_telas_do_gerente_nao_crescem_com_os_locais(app_module, gerente, url):
    from app import User
    with app_module.app.app_context():
        autor = User.query.filter_by(email='admin@grupotrino.com.br').one()
        for _ in range(2):
            _local_com_rota(app_module, autor)
    c = fabrica.entrar(app_module, gerente)
    com_2 = _medir(app_module, c, url)
    with app_module.app.app_context():
        autor = User.query.filter_by(email='admin@grupotrino.com.br').one()
        for _ in range(3):
            _local_com_rota(app_module, autor)
    com_5 = _medir(app_module, c, url)
    assert com_5 <= com_2 + 2, f'{url}: {com_2} consultas com 2 locais, {com_5} com 5'


def test_agendador_nao_cresce_com_os_locais(app_module):
    from app import User, db
    from facilities.rotas import servico
    from facilities.rotas.models import TarefaDia
    hoje = tempo.hoje()

    def gerar_e_medir():
        with Contador(db.engine) as c:
            servico.gerar(hoje)
            db.session.commit()
        return c.n

    with app_module.app.app_context():
        autor = User.query.filter_by(email='admin@grupotrino.com.br').one()
        for _ in range(2):
            _local_com_rota(app_module, autor)
        gerar_e_medir()                     # cria as tarefas
        com_2 = gerar_e_medir()             # já existem: só confere
        for _ in range(3):
            _local_com_rota(app_module, autor)
        gerar_e_medir()
        com_5 = gerar_e_medir()
        assert com_5 <= com_2 + 1, f'{com_2} consultas com 2 locais, {com_5} com 5'
        # E continua gerando cada horário uma vez só.
        por_item = db.session.query(TarefaDia.rota_item_id, TarefaDia.previsto_para,
                                    db.func.count()).filter(TarefaDia.data == hoje).group_by(
            TarefaDia.rota_item_id, TarefaDia.previsto_para).all()
        assert por_item and all(n == 1 for *_k, n in por_item)


def test_quem_pode_ser_escalado_e_a_mesma_conta_da_carteira(app_module):
    """A conta rápida de ``pessoas_escalaveis`` dá o mesmo que montar a
    carteira de cada pessoa (``hierarquia.carteira``), com cadeia, gente
    desativada no meio e quem vê todos os locais."""
    from app import Client, User, db
    from facilities.core.hierarquia import carteira
    from facilities.rotas.servico import PERFIS_ESCALAVEIS, pessoas_escalaveis
    with app_module.app.app_context():
        loc = fabrica.local()
        outro = Client.query.filter(Client.id != loc.id).first()
        sup = fabrica.pessoa(app_module, 'sup.esc@d.com', 'supervisor')
        sup_sem = fabrica.pessoa(app_module, 'sup.sem@d.com', 'supervisor', locais=[outro.id])
        meio = fabrica.pessoa(app_module, 'meio.esc@d.com', 'supervisor', superior_id=sup)
        fabrica.pessoa(app_module, 'enc.esc@d.com', 'encarregado', locais=[loc.id],
                       superior_id=meio)
        fabrica.pessoa(app_module, 'enc.fora@d.com', 'encarregado', locais=[outro.id],
                       superior_id=sup_sem)
        inativo = fabrica.pessoa(app_module, 'enc.inativo@d.com', 'encarregado',
                                 locais=[loc.id], superior_id=sup_sem)
        fabrica.pessoa(app_module, 'tec.todos@d.com', 'tecnico', all_clients=True)
        db.session.get(User, meio).is_active = False
        db.session.get(User, inativo).is_active = False
        db.session.commit()
        for local_id in (loc.id, outro.id):
            esperado = [p.id for p in User.query.filter(
                User.is_active.is_(True), User.is_deleted.is_(False),
                User.role.in_(PERFIS_ESCALAVEIS)).order_by(User.name)
                if carteira(p) is None or local_id in carteira(p)]
            assert [p.id for p in pessoas_escalaveis(local_id)] == esperado
        nomes = {p.email for p in pessoas_escalaveis(loc.id)}
        # O supervisor vê o local pelo encarregado abaixo (atravessando o
        # supervisor desativado); o do encarregado desativado, não.
        assert {'sup.esc@d.com', 'enc.esc@d.com', 'tec.todos@d.com'} <= nomes
        assert 'sup.sem@d.com' not in nomes
