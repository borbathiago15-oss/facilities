"""Auditoria da Fase 2 (entradas), 05/11/2026: a varredura de entradas hostis.

Regra do dono: **nenhuma entrada do usuário dá 500.** Esta varredura anda
por TODAS as rotas que gravam do ``app.url_map`` (rota nova entra sozinha)
com um jogo de corpos hostis — campo vazio, texto onde vai número, número
gigante (``1e308``, ``10**30``), negativo, data impossível, texto longo,
byte nulo, raiz JSON que é lista/texto/nula, JSON quebrado, estruturas com o
tipo errado — em JSON e em formulário, como **administrador** e como
**encarregado** do local (perfil de campo), e mais as rotas públicas sem
login. Também troca os ids do caminho por inteiros que não cabem na coluna
(``2**31`` e ``10**20``) em todas as rotas (GET inclusive) e manda consulta
hostil (``?client_id=abc``...) em todas as telas e APIs de leitura.

O que é cobrado em cada resposta:

* status < 500 (o 500 é o defeito);
* debaixo de ``/api/v1``: a resposta é JSON, e todo erro (>= 400) traz
  ``error`` — a tela nova sabe o que mostrar.

Defeito já conhecido fica em ``CONHECIDOS`` (endpoint → motivo) e tem um
teste próprio marcado ``xfail(strict=True)`` em ``test_auditoria_entradas.py``;
qualquer 500 NOVO reprova esta varredura. ``AUDITORIA_RELATORIO=<arquivo>``
grava o detalhe de cada achado em JSON (para o relatório da auditoria).
"""
import json
import os
import re
import traceback
import uuid

import pytest
from flask import got_request_exception

from facilities import tempo
from tests import fabrica
from tests.conftest import ADMIN_EMAIL, TEST_ADMIN_PASSWORD
from tests.test_isolamento_varredura import _valor_do_parametro, local_a  # noqa: F401

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Fora da varredura, com o motivo.
FORA = {
    'static': 'arquivos estáticos',
    'auth.logout': 'derrubaria a sessão no meio da varredura',
    # Senha errada conta no bloqueio da conta de quem chama: a varredura
    # bloquearia o próprio perfil. Os quatro estão em test_auditoria_entradas
    # (senha errada, vazia, de outro tipo) e em test_telas_conta.py.
    'api_v1.api_trocar_senha': 'conta erro de senha (bloqueio)',
    'api_v1.api_desativar_codigo': 'conta erro de senha (bloqueio)',
    'auth.ativar_codigo': 'conta erro de senha (bloqueio)',
    'api_v1.api_ativar_codigo': 'conta erro de senha (bloqueio)',
    'auth.trocar_senha': 'conta erro de senha (bloqueio)',
    'auth.desativar_codigo': 'conta erro de senha (bloqueio)',
    # Gerar senha nova e desligar o código de outra pessoa pedem a senha do
    # administrador; errada, conta no bloqueio DELE e a sessão cai (por
    # desenho: test_telas_conta.py e test_nucleo.py).
    'admin.nova_senha': 'senha do administrador conta no bloqueio',
    'admin.desligar_codigo': 'senha do administrador conta no bloqueio',
    'api_v1.api_admin_nova_senha': 'senha do administrador conta no bloqueio',
    'api_v1.api_admin_desligar_codigo': 'senha do administrador conta no bloqueio',
}

# Os 500 que a auditoria já achou: cada um tem o seu xfail(strict=True) em
# tests/test_auditoria_entradas.py. Corrigiu? Tire daqui e de lá.
# chave: (endpoint, classe da variante) — a classe é o que vem antes do ":"
# no nome da variante; '*' = qualquer variante.
# Os códigos (detalhe e passos no relatório da Fase 2; um teste de cada em
# test_auditoria_entradas.py):
#   E1 raiz JSON que não é objeto (lista/texto/número) → .get() estoura
#   E2 texto/estrutura com o tipo errado no JSON → .strip()/iteração estoura
#   E3 id do corpo que não cabe na coluna (SQLite: > 2^63; Postgres: > 2^31 ao gravar)
#   E4 int() sem tratamento ('abc', '', None)
#   E5 byte nulo (\x00) no texto — só Postgres
#   E6 texto maior que a coluna varchar — só Postgres
#   E7 id do caminho/consulta > 2^63 — só SQLite (dev/testes)
#   E9 contrato que não existe aceito para o administrador na Passagem (FK) — Postgres
ASSINATURAS_CONHECIDAS = ('cannot contain NUL (0x00)', 'StringDataRightTruncation')
CONHECIDOS = {
    ('admin.criar_contrato', 'texto'): 'E5',
    ('admin.editar_contrato', 'id'): 'E7',
    ('admin.editar_contrato', 'texto'): 'E5',
    ('admin.editar_usuario', 'id'): 'E7',
    ('admin.editar_usuario', 'texto'): 'E5',
    ('api_v1.api_abrir_aviso', 'id'): 'E7',
    ('api_v1.api_admin_criar_contrato', 'texto'): 'E5',
    ('api_v1.api_admin_editar_contrato', 'id'): 'E7',
    ('api_v1.api_admin_editar_contrato', 'texto'): 'E5',
    ('api_v1.api_admin_editar_usuario', 'id'): 'E7',
    ('api_v1.api_admin_editar_usuario', 'texto'): 'E5',
    ('api_v1.api_ativo_cliente', 'id'): 'E7',
    ('api_v1.api_ativo_empresa', 'id'): 'E7',
    ('api_v1.api_ativo_estado', 'id'): 'E7',
    ('api_v1.api_ativo_item', 'id'): 'E7',
    ('api_v1.api_cadastros_local', 'id'): 'E7',
    ('api_v1.api_cadastros_trilha_local', 'id'): 'E7',
    ('api_v1.api_centros_adicionar_linhas', 'id'): 'E7',
    ('api_v1.api_centros_centro', 'id'): 'E7',
    ('api_v1.api_centros_cliente', 'id'): 'E7',
    ('api_v1.api_centros_criar_areas', 'id'): 'E7',
    ('api_v1.api_centros_criar_centro', 'id'): 'E7',
    ('api_v1.api_centros_criar_rota', 'id'): 'E7',
    ('api_v1.api_centros_criar_rota', 'texto'): 'E5',
    ('api_v1.api_centros_escalar', 'id'): 'E7',
    ('api_v1.api_centros_escalar', 'numero'): 'E3+E4',
    ('api_v1.api_centros_marcar_posicao', 'id'): 'E7',
    ('api_v1.api_centros_remover_linha', 'id'): 'E7',
    ('api_v1.api_centros_rota', 'id'): 'E7',
    ('api_v1.api_centros_trocar_checklist', 'id'): 'E7',
    ('api_v1.api_centros_trocar_checklist', 'numero'): 'E3',
    ('api_v1.api_chamados_acao', 'id'): 'E7',
    ('api_v1.api_chamados_anexar', 'id'): 'E7',
    ('api_v1.api_chamados_criar', 'numero'): 'E3',
    ('api_v1.api_chamados_criar', 'texto'): 'E5',
    ('api_v1.api_chamados_ver', 'id'): 'E7',
    ('api_v1.api_cobrancas_responder', 'id'): 'E7',
    ('api_v1.api_cobrancas_ver', 'id'): 'E7',
    ('api_v1.api_criar_cliente', 'numero'): 'E3',
    ('api_v1.api_criar_empresa', 'texto'): 'E5',
    ('api_v1.api_criar_item', 'id'): 'E7',
    ('api_v1.api_criar_item', 'texto'): 'E5',
    ('api_v1.api_editar_cliente', 'id'): 'E7',
    ('api_v1.api_editar_cliente', 'numero'): 'E3',
    ('api_v1.api_editar_empresa', 'id'): 'E7',
    ('api_v1.api_editar_empresa', 'texto'): 'E5',
    ('api_v1.api_editar_item', 'id'): 'E7',
    ('api_v1.api_editar_item', 'texto'): 'E5',
    ('api_v1.api_equipes_criar_escala', 'id'): 'E7',
    ('api_v1.api_equipes_criar_funcionario', 'id'): 'E7',
    ('api_v1.api_equipes_criar_posto', 'id'): 'E7',
    ('api_v1.api_equipes_criar_posto', 'texto'): 'E5',
    ('api_v1.api_equipes_editar_funcionario', 'id'): 'E7',
    ('api_v1.api_equipes_editar_posto', 'id'): 'E7',
    ('api_v1.api_equipes_editar_posto', 'texto'): 'E5',
    ('api_v1.api_equipes_encerrar_escala', 'id'): 'E7',
    ('api_v1.api_equipes_local', 'id'): 'E7',
    ('api_v1.api_equipes_mes', 'id'): 'E7',
    ('api_v1.api_integracao_criar', 'numero'): 'E3',
    ('api_v1.api_integracao_criar', 'texto'): 'E5',
    ('api_v1.api_integracao_revogar', 'id'): 'E7',
    ('api_v1.api_materiais_consumo', 'id'): 'E7',
    ('api_v1.api_materiais_consumo', 'numero'): 'E3',
    ('api_v1.api_materiais_consumo', 'texto'): 'E5',
    ('api_v1.api_materiais_criar', 'texto'): 'E5',
    ('api_v1.api_materiais_editar', 'id'): 'E7',
    ('api_v1.api_materiais_editar', 'texto'): 'E5',
    ('api_v1.api_materiais_local', 'id'): 'E7',
    ('api_v1.api_materiais_mes', 'id'): 'E7',
    ('api_v1.api_materiais_movimento', 'id'): 'E7',
    ('api_v1.api_materiais_visto', 'id'): 'E7',
    ('api_v1.api_montagem_cancelar_convite', 'id'): 'E7',
    ('api_v1.api_montagem_convidar', 'id'): 'E7',
    ('api_v1.api_montagem_convidar', 'numero'): 'E3',
    ('api_v1.api_montagem_criar_cliente', 'numero'): 'E3',
    ('api_v1.api_montagem_criar_estrutura', 'id'): 'E7',
    ('api_v1.api_montagem_criar_estrutura', 'numero'): 'E3',
    ('api_v1.api_montagem_criar_local', 'id'): 'E7',
    ('api_v1.api_montagem_equipe', 'id'): 'E7',
    ('api_v1.api_montagem_estrutura', 'id'): 'E7',
    ('api_v1.api_montagem_novo_link', 'id'): 'E7',
    ('api_v1.api_montagem_novo_local', 'id'): 'E7',
    ('api_v1.api_montagem_trocar_logo', 'id'): 'E7',
    ('api_v1.api_passagem_relatorio_mensal', 'consulta'): 'E7',
    ('api_v1.api_passagem_ver_turno', 'id'): 'E7',
    ('api_v1.api_preventiva_criar', 'id'): 'E7',
    ('api_v1.api_preventiva_criar', 'numero'): 'E3',
    ('api_v1.api_preventiva_editar', 'id'): 'E7',
    ('api_v1.api_preventiva_editar', 'numero'): 'E3',
    ('api_v1.api_preventiva_local', 'id'): 'E7',
    ('api_v1.api_relatorios_agir', 'id'): 'E7',
    ('api_v1.api_relatorios_cliente', 'id'): 'E7',
    ('api_v1.api_rotas_acao_documento', 'id'): 'E7',
    ('api_v1.api_rotas_anexar_documento', 'id'): 'E7',
    ('api_v1.api_rotas_aplicar_rota_pronta', 'id'): 'E7',
    ('api_v1.api_rotas_aplicar_rota_pronta_post', 'id'): 'E7',
    ('api_v1.api_rotas_ativo_rota', 'id'): 'E7',
    ('api_v1.api_rotas_ativo_rota_pronta', 'id'): 'E7',
    ('api_v1.api_rotas_chamado_da_nc', 'id'): 'E7',
    ('api_v1.api_rotas_copiar', 'id'): 'E7',
    ('api_v1.api_rotas_copiar', 'numero'): 'E3',
    ('api_v1.api_rotas_corrigir', 'id'): 'E7',
    ('api_v1.api_rotas_criar_escala', 'id'): 'E7',
    ('api_v1.api_rotas_criar_escala', 'numero'): 'E3+E4',
    ('api_v1.api_rotas_criar_feriado', 'id'): 'E7',
    ('api_v1.api_rotas_criar_item', 'id'): 'E7',
    ('api_v1.api_rotas_criar_item', 'numero'): 'E3+E4',
    ('api_v1.api_rotas_criar_modelo', 'id'): 'E7',
    ('api_v1.api_rotas_criar_modelo', 'texto'): 'E5',
    ('api_v1.api_rotas_criar_na_biblioteca', 'texto'): 'E5',
    ('api_v1.api_rotas_criar_rota', 'id'): 'E7',
    ('api_v1.api_rotas_criar_rota', 'texto'): 'E5',
    ('api_v1.api_rotas_dia', 'id'): 'E7',
    ('api_v1.api_rotas_editar_item', 'id'): 'E7',
    ('api_v1.api_rotas_editar_item', 'numero'): 'E3+E4',
    ('api_v1.api_rotas_editar_rota', 'id'): 'E7',
    ('api_v1.api_rotas_editar_rota', 'texto'): 'E5',
    ('api_v1.api_rotas_encerrar_escala', 'id'): 'E7',
    ('api_v1.api_rotas_execucao', 'id'): 'E7',
    ('api_v1.api_rotas_feriados', 'id'): 'E7',
    ('api_v1.api_rotas_importar_plano', 'id'): 'E7',
    ('api_v1.api_rotas_importar_plano_criar', 'id'): 'E7',
    ('api_v1.api_rotas_importar_plano_previa', 'id'): 'E7',
    ('api_v1.api_rotas_local', 'id'): 'E7',
    ('api_v1.api_rotas_modelo', 'id'): 'E7',
    ('api_v1.api_rotas_ocorrencia', 'id'): 'E7',
    ('api_v1.api_rotas_ocorrencia', 'raiz'): 'E1',
    ('api_v1.api_rotas_publicar', 'id'): 'E7',
    ('api_v1.api_rotas_remover_feriado', 'id'): 'E7',
    ('api_v1.api_rotas_rota', 'id'): 'E7',
    ('api_v1.api_rotas_rota_pronta', 'id'): 'E7',
    ('api_v1.api_rotas_salvar_rota_pronta', 'id'): 'E7',
    ('api_v1.api_rotas_salvar_rota_pronta', 'texto'): 'E5',
    ('api_v1.api_rotas_salvar_rota_pronta_nova', 'texto'): 'E5',
    ('api_v1.api_visitas_criar', 'id'): 'E7',
    ('api_v1.api_visitas_criar', 'numero'): 'E3',
    ('api_v1.api_visitas_criar', 'texto'): 'E5',
    ('api_v1.api_visitas_editar', 'id'): 'E7',
    ('api_v1.api_visitas_editar', 'numero'): 'E3',
    ('api_v1.api_visitas_editar', 'texto'): 'E5',
    ('api_v1.api_visitas_local', 'id'): 'E7',
    ('api_v1.armazenamento_arquivar', 'raiz'): 'E1',
    ('api_v1.armazenamento_prazo', 'raiz'): 'E1',
    ('cadastros.ativo_cliente', 'id'): 'E7',
    ('cadastros.ativo_empresa', 'id'): 'E7',
    ('cadastros.ativo_estado', 'id'): 'E7',
    ('cadastros.ativo_item', 'id'): 'E7',
    ('cadastros.criar_cliente', 'numero'): 'E3',
    ('cadastros.criar_empresa', 'texto'): 'E5',
    ('cadastros.criar_item', 'id'): 'E7',
    ('cadastros.criar_item', 'texto'): 'E5',
    ('cadastros.editar_cliente', 'id'): 'E7',
    ('cadastros.editar_cliente', 'numero'): 'E3',
    ('cadastros.editar_empresa', 'id'): 'E7',
    ('cadastros.editar_empresa', 'texto'): 'E5',
    ('cadastros.editar_item', 'id'): 'E7',
    ('cadastros.editar_item', 'texto'): 'E5',
    ('cadastros.etiquetas', 'id'): 'E7',
    ('cadastros.local', 'id'): 'E7',
    ('cadastros.trilha_local', 'id'): 'E7',
    ('centros.adicionar_linhas', 'id'): 'E7',
    ('centros.centro', 'id'): 'E7',
    ('centros.cliente', 'id'): 'E7',
    ('centros.criar_areas', 'id'): 'E7',
    ('centros.criar_centro', 'id'): 'E7',
    ('centros.criar_rota', 'id'): 'E7',
    ('centros.criar_rota', 'texto'): 'E5',
    ('centros.escalar', 'id'): 'E7',
    ('centros.escalar', 'numero'): 'E3+E4',
    ('centros.marcar_posicao', 'id'): 'E7',
    ('centros.remover_linha', 'id'): 'E7',
    ('centros.rota', 'id'): 'E7',
    ('centros.trocar_checklist', 'id'): 'E7',
    ('centros.trocar_checklist', 'numero'): 'E3',
    ('chamados.acao', 'id'): 'E7',
    ('chamados.anexar', 'id'): 'E7',
    ('chamados.baixar_anexo', 'id'): 'E7',
    ('chamados.criar', 'numero'): 'E3',
    ('chamados.criar', 'texto'): 'E5',
    ('chamados.ver', 'id'): 'E7',
    ('cobrancas.responder', 'id'): 'E7',
    ('cobrancas.ver', 'id'): 'E7',
    ('core.abrir_aviso', 'id'): 'E7',
    ('diario_operacional.abrir_chamado', 'id'): 'E7',
    ('diario_operacional.anexar_no_turno', 'id'): 'E7',
    ('diario_operacional.anotar_na_pendencia', 'id'): 'E7',
    ('diario_operacional.atualizar_area', 'id'): 'E7',
    ('diario_operacional.atualizar_area', 'raiz'): 'E1',
    ('diario_operacional.atualizar_area', 'texto'): 'E2+E5',
    ('diario_operacional.atualizar_configuracao', 'estrutura'): 'E2',
    ('diario_operacional.atualizar_configuracao', 'id'): 'E7',
    ('diario_operacional.atualizar_configuracao', 'numero'): 'E3+E4',
    ('diario_operacional.atualizar_configuracao', 'raiz'): 'E1',
    ('diario_operacional.atualizar_configuracao', 'texto'): 'E2+E5+E6',
    ('diario_operacional.baixar_anexo', 'id'): 'E7',
    ('diario_operacional.corrigir_turno', 'id'): 'E7',
    ('diario_operacional.criar_area', 'numero'): 'E3+E4+E9',
    ('diario_operacional.criar_area', 'raiz'): 'E1',
    ('diario_operacional.criar_area', 'texto'): 'E2+E5',
    ('diario_operacional.criar_configuracao', 'data'): 'E4',
    ('diario_operacional.criar_configuracao', 'estrutura'): 'E2',
    ('diario_operacional.criar_configuracao', 'numero'): 'E3+E4+E9',
    ('diario_operacional.criar_configuracao', 'raiz'): 'E1',
    ('diario_operacional.criar_configuracao', 'texto'): 'E2+E4+E5+E6',
    ('diario_operacional.criar_pendencia_gestor', 'numero'): 'E3+E9',
    ('diario_operacional.criar_pendencia_gestor', 'raiz'): 'E1',
    ('diario_operacional.criar_pendencia_gestor', 'texto'): 'E2',
    ('diario_operacional.criar_tarefa_turno', 'numero'): 'E3',
    ('diario_operacional.criar_tarefa_turno', 'raiz'): 'E1',
    ('diario_operacional.criar_tarefa_turno', 'texto'): 'E2+E5+E6',
    ('diario_operacional.excluir_anexo', 'id'): 'E7',
    ('diario_operacional.relatorio_mensal', 'consulta'): 'E7',
    ('diario_operacional.resolver_pendencia', 'id'): 'E7',
    ('diario_operacional.resolver_pendencia', 'raiz'): 'E1',
    ('diario_operacional.resolver_pendencia', 'texto'): 'E2',
    ('diario_operacional.responder_tarefa_turno', 'id'): 'E7',
    ('diario_operacional.responder_tarefa_turno', 'raiz'): 'E1',
    ('diario_operacional.salvar_turno', 'numero'): 'E3',
    ('diario_operacional.salvar_turno', 'raiz'): 'E1',
    ('diario_operacional.salvar_turno', 'texto'): 'E2+E5+E6',
    ('diario_operacional.ver_turno', 'id'): 'E7',
    ('equipes.app_cobertura', 'id'): 'E7',
    ('equipes.criar_escala', 'id'): 'E7',
    ('equipes.criar_funcionario', 'id'): 'E7',
    ('equipes.criar_posto', 'id'): 'E7',
    ('equipes.criar_posto', 'texto'): 'E5',
    ('equipes.editar_funcionario', 'id'): 'E7',
    ('equipes.editar_posto', 'id'): 'E7',
    ('equipes.editar_posto', 'texto'): 'E5',
    ('equipes.encerrar_escala', 'id'): 'E7',
    ('equipes.local', 'id'): 'E7',
    ('equipes.mes', 'id'): 'E7',
    ('integracao.criar', 'numero'): 'E3',
    ('integracao.criar', 'texto'): 'E5',
    ('integracao.revogar', 'id'): 'E7',
    ('materiais.app_consumo', 'numero'): 'E3',
    ('materiais.app_consumo', 'texto'): 'E5',
    ('materiais.app_pedido', 'numero'): 'E3',
    ('materiais.app_pedido', 'texto'): 'E5',
    ('materiais.consumo', 'id'): 'E7',
    ('materiais.consumo', 'numero'): 'E3',
    ('materiais.consumo', 'texto'): 'E5',
    ('materiais.criar_material', 'texto'): 'E5',
    ('materiais.editar_material', 'id'): 'E7',
    ('materiais.editar_material', 'texto'): 'E5',
    ('materiais.foto', 'id'): 'E7',
    ('materiais.local', 'id'): 'E7',
    ('materiais.mes', 'id'): 'E7',
    ('materiais.movimento', 'id'): 'E7',
    ('materiais.visto', 'id'): 'E7',
    ('montagem.cancelar_convite', 'id'): 'E7',
    ('montagem.convidar', 'id'): 'E7',
    ('montagem.convidar', 'numero'): 'E3',
    ('montagem.criar_cliente', 'numero'): 'E3',
    ('montagem.criar_estrutura', 'id'): 'E7',
    ('montagem.criar_estrutura', 'numero'): 'E3',
    ('montagem.criar_local', 'id'): 'E7',
    ('montagem.equipe', 'id'): 'E7',
    ('montagem.estrutura', 'id'): 'E7',
    ('montagem.logo', 'id'): 'E7',
    ('montagem.novo_link', 'id'): 'E7',
    ('montagem.novo_local', 'id'): 'E7',
    ('montagem.trocar_logo', 'id'): 'E7',
    ('preventiva.criar', 'id'): 'E7',
    ('preventiva.criar', 'numero'): 'E3',
    ('preventiva.editar', 'id'): 'E7',
    ('preventiva.editar', 'numero'): 'E3',
    ('preventiva.local', 'id'): 'E7',
    ('publico.api_ocorrencia', 'id'): 'E7',
    ('publico.api_ocorrencia', 'raiz'): 'E1',
    ('publico.foto_da_ocorrencia', 'id'): 'E7',
    ('publico.ocorrencia_no_site', 'id'): 'E7',
    ('publico.ocorrencia_no_site', 'raiz'): 'E1',
    ('publico.presenca_confirmar', 'id'): 'E7',
    ('publico.push_inscrever', 'raiz'): 'E1',
    ('publico.push_inscrever', 'texto'): 'E2',
    ('publico.push_sair', 'raiz'): 'E1',
    ('publico.push_sair', 'texto'): 'E5',
    ('relatorios.agir', 'id'): 'E7',
    ('relatorios.baixar', 'id'): 'E7',
    ('relatorios.cliente', 'id'): 'E7',
    ('rotas.acao_documento', 'id'): 'E7',
    ('rotas.anexar_documento', 'id'): 'E7',
    ('rotas.api_chegada', 'raiz'): 'E1',
    ('rotas.api_chegada', 'texto'): 'E5',
    ('rotas.api_leitura', 'raiz'): 'E1',
    ('rotas.api_leitura', 'texto'): 'E5',
    ('rotas.api_materiais', 'consulta'): 'E7',
    ('rotas.api_nao_realizada', 'id'): 'E7',
    ('rotas.api_nao_realizada', 'raiz'): 'E1',
    ('rotas.api_turno', 'consulta'): 'E7',
    ('rotas.aplicar_rota_pronta', 'id'): 'E7',
    ('rotas.aplicar_rota_pronta_post', 'id'): 'E7',
    ('rotas.ativo_rota', 'id'): 'E7',
    ('rotas.ativo_rota_pronta', 'id'): 'E7',
    ('rotas.chamado_da_nc', 'id'): 'E7',
    ('rotas.copiar', 'id'): 'E7',
    ('rotas.copiar', 'numero'): 'E3',
    ('rotas.corrigir', 'id'): 'E7',
    ('rotas.criar_escala', 'id'): 'E7',
    ('rotas.criar_escala', 'numero'): 'E3+E4',
    ('rotas.criar_feriado', 'id'): 'E7',
    ('rotas.criar_item', 'id'): 'E7',
    ('rotas.criar_item', 'numero'): 'E3+E4',
    ('rotas.criar_modelo', 'id'): 'E7',
    ('rotas.criar_modelo', 'texto'): 'E5',
    ('rotas.criar_na_biblioteca', 'texto'): 'E5',
    ('rotas.criar_rota', 'id'): 'E7',
    ('rotas.criar_rota', 'texto'): 'E5',
    ('rotas.dia', 'id'): 'E7',
    ('rotas.documento', 'id'): 'E7',
    ('rotas.editar_item', 'id'): 'E7',
    ('rotas.editar_item', 'numero'): 'E3+E4',
    ('rotas.editar_rota', 'id'): 'E7',
    ('rotas.editar_rota', 'texto'): 'E5',
    ('rotas.encerrar_escala', 'id'): 'E7',
    ('rotas.execucao', 'id'): 'E7',
    ('rotas.feriados', 'id'): 'E7',
    ('rotas.foto', 'id'): 'E7',
    ('rotas.importar_plano', 'id'): 'E7',
    ('rotas.importar_plano_criar', 'id'): 'E7',
    ('rotas.importar_plano_previa', 'id'): 'E7',
    ('rotas.liberar_chegada', 'id'): 'E7',
    ('rotas.liberar_chegada', 'numero'): 'E3',
    ('rotas.liberar_chegada', 'raiz'): 'E1',
    ('rotas.local', 'id'): 'E7',
    ('rotas.modelo', 'id'): 'E7',
    ('rotas.publicar', 'id'): 'E7',
    ('rotas.referencia', 'id'): 'E7',
    ('rotas.remover_feriado', 'id'): 'E7',
    ('rotas.rota', 'id'): 'E7',
    ('rotas.rota_pronta', 'id'): 'E7',
    ('rotas.salvar_rota_pronta', 'id'): 'E7',
    ('rotas.salvar_rota_pronta', 'texto'): 'E5',
    ('telas.cadastros_local', 'id'): 'E7',
    ('telas.centros_centro', 'id'): 'E7',
    ('telas.centros_cliente', 'id'): 'E7',
    ('telas.centros_rota', 'id'): 'E7',
    ('telas.chamados_ver', 'id'): 'E7',
    ('telas.cobrancas_ver', 'id'): 'E7',
    ('telas.equipes_local', 'id'): 'E7',
    ('telas.materiais_local', 'id'): 'E7',
    ('telas.montagem_local', 'id'): 'E7',
    ('telas.montagem_novo_local', 'id'): 'E7',
    ('telas.passagem_ver_turno', 'id'): 'E7',
    ('telas.preventiva_local', 'id'): 'E7',
    ('telas.relatorios_cliente', 'id'): 'E7',
    ('telas.rotas_execucao', 'id'): 'E7',
    ('telas.rotas_local', 'id'): 'E7',
    ('telas.rotas_local_montar', 'id'): 'E7',
    ('telas.rotas_modelo', 'id'): 'E7',
    ('telas.rotas_rota', 'id'): 'E7',
    ('telas.rotas_rota_pronta', 'id'): 'E7',
    ('telas.visitas_local', 'id'): 'E7',
    ('visitas.criar', 'id'): 'E7',
    ('visitas.criar', 'numero'): 'E3',
    ('visitas.criar', 'texto'): 'E5',
    ('visitas.editar', 'id'): 'E7',
    ('visitas.editar', 'numero'): 'E3',
    ('visitas.editar', 'texto'): 'E5',
    ('visitas.fazer', 'id'): 'E7',
    ('visitas.foto', 'id'): 'E7',
    ('visitas.local', 'id'): 'E7',
    ('visitas.ver', 'id'): 'E7',
}

# ── O vocabulário: todos os nomes de campo que o código lê ────────────────

_RE_CAMPO = re.compile(r"\.get(?:list)?\(\s*'([a-z_][a-z0-9_]*)'")
ESTRUTURAS = ('dados', 'ocorrencias', 'pendencias', 'respostas', 'itens', 'motivos',
              'turnos', 'campos', 'atividades', 'tipos_ocorrencia', 'areas', 'fotos',
              'locais', 'permissoes', 'opcoes', 'horarios_por_dia', 'pontos', 'escopo')


def _vocabulario():
    nomes = set(ESTRUTURAS)
    for pasta, _dirs, arquivos in os.walk(os.path.join(RAIZ, 'facilities')):
        if '__pycache__' in pasta:
            continue
        for a in arquivos:
            if a.endswith('.py'):
                with open(os.path.join(pasta, a), encoding='utf-8') as f:
                    nomes.update(_RE_CAMPO.findall(f.read()))
    return sorted(nomes)


VOCAB = _vocabulario()
NUMERICOS = {'cid', 'quantidade', 'preco_unitario', 'intervalo_dias', 'antecedencia_dias',
             'tolerancia_min', 'tempo_previsto_min', 'raio', 'lat', 'lng', 'precisao', 'nota',
             'pct', 'ano', 'dias', 'ordem', 'presenca_prazo_min', 'presencas_por_turno',
             'prazo_pedido_insumo_horas', 'frequencia_min', 'local', 'u', 'm', 'p', 'id',
             'raio_gps_m', 'latitude', 'longitude', 'estrelas', 'valor', 'limite', 'pagina',
             'por_pagina', 'n', 'versao', 'minutos', 'segundos', 'horas'}
DATAS = {'data', 'prazo', 'proxima_em', 'concluida_em', 'de', 'ate', 'lido_em', 'mes',
         'hora', 'horarios', 'intervalo_inicio', 'intervalo_fim', 'vencimento', 'periodo',
         'semana', 'dia', 'inicio', 'fim', 'competencia'}


def classe_do_campo(nome):
    if nome in ESTRUTURAS:
        return 'estrutura'
    if nome.endswith('_id') or nome in NUMERICOS or nome.endswith(('_min', '_dias', '_horas')):
        return 'numero'
    if nome in DATAS or nome.startswith(('data_', 'hora_', 'prazo_')) \
            or nome.endswith(('_em', '_ate', '_de', '_data')):
        return 'data'
    return 'texto'


def _corpo_base(ids, papel):
    """O corpo "bom" (os ids do local A), como na varredura de isolamento."""
    return {'client_id': ids['local'], 'configuracao_id': ids['cfg'], 'titulo': 'Varredura',
            'nome': 'Varredura', 'texto': 'Varredura', 'resposta': 'x', 'descricao': 'x',
            'prioridade': 'media', 'categoria': 'eletrica', 'setor_id': ids['setor'],
            'ambiente_id': ids['ambiente'], 'data_turno': tempo.hoje().isoformat(),
            'turno': 'Diurno', 'ponto': ids['qr'], 'tarefa_id': ids['tarefa_rota'],
            'material_id': ids['material'], 'quantidade': '1', 'escala_id': ids['escala_trabalho'],
            'funcionario_id': ids['funcionario'], 'posto_id': ids['posto'],
            'modelo_id': ids['modelo'], 'ponto_id': ids['ponto'], 'area_id': ids['area'],
            'responsavel_id': ids['dono'], 'user_id': ids['dono'],
            'prazo': tempo.hoje().isoformat(), 'proxima_em': tempo.hoje().isoformat(),
            'intervalo_dias': '7', 'envio_id': f'fuzz-{papel}-0001',
            'email': f'fuzz.{papel}@trino.com', 'role': 'encarregado', 'locais': [ids['local']]}


NUMERO_HOSTIL = {'texto': 'abc', 'gigante': '1e308', 'enorme': '9' * 30, 'negativo': '-1',
                 'vazio': '', 'nan': 'NaN'}
DATA_HOSTIL = {'impossivel': '2026-02-30', 'texto': 'abc', 'ano5': '99999-01-01',
               'br': '30/02/2026', 'hora': '25:61'}
TEXTO_HOSTIL = {'longo': 'x' * 6000, 'nulo': 'a\x00b', 'xss': '"><img src=x onerror=alert(1)>',
                'vazio': '   '}


def _todos(classe, valor, base):
    corpo = dict(base)
    for nome in VOCAB:
        if classe_do_campo(nome) == classe:
            corpo[nome] = valor
    return corpo


def variantes(base):
    """(nome, tipo, corpo): tipo 'json' (objeto Python), 'form' (dict) ou
    'cru' ((bytes, content-type))."""
    v = [('raiz:objeto_vazio', 'json', {}), ('raiz:form_vazio', 'form', {}),
         ('raiz:lista', 'json', [base, 1, 'x']), ('raiz:texto', 'json', 'abc'),
         ('raiz:nula', 'json', None), ('raiz:numero', 'json', 1e308),
         ('raiz:json_quebrado', 'cru', (b'{"titulo": "x", ', 'application/json')),
         ('raiz:texto_puro', 'cru', (b'titulo=x', 'text/plain')),
         ('base:valido', 'json', base)]
    for k, val in NUMERO_HOSTIL.items():
        v.append((f'numero:{k}', 'json', _todos('numero', val, base)))
        v.append((f'numero:{k}', 'form', _todos('numero', val, base)))
    for k, val in DATA_HOSTIL.items():
        v.append((f'data:{k}', 'json', _todos('data', val, base)))
        v.append((f'data:{k}', 'form', _todos('data', val, base)))
    for k, val in TEXTO_HOSTIL.items():
        v.append((f'texto:{k}', 'json', _todos('texto', val, base)))
        v.append((f'texto:{k}', 'form', _todos('texto', val, base)))
    # Números de verdade no JSON (não texto): float gigante, inteiro enorme.
    v.append(('numero:json_float', 'json', _todos('numero', 1e308, base)))
    v.append(('numero:json_int', 'json', _todos('numero', 10 ** 30, base)))
    v.append(('numero:json_bool', 'json', _todos('numero', True, base)))
    # Texto que chega como número, lista ou objeto no JSON (as APIs da
    # passagem leem o JSON cru, sem passar pelo formulário).
    v.append(('texto:json_int', 'json', _todos('texto', 5, base)))
    v.append(('texto:json_lista', 'json', _todos('texto', ['a', 'b'], base)))
    v.append(('texto:json_objeto', 'json', _todos('texto', {'a': 1}, base)))
    v.append(('data:json_int', 'json', _todos('data', 20260230, base)))
    # As estruturas (listas e objetos que as APIs leem) com o tipo errado.
    for k, val in (('texto', 'abc'), ('numero', 5), ('objeto', {'a': {'b': 1}}),
                   ('lista_de_lixo', [1, 'x', None, [], {}]), ('nula', None)):
        v.append((f'estrutura:{k}', 'json', _todos('estrutura', val, base)))
    return v


# ── As rotas ──────────────────────────────────────────────────────────────

def _caminho(regra, ids, extra, ent=None, inteiro=None):
    valores = {}
    for arg in regra.arguments:
        if inteiro is not None and f'<int:{arg}>' in regra.rule:
            valores[arg] = inteiro
            continue
        if arg in extra:
            v = extra[arg]
        elif arg == 'anexo_id':
            v = ids['anexo_chamado'] if regra.endpoint.startswith(('chamados.', 'portal.')) \
                else ids['anexo_passagem']
        else:
            v = _valor_do_parametro(arg, ids, ent, regra.endpoint)
        assert v is not None, f'a varredura não sabe de onde vem <{arg}> de {regra.rule}'
        valores[arg] = v
    caminho = regra.rule
    for arg, v in valores.items():
        caminho = re.sub(r'<(?:[a-z]+:)?' + arg + '>', str(v), caminho)
    return caminho


def rotas(app_module, ids, extra, so_escrita=True, inteiro=None):
    """(endpoint, método, caminho) de cada rota do ``url_map``."""
    for regra in app_module.app.url_map.iter_rules():
        if regra.endpoint in FORA:
            continue
        metodos = sorted(regra.methods - {'HEAD', 'OPTIONS'})
        if so_escrita:
            metodos = [m for m in metodos if m != 'GET']
        if inteiro is not None and '<int:' not in regra.rule:
            continue
        for m in metodos:
            ent = 'setor' if 'entidade' in regra.arguments else None
            yield regra.endpoint, m, _caminho(regra, ids, extra, ent, inteiro)


# ── O registro do que deu errado ──────────────────────────────────────────

class Registro:
    def __init__(self, app):
        self.app = app
        self.achados = []
        self.pedidos = 0
        self.rotas = set()
        self._exc = None
        got_request_exception.connect(self._pegar, app)
        self._propagar = app.config.get('PROPAGATE_EXCEPTIONS')
        # Como na produção: a exceção vira o 500 da fábrica (core/erros.py),
        # e não um traceback no teste.
        app.config['PROPAGATE_EXCEPTIONS'] = False

    def fechar(self):
        got_request_exception.disconnect(self._pegar, self.app)
        self.app.config['PROPAGATE_EXCEPTIONS'] = self._propagar

    def _pegar(self, _app, exception, **_kw):
        quadros = [q for q in traceback.extract_tb(exception.__traceback__)
                   if '/facilities/' in q.filename]
        onde = (f'{os.path.relpath(quadros[-1].filename, RAIZ)}:{quadros[-1].lineno}'
                if quadros else '?')
        self._exc = f'{type(exception).__name__}: {str(exception)[:160]} @ {onde}'

    def chamar(self, c, perfil, endpoint, metodo, url, variante, tipo, corpo):
        self._exc = None
        self.pedidos += 1
        self.rotas.add((endpoint, metodo))
        chamar = getattr(c, metodo.lower())
        if tipo == 'json':
            r = chamar(url, data=json.dumps(corpo), content_type='application/json')
        elif tipo == 'form':
            r = chamar(url, data=corpo)
        elif tipo == 'cru':
            dados, ct = corpo
            r = chamar(url, data=dados, content_type=ct)
        else:                                                   # 'get'
            r = c.get(url)
        problema = None
        cookie = max((len(x) for x in r.headers.getlist('Set-Cookie')
                      if x.startswith('session=')), default=0)
        if r.status_code >= 500:
            problema = f'{r.status_code}'
        elif url.startswith('/api/v1/'):
            if not r.is_json:
                problema = f'{r.status_code} sem JSON ({r.mimetype})'
            elif r.status_code >= 400 and not (isinstance(r.get_json(silent=True), dict)
                                               and (r.get_json(silent=True).get('error')
                                                    # o armazenamento usa "erro"; a casca
                                                    # (frontend/src/api.ts) lê os dois
                                                    or r.get_json(silent=True).get('erro'))):
                problema = f'{r.status_code} JSON sem "error"'
        if not problema and cookie > 4093:
            # O navegador descarta cookie acima de 4 KB: a sessão cai.
            problema = f'cookie de sessão com {cookie} bytes'
        if problema:
            self.achados.append({'perfil': perfil, 'endpoint': endpoint, 'metodo': metodo,
                                 'url': url[:200], 'variante': variante, 'tipo': tipo,
                                 'problema': problema, 'excecao': self._exc})
        return r

    def novos(self):
        out = []
        for a in self.achados:
            classe = a['variante'].split(':')[0]
            if (a['endpoint'], classe) in CONHECIDOS or (a['endpoint'], '*') in CONHECIDOS:
                continue
            # E5 e E6 são de uma causa só (o texto vai cru ao Postgres) e a
            # correção é uma só, na entrada: qualquer rota que grava texto
            # cai neles — a assinatura da exceção basta.
            if any(x in (a['excecao'] or '') for x in ASSINATURAS_CONHECIDAS):
                continue
            out.append(a)
        return out

    def gravar(self, nome):
        destino = os.environ.get('AUDITORIA_RELATORIO')
        if not destino:
            return
        try:
            with open(destino) as f:
                tudo = json.load(f)
        except (OSError, ValueError):
            tudo = {}
        tudo[nome] = {'pedidos': self.pedidos, 'rotas': len(self.rotas),
                      'achados': self.achados}
        with open(destino, 'w') as f:
            json.dump(tudo, f, ensure_ascii=False, indent=1)


def _resumo(achados, n=25):
    vistos, linhas = set(), []
    for a in achados:
        chave = (a['endpoint'], a['variante'].split(':')[0], a['problema'][:3])
        if chave in vistos:
            continue
        vistos.add(chave)
        linhas.append(f"{a['perfil']} {a['metodo']} {a['endpoint']} [{a['variante']}/{a['tipo']}]"
                      f" → {a['problema']} {a['excecao'] or ''}")
    return '\n'.join(linhas[:n]) + (f'\n... e mais {len(linhas) - n}' if len(linhas) > n else '')


# ── A cena ────────────────────────────────────────────────────────────────

@pytest.fixture()
def cena_fuzz(app_module, local_a):  # noqa: F811
    from facilities.cadastros import montagem
    from app import User, db
    with app_module.app.app_context():
        alvo = fabrica.pessoa(app_module, 'alvo.fuzz@trino.com', 'encarregado',
                              locais=['Shopping Centro'])
        fabrica.pessoa(app_module, 'fuzz.encarregado@trino.com', 'encarregado',
                       locais=['Shopping Centro'])
        gestor = User.query.filter_by(email=ADMIN_EMAIL).one()
        _conv, token = montagem.criar_convite(gestor, {
            'nome': 'Convite da varredura', 'email': f'convite.{uuid.uuid4().hex[:10]}@trino.com',
            'role': 'encarregado', 'locais': [str(local_a['local'])]})
        db.session.commit()
    extra = {'uid': alvo, 'token': token}
    foto = _fotografar(app_module)
    yield local_a, extra
    _restaurar(app_module, foto)


# A varredura do administrador grava de verdade (renomeia e desliga locais,
# troca o perfil de pessoas...). O conftest só limpa o que é lançado: aqui a
# cena volta como estava para os testes seguintes (contratos e pessoas).
_TABELAS_DA_CENA = ('clients', 'users', 'estados')


def _fotografar(app_module):
    from sqlalchemy import MetaData, select
    from app import db
    with app_module.app.app_context():
        meta = MetaData()
        meta.reflect(bind=db.engine, only=_TABELAS_DA_CENA)
        return {t: [dict(r._mapping) for r in db.session.execute(select(meta.tables[t]))]
                for t in _TABELAS_DA_CENA}


def _restaurar(app_module, foto):
    from sqlalchemy import MetaData
    from app import db
    with app_module.app.app_context():
        db.session.rollback()
        meta = MetaData()
        meta.reflect(bind=db.engine, only=_TABELAS_DA_CENA)
        for t, linhas in foto.items():
            tab = meta.tables[t]
            for linha in linhas:
                db.session.execute(tab.update().where(tab.c.id == linha['id']).values(**linha))
            # O que a varredura criou (pessoas pelo convite aceito, locais
            # novos) fica, mas desligado e sem vínculo.
            antigos = [x['id'] for x in linhas]
            if t in ('clients', 'users'):
                db.session.execute(tab.update().where(tab.c.id.notin_(antigos))
                                   .values(is_active=False))
            if t == 'users':
                uc = MetaData()
                uc.reflect(bind=db.engine, only=('user_clients',))
                vinc = uc.tables['user_clients']
                db.session.execute(vinc.delete().where(vinc.c.user_id.notin_(antigos)))
        db.session.commit()


def _sessao_viva(c, quem, senha=fabrica.SENHA):
    """Se a varredura derrubou a sessão (ex.: desativou a pessoa), entra de
    novo — e conta: derrubar a própria sessão por entrada hostil é achado."""
    # Os recados (flash) das rotas antigas ficam no cookie até uma página
    # ser desenhada; a varredura não desenha nenhuma.
    with c.session_transaction() as sessao:
        sessao.pop('_flashes', None)
    if c.get('/api/v1/eu').status_code == 200:
        return c, False
    from app import User, db
    with c.application.app_context():
        u = User.query.filter_by(email=quem).first()
        u.is_active, u.failed_login_count, u.lockout_until = True, 0, None
        db.session.commit()
    c.post('/login', data={'email': quem, 'password': senha})
    return c, True


def _varrer_escrita(app_module, reg, c, perfil, quem, senha, ids, extra):
    base = _corpo_base(ids, perfil)
    for endpoint, metodo, url in list(rotas(app_module, ids, extra)):
        if endpoint.startswith('auth.'):
            continue                       # só no passe sem login
        for nome, tipo, corpo in variantes(base):
            with c.session_transaction() as sessao:
                sessao.pop('_flashes', None)
            reg.chamar(c, perfil, endpoint, metodo, url, nome, tipo, corpo)
        c, caiu = _sessao_viva(c, quem, senha)
        if caiu:
            reg.achados.append({'perfil': perfil, 'endpoint': endpoint, 'metodo': metodo,
                                'url': url, 'variante': 'sessao:caiu', 'tipo': '-',
                                'problema': 'a sessão de quem chamou caiu', 'excecao': None})


def test_escrita_hostil_como_encarregado_e_administrador(app_module, cena_fuzz):
    ids, extra = cena_fuzz
    reg = Registro(app_module.app)
    try:
        # O encarregado primeiro: o administrador pode desligar o local A.
        enc = fabrica.entrar(app_module, 'fuzz.encarregado@trino.com')
        _varrer_escrita(app_module, reg, enc, 'encarregado', 'fuzz.encarregado@trino.com',
                        fabrica.SENHA, ids, extra)
        adm = app_module.app.test_client()
        adm.post('/login', data={'email': ADMIN_EMAIL, 'password': TEST_ADMIN_PASSWORD})
        _varrer_escrita(app_module, reg, adm, 'administrador', ADMIN_EMAIL,
                        TEST_ADMIN_PASSWORD, ids, extra)
    finally:
        reg.fechar()
        reg.gravar('escrita')
    print(f'\nvarredura de escrita: {len(reg.rotas)} rota×método, {reg.pedidos} pedidos, '
          f'{len(reg.achados)} achados')
    novos = reg.novos()
    assert not novos, 'Entrada hostil quebrou o servidor:\n' + _resumo(novos)


def test_sem_login_nas_rotas_publicas(app_module, cena_fuzz):
    """Login, segunda etapa, convite, QR público (ocorrência, elogio): quem
    não entrou também não derruba o servidor."""
    ids, extra = cena_fuzz
    reg = Registro(app_module.app)
    base = _corpo_base(ids, 'anonimo')
    base.update(email='ninguem@trino.com', password='errada', senha='errada12345',
                confirma='errada12345', codigo='123456', estrelas='5')
    try:
        for endpoint, metodo, url in list(rotas(app_module, ids, extra)):
            c = app_module.app.test_client()
            for nome, tipo, corpo in variantes(base):
                reg.chamar(c, 'anonimo', endpoint, metodo, url, nome, tipo, corpo)
    finally:
        reg.fechar()
        reg.gravar('sem_login')
    novos = reg.novos()
    assert not novos, 'Entrada hostil (sem login) quebrou o servidor:\n' + _resumo(novos)


@pytest.mark.parametrize('inteiro', [2 ** 31, 10 ** 20], ids=['2^31', '10^20'])
def test_id_que_nao_cabe_na_coluna(app_module, cena_fuzz, inteiro):
    """``/chamados/99999999999999999999``: o conversor ``int`` do Flask aceita
    qualquer tamanho; o banco não (Postgres: integer vai até 2^31-1). Tem de
    ser 404, nunca 500 — em toda rota com id no caminho, ler ou gravar."""
    ids, extra = cena_fuzz
    reg = Registro(app_module.app)
    try:
        for perfil, c in (('administrador', None), ('encarregado', None)):
            if perfil == 'administrador':
                c = app_module.app.test_client()
                c.post('/login', data={'email': ADMIN_EMAIL, 'password': TEST_ADMIN_PASSWORD})
            else:
                c = fabrica.entrar(app_module, 'fuzz.encarregado@trino.com')
            for endpoint, metodo, url in list(rotas(app_module, ids, extra, so_escrita=False,
                                                    inteiro=inteiro)):
                if endpoint.startswith('auth.'):
                    continue
                tipo = 'get' if metodo == 'GET' else 'json'
                reg.chamar(c, perfil, endpoint, metodo, url, 'id:grande', tipo,
                           _corpo_base(ids, perfil))
    finally:
        reg.fechar()
        reg.gravar(f'id_{inteiro}')
    novos = reg.novos()
    assert not novos, f'Id {inteiro} no caminho quebrou o servidor:\n' + _resumo(novos)


CONSULTAS_HOSTIS = {'texto': 'abc', 'enorme': '9' * 30, 'negativo': '-1',
                    'data_impossivel': '2026-02-30', 'mes_impossivel': '2026-13'}
_RE_ARG = re.compile(r"request\.args\.get(?:list)?\(\s*'([a-z_][a-z0-9_]*)'"
                     r"|args\.get(?:list)?\(\s*'([a-z_][a-z0-9_]*)'")


def _nomes_da_consulta():
    nomes = {'client_id', 'local', 'mes', 'de', 'ate', 'periodo', 'pagina', 'visao', 'tipo'}
    for pasta, _d, arquivos in os.walk(os.path.join(RAIZ, 'facilities')):
        for a in arquivos:
            if a.endswith('.py'):
                with open(os.path.join(pasta, a), encoding='utf-8') as f:
                    for x, y in _RE_ARG.findall(f.read()):
                        nomes.add(x or y)
    return sorted(nomes)


def test_consulta_hostil_nas_telas_e_apis_de_leitura(app_module, cena_fuzz):
    """Toda rota de leitura com ``?client_id=abc``, ``?mes=2026-13``,
    ``?de=2026-02-30``, ``?pagina=-1``... (todas as chaves de consulta que o
    código lê, de uma vez)."""
    from urllib.parse import urlencode
    ids, extra = cena_fuzz
    nomes = _nomes_da_consulta()
    reg = Registro(app_module.app)
    try:
        for perfil in ('encarregado', 'administrador'):
            if perfil == 'administrador':
                c = app_module.app.test_client()
                c.post('/login', data={'email': ADMIN_EMAIL, 'password': TEST_ADMIN_PASSWORD})
            else:
                c = fabrica.entrar(app_module, 'fuzz.encarregado@trino.com')
            for regra in app_module.app.url_map.iter_rules():
                if 'GET' not in regra.methods or regra.endpoint in FORA \
                        or regra.endpoint.startswith('auth.'):
                    continue
                ent = 'setor' if 'entidade' in regra.arguments else None
                url = _caminho(regra, ids, extra, ent)
                for k, val in CONSULTAS_HOSTIS.items():
                    q = urlencode({n: val for n in nomes})
                    reg.chamar(c, perfil, regra.endpoint, 'GET', f'{url}?{q}', f'consulta:{k}',
                               'get', None)
    finally:
        reg.fechar()
        reg.gravar('consulta')
    novos = reg.novos()
    assert not novos, 'Consulta hostil quebrou o servidor:\n' + _resumo(novos)
