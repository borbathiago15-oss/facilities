"""Fase 1 — as regras dos cadastros, direto no serviço.

* nome repetido no mesmo nível é recusado (sem olhar maiúsculas), inclusive
  contra o desativado — a mensagem manda reativar;
* desativar desce em cascata; reativar não, e não reativa debaixo de pai
  desativado; nada nasce debaixo de desativado;
* mover só dentro do mesmo local;
* o QR é aleatório, único e não muda;
* o banco recusa apagar pai com filho (RESTRICT).
"""
import pytest
from sqlalchemy.exc import IntegrityError

from tests import fabrica


@pytest.fixture()
def ctx(app_module):
    with app_module.app.app_context():
        yield app_module


def _s():
    from facilities.cadastros import servico
    return servico


def test_estrutura_completa_e_ids_ligados(ctx):
    ids = fabrica.estrutura(ctx)
    from facilities.cadastros.models import Ambiente, PontoInspecao
    from app import Client, db
    loc = db.session.get(Client, ids['local'])
    assert loc.contratante.nome == 'Grupo GL' and loc.estado.sigla == 'BA'
    amb = db.session.get(Ambiente, ids['ambiente'])
    assert amb.client_id == loc.id and amb.setor.nome == 'Administrativo'
    assert db.session.get(PontoInspecao, ids['ponto']).ambiente_id == amb.id


def test_nome_repetido_no_mesmo_nivel_e_recusado_sem_olhar_maiusculas(ctx):
    ids = fabrica.estrutura(ctx)
    s = _s()
    loc = fabrica.local()
    with pytest.raises(s.CadastroInvalido, match='Já existe'):
        s.salvar_setor(loc, None, {'nome': 'ADMINISTRATIVO'}, None)
    with pytest.raises(s.CadastroInvalido):
        s.salvar_ambiente(loc, None, {'nome': 'banheiro masculino 2º andar',
                                      'setor_id': ids['setor']}, None)
    # Outro setor pode ter um ambiente com o mesmo nome.
    outro = s.salvar_setor(loc, None, {'nome': 'Armazém 1'}, None)
    s.salvar_ambiente(loc, None, {'nome': 'Banheiro masculino 2º andar',
                                  'setor_id': outro.id}, None)
    # E outro local pode ter o seu "Administrativo".
    s.salvar_setor(fabrica.local('Hospital Norte'), None, {'nome': 'Administrativo'}, None)


def test_nome_de_desativado_manda_reativar(ctx):
    ids = fabrica.estrutura(ctx)
    s = _s()
    from facilities.cadastros.models import Setor
    from app import db
    s.definir_ativo('setor', db.session.get(Setor, ids['setor']), False, None)
    with pytest.raises(s.CadastroInvalido, match='Reative'):
        s.salvar_setor(fabrica.local(), None, {'nome': 'Administrativo'}, None)


def test_desativar_desce_em_cascata_e_reativar_nao(ctx):
    ids = fabrica.estrutura(ctx)
    s = _s()
    from facilities.cadastros.models import Ambiente, Equipamento, PontoInspecao, Setor
    from app import db
    setor = db.session.get(Setor, ids['setor'])
    s.definir_ativo('setor', setor, False, None)
    db.session.commit()
    for modelo, chave in ((Ambiente, 'ambiente'), (Equipamento, 'equipamento'),
                          (PontoInspecao, 'ponto')):
        assert db.session.get(modelo, ids[chave]).is_active is False
    amb = db.session.get(Ambiente, ids['ambiente'])
    with pytest.raises(s.CadastroInvalido, match='Reative primeiro'):
        s.definir_ativo('ambiente', amb, True, None)
    with pytest.raises(s.CadastroInvalido, match='desativado'):
        s.salvar_ambiente(fabrica.local(), None, {'nome': 'Copa', 'setor_id': setor.id}, None)
    s.definir_ativo('setor', setor, True, None)
    db.session.commit()
    assert db.session.get(Ambiente, ids['ambiente']).is_active is False   # escolha de quem reativa
    s.definir_ativo('ambiente', amb, True, None)
    assert amb.is_active is True


def test_mover_so_dentro_do_mesmo_local(ctx):
    ids = fabrica.estrutura(ctx)
    s = _s()
    from facilities.cadastros.models import Ambiente
    from app import db
    outro_local = fabrica.local('Hospital Norte')
    setor_alheio = s.salvar_setor(outro_local, None, {'nome': 'Recepção'}, None)
    loc = fabrica.local()
    amb = db.session.get(Ambiente, ids['ambiente'])
    with pytest.raises(s.CadastroInvalido, match='deste local'):
        s.salvar_ambiente(loc, amb, {'nome': amb.nome, 'setor_id': setor_alheio.id}, None)
    db.session.rollback()
    destino = s.salvar_setor(loc, None, {'nome': 'Operação'}, None)
    amb = db.session.get(Ambiente, ids['ambiente'])
    s.salvar_ambiente(loc, amb, {'nome': amb.nome, 'setor_id': destino.id}, None)
    db.session.commit()
    assert db.session.get(Ambiente, ids['ambiente']).setor_id == destino.id
    from facilities.cadastros.models import CadastroEvento
    assert CadastroEvento.query.filter_by(entidade='ambiente', entidade_id=amb.id,
                                          acao='movido').count() == 1


def test_ponto_e_equipamento_do_mesmo_ambiente(ctx):
    ids = fabrica.estrutura(ctx)
    s = _s()
    loc = fabrica.local()
    outro = s.salvar_ambiente(loc, None, {'nome': 'Copa', 'setor_id': ids['setor']}, None)
    with pytest.raises(s.CadastroInvalido, match='mesmo ambiente'):
        s.salvar_ponto(loc, None, {'nome': 'Pia', 'ambiente_id': outro.id,
                                   'equipamento_id': ids['equipamento']}, None)


def test_qr_aleatorio_unico_e_imutavel(ctx):
    ids = fabrica.estrutura(ctx)
    s = _s()
    from facilities.cadastros.models import PontoInspecao
    from app import db
    loc = fabrica.local()
    codigos = {s.salvar_ponto(loc, None, {'nome': f'P{i}', 'ambiente_id': ids['ambiente']},
                              None).codigo_qr for i in range(20)}
    db.session.commit()
    assert len(codigos) == 20
    assert all(len(c) >= 20 and not c.isdigit() for c in codigos)
    p = db.session.get(PontoInspecao, ids['ponto'])
    original = p.codigo_qr
    with pytest.raises(ValueError):
        p.codigo_qr = 'outro'
    db.session.rollback()
    # Editar, mover e desativar não mexem no QR.
    destino = s.salvar_ambiente(loc, None, {'nome': 'Copa', 'setor_id': ids['setor']}, None)
    p = db.session.get(PontoInspecao, ids['ponto'])
    s.salvar_ponto(loc, p, {'nome': 'Porta (novo nome)', 'ambiente_id': destino.id}, None)
    s.definir_ativo('ponto', p, False, None)
    db.session.commit()
    assert db.session.get(PontoInspecao, ids['ponto']).codigo_qr == original
    assert s.ponto_pelo_codigo(original).id == ids['ponto']
    assert s.ponto_pelo_codigo('x' * 40) is None


def test_banco_recusa_apagar_pai_com_filho(ctx):
    """RESTRICT nas chaves: o banco (Postgres, como a produção) recusa o
    DELETE do setor que tem ambiente, mesmo por fora do sistema."""
    from app import db
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('o SQLite dos testes não liga as chaves estrangeiras')
    ids = fabrica.estrutura(ctx)
    with pytest.raises(IntegrityError):
        db.session.execute(db.text('DELETE FROM setores WHERE id = :i'), {'i': ids['setor']})
    db.session.rollback()


def test_estado_com_local_ativo_nao_desativa(ctx):
    ids = fabrica.estrutura(ctx)
    s = _s()
    from facilities.cadastros.models import Estado
    from app import db
    ba = db.session.get(Estado, ids['estado'])
    with pytest.raises(s.CadastroInvalido, match='local'):
        s.definir_estado_ativo(ba, False, None)


def test_os_27_estados_vem_carregados(ctx):
    from facilities.cadastros.models import Estado
    assert Estado.query.count() == 27
    assert {e.sigla for e in Estado.query} >= {'BA', 'MG', 'SP', 'DF'}


def test_gerente_do_cliente_tem_de_ser_gestor_ativo(ctx):
    s = _s()
    enc = fabrica.pessoa(ctx, 'enc.gerente@trino.com', 'encarregado')
    ges = fabrica.pessoa(ctx, 'ges.gerente@trino.com', 'gerente')
    emp = s.salvar_empresa(None, {'nome': 'Trino Serviços'}, None)
    with pytest.raises(s.CadastroInvalido, match='gerente'):
        s.salvar_contratante(None, {'nome': 'GL', 'empresa_id': emp.id,
                                    'gerente_id': enc}, None)
    c = s.salvar_contratante(None, {'nome': 'GL', 'empresa_id': emp.id, 'gerente_id': ges}, None)
    assert c.gerente_id == ges
