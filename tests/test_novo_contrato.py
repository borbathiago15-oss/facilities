"""Assistente "Novo contrato" e convites (decisões do dono, 22/10/2026).

* O gerente cria cliente (vira o gerente dele), local, estrutura e convida;
  o coordenador monta locais só nos clientes do gerente dele; quem é do
  posto não abre o assistente.
* Convite: link de uso único, 7 dias, só o hash no banco; a pessoa cria a
  senha e entra no perfil, no superior e nos locais escolhidos.
* Convites seguem a hierarquia e ficam dentro da carteira de quem convida.
* A etiqueta sai com o número do ponto no local e a logo do cliente.
"""
import io
import json
import re
from datetime import datetime, timedelta

import pytest

from tests import fabrica


def _png(lado=40):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGBA', (lado, lado), (157, 32, 44, 255)).save(buf, format='PNG')
    return buf.getvalue()


@pytest.fixture()
def base(app_module):
    """Empresa ativa, BA ativo, um gerente com um coordenador abaixo."""
    from app import User, db
    from facilities.cadastros import servico
    from facilities.cadastros.models import Estado
    with app_module.app.app_context():
        emp = servico.salvar_empresa(None, {'nome': 'Trino Serviços'}, None)
        Estado.query.filter_by(sigla='BA').one().is_active = True
        db.session.commit()
        gerente = fabrica.pessoa(app_module, 'gerente.nc@trino.com', 'gerente', nome='Gerente NC')
        coord = fabrica.pessoa(app_module, 'coord.nc@trino.com', 'pleno', nome='Coord NC')
        db.session.get(User, coord).superior_id = gerente
        db.session.commit()
        ba = Estado.query.filter_by(sigla='BA').one().id
        return {'empresa': emp.id, 'gerente': gerente, 'coord': coord, 'ba': ba}


def _cliente_e_local(app_module, base, c=None):
    # Os locais ficam de um teste para o outro (o conftest só os desliga): nome único.
    import uuid
    sufixo = uuid.uuid4().hex[:6]
    c = c or fabrica.entrar(app_module, 'gerente.nc@trino.com')
    r = c.post('/novo-contrato/cliente', data={
        'nome': 'Trino Frio Teste', 'centro_custo': 'TF', 'empresa_id': str(base['empresa']),
        'logo': (io.BytesIO(_png()), 'logo.png')}, content_type='multipart/form-data')
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    ctid = int(re.search(r'/cliente/(\d+)/local', r.headers['Location']).group(1))
    r = c.post(f'/novo-contrato/cliente/{ctid}/local', data={
        'name': f'Trino Frio — Armazém Teste {sufixo}', 'estado_id': str(base['ba']),
        'cost_center': 'TF-01'})
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    cid = int(re.search(r'/novo-contrato/(\d+)/estrutura', r.headers['Location']).group(1))
    return c, ctid, cid


def test_gerente_monta_cliente_local_estrutura_e_etiqueta(app_module, base):
    from app import Client, db
    from facilities.cadastros.models import Contratante, PontoInspecao
    c, ctid, cid = _cliente_e_local(app_module, base)
    with app_module.app.app_context():
        cli = db.session.get(Contratante, ctid)
        assert cli.gerente_id == base['gerente']
        assert cli.logo_key and cli.logo_key.endswith('.png')
        loc = db.session.get(Client, cid)
        assert loc.contratante_id == ctid and loc.responsible_user_id == base['gerente']
    r = c.post(f'/novo-contrato/{cid}/estrutura', data={
        'setor_nome': 'Administrativo', 'ambiente_nome': 'Recepção',
        'pontos': 'Porta principal\nBalcão', 'entrada': '1'})
    assert r.status_code == 302
    r = c.post(f'/novo-contrato/{cid}/estrutura', data={
        'setor_nome': 'administrativo', 'ambiente_nome': 'Banheiro masculino'})
    assert r.status_code == 302
    with app_module.app.app_context():
        pontos = PontoInspecao.query.filter_by(client_id=cid).order_by(PontoInspecao.id).all()
        assert [p.nome for p in pontos] == ['Porta principal', 'Balcão', 'Banheiro masculino']
        assert [p.entrada_do_local for p in pontos] == [True, False, False]
        # O mesmo setor (sem olhar maiúsculas): não criou "administrativo" de novo.
        assert len({p.ambiente.setor_id for p in pontos}) == 1
    tela = c.get(f'/novo-contrato/{cid}/estrutura').get_data(as_text=True)
    assert 'QR 001 · Porta principal · entrada' in tela and 'QR 003' in tela
    pdf = c.get(f'/cadastros/locais/{cid}/etiquetas.pdf')
    assert pdf.status_code == 200 and pdf.data.startswith(b'%PDF')
    assert c.get(f'/cadastros/clientes/{ctid}/logo.png').status_code == 200


def test_numero_do_ponto_nao_muda_quando_outro_e_desativado(app_module, base):
    from app import db
    from facilities.cadastros import montagem, servico
    from facilities.cadastros.models import PontoInspecao
    c, _ctid, cid = _cliente_e_local(app_module, base)
    c.post(f'/novo-contrato/{cid}/estrutura', data={
        'setor_nome': 'Operação', 'ambiente_nome': 'Doca', 'pontos': 'Doca 1\nDoca 2\nDoca 3'})
    with app_module.app.app_context():
        p1, p2, p3 = PontoInspecao.query.filter_by(client_id=cid).order_by(PontoInspecao.id)
        servico.definir_ativo('ponto', p2, False, None)
        db.session.commit()
        assert montagem.numeros_dos_pontos(cid)[p3.id] == 3


def test_coordenador_monta_local_so_nos_clientes_do_gerente(app_module, base):
    from app import Client, User, db
    from facilities.cadastros import servico
    _g, ctid, _cid = _cliente_e_local(app_module, base)
    with app_module.app.app_context():
        outro = servico.salvar_contratante(None, {'nome': 'Cliente de outro',
                                                  'empresa_id': base['empresa']}, None)
        db.session.commit()
        outro_id = outro.id
    c = fabrica.entrar(app_module, 'coord.nc@trino.com')
    # Cliente novo é do gerente.
    r = c.post('/novo-contrato/cliente', data={'nome': 'X', 'empresa_id': str(base['empresa'])})
    assert r.status_code == 302
    with app_module.app.app_context():
        from facilities.cadastros.models import Contratante
        assert Contratante.query.filter_by(nome='X').count() == 0
    assert c.get(f'/novo-contrato/cliente/{outro_id}/local').status_code == 403
    r = c.post(f'/novo-contrato/cliente/{ctid}/local', data={
        'name': 'Local do coordenador NC', 'estado_id': str(base['ba'])})
    assert r.status_code == 302
    with app_module.app.app_context():
        loc = Client.query.filter_by(name='Local do coordenador NC').order_by(Client.id.desc()).first()
        assert loc in db.session.get(User, base['coord']).clients


@pytest.mark.parametrize('papel', ['supervisor', 'encarregado', 'tecnico', 'visualizador'])
def test_quem_nao_e_gestao_nao_abre_o_assistente(app_module, base, papel):
    _g, ctid, cid = _cliente_e_local(app_module, base)
    with app_module.app.app_context():
        fabrica.pessoa(app_module, f'{papel}.nc@trino.com', papel, locais=[cid])
    c = fabrica.entrar(app_module, f'{papel}.nc@trino.com')
    for url in ('/novo-contrato', f'/novo-contrato/{cid}/estrutura',
                f'/novo-contrato/{cid}/equipe', '/convites'):
        assert c.get(url).status_code == 403, url
    r = c.post(f'/novo-contrato/{cid}/equipe', data={
        'nome': 'X', 'email': 'x@x.com', 'role': 'encarregado', 'locais': str(cid)})
    assert r.status_code == 403


def _convidar(c, cid, **dados):
    base_dados = {'nome': 'Maria Teste', 'email': 'maria.nc@trino.com', 'role': 'encarregado',
                  'telefone': '71 99999-0000', 'locais': str(cid)}
    base_dados.update(dados)
    r = c.post(f'/novo-contrato/{cid}/equipe', data=base_dados)
    return r, r.get_data(as_text=True)


def _token(html):
    return re.search(r'/convite/([A-Za-z0-9_-]{30,})', html).group(1)


def test_convite_do_gerente_cria_a_conta_no_lugar_certo(app_module, base):
    from app import User
    from facilities.cadastros.models import Convite
    from facilities.core.models import Notification
    c, _ctid, cid = _cliente_e_local(app_module, base)
    r, html = _convidar(c, cid, role='pleno', nome='Coordenadora Nova',
                        email='Coord.Nova@Trino.com')
    assert r.status_code == 200, html[:400]
    token = _token(html)
    assert 'https://wa.me/5571999990000?text=' in html and 'mailto:coord.nova@trino.com' in html
    with app_module.app.app_context():
        conv = Convite.query.filter_by(email='coord.nova@trino.com').one()
        assert token not in json.dumps([conv.token_hash, conv.locais_json])
        assert conv.superior_id == base['gerente']      # quem convida, por padrão
    publico = app_module.app.test_client()
    tela = publico.get(f'/convite/{token}').get_data(as_text=True)
    assert 'Coordenadora Nova'.split()[0] in tela and 'Trino Frio — Armazém Teste' in tela
    r = publico.post(f'/convite/{token}', data={'senha': 'curta', 'confirma': 'curta'})
    assert r.status_code == 400
    r = publico.post(f'/convite/{token}', data={'senha': 'senha-forte-1', 'confirma':
                                                'senha-forte-1'})
    assert r.status_code == 302 and '/login' in r.headers['Location']
    with app_module.app.app_context():
        u = User.query.filter_by(email='coord.nova@trino.com').one()
        assert u.role == 'pleno' and u.superior_id == base['gerente']
        assert [loc.id for loc in u.clients] == [cid]
        assert not u.must_change_password
        assert Notification.query.filter_by(user_id=base['gerente'],
                                            notification_type='convite').count() == 1
        fabrica.CRIADAS.add(u.email)
    # Uso único.
    assert publico.get(f'/convite/{token}').status_code == 404
    r = publico.post(f'/convite/{token}', data={'senha': 'outra-senha-1',
                                                'confirma': 'outra-senha-1'})
    assert r.status_code == 404
    # E entra com a senha que criou.
    fabrica.entrar(app_module, 'coord.nova@trino.com', 'senha-forte-1')


def test_convite_vencido_cancelado_ou_de_quem_saiu_nao_abre(app_module, base):
    from app import User, db
    from facilities.cadastros import montagem
    from facilities.cadastros.models import Convite
    c, _ctid, cid = _cliente_e_local(app_module, base)
    publico = app_module.app.test_client()
    _r, html = _convidar(c, cid)
    token = _token(html)
    with app_module.app.app_context():
        conv = Convite.query.filter_by(email='maria.nc@trino.com').one()
        assert montagem.convite_pelo_token(token, datetime.utcnow() + timedelta(days=8)) is None
        conv_id = conv.id
    # Link novo: o antigo deixa de valer.
    r = c.post(f'/convites/{conv_id}/novo-link')
    novo = _token(r.get_data(as_text=True))
    assert novo != token
    assert publico.get(f'/convite/{token}').status_code == 404
    assert publico.get(f'/convite/{novo}').status_code == 200
    # Quem convidou foi desativado: o convite cai junto.
    with app_module.app.app_context():
        db.session.get(User, base['gerente']).is_active = False
        db.session.commit()
    assert publico.get(f'/convite/{novo}').status_code == 404
    with app_module.app.app_context():
        db.session.get(User, base['gerente']).is_active = True
        db.session.commit()
    c.post(f'/convites/{conv_id}/cancelar')
    assert publico.get(f'/convite/{novo}').status_code == 404


def test_convite_segue_a_hierarquia_e_a_carteira(app_module, base):
    from app import Client
    _g, _ctid, cid = _cliente_e_local(app_module, base)
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'coord.nc@trino.com', 'pleno', locais=[cid],
                       superior_id=base['gerente'])
    c = fabrica.entrar(app_module, 'coord.nc@trino.com')
    for papel in ('gerente', 'cliente', 'visualizador', 'master', 'pleno'):
        r, html = _convidar(c, cid, role=papel)
        assert r.status_code == 400, papel
        assert 'não pode convidar' in html
    with app_module.app.app_context():
        fora = Client.query.filter(Client.id != cid).first().id
    r, html = _convidar(c, cid, locais=[str(cid), str(fora)])
    assert r.status_code == 400 and 'não está entre os seus' in html
    # O superior precisa ser o coordenador ou alguém da equipe dele.
    r, html = _convidar(c, cid, superior_id=str(base['gerente']))
    assert r.status_code == 400 and 'alguém da sua equipe' in html
    r, html = _convidar(c, cid, role='supervisor')
    assert r.status_code == 200


def test_convite_para_email_que_ja_existe_e_recusado(app_module, base):
    c, _ctid, cid = _cliente_e_local(app_module, base)
    r, html = _convidar(c, cid, email='COORD.nc@trino.com')
    assert r.status_code == 400 and 'Já existe uma pessoa com este e-mail' in html


def test_convite_sai_por_email_quando_ha_servidor(app_module, base):
    enviados = []
    app_module.app.extensions['facilities_correio'] = lambda *a: enviados.append(a)
    try:
        c, _ctid, cid = _cliente_e_local(app_module, base)
        r, html = _convidar(c, cid)
        assert r.status_code == 200 and 'já foi enviado' in html
    finally:
        app_module.app.extensions.pop('facilities_correio', None)
    para, assunto, texto = enviados[0]
    assert para == 'maria.nc@trino.com' and _token(html) in texto


def test_gerente_convida_cliente_do_portal(app_module, base):
    from app import User
    from facilities.cadastros.models import Convite
    c, ctid, cid = _cliente_e_local(app_module, base)
    r, html = _convidar(c, cid, role='cliente', cliente_id=str(ctid), email='cli.nc@frio.com')
    assert r.status_code == 200, html[:300]
    publico = app_module.app.test_client()
    publico.post(f'/convite/{_token(html)}', data={'senha': 'senha-do-cliente',
                                                   'confirma': 'senha-do-cliente'})
    with app_module.app.app_context():
        u = User.query.filter_by(email='cli.nc@frio.com').one()
        assert u.role == 'cliente' and u.cliente_id == ctid and u.clients == []
        assert Convite.query.filter_by(email='cli.nc@frio.com').one().usuario_id == u.id
        fabrica.CRIADAS.add(u.email)


def test_logo_recusa_arquivo_que_nao_e_imagem(app_module, base):
    c, ctid, _cid = _cliente_e_local(app_module, base)
    r = c.post(f'/novo-contrato/cliente/{ctid}/logo', data={
        'logo': (io.BytesIO(b'MZ\x90\x00 nao sou imagem'), 'logo.png')},
        content_type='multipart/form-data', follow_redirects=True)
    assert 'Não foi possível abrir esta imagem' in r.get_data(as_text=True)


def test_logo_de_outro_cliente_nao_abre(app_module, base):
    _g, ctid, _cid = _cliente_e_local(app_module, base)
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'coord.fora@trino.com', 'pleno',
                       locais=[fabrica.local().id])
    c = fabrica.entrar(app_module, 'coord.fora@trino.com')
    assert c.get(f'/cadastros/clientes/{ctid}/logo.png').status_code == 404
