"""Servidor descartável para os testes de navegador (SQLite temporário).

    python e2e/servidor.py <porta> <arquivo.db>

Semeia um local com estrutura, um ponto com QR conhecido (``QR_DO_TESTE``),
um modelo de passagem simples e três pessoas: o administrador, a Ana e a
Mariana (encarregadas do mesmo local, para o teste do celular compartilhado).
"""
import json
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

QR_DO_TESTE = 'QRdoTesteE2E0000000001'
SENHA = 'senha12345'


def montar(caminho_db):
    os.environ.update(DATABASE_URL=f'sqlite:///{caminho_db}', SECRET_KEY='e2e',
                      SESSION_COOKIE_SECURE='0', RATELIMIT_ENABLED='0',
                      STORAGE_BACKEND='local', UPLOAD_FOLDER=tempfile.mkdtemp())
    from facilities import create_app
    from facilities.extensions import db
    app = create_app()
    with app.app_context():
        db.create_all()
        from facilities.core.models import Client, User
        from facilities.cadastros.models import UFS, Estado, PontoInspecao
        from facilities.cadastros import servico
        from facilities.passagem.models import DiarioArea, DiarioConfiguracao
        for s, n in UFS:
            db.session.add(Estado(sigla=s, nome=n, is_active=(s == 'BA')))
        local = Client(name='GL Armazém 1', cost_center='GL-01', is_active=True)
        db.session.add(local)
        pessoas = {}
        for email, nome, papel in (('admin@e2e.test', 'Administrador', 'master'),
                                   ('ana@e2e.test', 'Ana Souza', 'encarregado'),
                                   ('mariana@e2e.test', 'Mariana Lima', 'encarregado')):
            u = User(name=nome, email=email, role=papel)
            u.set_password(SENHA)
            db.session.add(u)
            pessoas[email] = u
        db.session.flush()
        for email in ('ana@e2e.test', 'mariana@e2e.test'):
            pessoas[email].clients = [local]
        admin = pessoas['admin@e2e.test']
        setor = servico.salvar_setor(local, None, {'nome': 'Administrativo'}, admin)
        amb = servico.salvar_ambiente(local, None, {'nome': 'Banheiro masculino 2º andar',
                                                    'setor_id': setor.id}, admin)
        db.session.add(PontoInspecao(ambiente_id=amb.id, client_id=local.id,
                                     nome='Porta do banheiro', codigo_qr=QR_DO_TESTE))
        area = DiarioArea(client_id=local.id, nome='Limpeza', ativo=True, created_by=admin.id)
        db.session.add(area)
        db.session.flush()
        db.session.add(DiarioConfiguracao(
            client_id=local.id, area_id=area.id, nome='Limpeza — rotina',
            turnos_json=json.dumps([{'nome': '1º Turno'}, {'nome': '2º Turno'},
                                    {'nome': '3º Turno'}]),
            campos_json='[]',
            atividades_json=json.dumps([{'nome': 'Banheiros limpos', 'codigo': 'banheiros',
                                         'obrigatorio': False}]),
            tipos_ocorrencia_json='[]', ativo=True, created_by=admin.id))
        db.session.commit()
    return app


if __name__ == '__main__':
    porta, arquivo = int(sys.argv[1]), sys.argv[2]
    montar(arquivo).run(host='127.0.0.1', port=porta, use_reloader=False)
