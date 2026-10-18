"""POP/FIT do checklist (decisões do dono, 18/10/2026): a gestão escreve o
resumo (o procedimento do checklist) e guarda o documento completo no próprio
checklist; o cliente só vê o documento que a gestão marcar."""
import pytest

from tests import fabrica
from tests.test_rotas_servico import Arquivo

PDF = b'%PDF-1.4 POP do banheiro'
XLSX = b'PK\x03\x04 planilha da FIT'


@pytest.fixture()
def cena(app_module):
    from app import db
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        fabrica.pessoa(app_module, 'coord.pop@trino.com', 'pleno', locais=['Shopping Centro'])
        fabrica.pessoa(app_module, 'asg.pop@trino.com', 'encarregado', locais=['Shopping Centro'])
        fabrica.pessoa(app_module, 'fora.pop@trino.com', 'encarregado', locais=['Hospital Norte'])
        m = s.criar_modelo(fabrica.local().id, {'nome': 'Banheiro',
                                                'descricao': 'Luva e placa de piso molhado.'},
                           None)
        s.publicar(m, s.normalizar_itens([{'texto': 'Piso limpo?', 'tipo': 'sim_nao'}]),
                   {'descricao': 'Luva e placa de piso molhado.'}, None)
        db.session.commit()
        ids['modelo'] = m.id
    return ids


def _documento(app_module, mid):
    from facilities.rotas.models import ChecklistDocumento
    with app_module.app.app_context():
        return ChecklistDocumento.query.filter_by(modelo_id=mid).order_by(
            ChecklistDocumento.id.desc()).first()


def test_gestao_guarda_e_asg_abre_pelo_aplicativo(app_module, cena):
    coord = fabrica.entrar(app_module, 'coord.pop@trino.com')
    url = f"/rotas/modelos/{cena['modelo']}"
    r = coord.post(url + '/documentos', data={'arquivo': (Arquivo(PDF, 'POP Banheiro.pdf'),
                                                          'POP Banheiro.pdf')},
                   content_type='multipart/form-data', follow_redirects=True)
    pag = r.get_data(as_text=True)
    assert 'POP Banheiro.pdf' in pag and 'Só a equipe' in pag
    assert 'Resumo do procedimento (POP/FIT)' in pag
    doc = _documento(app_module, cena['modelo'])
    assert doc.mime == 'application/pdf' and not doc.visivel_cliente

    asg = fabrica.entrar(app_module, 'asg.pop@trino.com')
    r = asg.get(f'/rotas/documentos/{doc.id}')
    assert r.status_code == 200 and r.data == PDF
    assert 'attachment' in r.headers['Content-Disposition']
    turno = asg.get('/app/turno').get_data(as_text=True)
    assert f'/rotas/documentos/{doc.id}' in turno and 'Luva e placa' in turno

    # Quem é de outro local não abre; e o ASG não envia nem retira.
    fora = fabrica.entrar(app_module, 'fora.pop@trino.com')
    assert fora.get(f'/rotas/documentos/{doc.id}').status_code == 403
    assert asg.post(f'/rotas/documentos/{doc.id}/retirar').status_code == 403
    assert asg.post(url + '/documentos', data={'arquivo': (Arquivo(PDF, 'x.pdf'), 'x.pdf')},
                    content_type='multipart/form-data').status_code == 403


@pytest.mark.parametrize('nome,dados', [('falso.pdf', b'MZ executavel'), ('lista.csv', b'a;b'),
                                        ('virus.exe', b'MZ'), ('vazio.pdf', b'')])
def test_so_aceita_documento_de_verdade(app_module, cena, nome, dados):
    from app import Client, db
    from facilities.rotas import servico as s
    from facilities.rotas.models import ChecklistModelo
    from facilities.rotas.servico import RegraDaRota
    with app_module.app.app_context():
        m = db.session.get(ChecklistModelo, cena['modelo'])
        with pytest.raises(RegraDaRota):
            s.anexar_documento(m, Arquivo(dados, nome), None)
        assert s.anexar_documento(m, Arquivo(XLSX, 'FIT.xlsx'), None).mime.endswith('sheet')
        assert db.session.get(Client, cena['local']) is not None


def test_limite_e_retirar_sem_perder(app_module, cena):
    from app import db
    from facilities.rotas import servico as s
    from facilities.rotas.models import ChecklistDocumento, ChecklistModelo
    from facilities.rotas.servico import RegraDaRota
    with app_module.app.app_context():
        m = db.session.get(ChecklistModelo, cena['modelo'])
        for i in range(s.DOCUMENTOS_POR_CHECKLIST):
            s.anexar_documento(m, Arquivo(PDF, f'POP {i}.pdf'), None)
        with pytest.raises(RegraDaRota, match='No máximo'):
            s.anexar_documento(m, Arquivo(PDF, 'demais.pdf'), None)
        db.session.commit()
        primeiro = ChecklistDocumento.query.filter_by(modelo_id=m.id).first().id
    coord = fabrica.entrar(app_module, 'coord.pop@trino.com')
    coord.post(f'/rotas/documentos/{primeiro}/retirar')
    with app_module.app.app_context():
        d = db.session.get(ChecklistDocumento, primeiro)
        assert d is not None and d.is_active is False
        assert len(s.documentos_ativos(d.modelo)) == s.DOCUMENTOS_POR_CHECKLIST - 1
    assert coord.get(f'/rotas/documentos/{primeiro}').status_code == 404


def test_cliente_so_ve_o_que_a_gestao_marcar(app_module, cena):
    from app import db
    from facilities.rotas import servico as s
    from facilities.rotas.models import ChecklistModelo
    with app_module.app.app_context():
        doc = s.anexar_documento(db.session.get(ChecklistModelo, cena['modelo']),
                                 Arquivo(PDF, 'POP Banheiro.pdf'), None)
        db.session.commit()
        did = doc.id
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    with app_module.app.app_context():
        fabrica.cliente(app_module, 'cli.pop@gl.com', cena['cliente'])
    cli = fabrica.entrar_com_codigo(app_module, 'cli.pop@gl.com')
    pagina = f"/cliente/locais/{cena['local']}"
    assert 'POP Banheiro.pdf' not in cli.get(pagina).get_data(as_text=True)
    assert cli.get(f'/cliente/documentos/{did}').status_code == 404

    coord = fabrica.entrar(app_module, 'coord.pop@trino.com')
    coord.post(f'/rotas/documentos/{did}/cliente')
    assert 'POP Banheiro.pdf' in cli.get(pagina).get_data(as_text=True)
    r = cli.get(f'/cliente/documentos/{did}')
    assert r.status_code == 200 and r.data == PDF

    coord.post(f'/rotas/documentos/{did}/interno')
    assert cli.get(f'/cliente/documentos/{did}').status_code == 404


def test_copiar_da_biblioteca_leva_o_documento(app_module, cena):
    from app import db
    from facilities.rotas import servico as s
    with app_module.app.app_context():
        lib = s.criar_modelo(None, {'nome': 'Copa — padrão Trino'}, None)
        s.publicar(lib, s.normalizar_itens([{'texto': 'Pia limpa?', 'tipo': 'sim_nao'}]), {},
                   None)
        s.anexar_documento(lib, Arquivo(PDF, 'POP Copa.pdf'), None)
        db.session.commit()
        copia = s.copiar_da_biblioteca(lib, cena['local'], None)
        db.session.commit()
        docs = s.documentos_ativos(copia)
        assert [d.nome for d in docs] == ['POP Copa.pdf']
        assert docs[0].visivel_cliente is False
        assert docs[0].storage_key == s.documentos_ativos(lib)[0].storage_key
        # Na biblioteca não existe "mostrar ao cliente".
        lib_doc = s.documentos_ativos(lib)[0].id
        fabrica.pessoa(app_module, 'master.pop@trino.com', 'master')
    admin = fabrica.entrar(app_module, 'master.pop@trino.com')
    assert admin.post(f'/rotas/documentos/{lib_doc}/cliente').status_code == 404
