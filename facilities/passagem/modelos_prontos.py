"""Modelos prontos de passagem de turno: limpeza, portaria e manutenção predial.

Ponto de partida, não camisa de força: o gestor ajusta perguntas, turnos e
tipos de ocorrência na tela de configuração depois. O que vem aqui é o que a
rotina de facilities pede em quase todo contrato — e evita que o primeiro
turno do contrato novo comece com um modelo em branco.

As perguntas ``sim_nao`` são a ROTINA (contam para a aderência do turno); as
de número e texto só registram. Obrigatória é o que não pode faltar em turno
nenhum.

``semear`` é idempotente por nome: rodar de novo não duplica área nem modelo.
"""
import json
import unicodedata

from facilities.extensions import db
from facilities.passagem.models import DiarioArea, DiarioConfiguracao
from facilities.passagem.rotas import separar_perguntas

TURNOS_12x36 = ['Diurno', 'Noturno']
TURNOS_3 = ['1º Turno', '2º Turno', '3º Turno']
TURNOS_COMERCIAL = ['Manhã', 'Tarde']


def _p(nome, tipo='sim_nao', obrigatorio=True, opcoes=None):
    item = {'nome': nome, 'tipo': tipo, 'obrigatorio': obrigatorio}
    if opcoes:
        item['opcoes'] = list(opcoes)
    return item


SEMAFORO = ['🟢 Normal', '🟡 Atenção', '🔴 Crítico']

MODELOS = {
    'limpeza': {
        'area': 'Limpeza e conservação',
        'nome': 'Limpeza e conservação — rotina do turno',
        'descricao': 'Rotina dos postos de limpeza: sanitários, áreas comuns, '
                     'resíduos e reposição de insumos.',
        'turnos': TURNOS_3,
        'perguntas': [
            _p('Sanitários limpos e abastecidos (papel, sabonete, álcool)'),
            _p('Áreas comuns e circulação limpas'),
            _p('Lixeiras esvaziadas e resíduos levados ao abrigo'),
            _p('Coleta seletiva separada corretamente'),
            _p('Copa / refeitório higienizado'),
            _p('Vidros e superfícies de contato higienizados', obrigatorio=False),
            _p('Equipe completa no posto (EPI em uso)'),
            _p('Faltas ou atrasos na equipe', 'numero', obrigatorio=False),
            _p('Insumos que estão acabando', 'texto', obrigatorio=False),
            _p('Situação geral do turno', 'escolha', obrigatorio=True, opcoes=SEMAFORO),
        ],
        'tipos_ocorrencia': ['Falta de insumo', 'Vazamento ou piso molhado', 'Dano ao patrimônio',
                             'Reclamação de usuário', 'Falta de colaborador',
                             'Acidente ou incidente'],
    },
    'portaria': {
        'area': 'Portaria e segurança',
        'nome': 'Portaria e segurança — livro do turno',
        'descricao': 'Controle de acesso, rondas, chaves e equipamentos de '
                     'segurança — o livro de ocorrências da portaria.',
        'turnos': TURNOS_12x36,
        'perguntas': [
            _p('Rondas realizadas nos horários previstos'),
            _p('Controle de acesso registrado (visitantes e prestadores)'),
            _p('Chaves conferidas e no quadro'),
            _p('CFTV e gravação funcionando'),
            _p('Rádios e lanternas carregados'),
            _p('Portões, cancelas e alarmes testados'),
            _p('Iluminação externa funcionando', obrigatorio=False),
            _p('Visitantes no turno', 'numero', obrigatorio=False),
            _p('Encomendas recebidas e pendentes', 'texto', obrigatorio=False),
            _p('Situação geral do turno', 'escolha', obrigatorio=True, opcoes=SEMAFORO),
        ],
        'tipos_ocorrencia': ['Acesso não autorizado', 'Alarme disparado', 'Objeto achado ou perdido',
                             'Dano ao patrimônio', 'Equipamento de segurança com defeito',
                             'Atendimento de emergência'],
    },
    'manutencao': {
        'area': 'Manutenção predial',
        'nome': 'Manutenção predial — rotina do turno',
        'descricao': 'Inspeção dos sistemas do prédio e acompanhamento dos '
                     'chamados do turno.',
        'turnos': TURNOS_COMERCIAL,
        'perguntas': [
            _p('Inspeção do quadro elétrico e iluminação de emergência'),
            _p('Bombas, caixas d’água e reservatórios verificados'),
            _p('Ar-condicionado sem alarme'),
            _p('Elevadores operando (sem chamado aberto na empresa)'),
            _p('Gerador e no-break testados', obrigatorio=False),
            _p('Chamados do turno atualizados no sistema'),
            _p('Ferramentas e materiais guardados'),
            _p('Leitura do hidrômetro', 'numero', obrigatorio=False),
            _p('Materiais a comprar', 'texto', obrigatorio=False),
            _p('Situação geral do turno', 'escolha', obrigatorio=True, opcoes=SEMAFORO),
        ],
        'tipos_ocorrencia': ['Falta de energia', 'Falta de água', 'Vazamento',
                             'Equipamento parado', 'Serviço de terceiro', 'Risco à segurança'],
    },
}


def codigo_de(nome):
    """O mesmo código que a tela de configuração gera (``codigoDe`` no JS)."""
    s = unicodedata.normalize('NFD', str(nome).strip().lower())
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    saida, ultimo_sublinhado = [], False
    for ch in s:
        if ch.isascii() and ch.isalnum():
            saida.append(ch)
            ultimo_sublinhado = False
        elif not ultimo_sublinhado:
            saida.append('_')
            ultimo_sublinhado = True
    return ''.join(saida).strip('_')


def semear(client_id, servicos=None, criado_por=None):
    """Cria as áreas e os modelos prontos do contrato → nomes dos modelos criados.

    O commit é de quem chama. Área ou modelo com o mesmo nome já existente
    no contrato é mantido como está (rodar de novo não duplica nem apaga o
    que o gestor ajustou).
    """
    criados = []
    for chave in (servicos or MODELOS.keys()):
        m = MODELOS[chave]
        area = DiarioArea.query.filter_by(client_id=client_id, nome=m['area']).first()
        if area is None:
            area = DiarioArea(client_id=client_id, nome=m['area'], ativo=True,
                              created_by=criado_por)
            db.session.add(area)
            db.session.flush()
        if DiarioConfiguracao.query.filter_by(client_id=client_id, nome=m['nome']).first():
            continue
        perguntas = [dict(p, codigo=codigo_de(p['nome'])) for p in m['perguntas']]
        atividades, campos = separar_perguntas(perguntas)
        db.session.add(DiarioConfiguracao(
            client_id=client_id, area_id=area.id, nome=m['nome'], descricao=m['descricao'],
            turnos_json=json.dumps([{'nome': t} for t in m['turnos']], ensure_ascii=False),
            atividades_json=json.dumps(atividades, ensure_ascii=False),
            campos_json=json.dumps(campos, ensure_ascii=False),
            tipos_ocorrencia_json=json.dumps([{'nome': t} for t in m['tipos_ocorrencia']],
                                             ensure_ascii=False),
            ativo=True, created_by=criado_por))
        criados.append(m['nome'])
    return criados
