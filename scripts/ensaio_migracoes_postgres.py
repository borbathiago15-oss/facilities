"""Ensaio das migrações num Postgres de verdade: ida → volta → ida, com dados.

    python scripts/ensaio_migracoes_postgres.py postgresql://u:s@host/banco_test

O banco é ZERADO (precisa ter "test" no nome). O ensaio:

1. sobe todas as migrações;
2. semeia dado em todas as tabelas das fases novas (``SEMENTES``);
3. para cada migração, de trás para a frente: volta um passo e sobe de novo;
4. confere que a contagem de cada tabela e a "impressão digital" das linhas
   (todas as colunas, ordenadas) ficaram iguais — nada se perdeu nem mudou;
5. ``flask db check`` sem diferença.

Sai com código 1 e diz a tabela quando algo se perde.
"""
import hashlib
import os
import subprocess
import sys

import sqlalchemy as sa

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Dado de exemplo, na ordem de dependência. Cada fase acrescenta o seu.
SEMENTES = [
    "INSERT INTO users (name,email,password_hash,role,is_active,is_deleted,all_clients,"
    "must_change_password,failed_login_count,session_epoch) VALUES "
    "('Gerente','gerente@ensaio','x','pleno',true,false,false,false,0,0)",
    "INSERT INTO clients (name,cost_center,is_active,is_deleted) VALUES "
    "('GL Armazém 1','GL-01',true,false)",
    "INSERT INTO empresas (nome,is_active) VALUES ('Trino Serviços',true)",
    "INSERT INTO contratantes (empresa_id,nome,centro_custo,gerente_id,is_active) "
    "SELECT e.id,'Grupo GL','GL',u.id,true FROM empresas e, users u "
    "WHERE u.email='gerente@ensaio'",
    "UPDATE estados SET is_active=true WHERE sigla IN ('BA','MG')",
    "UPDATE clients SET contratante_id=(SELECT id FROM contratantes), "
    "estado_id=(SELECT id FROM estados WHERE sigla='BA') WHERE name='GL Armazém 1'",
    "INSERT INTO setores (client_id,nome,is_active) SELECT id,'Administrativo',true "
    "FROM clients WHERE name='GL Armazém 1'",
    "INSERT INTO ambientes (setor_id,client_id,nome,is_active) "
    "SELECT s.id,s.client_id,'Banheiro 2º andar',true FROM setores s",
    "INSERT INTO equipamentos (ambiente_id,client_id,nome,is_active) "
    "SELECT a.id,a.client_id,'Secador',true FROM ambientes a",
    "INSERT INTO pontos_inspecao (ambiente_id,client_id,equipamento_id,nome,codigo_qr,"
    "is_active) SELECT a.id,a.client_id,e.id,'Porta','QR-ENSAIO-1',true "
    "FROM ambientes a, equipamentos e",
    "INSERT INTO cadastro_eventos (entidade,entidade_id,client_id,acao,depois_json,criado_em)"
    " SELECT 'ponto',p.id,p.client_id,'criado','{}',now() FROM pontos_inspecao p",
    # Fase 2: cadeia, perfil cliente e segunda etapa.
    "UPDATE users SET role='gerente', totp_segredo='JBSWY3DPEHPK3PXP', totp_ativo=true, "
    "totp_ultimo_passo=59742556 WHERE email='gerente@ensaio'",
    "INSERT INTO users (name,email,password_hash,role,is_active,is_deleted,all_clients,"
    "must_change_password,failed_login_count,session_epoch,superior_id,totp_ativo) SELECT "
    "'Supervisor','sup@ensaio','x','supervisor',true,false,false,false,0,0,id,false "
    "FROM users WHERE email='gerente@ensaio'",
    "INSERT INTO users (name,email,password_hash,role,is_active,is_deleted,all_clients,"
    "must_change_password,failed_login_count,session_epoch,cliente_id,totp_ativo) SELECT "
    "'Cliente GL','cli@ensaio','x','cliente',true,false,false,false,0,0,id,false "
    "FROM contratantes",
    # Fase 4A: checklist, rota, escala, tarefa, execução, foto, NC, correção.
    "INSERT INTO checklist_modelos (client_id,nome,exige_foto_antes,exige_foto_depois,"
    "is_active) VALUES (NULL,'Limpeza de banheiro',false,true,true)",
    "INSERT INTO checklist_modelos (client_id,nome,exige_foto_antes,exige_foto_depois,"
    "is_active,origem_id) SELECT c.id,'Limpeza de banheiro',false,true,true,m.id "
    "FROM clients c, checklist_modelos m WHERE c.name='GL Armazém 1'",
    "INSERT INTO checklist_versoes (modelo_id,numero,itens_json,exige_foto_antes,"
    "exige_foto_depois,publicada_em) SELECT id,1,'[]',false,true,now() FROM checklist_modelos",
    "INSERT INTO rotas (client_id,nome,turno,hora_inicio,hora_fim,tolerancia_min,dias_semana,"
    "is_active) SELECT id,'Limpeza T1','1º Turno','07:00','15:00',15,'12345',true "
    "FROM clients WHERE name='GL Armazém 1'",
    "INSERT INTO rota_itens (rota_id,ponto_id,modelo_id,ordem,horarios,is_active) "
    "SELECT r.id,p.id,m.id,1,'09:00',true FROM rotas r, pontos_inspecao p, checklist_modelos m "
    "WHERE m.client_id IS NOT NULL",
    "INSERT INTO rota_escalas (rota_id,user_id,dias_semana,data_inicio,is_active) "
    "SELECT r.id,u.id,'12345','2026-10-01',true FROM rotas r, users u WHERE u.email='sup@ensaio'",
    "INSERT INTO tarefas_dia (rota_id,rota_item_id,client_id,ponto_id,versao_id,user_id,data,"
    "previsto_para,fim_do_turno,tolerancia_min,status) SELECT i.rota_id,i.id,r.client_id,"
    "i.ponto_id,v.id,u.id,'2026-10-17','2026-10-17 12:00','2026-10-17 18:00',15,"
    "'concluida_no_prazo' FROM rota_itens i JOIN rotas r ON r.id=i.rota_id "
    "JOIN checklist_versoes v ON v.modelo_id=i.modelo_id, users u WHERE u.email='sup@ensaio'",
    "INSERT INTO execucoes (tarefa_id,client_id,ponto_id,versao_id,user_id,extra,lido_em,"
    "iniciada_em,concluida_em,sem_sinal,recebida_em,respostas_json,envio_id,n_nao_conformes) "
    "SELECT t.id,t.client_id,t.ponto_id,t.versao_id,t.user_id,false,'2026-10-17 12:05',"
    "'2026-10-17 12:05','2026-10-17 12:15',true,'2026-10-17 13:00','{}','envio-ensaio-1',1 "
    "FROM tarefas_dia t",
    "INSERT INTO execucao_fotos (execucao_id,momento,mime,tamanho,storage_key,created_at) "
    "SELECT id,'depois','image/jpeg',10,'execucoes/1/x.jpg',now() FROM execucoes",
    "INSERT INTO nao_conformidades (execucao_id,client_id,item_codigo,item_texto,resposta,"
    "created_at) SELECT id,client_id,'papel','Papel reposto?','nao',now() FROM execucoes",
    "INSERT INTO execucao_correcoes (execucao_id,motivo,respostas_antes_json,"
    "respostas_depois_json,user_id,created_at) SELECT id,'erro de digitação','{}','{}',"
    "user_id,now() FROM execucoes",
    "INSERT INTO agendador_execucoes (iniciada_em,concluida_em,origem,tarefas_geradas,"
    "tarefas_perdidas,ok) VALUES (now(),now(),'comando',1,0,true)",
    # Fase 4B: QR público, presença, push e as colunas novas.
    "UPDATE contratantes SET prazos_ocorrencia_json='{\"sujo\": 30}'",
    "UPDATE rotas SET presencas_por_turno=3, presenca_prazo_min=15",
    "UPDATE tarefas_dia SET avisada_em='2026-10-17 12:00'",
    "INSERT INTO push_inscricoes (user_id,endpoint,p256dh,auth,created_at,falhas) SELECT id,"
    "'https://fcm.googleapis.com/fcm/send/x','p','a',now(),0 FROM users WHERE email='sup@ensaio'",
    "INSERT INTO ocorrencias_publicas (ponto_id,client_id,tipo,texto,token,status,criada_em) "
    "SELECT id,client_id,'sujo','piso molhado','tok-ensaio-1','aberta',now() FROM pontos_inspecao",
    "INSERT INTO confirmacoes_presenca (rota_id,client_id,user_id,data,pedido_em,prazo_ate,"
    "status,supervisor_avisado) SELECT r.id,r.client_id,u.id,'2026-10-17','2026-10-17 13:00',"
    "'2026-10-17 13:15','confirmada',false FROM rotas r, users u WHERE u.email='sup@ensaio'",
    # Fase 5: plano preventivo, ciclo, ordem, prazo parado e régua do cliente.
    "UPDATE contratantes SET prazos_chamado_json='{\"urgente\": 2, \"media\": 48}'",
    "INSERT INTO planos_preventivos (client_id,nome,ponto_id,equipamento_id,modelo_id,"
    "intervalo_dias,proxima_em,antecedencia_dias,prioridade,responsavel_id,criado_por,"
    "is_active,created_at) SELECT p.client_id,'Filtro do secador',p.id,p.equipamento_id,m.id,"
    "30,'2026-11-17',2,'media',s.id,g.id,true,now() FROM pontos_inspecao p, "
    "checklist_modelos m, users s, users g WHERE m.client_id IS NOT NULL "
    "AND s.email='sup@ensaio' AND g.email='gerente@ensaio'",
    "INSERT INTO preventiva_ordens (plano_id,vencimento,criada_em) "
    "SELECT id,'2026-10-18',now() FROM planos_preventivos",
    "INSERT INTO chamados (client_id,titulo,categoria,prioridade,status,solicitante_id,origem,"
    "origem_id,aberto_em,prazo,pausado_desde,pausa_total_seg,aviso_vencendo_em) "
    "SELECT pl.client_id,'Preventiva: Filtro do secador','equipamento','media','aguardando',"
    "pl.criado_por,'preventiva',o.id,'2026-10-16 10:00','2026-10-19 02:59',"
    "'2026-10-17 10:00',3600,'2026-10-18 01:00' FROM preventiva_ordens o "
    "JOIN planos_preventivos pl ON pl.id=o.plano_id",
    "UPDATE preventiva_ordens SET chamado_id=(SELECT max(id) FROM chamados)",
    "UPDATE execucoes SET chamado_id=(SELECT max(id) FROM chamados)",
    # Fase 6: funcionários (com e sem login), posto com rota, escala, falta
    # coberta e visita de supervisão feita.
    "INSERT INTO funcionarios (client_id,nome,funcao,matricula,user_id,is_active,created_at) "
    "SELECT c.id,'Ana Souza','ASG','123',u.id,true,now() FROM clients c, users u "
    "WHERE c.name='GL Armazém 1' AND u.email='sup@ensaio'",
    "INSERT INTO funcionarios (client_id,nome,funcao,is_active,created_at) "
    "SELECT id,'Mariana Lima','ASG',true,now() FROM clients WHERE name='GL Armazém 1'",
    "INSERT INTO postos (client_id,nome,hora_inicio,hora_fim,rota_id,is_active,created_at) "
    "SELECT r.client_id,'Limpeza T1','07:00','15:00',r.id,true,now() FROM rotas r",
    "INSERT INTO escalas (client_id,funcionario_id,posto_id,dias_semana,data_inicio,is_active,"
    "created_at) SELECT p.client_id,f.id,p.id,'12345','2026-10-01',true,now() "
    "FROM postos p, funcionarios f WHERE f.nome='Ana Souza'",
    "INSERT INTO presencas (client_id,funcionario_id,posto_id,data,situacao,registrada_por,"
    "registrada_em) SELECT e.client_id,e.funcionario_id,e.posto_id,'2026-10-16','faltou',u.id,"
    "now() FROM escalas e, users u WHERE u.email='gerente@ensaio'",
    "INSERT INTO coberturas (presenca_id,client_id,funcionario_id,motivo,registrada_por,"
    "registrada_em) SELECT p.id,p.client_id,f.id,'atestado',u.id,now() FROM presencas p, "
    "funcionarios f, users u WHERE f.nome='Mariana Lima' AND u.email='gerente@ensaio'",
    "INSERT INTO visitas_programadas (client_id,nome,modelo_id,supervisor_id,intervalo_dias,"
    "proxima_em,is_active,criado_por,created_at) SELECT m.client_id,'Visita semanal',m.id,s.id,"
    "7,'2026-10-23',true,g.id,now() FROM checklist_modelos m, users s, users g "
    "WHERE m.client_id IS NOT NULL AND s.email='sup@ensaio' AND g.email='gerente@ensaio'",
    "INSERT INTO visitas (programada_id,client_id,vencimento,supervisor_id,status,criada_em,"
    "feita_por,feita_em,versao_id,respostas_json,n_nao_conformes,chamado_id) SELECT vp.id,"
    "vp.client_id,'2026-10-16',vp.supervisor_id,'feita',now(),vp.supervisor_id,now(),v.id,"
    "'{}',1,(SELECT max(id) FROM chamados) FROM visitas_programadas vp JOIN checklist_versoes v "
    "ON v.modelo_id=vp.modelo_id",
    # Fase 7: catálogo (com e sem preço), entrada, consumo na OS, pedido.
    "UPDATE contratantes SET prazo_pedido_insumo_horas=24",
    "INSERT INTO materiais (nome,unidade,preco_unitario,is_active,created_at) VALUES "
    "('Detergente neutro 5 L','un',12.90,true,now()),('Pano de chão','un',NULL,true,now())",
    "INSERT INTO movimentos_estoque (client_id,material_id,tipo,quantidade,preco_unitario,valor,"
    "data,user_id,criado_em) SELECT c.id,m.id,'entrada',10.000,m.preco_unitario,"
    "10*m.preco_unitario,'2026-10-15',u.id,now() FROM clients c, materiais m, users u "
    "WHERE c.name='GL Armazém 1' AND u.email='gerente@ensaio'",
    "INSERT INTO movimentos_estoque (client_id,material_id,tipo,quantidade,preco_unitario,valor,"
    "data,motivo,user_id,criado_em) SELECT c.id,m.id,'consumo',-1.500,m.preco_unitario,"
    "1.5*m.preco_unitario,'2026-10-16','na OS',u.id,now() FROM clients c, materiais m, users u "
    "WHERE c.name='GL Armazém 1' AND u.email='sup@ensaio'",
    "INSERT INTO consumos (movimento_id,client_id,chamado_id,rota_id) SELECT mv.id,mv.client_id,"
    "(SELECT max(id) FROM chamados),(SELECT min(id) FROM rotas) FROM movimentos_estoque mv "
    "WHERE mv.tipo='consumo'",
    "INSERT INTO pedidos_insumo (client_id,material_id,quantidade,texto,prazo,status,user_id,"
    "criado_em) SELECT c.id,m.id,5,'acabou','2026-10-19 12:00','aberto',u.id,now() "
    "FROM clients c, materiais m, users u WHERE c.name='GL Armazém 1' "
    "AND m.nome='Pano de chão' AND u.email='sup@ensaio'",
    # Fase 8: uma chave da integração (com local) e um acesso registrado.
    "INSERT INTO integracao_chaves (nome,prefixo,hash_chave,todos_os_locais,is_active,"
    "criada_por,criada_em) SELECT 'Intelligence','abcd1234',repeat('a',64),false,true,id,now() "
    "FROM users WHERE email='gerente@ensaio'",
    "INSERT INTO integracao_chave_locais (chave_id,client_id) SELECT k.id,c.id "
    "FROM integracao_chaves k, clients c WHERE c.name='GL Armazém 1'",
    "INSERT INTO integracao_acessos (chave_id,em,rota,parametros,status,itens,ip) "
    "SELECT id,now(),'nota','ate=2026-10-17&de=2026-10-01',200,1,'10.0.0.1' "
    "FROM integracao_chaves",
    # Fase 9B: uma cobrança do cliente com a trilha, e o interruptor do nome ligado.
    "UPDATE contratantes SET mostrar_nome_executor=true",
    "INSERT INTO cobrancas (client_id,titulo,texto,prazo,status,autor_id,criada_em,"
    "respondida_em,reaberturas) SELECT c.id,'Banheiro sujo','Limpar o 2º andar',"
    "'2026-10-20 02:59','respondida',u.id,now(),now(),1 FROM clients c, users u "
    "WHERE c.name='GL Armazém 1' AND u.email='cli@ensaio'",
    "INSERT INTO cobranca_eventos (cobranca_id,tipo,texto,prazo,autor_id,created_at) "
    "SELECT b.id,'aberta',b.texto,b.prazo,b.autor_id,now() FROM cobrancas b",
    "INSERT INTO cobranca_eventos (cobranca_id,tipo,texto,prazo,autor_id,created_at) "
    "SELECT b.id,'resposta','Feito às 14h',b.prazo,u.id,now() FROM cobrancas b, users u "
    "WHERE u.email='gerente@ensaio'",
    # Fase 10: uma foto livre numa visita de supervisão.
    "INSERT INTO visita_fotos (visita_id,momento,item_codigo,mime,tamanho,storage_key,"
    "created_at) SELECT id,'livre',NULL,'image/jpeg',1234,'visitas/1/a.jpg',now() "
    "FROM visitas",
    # Relatório do cliente: um mês liberado, com fotos e recado.
    "INSERT INTO relatorios_cliente (client_id,mes,fotos_json,recado,liberado_em,liberado_por,"
    "atualizado_em) SELECT c.id,'2026-09-01','[\"execucao:1\"]','Reforço no 2º andar',now(),"
    "u.id,now() FROM clients c, users u WHERE c.name='GL Armazém 1' "
    "AND u.email='gerente@ensaio'",
    # POP/FIT: um documento guardado num checklist do local, visível ao cliente.
    "INSERT INTO checklist_documentos (modelo_id,nome,mime,tamanho,storage_key,visivel_cliente,"
    "is_active,enviado_por,enviado_em) SELECT m.id,'POP Banheiro.pdf','application/pdf',2048,"
    "'checklists/1/docs/a.pdf',true,true,u.id,now() FROM checklist_modelos m, users u "
    "WHERE m.client_id IS NOT NULL AND u.email='gerente@ensaio'",
    # Auditoria SEC-003: uma conta com o código travado no servidor.
    "UPDATE users SET totp_falhas=3, totp_bloqueio_ate='2026-10-19 12:00' "
    "WHERE email='gerente@ensaio'",
    # Rotas prontas: um modelo com uma linha apontando para um checklist da biblioteca.
    "INSERT INTO rota_modelos (nome,segmento,descricao,turno,hora_inicio,hora_fim,"
    "tolerancia_min,dias_semana,is_active,atualizado_em) VALUES ('Escritório — ensaio',"
    "'Escritório / corporativo',NULL,'Diurno','06:00','18:00',30,'12345',true,now())",
    "INSERT INTO rota_modelo_itens (rota_modelo_id,ordem,setor,ambiente,checklist_id,horarios,"
    "quantidade) SELECT r.id,0,'Sanitários','Banheiro masculino',m.id,'08:00, 10:00',2 "
    "FROM rota_modelos r, (SELECT min(id) AS id FROM checklist_modelos) m",
    # Bloco do técnico, etapa 1: o ponto vira a entrada do local, o item da
    # rota (e o da rota pronta) ganha tempo previsto, a execução tem motivo de
    # atraso, a ocorrência pública tem itens marcados e autor, e há uma
    # chegada registrada pela câmera e outra liberada pela gestão.
    "UPDATE pontos_inspecao SET entrada_do_local=true WHERE codigo_qr='QR-ENSAIO-1'",
    "UPDATE rota_itens SET tempo_previsto_min=30",
    "UPDATE rota_modelo_itens SET tempo_previsto_min=30",
    "UPDATE execucoes SET motivo_atraso='outro', motivo_atraso_texto='reunião no meio' "
    "WHERE envio_id='envio-ensaio-1'",
    "UPDATE ocorrencias_publicas SET itens_json='[\"papel\"]', autor_id=(SELECT id FROM users "
    "WHERE email='cli@ensaio') WHERE token='tok-ensaio-1'",
    "INSERT INTO chegadas (user_id,client_id,ponto_id,data,chegou_em,com_camera,created_at) "
    "SELECT u.id,p.client_id,p.id,'2026-10-17','2026-10-17 10:02',true,now() "
    "FROM users u, pontos_inspecao p WHERE u.email='sup@ensaio'",
    "INSERT INTO chegadas (user_id,client_id,ponto_id,data,chegou_em,com_camera,liberada_por,"
    "created_at) SELECT u.id,p.client_id,p.id,'2026-10-18','2026-10-18 10:30',false,g.id,now() "
    "FROM users u, users g, pontos_inspecao p WHERE u.email='sup@ensaio' "
    "AND g.email='gerente@ensaio'",
    # Plano de limpeza: o item só de segunda a sexta com sábado diferente, a
    # versão com materiais e EPI, a rota com intervalo e observações.
    "UPDATE rota_itens SET dias_semana='12345', horarios_por_dia='{\"6\": \"08:00\"}'",
    "UPDATE checklist_versoes SET materiais='Vassoura, pá, mop úmido', epi='Luva nitrílica'",
    "UPDATE rotas SET intervalo_inicio='11:00', intervalo_fim='12:00', "
    "observacoes='Manter as gaiolas conforme a identificação da câmara.'",
    # Novo contrato: a logo do cliente e dois convites (um aberto, um aceito).
    "UPDATE contratantes SET logo_key='logos/cliente-1-abc123.png'",
    "INSERT INTO convites (token_hash,nome,email,telefone,role,superior_id,locais_json,"
    "criado_por_id,criado_em,expira_em) SELECT 'hash-ensaio-1','Maria Convidada',"
    "'maria@ensaio','5571999990000','encarregado',u.id,'[' || c.id || ']',u.id,now(),"
    "now() + interval '7 days' FROM users u, clients c WHERE u.email='gerente@ensaio' "
    "AND c.name='GL Armazém 1'",
    "INSERT INTO convites (token_hash,nome,email,role,cliente_id,locais_json,criado_por_id,"
    "criado_em,expira_em,aceito_em,usuario_id) SELECT 'hash-ensaio-2','Cliente Convidado',"
    "'cli@ensaio','cliente',k.id,'[]',u.id,now(),now() + interval '7 days',now(),x.id "
    "FROM users u, users x, contratantes k WHERE u.email='gerente@ensaio' "
    "AND x.email='cli@ensaio'",
    # Ajustes de fluxo: um feriado do local, uma rota que para no feriado e
    # mudou à tarde, e um relatório liberado congelado.
    "INSERT INTO feriados (client_id,data,nome,criado_por,criado_em) SELECT c.id,'2026-07-02',"
    "'Independência da Bahia',u.id,now() FROM clients c, users u "
    "WHERE c.name='GL Armazém 1' AND u.email='gerente@ensaio'",
    "UPDATE rotas SET funciona_em_feriado=false, vale_a_partir='2026-10-23 17:00'",
    "UPDATE relatorios_cliente SET congelado_json='{\"dados\": {}, \"fotos\": []}'",
    # Reclamação e elogio pelo QR: um elogio e um aviso com responsável e resumo.
    "INSERT INTO elogios_publicos (ponto_id,client_id,nota,texto,criado_em,responsavel_id) "
    "SELECT p.id,p.client_id,5,'Impecável',now(),u.id FROM pontos_inspecao p, users u "
    "WHERE u.email='sup@ensaio'",
    "UPDATE ocorrencias_publicas SET resumo='Lixeiras esvaziadas', "
    "responsavel_id=(SELECT id FROM users WHERE email='sup@ensaio')",
    # Troca de área: uma execução adiantada a pedido do cliente.
    "UPDATE execucoes SET motivo_troca='pedido_cliente', motivo_troca_texto='Reunião às 8h'",
    # Cadastro simplificado: a área com o checklist dela.
    "UPDATE pontos_inspecao SET checklist_id=(SELECT MIN(id) FROM checklist_modelos "
    "WHERE client_id IS NOT NULL)",
    # GPS na leitura do QR: a posição do local e a situação das leituras.
    "UPDATE clients SET latitude=-12.977749, longitude=-38.501630, raio_gps_m=250, "
    "posicao_marcada_em=now(), posicao_marcada_por=(SELECT id FROM users "
    "WHERE email='gerente@ensaio')",
    "UPDATE execucoes SET gps_situacao='fora', gps_distancia_m=1100, gps_precisao_m=25",
    "UPDATE chegadas SET gps_situacao='sem_gps'",
]


def _flask(*args, url):
    env = dict(os.environ, DATABASE_URL=url, SECRET_KEY=os.environ.get('SECRET_KEY', 'ensaio'),
               STORAGE_BACKEND='local', SESSION_COOKIE_SECURE='0')
    r = subprocess.run([sys.executable, '-m', 'flask', '--app', 'facilities', 'db', *args],
                       cwd=RAIZ, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f'flask db {" ".join(args)} falhou:\n{r.stdout}\n{r.stderr}')
    return r.stdout + r.stderr


def _revisoes(url):
    saida = _flask('history', url=url)
    revs = []
    for linha in saida.splitlines():
        if '->' in linha:
            destino = linha.split('->', 1)[1].strip().split(' ', 1)[0].strip(',')
            revs.append(destino)
    return revs   # da mais nova para a mais velha


def _digitais(engine):
    insp = sa.inspect(engine)
    out = {}
    with engine.connect() as c:
        for t in sorted(insp.get_table_names()):
            if t.startswith('_quarentena_') or t == 'alembic_version':
                continue
            linhas = c.execute(sa.text(f'SELECT * FROM {t} ORDER BY 1')).fetchall()
            h = hashlib.sha256(repr([tuple(map(str, r)) for r in linhas]).encode()).hexdigest()
            out[t] = (len(linhas), h[:12])
    return out


def ensaiar(url, sementes=SEMENTES):
    nome = sa.engine.make_url(url).database or ''
    if 'test' not in nome.lower():
        raise SystemExit(f'O banco {nome!r} não tem "test" no nome: o ensaio o zera.')
    engine = sa.create_engine(url)
    with engine.begin() as c:
        c.execute(sa.text('DROP SCHEMA public CASCADE'))
        c.execute(sa.text('CREATE SCHEMA public'))
    _flask('upgrade', url=url)
    with engine.begin() as c:
        for sql in sementes:
            c.execute(sa.text(sql))
    antes = _digitais(engine)
    revs = _revisoes(url)
    for i, rev in enumerate(revs[:-1]):            # a inicial não tem volta com dados
        anterior = revs[i + 1]
        _flask('downgrade', anterior, url=url)
        _flask('upgrade', url=url)
        depois = _digitais(engine)
        for t, v in antes.items():
            if depois.get(t) != v:
                raise SystemExit(f'Volta e ida de {rev}: a tabela {t} mudou '
                                 f'({v} → {depois.get(t)}).')
        print(f'ok: {rev} — volta e ida sem perder nada')
    saida = _flask('check', url=url)
    if 'No new upgrade operations detected' not in saida:
        raise SystemExit(f'flask db check acusou diferença:\n{saida}')
    print('ok: flask db check sem diferença')
    engine.dispose()
    return antes


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    ensaiar(sys.argv[1])
