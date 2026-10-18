"""Servidor descartável para os testes de navegador (SQLite temporário).

    python e2e/servidor.py <porta> <arquivo.db>

Semeia um local com estrutura, um ponto com QR conhecido (``QR_DO_TESTE``),
um modelo de passagem simples e as pessoas: o administrador, a Ana e a
Mariana (encarregadas do mesmo local, para o teste do celular compartilhado),
o Caio, a Sueli e, desde a Fase 9B, o cliente do local (portal ligado).
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
                      STORAGE_BACKEND='local', UPLOAD_FOLDER=tempfile.mkdtemp(),
                      CLIENTE_EXTERNO_LIBERADO='1')
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
                                   ('mariana@e2e.test', 'Mariana Lima', 'encarregado'),
                                   ('caio@e2e.test', 'Caio Técnico', 'tecnico'),
                                   ('sueli@e2e.test', 'Sueli Supervisora', 'supervisor')):
            u = User(name=nome, email=email, role=papel)
            u.set_password(SENHA)
            db.session.add(u)
            pessoas[email] = u
        db.session.flush()
        for email in ('ana@e2e.test', 'mariana@e2e.test', 'caio@e2e.test', 'sueli@e2e.test'):
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
        # Fase 4A: a rota da Ana — o banheiro AGORA (para o teste não depender
        # da hora em que roda), com uma pergunta e foto de depois.
        from facilities import tempo
        from facilities.rotas import servico as rotas
        m = rotas.criar_modelo(local.id, {'nome': 'Limpeza de banheiro',
                                          'descricao': 'Repor papel, limpar e secar o piso.'},
                               admin)
        rotas.publicar(m, rotas.normalizar_itens([
            {'texto': 'Papel higiênico reposto?', 'tipo': 'sim_nao', 'obrigatorio': True,
             'problema_se': 'nao', 'como_fazer': 'Deixe 2 rolos em cada cabine.'}]),
            {'exige_foto_depois': '1'}, admin)
        # O POP completo do banheiro, guardado no checklist.
        import io

        class _Pop(io.BytesIO):
            filename = 'POP Banheiro.pdf'
        rotas.anexar_documento(m, _Pop(b'%PDF-1.4 POP do banheiro'), admin)
        rota = rotas.salvar_rota(local, None, {
            'nome': 'Limpeza 2º andar', 'turno': '1º Turno', 'hora_inicio': '00:00',
            'hora_fim': '23:59', 'tolerancia_min': '240', 'dias_semana': '1234567'})
        ponto = PontoInspecao.query.filter_by(codigo_qr=QR_DO_TESTE).one()
        rotas.salvar_item(rota, None, {'ponto_id': ponto.id, 'modelo_id': m.id,
                                       'horarios': tempo.agora().strftime('%H:%M')})
        rotas.salvar_escala(rota, {'user_id': pessoas['ana@e2e.test'].id,
                                   'dias_semana': '1234567',
                                   'data_inicio': tempo.hoje().isoformat()})
        # Fase 5: a preventiva do Caio no mesmo ponto, com a ordem já aberta.
        from facilities.preventiva import servico as preventiva
        filtro = rotas.criar_modelo(local.id, {'nome': 'Limpeza do filtro'}, admin)
        rotas.publicar(filtro, rotas.normalizar_itens([
            {'texto': 'Filtro lavado?', 'tipo': 'sim_nao', 'obrigatorio': True}]), {}, admin)
        preventiva.salvar_plano(local, None, {
            'nome': 'Filtro do secador', 'ponto_id': ponto.id, 'modelo_id': filtro.id,
            'intervalo_dias': '30', 'proxima_em': tempo.hoje().isoformat(),
            'responsavel_id': pessoas['caio@e2e.test'].id}, admin)
        db.session.flush()
        preventiva.gerar_ordens(tempo.hoje())
        # Fase 6: a equipe do posto (Ana com login, Mariana sem) e a visita de
        # supervisão de hoje da Sueli.
        from facilities.equipes import servico as equipes
        from facilities.visitas import servico as visitas
        ana = equipes.salvar_funcionario(local, None, {
            'nome': 'Ana Souza', 'funcao': 'ASG', 'user_id': pessoas['ana@e2e.test'].id}, admin)
        equipes.salvar_funcionario(local, None, {'nome': 'Mariana Lima', 'funcao': 'ASG'}, admin)
        posto = equipes.salvar_posto(local, None, {'nome': 'Limpeza 2º andar — manhã',
                                                   'hora_inicio': '00:00', 'hora_fim': '23:59',
                                                   'rota_id': rota.id})
        equipes.salvar_escala(local, {'funcionario_id': ana.id, 'posto_id': posto.id,
                                      'dias_semana': '1234567'}, admin)
        qualidade = rotas.criar_modelo(local.id, {'nome': 'Visita de qualidade'}, admin)
        rotas.publicar(qualidade, rotas.normalizar_itens([
            {'texto': 'Uniforme completo?', 'tipo': 'sim_nao', 'obrigatorio': True,
             'problema_se': 'nao'}]), {}, admin)
        visitas.salvar_programada(local, None, {
            'nome': 'Visita semanal', 'modelo_id': qualidade.id, 'intervalo_dias': '7',
            'proxima_em': tempo.hoje().isoformat(),
            'supervisor_id': pessoas['sueli@e2e.test'].id}, admin)
        db.session.flush()
        visitas.gerar_visitas(tempo.hoje())
        # Fase 7: detergente no estoque do local.
        from facilities.materiais import servico as materiais
        det = materiais.salvar_material(None, {'nome': 'Detergente neutro', 'unidade': 'L',
                                               'preco_unitario': '12,90'})
        materiais.movimentar(admin, local, {'material_id': det.id, 'quantidade': '10'},
                             'entrada')
        # Fase 9B: o cliente do local (Grupo GL), ainda sem a segunda etapa.
        emp = servico.salvar_empresa(None, {'nome': 'Trino Serviços'}, admin)
        gl = servico.salvar_contratante(None, {'nome': 'Grupo GL', 'empresa_id': emp.id}, admin)
        servico.vincular_local(local, {'contratante_id': gl.id,
                                       'estado_id': Estado.query.filter_by(sigla='BA').one().id},
                               admin)
        cli = User(name='Cláudia do Cliente', email='cliente@e2e.test', role='cliente',
                   cliente_id=gl.id)
        cli.set_password(SENHA)
        db.session.add(cli)
        db.session.commit()
    return app


if __name__ == '__main__':
    porta, arquivo = int(sys.argv[1]), sys.argv[2]
    montar(arquivo).run(host='127.0.0.1', port=porta, use_reloader=False)
