"""Fábricas para os testes das fases novas: pessoas, estrutura e login."""
from tests.conftest import CONTRATOS_SEMEADOS

SENHA = 'senha12345'

# Quem foi criado por aqui: o conftest desliga ao fim de cada teste (pessoa
# ativa vinculada a um local passa a ser "gestor do contrato" para os outros
# testes e recebe os avisos deles).
CRIADAS = set()


def desligar_criadas():
    from app import User, db
    if not CRIADAS:
        return
    for u in User.query.filter(User.email.in_(CRIADAS)):
        u.is_active = False
        u.clients = []
    db.session.commit()
    CRIADAS.clear()


def pessoa(app_module, email, papel='encarregado', locais=(), **extra):
    """Cria (ou reaproveita) uma pessoa ativa; devolve o id."""
    from app import Client, User, db
    u = User.query.filter_by(email=email).first()
    if u is None:
        u = User(name=extra.pop('nome', email.split('@')[0].title()), email=email)
        db.session.add(u)
    u.role = papel
    u.is_active = True
    u.is_deleted = False
    u.must_change_password = False
    u.failed_login_count = 0
    u.lockout_until = None
    u.all_clients = False
    for k, v in extra.items():
        setattr(u, k, v)
    u.set_password(SENHA)
    CRIADAS.add(email)
    u.clients = [local(nome) if isinstance(nome, str) else db.session.get(Client, nome)
                 for nome in locais]
    db.session.commit()
    return u.id


def local(nome=CONTRATOS_SEMEADOS[0]):
    from app import Client
    return Client.query.filter_by(name=nome).one()


def entrar(app_module, email, senha=SENHA):
    c = app_module.app.test_client()
    r = c.post('/login', data={'email': email, 'password': senha})
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    return c


def estrutura(app_module, nome_local=CONTRATOS_SEMEADOS[0], autor=None):
    """Empresa → cliente → local (BA) → setor → ambiente → equipamento → ponto.

    Devolve um dicionário com os ids.
    """
    from app import db
    from facilities.cadastros import servico
    from facilities.cadastros.models import Estado
    loc = local(nome_local)
    emp = servico.salvar_empresa(None, {'nome': 'Trino Serviços'}, autor)
    cli = servico.salvar_contratante(None, {'nome': 'Grupo GL', 'empresa_id': emp.id,
                                            'centro_custo': 'GL'}, autor)
    ba = Estado.query.filter_by(sigla='BA').one()
    ba.is_active = True
    servico.vincular_local(loc, {'contratante_id': cli.id, 'estado_id': ba.id}, autor)
    setor = servico.salvar_setor(loc, None, {'nome': 'Administrativo'}, autor)
    amb = servico.salvar_ambiente(loc, None, {'nome': 'Banheiro masculino 2º andar',
                                              'setor_id': setor.id}, autor)
    eq = servico.salvar_equipamento(loc, None, {'nome': 'Secador de mãos',
                                                'ambiente_id': amb.id}, autor)
    ponto = servico.salvar_ponto(loc, None, {'nome': 'Porta do banheiro',
                                             'ambiente_id': amb.id}, autor)
    db.session.commit()
    return {'local': loc.id, 'empresa': emp.id, 'cliente': cli.id, 'estado': ba.id,
            'setor': setor.id, 'ambiente': amb.id, 'equipamento': eq.id,
            'ponto': ponto.id, 'qr': ponto.codigo_qr}
