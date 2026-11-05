"""Massa de dados para o teste de carga da auditoria (Fase 3).

    DATABASE_URL=postgresql://.../f3_carga python scripts/auditoria/semear_carga.py SAIDA.json

SÓ banco local descartável: recusa se o nome do banco não tiver "carga" ou
"test". Cria 3 clientes, 40 locais, ~600 pessoas nos perfis de campo e de
gestão, uma rota por local (6 pontos, um horário por hora, checklist com foto
"depois"), um modelo de passagem por local, ~12 mil chamados e ~10 mil
passagens de histórico, e as tarefas dos últimos 7 dias. Escreve em SAIDA.json
as contas (e-mail, perfil, locais, QRs) que o gerador de carga usa.
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

SENHA = 'carga-Senha-2026'
N_LOCAIS = 40
PERFIS = (('visualizador', 4, 'all'), ('gerente', 8, 5), ('pleno', 16, 3),
          ('supervisor', 40, 2), ('encarregado', 380, 1), ('tecnico', 150, 1))


def main(saida):
    from sqlalchemy.engine import make_url
    nome = make_url(os.environ['DATABASE_URL']).database or ''
    if 'carga' not in nome and 'test' not in nome:
        sys.exit(f'recusado: o banco {nome!r} não parece descartável')
    random.seed(42)
    from facilities import create_app, tempo
    from facilities.extensions import db
    app = create_app()
    with app.app_context():
        from facilities.cadastros import servico as cad
        from facilities.cadastros.models import Estado, PontoInspecao
        from facilities.chamados.models import Chamado, ChamadoEvento
        from facilities.core.models import Client, User
        from facilities.passagem.models import (DiarioArea, DiarioConfiguracao,
                                                DiarioPendencia, DiarioTurno)
        from facilities.rotas import servico as rotas
        if User.query.count() > 1:
            sys.exit('banco já semeado')
        ba = Estado.query.filter_by(sigla='BA').one()
        ba.is_active = True
        admin = User(name='Administrador Carga', email='admin@carga.test', role='master',
                     all_clients=True)
        admin.set_password(SENHA)
        hash_comum = admin.password_hash
        admin.must_change_password = False
        db.session.add(admin)
        db.session.flush()
        emp = cad.salvar_empresa(None, {'nome': 'Trino Carga'}, admin)
        contratantes = [cad.salvar_contratante(None, {'nome': f'Cliente {i}', 'empresa_id': emp.id,
                                                       'centro_custo': f'C{i}'}, admin)
                        for i in range(3)]
        locais, qrs, cfgs = [], {}, {}
        hoje = tempo.hoje()
        horarios = ', '.join(f'{h:02d}:{m:02d}' for h in range(24) for m in (0,))
        for i in range(N_LOCAIS):
            loc = Client(name=f'Local {i:02d}', cost_center=f'L{i:02d}', is_active=True)
            db.session.add(loc)
            db.session.flush()
            cad.vincular_local(loc, {'contratante_id': contratantes[i % 3].id,
                                     'estado_id': ba.id}, admin)
            setor = cad.salvar_setor(loc, None, {'nome': 'Operação'}, admin)
            amb = cad.salvar_ambiente(loc, None, {'nome': 'Térreo', 'setor_id': setor.id}, admin)
            pontos = []
            for p in range(6):
                pt = PontoInspecao(ambiente_id=amb.id, client_id=loc.id, nome=f'Ponto {p}',
                                   codigo_qr=f'QRcarga{i:03d}p{p}'.ljust(22, '0'))
                db.session.add(pt)
                pontos.append(pt)
            db.session.flush()
            m = rotas.criar_modelo(loc.id, {'nome': f'Limpeza {i}'}, admin)
            rotas.publicar(m, rotas.normalizar_itens([
                {'texto': 'Piso limpo?', 'tipo': 'sim_nao', 'obrigatorio': True},
                {'texto': 'Lixo retirado?', 'tipo': 'sim_nao', 'obrigatorio': True}]),
                {'exige_foto_depois': '1'}, admin)
            rota = rotas.salvar_rota(loc, None, {
                'nome': f'Rota {i}', 'turno': '1º Turno', 'hora_inicio': '00:00',
                'hora_fim': '23:59', 'tolerancia_min': '240', 'dias_semana': '1234567'})
            for pt in pontos:
                rotas.salvar_item(rota, None, {'ponto_id': pt.id, 'modelo_id': m.id,
                                               'horarios': horarios})
            area = DiarioArea(client_id=loc.id, nome='Limpeza', ativo=True, created_by=admin.id)
            db.session.add(area)
            db.session.flush()
            cfg = DiarioConfiguracao(
                client_id=loc.id, area_id=area.id, nome=f'Limpeza — rotina {i}',
                turnos_json=json.dumps([{'nome': '1º Turno'}, {'nome': '2º Turno'},
                                        {'nome': '3º Turno'}]),
                campos_json='[]',
                atividades_json=json.dumps([{'nome': 'Banheiros limpos', 'codigo': 'banheiros',
                                             'obrigatorio': False}]),
                tipos_ocorrencia_json='[]', ativo=True, created_by=admin.id)
            db.session.add(cfg)
            db.session.flush()
            locais.append((loc, rota))
            qrs[loc.id] = [p.codigo_qr for p in pontos]
            cfgs[loc.id] = cfg.id
        db.session.commit()
        print('locais ok', flush=True)

        contas = []
        n = 0
        por_local = {loc.id: [] for loc, _ in locais}
        for papel, qtd, quantos in PERFIS:
            for k in range(qtd):
                n += 1
                u = User(name=f'{papel.title()} {k:03d}', email=f'{papel}{k:03d}@carga.test',
                         role=papel)
                u.password_hash = hash_comum
                u.must_change_password = False
                if quantos == 'all':
                    u.all_clients = True
                    meus = []
                else:
                    base = (k * quantos) % N_LOCAIS
                    meus = [locais[(base + j) % N_LOCAIS][0] for j in range(quantos)]
                    u.clients = meus
                db.session.add(u)
                db.session.flush()
                for loc in meus:
                    por_local[loc.id].append((u.id, papel))
                contas.append({'email': u.email, 'papel': papel, 'id': u.id,
                               'locais': [c.id for c in meus]})
        db.session.commit()
        print('pessoas ok', len(contas), flush=True)
        # Gerente responsável pelos locais dele; escala dos encarregados.
        for loc, rota in locais:
            ger = [uid for uid, p in por_local[loc.id] if p == 'gerente']
            if ger:
                loc.responsible_user_id = ger[0]
            for uid, p in por_local[loc.id]:
                if p == 'encarregado':
                    rotas.salvar_escala(rota, {'user_id': uid, 'dias_semana': '1234567',
                                               'data_inicio': (hoje - timedelta(days=30))
                                               .isoformat()})
        db.session.commit()
        # Tarefas dos últimos 7 dias (histórico) e de hoje.
        for d in range(7, -1, -1):
            rotas.gerar(hoje - timedelta(days=d))
            db.session.commit()
        print('tarefas ok', flush=True)
        # Histórico: chamados e passagens (direto no ORM, sem avisos).
        agora = datetime.utcnow()
        status = ['aberto', 'em_atendimento', 'resolvido', 'fechado', 'fechado', 'fechado',
                  'cancelado']
        for loc, _ in locais:
            gente = por_local[loc.id]
            enc = [u for u, p in gente if p in ('encarregado', 'supervisor')] or [admin.id]
            tec = [u for u, p in gente if p == 'tecnico'] or [None]
            for j in range(300):
                quando = agora - timedelta(hours=random.randint(1, 24 * 120))
                st = random.choice(status)
                ch = Chamado(client_id=loc.id, titulo=f'Histórico {j}', categoria='outro',
                             prioridade=random.choice(['baixa', 'media', 'alta']),
                             status=st, solicitante_id=random.choice(enc),
                             responsavel_id=random.choice(tec) if st != 'aberto' else None,
                             origem='manual', aberto_em=quando, prazo=quando + timedelta(days=2))
                db.session.add(ch)
                db.session.flush()
                db.session.add(ChamadoEvento(chamado_id=ch.id, tipo='aberto',
                                             created_by=ch.solicitante_id, texto='Aberto.',
                                             created_at=quando))
            for d in range(1, 91):
                for turno in ('1º Turno', '2º Turno', '3º Turno'):
                    t = DiarioTurno(client_id=loc.id, configuracao_id=cfgs[loc.id],
                                    data_turno=hoje - timedelta(days=d), turno=turno,
                                    status='encerrado', dados_json='{}',
                                    created_by=random.choice(enc),
                                    submitted_at=agora - timedelta(days=d))
                    db.session.add(t)
                    if random.random() < 0.2:
                        db.session.flush()
                        db.session.add(DiarioPendencia(client_id=loc.id, turno_id=t.id,
                                                       titulo=f'Pendência {d}', descricao='',
                                                       prioridade='media',
                                                       created_by=t.created_by))
            db.session.commit()
        print('histórico ok', flush=True)
        with open(saida, 'w') as f:
            json.dump({'senha': SENHA, 'contas': contas, 'qrs': {str(k): v for k, v in qrs.items()},
                       'cfgs': {str(k): v for k, v in cfgs.items()}}, f)


if __name__ == '__main__':
    main(sys.argv[1])
