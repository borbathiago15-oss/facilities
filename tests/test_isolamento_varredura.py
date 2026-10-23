"""Fase 2 — varredura de isolamento: TODAS as rotas, contra a carteira.

O local A recebe de tudo (estrutura com QR, modelo de passagem, passagem
com ocorrência e pendência, tarefa do turno, chamado, anexo). Pessoas do
local B — coordenador, supervisor e encarregado — chamam cada rota do
sistema com os ids de A: no caminho (``/chamados/<id>``), na consulta
(``?client_id=A``) e no corpo (JSON e formulário).

O que não pode acontecer, em rota nenhuma:

* a resposta mostrar um texto que só existe em A (``MARCA``);
* qualquer dado de A mudar (a "impressão digital" das tabelas de A).

Rota nova entra sozinha na varredura: a lista vem do ``url_map``. Rota com
um parâmetro de id que a varredura não conhece faz o teste falhar — para
quem a criou dizer aqui de onde vem o id.
"""
import hashlib
import io
import json
from datetime import timedelta

import pytest

from facilities import tempo
from tests import fabrica

MARCA = 'SEGREDO-DO-LOCAL-A'

# Rotas que não recebem dado de local nenhum (ou são do administrador, que
# já é testado em test_nucleo): fora da varredura, com o motivo.
FORA = {
    'static': 'arquivos estáticos',
    'auth.logout': 'derrubaria a sessão no meio da varredura',
    # Público por decisão (D47): qualquer pessoa no local abre ocorrência
    # pelo QR, logada ou não. Testado em test_qr_publico.py.
    'publico.abrir_ocorrencia': 'aberto ao público por desenho',
}
# Rotas fora da varredura só para UM perfil, com o motivo.
FORA_PARA = {
    # Para o cliente do portal, /q/<código> é a MESMA página pública que o
    # visitante sem login vê (bloco do técnico, etapa 2: "É aqui?" e os itens
    # do checklist do ponto como problemas a marcar). Para a equipe e a
    # gestão a rota continua na varredura (exige a carteira).
    ('cliente', 'cadastros.qr'): 'a página pública do QR, igual à de quem não tem login',
}


def _png():
    import struct
    import zlib

    def bloco(tipo, dados):
        c = tipo + dados
        return struct.pack('>I', len(dados)) + c + struct.pack('>I', zlib.crc32(c))
    return (b'\x89PNG\r\n\x1a\n' + bloco(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + bloco(b'IDAT', zlib.compress(b'\x00\x0a\x78\x1e')) + bloco(b'IEND', b''))


@pytest.fixture()
def local_a(app_module, auth_client):
    from app import db
    from facilities.passagem.models import (DiarioAnexo, DiarioArea, DiarioConfiguracao,
                                            DiarioOcorrencia, DiarioPendencia,
                                            DiarioTarefaTurno)
    from facilities.chamados.models import Chamado, ChamadoAnexo
    with app_module.app.app_context():
        ids = fabrica.estrutura(app_module)
        a = ids['local']
        from facilities.cadastros.models import Setor
        db.session.get(Setor, ids['setor']).nome = f'Setor {MARCA}'
        admin = app_module.User.query.filter_by(email='admin@grupotrino.com.br').one()
        area = DiarioArea(client_id=a, nome=f'Área {MARCA}', ativo=True, created_by=admin.id)
        db.session.add(area)
        db.session.flush()
        cfg = DiarioConfiguracao(
            client_id=a, area_id=area.id, nome=f'Modelo {MARCA}',
            turnos_json=json.dumps([{'nome': 'Diurno'}, {'nome': 'Noturno'}]), campos_json='[]',
            atividades_json=json.dumps([{'nome': f'Atividade {MARCA}', 'codigo': 'ativ',
                                         'obrigatorio': False}]),
            tipos_ocorrencia_json=json.dumps([{'nome': 'Avaria'}]),
            ativo=True, created_by=admin.id)
        db.session.add(cfg)
        db.session.commit()
        ids.update(area=area.id, cfg=cfg.id)
    r = auth_client.post('/passagem-de-turno/api/turnos', json={
        'client_id': a, 'configuracao_id': ids['cfg'], 'data_turno': tempo.hoje().isoformat(),
        'turno': 'Diurno', 'dados': {'atividade:ativ': {'concluido': True}},
        'ocorrencias': [{'tipo': 'Avaria', 'descricao': f'Ocorrência {MARCA}'}],
        'pendencias': [{'titulo': f'Pendência {MARCA}', 'prioridade': 'media'}],
        'finalizar': True})
    assert r.status_code == 201, r.get_data(as_text=True)
    ids['turno'] = r.get_json()['id']
    r = auth_client.post('/passagem-de-turno/api/tarefas-turno', json={
        'client_id': a, 'configuracao_id': ids['cfg'], 'data_turno': tempo.hoje().isoformat(),
        'turno': 'Noturno', 'titulo': f'Tarefa {MARCA}', 'forma_resposta': 'texto'})
    assert r.status_code == 201, r.get_data(as_text=True)
    r = auth_client.post(f"/passagem-de-turno/api/turnos/{ids['turno']}/anexos",
                         data={'arquivo': (io.BytesIO(_png()), 'a.png')},
                         content_type='multipart/form-data')
    r = auth_client.post('/chamados/', data={
        'client_id': a, 'titulo': f'Chamado {MARCA}', 'prioridade': 'media',
        'categoria': 'eletrica', 'arquivo': (io.BytesIO(_png()), 'c.png')},
        content_type='multipart/form-data')
    assert r.status_code == 302
    with app_module.app.app_context():
        ids['ocorrencia'] = DiarioOcorrencia.query.filter_by(client_id=a).first().id
        ids['pendencia'] = DiarioPendencia.query.filter_by(client_id=a).first().id
        ids['tarefa'] = DiarioTarefaTurno.query.filter_by(client_id=a).first().id
        ids['chamado'] = Chamado.query.filter_by(client_id=a).first().id
        an = DiarioAnexo.query.filter_by(turno_id=ids['turno']).first()
        ids['anexo_passagem'] = an.id if an else 999999
        ca = ChamadoAnexo.query.filter_by(chamado_id=ids['chamado']).first()
        ids['anexo_chamado'] = ca.id if ca else 999999
        ids.update(_rotas_de_a(app_module, a, ids))
    return ids


def _rotas_de_a(app_module, a, ids):
    """Fase 4A: checklist, rota, escala, tarefa, execução com foto e NC em A."""
    from app import User, db
    from facilities.rotas import servico as s
    from facilities.rotas.models import ExecucaoFoto, NaoConformidade, RotaEscala
    from tests.test_rotas_servico import Arquivo
    loc = fabrica.local()
    m = s.criar_modelo(a, {'nome': f'Checklist {MARCA}'}, None)
    s.publicar(m, s.normalizar_itens([{'texto': f'Pergunta {MARCA}', 'tipo': 'sim_nao',
                                       'problema_se': 'nao'}]), {}, None)
    rota = s.salvar_rota(loc, None, {'nome': f'Rota {MARCA}', 'turno': 'T1',
                                     'hora_inicio': '00:00', 'hora_fim': '23:59',
                                     'tolerancia_min': '240', 'dias_semana': '1234567'})
    item = s.salvar_item(rota, None, {'ponto_id': ids['ponto'], 'modelo_id': m.id,
                                      'horarios': tempo.agora().strftime('%H:%M')})
    dono = fabrica.pessoa(app_module, 'dono.a@trino.com', 'encarregado',
                          locais=['Shopping Centro'])
    s.salvar_escala(rota, {'user_id': dono, 'dias_semana': '1234567',
                           'data_inicio': tempo.hoje().isoformat()})
    s.garantir_hoje([a])
    db.session.commit()
    tarefa = s.tarefas_do_dia([a], tempo.hoje())[0]
    from facilities.cadastros.models import PontoInspecao
    ex, _ = s.registrar_execucao(db.session.get(User, dono), {
        'envio_id': 'varredura-a-0001', 'ponto': db.session.get(PontoInspecao, ids['ponto']).codigo_qr,
        'tarefa_id': tarefa.id, 'respostas': {s.normalizar_itens([{'texto': f'Pergunta {MARCA}'}])[0]['codigo']: 'nao'},
        'sem_sinal': True, 'lido_em': tarefa.previsto_para.isoformat()},
        {'depois': [Arquivo()]}, agora_utc=tarefa.previsto_para)
    # Uma segunda tarefa, ainda aberta, para a rota "não realizada".
    db.session.commit()
    # Fase 4B: uma ocorrência do público e um pedido de presença em A.
    from facilities.rotas import ocorrencias
    from facilities.rotas.models import ConfirmacaoPresenca
    from datetime import datetime, timedelta
    oc = ocorrencias.abrir(db.session.get(PontoInspecao, ids['ponto']), 'outro',
                           f'Aviso {MARCA}')
    pres = ConfirmacaoPresenca(rota_id=rota.id, client_id=a, user_id=dono, data=tempo.hoje(),
                               pedido_em=datetime.utcnow() - timedelta(minutes=1),
                               prazo_ate=datetime.utcnow() + timedelta(minutes=9))
    db.session.add(pres)
    db.session.commit()
    # Fase 5: um plano preventivo em A, com a ordem já aberta.
    from facilities.preventiva import servico as prev
    gestor = User.query.filter_by(email='admin@grupotrino.com.br').one()
    plano = prev.salvar_plano(loc, None, {
        'nome': f'Plano {MARCA}', 'ponto_id': ids['ponto'], 'modelo_id': m.id,
        'intervalo_dias': '30', 'proxima_em': tempo.hoje().isoformat()}, gestor)
    prev.gerar_ordens(tempo.hoje())
    db.session.commit()
    # Fase 6: equipe (funcionário, posto, escala, falta) e visita de supervisão em A.
    from facilities.equipes import servico as eq
    from facilities.visitas import servico as vis
    func = eq.salvar_funcionario(loc, None, {'nome': f'Funcionária {MARCA}'}, gestor)
    posto = eq.salvar_posto(loc, None, {'nome': f'Posto {MARCA}', 'hora_inicio': '07:00',
                                        'hora_fim': '15:00', 'rota_id': str(rota.id)})
    esc = eq.salvar_escala(loc, {'funcionario_id': func.id, 'posto_id': posto.id,
                                 'dias_semana': '1234567'}, gestor)
    falta = eq.registrar_presenca(gestor, esc, tempo.hoje(), 'faltou', f'Falta {MARCA}')
    prog = vis.salvar_programada(loc, None, {
        'nome': f'Visita {MARCA}', 'modelo_id': str(m.id), 'intervalo_dias': '7',
        'proxima_em': tempo.hoje().isoformat()}, gestor)
    vis.gerar_visitas(tempo.hoje())
    db.session.commit()
    from facilities.visitas.models import Visita, VisitaFoto
    # Fase 10: uma visita de A JÁ FEITA, com foto (a outra fica aberta).
    prog_feita = vis.salvar_programada(loc, None, {
        'nome': f'Visita feita {MARCA}', 'modelo_id': str(m.id), 'intervalo_dias': '7',
        'proxima_em': tempo.hoje().isoformat()}, gestor)
    vis.gerar_visitas(tempo.hoje())
    feita = Visita.query.filter_by(programada_id=prog_feita.id).one()
    vis.registrar(gestor, feita, {s.normalizar_itens([{'texto': f'Pergunta {MARCA}'}])[0]
                                  ['codigo']: 'sim'}, f'Obs {MARCA}',
                  fotos={'livre': [Arquivo()]})
    db.session.commit()
    foto_visita = VisitaFoto.query.filter_by(visita_id=feita.id).one().id
    # Fase 7: estoque, consumo e pedido de insumo em A (o catálogo é do grupo).
    from facilities.materiais import servico as mat
    material = mat.salvar_material(None, {'nome': 'Detergente da varredura', 'unidade': 'L',
                                          'preco_unitario': '10'})
    mat.movimentar(gestor, loc, {'material_id': str(material.id), 'quantidade': '5',
                                 'motivo': f'Entrada {MARCA}'}, 'entrada')
    mat.consumir(gestor, loc, {'material_id': str(material.id), 'quantidade': '1',
                               'motivo': f'Consumo {MARCA}'})
    pedido = mat.pedir(gestor, loc, {'texto': f'Pedido {MARCA}'})
    # Fase 8: uma chave da integração que lê só A.
    from facilities.integracao import servico as integ
    chave, _texto = integ.criar_chave(f'Chave {MARCA}', [a], False, gestor)
    db.session.commit()
    # Fase 9B: uma cobrança do cliente de A, já respondida.
    from facilities.portal import servico as portal
    cli_a = fabrica.cliente(app_module, 'cliente.a@gl.com', ids['cliente'])
    cob = portal.abrir(db.session.get(User, cli_a), {
        'client_id': str(a), 'titulo': f'Cobrança {MARCA}', 'texto': f'Pedido {MARCA}',
        'prazo': (tempo.hoje() + timedelta(days=3)).isoformat()})
    portal.responder(gestor, cob, {'texto': f'Resposta {MARCA}'})
    db.session.commit()
    # Relatório do cliente: o mês passado de A, liberado, com recado.
    from facilities.relatorios import cliente as relat
    mes_rel = relat.mes_de('')
    relat.salvar_recado(a, mes_rel, f'Recado {MARCA}', gestor)
    relat.liberar(a, mes_rel, gestor)
    db.session.commit()
    # POP/FIT: um documento do checklist de A, que o cliente de A pode ver.
    doc = s.anexar_documento(m, Arquivo(b'%PDF-1.4 ' + MARCA.encode(), 'pop.pdf'), gestor)
    doc.visivel_cliente = True
    db.session.commit()
    # Rotas prontas: um modelo da biblioteca (do grupo, sem dado de A).
    from facilities.rotas import rotas_prontas
    lib = s.criar_modelo(None, {'nome': 'Checklist da biblioteca (varredura)'}, None)
    s.publicar(lib, s.normalizar_itens([{'texto': 'Limpo?', 'tipo': 'sim_nao'}]), {}, None)
    pronta = rotas_prontas.salvar_modelo(None, {
        'nome': 'Rota pronta da varredura', 'turno': 'Diurno', 'hora_inicio': '06:00',
        'hora_fim': '18:00', 'dias_semana': '12345'}, [
        {'setor': 'Sanitários', 'ambiente': 'Banheiro', 'checklist_id': str(lib.id),
         'horarios': '08:00', 'quantidade': '1'}])
    db.session.commit()
    # Bloco do técnico: o ponto de A é a ENTRADA do local, com a chegada de hoje do dono.
    from facilities.rotas import chegadas
    p_a = db.session.get(PontoInspecao, ids['ponto'])
    p_a.entrada_do_local = True
    chegadas.registrar(db.session.get(User, dono), p_a)
    db.session.commit()
    # Novo contrato: um convite para A, criado pelo administrador.
    from facilities.cadastros import montagem
    convite, _token = montagem.criar_convite(gestor, {
        'nome': f'Convidada {MARCA}', 'email': 'convidada.a@trino.com', 'role': 'encarregado',
        'locais': [str(a)]})
    db.session.commit()
    # Ajustes de fluxo: um feriado do local A.
    from datetime import date
    from facilities.rotas import feriados
    feriado = feriados.cadastrar(loc, {'data': date(tempo.hoje().year, 7, 2).isoformat(),
                                       'nome': f'Feriado {MARCA}'}, gestor)
    db.session.commit()
    return {'feriado': feriado.id, 'convite': convite.id, 'dono': dono, 'rota_pronta': pronta.id, 'documento': doc.id, 'mes_relatorio': mes_rel.strftime('%Y-%m'), 'cobranca': cob.id, 'cliente_a': cli_a, 'foto_visita': foto_visita, 'material': material.id, 'pedido': pedido.id, 'chave': chave.id,'ocorrencia_publica': oc.id, 'presenca': pres.id, 'plano': plano.id,
            'funcionario': func.id, 'posto': posto.id, 'escala_trabalho': esc.id,
            'falta': falta.id, 'programada': prog.id,
            'visita': Visita.query.filter_by(programada_id=prog.id).one().id,
            'modelo': m.id, 'versao': m.versao_atual.id, 'rota': rota.id, 'item': item.id,
            'escala': RotaEscala.query.filter_by(rota_id=rota.id).one().id,
            'tarefa_rota': tarefa.id, 'execucao': ex.id,
            'foto': ExecucaoFoto.query.filter_by(execucao_id=ex.id).first().id,
            'nc': NaoConformidade.query.filter_by(execucao_id=ex.id).first().id}


def _digital(app_module, a):
    """As linhas de A em todas as tabelas com client_id (e as filhas por id)."""
    from app import db
    from sqlalchemy import inspect, text
    partes = []
    with app_module.app.app_context():
        insp = inspect(db.engine)
        for t in sorted(insp.get_table_names()):
            cols = [c['name'] for c in insp.get_columns(t)]
            if 'client_id' not in cols:
                continue
            linhas = db.session.execute(text(
                f'SELECT * FROM {t} WHERE client_id = :a'), {'a': a}).fetchall()
            partes.append((t, sorted(tuple(map(str, r)) for r in linhas)))
        for t, fk in (('chamado_eventos', 'chamado_id'), ('diario_operacional_pendencia_eventos',
                                                          'pendencia_id'),
                      ('cobranca_eventos', 'cobranca_id')):
            if t in insp.get_table_names():
                partes.append((t, db.session.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar()))
        # POP/FIT: não tem client_id (é filho do checklist); entra linha a linha.
        partes.append(('checklist_documentos', sorted(tuple(map(str, r)) for r in db.session.execute(
            text('SELECT * FROM checklist_documentos')).fetchall())))
    return hashlib.sha256(repr(partes).encode()).hexdigest()


def _valor_do_parametro(nome, ids, entidade=None, endpoint=''):
    if endpoint.startswith('publico.') and nome == 'oid':
        return ids['ocorrencia_publica']
    if endpoint.startswith('preventiva.') and nome == 'pid':
        return ids['plano']
    if endpoint.startswith('equipes.'):
        por_equipe = {'cid': ids['local'], 'fid': ids['funcionario'], 'pid': ids['posto'],
                      'eid': ids['escala_trabalho'], 'prid': ids['falta']}
        if nome in por_equipe:
            return por_equipe[nome]
    if endpoint.startswith('integracao.') and nome == 'kid':
        return ids['chave']
    if endpoint.startswith('materiais.'):
        por_material = {'cid': ids['local'], 'mid': ids['material'], 'pid': ids['pedido']}
        if nome in por_material:
            return por_material[nome]
    if endpoint.startswith('visitas.'):
        por_visita = {'cid': ids['local'], 'pid': ids['programada'], 'vid': ids['visita'],
                      'vfid': ids['foto_visita']}
        if nome in por_visita:
            return por_visita[nome]
    if endpoint == 'rotas.remover_feriado' and nome == 'fid':
        return ids['feriado']
    if endpoint.startswith('rotas.'):
        por_rota = {'eid': ids['escala'] if 'escala' in endpoint else ids['execucao'],
                    'rid': ids['rota'], 'iid': ids['item'], 'mid': ids['modelo'],
                    'nid': ids['nc'], 'fid': ids['foto'], 'tid': ids['tarefa_rota'],
                    'cid': ids['local'], 'vid': ids['versao'], 'did': ids['documento'],
                    'rmid': ids['rota_pronta'], 'acao': 'retirar'}
        if nome in por_rota:
            return por_rota[nome]
    if endpoint.startswith('relatorios.'):
        por_relatorio = {'cid': ids['local'], 'mes': ids['mes_relatorio'], 'acao': 'recolher',
                         'formato': 'pdf'}
        if nome in por_relatorio:
            return por_relatorio[nome]
    if endpoint.startswith(('portal.', 'cobrancas.')):
        por_portal = {'cid': ids['local'], 'chamado_id': ids['chamado'], 'fid': ids['foto'],
                      'cobid': ids['cobranca'], 'acao': 'confirmar',
                      'vfid': ids['foto_visita'], 'mes': ids['mes_relatorio'],
                      'formato': 'pdf', 'did': ids['documento']}
        if nome in por_portal:
            return por_portal[nome]
    mapa = {
        'cid': ids['local'], 'client_id': ids['local'], 'chamado_id': ids['chamado'],
        'turno_id': ids['turno'], 'pending_id': ids['pendencia'], 'tarefa_id': ids['tarefa'],
        'ocorrencia_id': ids['ocorrencia'], 'config_id': ids['cfg'], 'area_id': ids['area'],
        'codigo': ids['qr'], 'aviso_id': 1, 'uid': 1, 'eid': ids['empresa'],
        'entidade': entidade or 'setor',
        'oid_ocorrencia': ids['ocorrencia_publica'], 'pid': ids['presenca'],
        'token': 'token-inventado', 'acao': 'resolver',
        'ctid': ids['cliente'], 'conv_id': ids['convite'],
        'oid': ids.get(entidade or 'setor'),
    }
    return mapa.get(nome)


def _urls(app_module, ids):
    for regra in app_module.app.url_map.iter_rules():
        if regra.endpoint in FORA:
            continue
        metodos = sorted(regra.methods - {'HEAD', 'OPTIONS'})
        entidades = ['setor', 'ambiente', 'equipamento', 'ponto'] \
            if 'entidade' in regra.arguments else [None]
        for ent in entidades:
            valores = {}
            for arg in regra.arguments:
                if arg == 'anexo_id':
                    v = ids['anexo_chamado'] \
                        if regra.endpoint.startswith(('chamados.', 'portal.')) \
                        else ids['anexo_passagem']
                else:
                    v = _valor_do_parametro(arg, ids, ent, regra.endpoint)
                assert v is not None, (f'A varredura não sabe de onde vem <{arg}> de '
                                       f'{regra.rule}: ensine em _valor_do_parametro.')
                valores[arg] = v
            caminho = regra.rule
            for arg, v in valores.items():
                caminho = caminho.replace(f'<int:{arg}>', str(v)).replace(f'<{arg}>', str(v))
            for m in metodos:
                yield regra.endpoint, m, caminho


@pytest.mark.parametrize('papel', ['pleno', 'supervisor', 'encarregado', 'tecnico'])
def test_ninguem_de_b_le_ou_altera_a(app_module, local_a, papel):
    with app_module.app.app_context():
        email = f'varredura.{papel}@trino.com'
        fabrica.pessoa(app_module, email, papel, locais=['Hospital Norte'])
    _varrer(app_module, local_a, fabrica.entrar(app_module, email), papel)


def test_cliente_de_b_nao_le_nem_altera_a(app_module, local_a):
    """Fase 9B: o cliente de outro contratante, com o portal LIGADO e a
    segunda etapa feita, passa por todas as rotas — as do portal e as da
    equipe — com os ids de A."""
    from app import db
    from facilities.cadastros import servico as cad
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    with app_module.app.app_context():
        emp = cad.salvar_empresa(None, {'nome': 'Outra empresa'}, None)
        hn = cad.salvar_contratante(None, {'nome': 'Grupo HN', 'empresa_id': emp.id}, None)
        db.session.flush()
        fabrica.local('Hospital Norte').contratante_id = hn.id
        db.session.commit()
        fabrica.cliente(app_module, 'cliente.b@hn.com', hn.id)
    c = fabrica.entrar_com_codigo(app_module, 'cliente.b@hn.com')
    assert c.get('/cliente/').status_code == 200
    _varrer(app_module, local_a, c, 'cliente')


def _varrer(app_module, local_a, c, papel):
    a = local_a['local']
    antes = _digital(app_module, a)
    corpo = {'client_id': a, 'configuracao_id': local_a['cfg'], 'titulo': 'Invasão',
             'nome': 'Invasão', 'texto': 'Invasão', 'resposta': 'x',
             'acao': 'cancelar', 'setor_id': local_a['setor'],
             'ambiente_id': local_a['ambiente'], 'data_turno': tempo.hoje().isoformat(),
             'turno': 'Diurno', 'ativo': '0',
             # Fase 4A: o QR e a tarefa de A, no JSON e no "corpo" do aplicativo.
             'ponto': local_a['qr'], 'tarefa_id': local_a['tarefa_rota'],
             'motivo': 'acesso', 'versao_id': '1',
             # Fase 6: a escala e a falta de A, e quem "cobriria".
             'escala_id': local_a['escala_trabalho'], 'situacao': 'veio',
             'funcionario_id': local_a['funcionario'], 'posto_id': local_a['posto'],
             'r_pergunta': 'sim',
             # Fase 7: material de A, no estoque e no pedido.
             'material_id': local_a['material'], 'quantidade': '1', 'tipo': 'saida',
             'autorizar_negativo': '1',
             # Fase 9B: a cobrança (prazo) e o comentário de quem confirma.
             'prazo': (tempo.hoje() + timedelta(days=3)).isoformat(),
             # Bloco do técnico: o QR de A na chegada, o local de A no turno, a
             # pessoa de A na liberação da chegada e os itens do QR público.
             'local': local_a['local'], 'user_id': local_a['dono'], 'itens': ['pergunta'],
             'motivos': {'pergunta': {'motivo': 'faltou_material',
                                      'material_id': local_a['material']}},
             'corpo': json.dumps({'envio_id': f'invasao-{papel}-0001', 'ponto': local_a['qr'],
                                  'tarefa_id': local_a['tarefa_rota'], 'respostas': {},
                                  'sem_sinal': True,
                                  'lido_em': '2026-10-17T12:00:00'})}
    vazou = []
    for endpoint, metodo, caminho in _urls(app_module, local_a):
        if (papel, endpoint) in FORA_PARA:
            continue
        url = caminho + (('&' if '?' in caminho else '?') + f'client_id={a}')
        if metodo == 'GET':
            respostas = [c.get(url)]
        else:
            chamar = getattr(c, metodo.lower())
            respostas = [chamar(url, json=corpo), chamar(url, data=corpo)]
        for r in respostas:
            texto = r.get_data(as_text=True) if r.mimetype.startswith(('text', 'application/json')) \
                else ''
            if MARCA in texto:
                vazou.append(f'{metodo} {caminho} → {r.status_code}')
    assert not vazou, f'{papel} de B leu dado de A em: ' + '; '.join(vazou)
    assert _digital(app_module, a) == antes, f'{papel} de B alterou dado de A'


def test_a_marca_aparece_para_quem_e_de_a(app_module, local_a):
    """Contraprova: a varredura enxergaria o vazamento (a marca aparece)."""
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'varredura.dono@trino.com', 'pleno',
                       locais=['Shopping Centro'])
    c = fabrica.entrar(app_module, 'varredura.dono@trino.com')
    assert MARCA in c.get(f"/chamados/{local_a['chamado']}").get_data(as_text=True)
    assert MARCA in c.get(f"/cadastros/locais/{local_a['local']}").get_data(as_text=True)


def test_a_marca_aparece_para_o_cliente_de_a(app_module, local_a):
    """Contraprova da 9B: o cliente de A enxerga a cobrança e o chamado de A."""
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    c = fabrica.entrar_com_codigo(app_module, 'cliente.a@gl.com')
    assert MARCA in c.get(f"/cliente/cobrancas/{local_a['cobranca']}").get_data(as_text=True)
    assert MARCA in c.get(f"/cliente/chamados/{local_a['chamado']}").get_data(as_text=True)


def test_relatorio_liberado_de_a_aparece_para_o_cliente_de_a(app_module, local_a):
    app_module.app.config['CLIENTE_EXTERNO_LIBERADO'] = True
    c = fabrica.entrar_com_codigo(app_module, 'cliente.a@gl.com')
    url = f"/cliente/relatorios/{local_a['local']}/{local_a['mes_relatorio']}"
    assert MARCA in c.get(url).get_data(as_text=True)
    assert c.get(url + '/arquivo.pdf').mimetype == 'application/pdf'

