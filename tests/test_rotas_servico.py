"""Fase 4A — as regras das rotas, direto no serviço.

O dia da Ana: rota "Limpeza 2º andar — turno 1" (07:00–15:00, tolerância
15 min), banheiro às 09:00 e 11:00, a Ana escalada de segunda a sexta.
"""
import io
import json
from datetime import date, time, timedelta

import pytest

from facilities import tempo
from tests import fabrica

SEGUNDA = date(2026, 10, 19)           # uma segunda-feira


def _png():
    import struct
    import zlib

    def bloco(tipo, dados):
        c = tipo + dados
        return struct.pack('>I', len(dados)) + c + struct.pack('>I', zlib.crc32(c))
    return (b'\x89PNG\r\n\x1a\n' + bloco(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
            + bloco(b'IDAT', zlib.compress(b'\x00\x0a\x78\x1e')) + bloco(b'IEND', b''))


class Arquivo(io.BytesIO):
    def __init__(self, dados=None, nome='foto.png'):
        super().__init__(dados if dados is not None else _png())
        self.filename = nome


def utc(dia, hhmm):
    h, m = map(int, hhmm.split(':'))
    return tempo.para_utc(dia, time(h, m))


@pytest.fixture()
def cena(app_module):
    """O cenário, com o contexto da aplicação ABERTO durante o teste (testes
    de serviço). Para testes por HTTP com mais de um login, use
    ``montar_cena`` num contexto próprio (o ``g`` de um contexto aberto
    guarda o login do primeiro cliente)."""
    with app_module.app.app_context():
        yield montar_cena(app_module)


def montar_cena(app_module):
    from app import db
    from facilities.rotas import servico as s
    if True:
        ids = fabrica.estrutura(app_module)
        loc = fabrica.local()
        ana = fabrica.pessoa(app_module, 'ana.rota@trino.com', 'encarregado',
                             locais=['Shopping Centro'], nome='Ana')
        mariana = fabrica.pessoa(app_module, 'mariana.rota@trino.com', 'encarregado',
                                 locais=['Shopping Centro'], nome='Mariana')
        m = s.criar_modelo(loc.id, {'nome': 'Limpeza de banheiro'}, None)
        itens = s.normalizar_itens([
            {'texto': 'Papel higiênico reposto?', 'tipo': 'sim_nao', 'obrigatorio': True,
             'problema_se': 'nao'},
            {'texto': 'Mictórios', 'tipo': 'conforme', 'obrigatorio': True},
            {'texto': 'Vazamento?', 'tipo': 'sim_nao'},
            {'texto': 'Onde vaza', 'tipo': 'texto', 'obrigatorio': True,
             'mostrar_se': 'vazamento=sim'},
            {'texto': 'Cloro (ppm)', 'tipo': 'numero', 'minimo': '1', 'maximo': '3'},
        ])
        v, _ = s.publicar(m, itens, {'exige_foto_depois': '1'}, None)
        rota = s.salvar_rota(loc, None, {'nome': 'Limpeza 2º andar — turno 1',
                                         'turno': '1º Turno', 'hora_inicio': '07:00',
                                         'hora_fim': '15:00', 'tolerancia_min': '15',
                                         'dias_semana': '12345'})
        item = s.salvar_item(rota, None, {'ponto_id': ids['ponto'], 'modelo_id': m.id,
                                          'horarios': '11:00, 09:00'})
        s.salvar_escala(rota, {'user_id': ana, 'dias_semana': '12345',
                               'data_inicio': '2026-10-01'})
        db.session.commit()
        ids.update(modelo=m.id, versao=v.id, rota=rota.id, item=item.id, ana=ana,
                   mariana=mariana)
        return ids


def _s():
    from facilities.rotas import servico
    return servico


def _tarefas(dia=SEGUNDA):
    from facilities.rotas.models import TarefaDia
    return TarefaDia.query.filter_by(data=dia).order_by(TarefaDia.previsto_para).all()


def _respostas(**extra):
    r = {'papel_higienico_reposto': 'sim', 'mictorios': 'conforme', 'vazamento': 'nao'}
    r.update(extra)
    return r


def _executar(user_id, tarefa, lido, concluida=None, envio=None, respostas=None, fotos=None,
              ponto=None, agora=None):
    from app import User, db
    s = _s()
    u = db.session.get(User, user_id)
    dados = {'envio_id': envio or f'envio-{tarefa.id}-{lido.isoformat()}',
             'ponto': ponto or tarefa.ponto.codigo_qr, 'tarefa_id': tarefa.id,
             'respostas': respostas or _respostas(), 'sem_sinal': True,
             'lido_em': lido.isoformat(), 'concluida_em': (concluida or lido).isoformat()}
    fotos = fotos if fotos is not None else {'depois': [Arquivo()]}
    return s.registrar_execucao(u, dados, fotos, agora_utc=agora or (concluida or lido)
                                + timedelta(minutes=1))


# ── Agendador ─────────────────────────────────────────────────────────────

def test_agendador_gera_um_por_horario_e_nao_duplica(app_module, cena):
    from app import db
    with app_module.app.app_context():
        s = _s()
        assert s.gerar(SEGUNDA) == 2
        assert s.gerar(SEGUNDA) == 0
        db.session.commit()
        ts = _tarefas()
        assert [tempo.fmt(t.previsto_para, '%H:%M') for t in ts] == ['09:00', '11:00']
        assert all(t.user_id == cena['ana'] for t in ts)
        assert tempo.fmt(ts[0].fim_do_turno, '%d/%m %H:%M') == '19/10 15:00'


def test_sem_rota_no_fim_de_semana_e_sem_escala_fica_sem_dono(app_module, cena):
    from app import db
    from facilities.rotas.models import RotaEscala
    with app_module.app.app_context():
        s = _s()
        assert s.gerar(SEGUNDA + timedelta(days=5)) == 0          # sábado
        RotaEscala.query.update({'is_active': False})
        db.session.commit()
        s.gerar(SEGUNDA)
        assert {t.user_id for t in _tarefas()} == {None}


def test_frequencia_e_turno_que_vira_o_dia(app_module, cena):
    from app import db
    from facilities.rotas.models import Rota, RotaItem
    with app_module.app.app_context():
        s = _s()
        rota = db.session.get(Rota, cena['rota'])
        s.salvar_rota(rota.local, rota, {'nome': rota.nome, 'turno': 'Noturno',
                                         'hora_inicio': '22:00', 'hora_fim': '02:00',
                                         'tolerancia_min': '10', 'dias_semana': '1234567'})
        item = db.session.get(RotaItem, cena['item'])
        s.salvar_item(rota, item, {'ponto_id': item.ponto_id, 'modelo_id': item.modelo_id,
                                   'horarios': '23:30, 01:00', 'frequencia_min': '60'})
        db.session.commit()
        horas = [m.strftime('%d %H:%M') for m in s.horarios_do_item(rota, item, SEGUNDA)]
        assert horas == ['19 22:00', '19 23:00', '19 23:30', '20 00:00', '20 01:00']
        with pytest.raises(s.RegraDaRota, match='fora do turno'):
            s.salvar_item(rota, item, {'ponto_id': item.ponto_id, 'modelo_id': item.modelo_id,
                                       'horarios': '12:00'})


def test_turno_encerrado_sem_registro_vira_perdida(app_module, cena):
    from app import db
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        assert s.fechar_perdidas(utc(SEGUNDA, '14:00')) == 0
        assert s.fechar_perdidas(utc(SEGUNDA, '15:01')) == 2
        db.session.commit()
        assert {t.status for t in _tarefas()} == {'perdida'}


def test_rodada_fica_registrada(app_module, cena):
    from app import db
    from facilities.rotas.models import AgendadorExecucao
    with app_module.app.app_context():
        reg = _s().rodar(agora_utc=utc(SEGUNDA, '06:00'))
        db.session.commit()
        assert reg.ok and reg.tarefas_geradas == 4          # segunda e terça
        assert AgendadorExecucao.query.count() == 1


def test_situacao_e_aderencia(app_module, cena):
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        t9, t11 = _tarefas()
        assert s.situacao(t9, utc(SEGUNDA, '08:40')) == 'prevista'
        assert s.situacao(t9, utc(SEGUNDA, '09:14')) == 'no_horario'
        assert s.situacao(t9, utc(SEGUNDA, '09:16')) == 'atrasada'
        _executar(cena['ana'], t9, utc(SEGUNDA, '09:04'), utc(SEGUNDA, '09:17'))
        assert s.aderencia([t9, t11], utc(SEGUNDA, '10:00')) == (1, 1, 100.0)
        assert s.aderencia([t9, t11], utc(SEGUNDA, '11:20')) == (1, 2, 50.0)


# ── Checklist ─────────────────────────────────────────────────────────────

def test_versao_publicada_nao_muda_e_so_republica_se_mudou(app_module, cena):
    from app import db
    from facilities.rotas.models import ChecklistModelo
    with app_module.app.app_context():
        s = _s()
        m = db.session.get(ChecklistModelo, cena['modelo'])
        itens = s.itens_da_versao(m.versao_atual)
        v, publicou = s.publicar(m, itens, {'exige_foto_depois': '1'}, None)
        assert not publicou and v.numero == 1
        s.gerar(SEGUNDA)
        itens2 = itens + [{'texto': 'Lixeira vazia?', 'tipo': 'sim_nao', 'codigo': ''}]
        v2, publicou = s.publicar(m, s.normalizar_itens(itens2), {'exige_foto_depois': '1'}, None)
        db.session.commit()
        assert publicou and v2.numero == 2
        # A tarefa gerada antes continua com a versão 1.
        assert {t.versao.numero for t in _tarefas()} == {1}


def test_itens_invalidos_sao_recusados(app_module):
    with app_module.app.app_context():
        s = _s()
        with pytest.raises(s.RegraDaRota, match='pelo menos uma'):
            s.normalizar_itens([{'texto': ''}])
        with pytest.raises(s.RegraDaRota, match='duas opções'):
            s.normalizar_itens([{'texto': 'Estado', 'tipo': 'escolha', 'opcoes': 'Bom'}])
        with pytest.raises(s.RegraDaRota, match='mínimo é maior'):
            s.normalizar_itens([{'texto': 'T', 'tipo': 'numero', 'minimo': '5', 'maximo': '1'}])
        with pytest.raises(s.RegraDaRota, match='pergunta anterior'):
            s.normalizar_itens([{'texto': 'A', 'mostrar_se': 'nao_existe=sim'}])


def test_biblioteca_e_copiada_para_o_local(app_module, cena):
    from app import db
    with app_module.app.app_context():
        s = _s()
        lib = s.criar_modelo(None, {'nome': 'Copa — padrão Trino'}, None)
        s.publicar(lib, s.normalizar_itens([{'texto': 'Pia limpa?', 'tipo': 'sim_nao'}]), {}, None)
        copia = s.copiar_da_biblioteca(lib, fabrica.local().id, None)
        db.session.commit()
        assert copia.client_id == fabrica.local().id and copia.origem_id == lib.id
        assert s.itens_da_versao(copia.versao_atual)[0]['texto'] == 'Pia limpa?'
        with pytest.raises(s.RegraDaRota, match='já tem uma cópia'):
            s.copiar_da_biblioteca(lib, fabrica.local().id, None)
        # Mudar a cópia não mexe na biblioteca.
        s.publicar(copia, s.normalizar_itens([{'texto': 'Pia e bancada limpas?'}]), {}, None)
        assert s.itens_da_versao(lib.versao_atual)[0]['texto'] == 'Pia limpa?'


def test_rota_so_usa_checklist_e_ponto_do_proprio_local(app_module, cena):
    from app import db
    from facilities.rotas.models import Rota
    with app_module.app.app_context():
        s = _s()
        rota = db.session.get(Rota, cena['rota'])
        lib = s.criar_modelo(None, {'nome': 'Da biblioteca'}, None)
        s.publicar(lib, s.normalizar_itens([{'texto': 'X'}]), {}, None)
        with pytest.raises(s.RegraDaRota, match='checklist deste local'):
            s.salvar_item(rota, None, {'ponto_id': cena['ponto'], 'modelo_id': lib.id,
                                       'horarios': '09:00'})
        outro = fabrica.local('Hospital Norte')
        from facilities.cadastros import servico as cad
        st = cad.salvar_setor(outro, None, {'nome': 'S'}, None)
        am = cad.salvar_ambiente(outro, None, {'nome': 'A', 'setor_id': st.id}, None)
        pt = cad.salvar_ponto(outro, None, {'nome': 'P', 'ambiente_id': am.id}, None)
        with pytest.raises(s.RegraDaRota, match='ponto ativo deste local'):
            s.salvar_item(rota, None, {'ponto_id': pt.id, 'modelo_id': cena['modelo'],
                                       'horarios': '09:00'})


# ── Execução ──────────────────────────────────────────────────────────────

def test_ana_executa_no_prazo_e_a_tarefa_fecha(app_module, cena):
    from app import db
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        t9 = _tarefas()[0]
        ex, nova = _executar(cena['ana'], t9, utc(SEGUNDA, '09:04'), utc(SEGUNDA, '09:17'))
        db.session.commit()
        assert nova and ex.sem_sinal and t9.status == 'concluida_no_prazo'
        assert ex.pessoa.name == 'Ana' and len(ex.fotos) == 1
        assert tempo.fmt(ex.lido_em, '%H:%M') == '09:04'
        assert tempo.fmt(ex.concluida_em, '%H:%M') == '09:17'


def test_depois_da_tolerancia_e_com_atraso(app_module, cena):
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        t9 = _tarefas()[0]
        _executar(cena['ana'], t9, utc(SEGUNDA, '09:20'))
        assert t9.status == 'concluida_com_atraso'


def test_cedo_demais_e_recusado(app_module, cena):
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        with pytest.raises(s.RegraDaRota, match='a partir das 08:45'):
            _executar(cena['ana'], _tarefas()[0], utc(SEGUNDA, '08:30'))


def test_qr_de_outro_ponto_e_recusado(app_module, cena):
    from facilities.cadastros import servico as cad
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        outro = cad.salvar_ponto(fabrica.local(), None, {'nome': 'Copa',
                                                         'ambiente_id': cena['ambiente']}, None)
        with pytest.raises(s.RegraDaRota, match='outro ponto'):
            _executar(cena['ana'], _tarefas()[0], utc(SEGUNDA, '09:00'),
                      ponto=outro.codigo_qr)


def test_obrigatorios_condicionais_e_fotos(app_module, cena):
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        t9 = _tarefas()[0]
        with pytest.raises(s.RegraDaRota, match='Papel'):
            _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'), respostas={'mictorios': 'conforme'})
        # "Onde vaza" só é obrigatório se houve vazamento.
        with pytest.raises(s.RegraDaRota, match='Onde vaza'):
            _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'),
                      respostas=_respostas(vazamento='sim'))
        with pytest.raises(s.RegraDaRota, match='DEPOIS'):
            _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'), fotos={})
        with pytest.raises(s.RegraDaRota, match='não é imagem'):
            _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'),
                      fotos={'depois': [Arquivo(b'MZ executavel', 'virus.png')]})


def test_nao_conformidade_e_registrada_e_vira_chamado(app_module, cena):
    from app import User, db
    from facilities.chamados.models import Chamado
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        ex, _ = _executar(cena['ana'], _tarefas()[0], utc(SEGUNDA, '09:00'),
                          respostas=_respostas(papel_higienico_reposto='nao', cloro_ppm='5'))
        db.session.commit()
        assert ex.n_nao_conformes == 2
        nc = ex.nao_conformidades[0]
        cid = s.abrir_chamado_da_nc(nc, db.session.get(User, cena['ana']))
        db.session.commit()
        ch = db.session.get(Chamado, cid)
        # O chamado já nasceu na execução (um por execução, com os 2 itens).
        assert ch.origem == 'execucao' and ch.origem_id == ex.id
        assert 'Porta do banheiro' in ch.titulo and '2 item(ns)' in ch.titulo
        assert s.abrir_chamado_da_nc(nc, db.session.get(User, cena['ana'])) == cid


def test_o_mesmo_envio_nao_duplica(app_module, cena):
    from app import db
    from facilities.rotas.models import Execucao
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        t9 = _tarefas()[0]
        ex1, nova1 = _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'), envio='mesmo-envio-123')
        db.session.commit()
        ex2, nova2 = _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'), envio='mesmo-envio-123')
        assert nova1 and not nova2 and ex1.id == ex2.id
        assert Execucao.query.count() == 1


def test_tarefa_feita_nao_e_feita_de_novo_por_outra_pessoa(app_module, cena):
    from app import db
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        t9 = _tarefas()[0]
        _executar(cena['ana'], t9, utc(SEGUNDA, '09:00'))
        db.session.commit()
        # O trabalho foi feito: não se perde — vira atividade extra, dizendo
        # por quê; a tarefa continua com a execução da Ana.
        ex, nova = _executar(cena['mariana'], t9, utc(SEGUNDA, '09:05'))
        db.session.commit()
        assert nova and ex.extra and ex.tarefa_id is None
        assert 'já tinha sido registrada por Ana' in ex.observacao
        assert len(t9.execucoes) == 1


def test_mariana_cobre_a_ana(app_module, cena):
    """A tarefa é da escala da Ana, mas quem está no posto pode cobrir: fica
    registrado quem fez."""
    from app import db
    with app_module.app.app_context():
        _s().gerar(SEGUNDA)
        t9 = _tarefas()[0]
        ex, _ = _executar(cena['mariana'], t9, utc(SEGUNDA, '09:00'))
        db.session.commit()
        assert t9.user_id == cena['ana'] and ex.pessoa.name == 'Mariana'


def test_relogio_do_celular_errado_e_recusado(app_module, cena):
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        with pytest.raises(s.RegraDaRota, match='horário do celular'):
            _executar(cena['ana'], _tarefas()[0], utc(SEGUNDA, '09:00'),
                      agora=utc(SEGUNDA, '08:00'))


def test_sem_sinal_chega_depois_e_entra_mesmo_com_a_tarefa_perdida(app_module, cena):
    from app import db
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        s.fechar_perdidas(utc(SEGUNDA, '16:00'))
        t9 = _tarefas()[0]
        assert t9.status == 'perdida'
        ex, _ = _executar(cena['ana'], t9, utc(SEGUNDA, '09:05'), agora=utc(SEGUNDA, '18:00'))
        db.session.commit()
        assert t9.status == 'concluida_no_prazo' and ex.sem_sinal


def test_selo_do_servidor_vale_mais_que_o_relogio_do_celular(app_module, cena):
    from app import User, db
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        t9 = _tarefas()[0]
        ana = db.session.get(User, cena['ana'])
        selo = s.registrar_leitura(ana, t9.ponto, agora_utc=utc(SEGUNDA, '09:10'))
        ex, _ = s.registrar_execucao(ana, {
            'envio_id': 'com-selo-0001', 'ponto': t9.ponto.codigo_qr, 'tarefa_id': t9.id,
            'respostas': _respostas(), 'selo_leitura': selo,
            'lido_em': utc(SEGUNDA, '08:00').isoformat()}, {'depois': [Arquivo()]},
            agora_utc=utc(SEGUNDA, '09:20'))
        assert not ex.sem_sinal
        assert tempo.fmt(ex.lido_em, '%H:%M') == '09:10'
        assert tempo.fmt(ex.concluida_em, '%H:%M') == '09:20'
        # O selo de outra pessoa não vale para a Ana.
        mariana = db.session.get(User, cena['mariana'])
        assert s._hora_da_leitura(selo, mariana, t9.ponto) is None


def test_atividade_extra(app_module, cena):
    from app import User, db
    with app_module.app.app_context():
        s = _s()
        ana = db.session.get(User, cena['ana'])
        from facilities.cadastros.models import PontoInspecao
        ponto = db.session.get(PontoInspecao, cena['ponto'])
        ex, _ = s.registrar_execucao(ana, {
            'envio_id': 'extra-000001', 'ponto': ponto.codigo_qr, 'versao_id': cena['versao'],
            'respostas': _respostas(), 'sem_sinal': True,
            'lido_em': utc(SEGUNDA, '13:00').isoformat()}, {'depois': [Arquivo()]},
            agora_utc=utc(SEGUNDA, '13:05'))
        assert ex.extra and ex.tarefa_id is None


def test_nao_realizada_exige_motivo_e_pode_abrir_chamado(app_module, cena):
    from app import User, db
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        t9 = _tarefas()[0]
        ana = db.session.get(User, cena['ana'])
        with pytest.raises(s.RegraDaRota, match='motivo'):
            s.marcar_nao_realizada(t9, ana, '')
        with pytest.raises(s.RegraDaRota, match='o que aconteceu'):
            s.marcar_nao_realizada(t9, ana, 'outro', '')
        s.marcar_nao_realizada(t9, ana, 'falta_material', 'sem papel no estoque',
                               abrir_chamado=True)
        db.session.commit()
        from facilities.chamados.models import Chamado
        assert t9.status == 'nao_realizada' and t9.chamado_id
        assert 'falta de material' in db.session.get(Chamado, t9.chamado_id).titulo
        with pytest.raises(s.RegraDaRota, match='já foi registrada'):
            s.marcar_nao_realizada(t9, ana, 'acesso')


def test_correcao_guarda_o_original(app_module, cena):
    from app import User, db
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        ex, _ = _executar(cena['ana'], _tarefas()[0], utc(SEGUNDA, '09:00'))
        db.session.commit()
        ana = db.session.get(User, cena['ana'])
        with pytest.raises(s.RegraDaRota, match='gestão'):
            s.corrigir(ex, ana, 'errei', {'mictorios': 'nao_conforme'})
        gestor = db.session.get(User, fabrica.pessoa(app_module, 'g.corr@trino.com', 'pleno',
                                                     locais=['Shopping Centro']))
        with pytest.raises(s.RegraDaRota, match='motivo'):
            s.corrigir(ex, gestor, '', {'mictorios': 'nao_conforme'})
        s.corrigir(ex, gestor, 'A encarregada avisou que errou', {'mictorios': 'nao_conforme'})
        db.session.commit()
        assert json.loads(ex.respostas_json)['mictorios'] == 'conforme'
        assert s.respostas_vigentes(ex)['mictorios'] == 'nao_conforme'


def test_fora_da_carteira_nao_executa(app_module, cena):
    with app_module.app.app_context():
        s = _s()
        s.gerar(SEGUNDA)
        fora = fabrica.pessoa(app_module, 'fora.rota@trino.com', 'encarregado',
                              locais=['Hospital Norte'])
        with pytest.raises(s.RegraDaRota, match='não está entre os seus'):
            _executar(fora, _tarefas()[0], utc(SEGUNDA, '09:00'))
