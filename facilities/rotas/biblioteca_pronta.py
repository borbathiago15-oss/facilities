"""Modelos prontos de limpeza para a biblioteca da Trino (decisão do dono,
18/10/2026): banheiro, copa, recepção/escritório, vestiário, área externa e
(19/10/2026) piso operacional de armazém. E as ROTAS prontas (19/10/2026):
escritório corporativo e centro de distribuição.

Cada pergunta traz o "como fazer" — o que o ASG lê embaixo da pergunta, no
celular — em linguagem do posto. O administrador instala uma vez (botão na
biblioteca ou ``flask --app facilities semear-checklists``); cada local copia
e ajusta. Instalar de novo não duplica: modelo com o mesmo nome é pulado.
"""
from facilities.extensions import db
from facilities.rotas.models import ChecklistModelo

_DANO = {'codigo': 'dano', 'texto': 'Viu algum vazamento, dano ou lâmpada queimada?',
         'tipo': 'sim_nao',
         'obrigatorio': True, 'problema_se': 'sim',
         'como_fazer': 'Torneira pingando, descarga com defeito, louça ou porta quebrada, '
                       'lâmpada queimada, infiltração. Se sim, conte onde na pergunta abaixo.'}
_ONDE = {'texto': 'O que e onde?', 'tipo': 'texto', 'obrigatorio': True,
         'mostrar_se': 'dano=sim',
         'como_fazer': 'Ex.: "Torneira da 2ª pia pingando". Vira chamado para a manutenção.'}

MODELOS = [
    {'nome': 'Limpeza de banheiro — padrão Trino',
     'descricao': 'Rotina de limpeza e reposição do banheiro. Use luvas e a placa de piso '
                  'molhado. Comece pelo lixo e termine pelo piso.',
     'exige_foto_depois': True,
     'itens': [
         {'texto': 'Lixeiras esvaziadas e com saco novo?', 'tipo': 'sim_nao', 'obrigatorio': True,
          'problema_se': 'nao',
          'como_fazer': 'Amarre o saco, leve ao abrigo de lixo e coloque um saco novo do '
                        'tamanho da lixeira.'},
         {'texto': 'Papel higiênico, papel-toalha e sabonete repostos?', 'tipo': 'sim_nao',
          'obrigatorio': True, 'problema_se': 'nao',
          'como_fazer': 'Deixe 2 rolos de papel higiênico por cabine, o papel-toalha cheio e '
                        'o sabonete acima da metade. Faltou material? Peça pelo app.'},
         {'texto': 'Pias, espelhos e bancadas', 'tipo': 'conforme', 'obrigatorio': True,
          'como_fazer': 'Pano úmido com detergente neutro na pia e na bancada; seque o espelho '
                        'com pano de microfibra, sem manchas.'},
         {'texto': 'Vasos sanitários e mictórios', 'tipo': 'conforme', 'obrigatorio': True,
          'como_fazer': 'Escova com desinfetante por dentro; pano com desinfetante por fora, '
                        'no assento e na tampa. Dê descarga no fim.'},
         {'texto': 'Piso limpo e seco', 'tipo': 'conforme', 'obrigatorio': True,
          'como_fazer': 'Varra, passe pano com desinfetante e deixe a placa de piso molhado '
                        'até secar.'},
         _DANO, _ONDE]},
    {'nome': 'Limpeza de copa e cozinha — padrão Trino',
     'descricao': 'Rotina da copa: lixo, louça, bancadas, eletrodomésticos por fora e piso.',
     'exige_foto_depois': True,
     'itens': [
         {'texto': 'Lixo orgânico e reciclável retirados?', 'tipo': 'sim_nao', 'obrigatorio': True,
          'problema_se': 'nao',
          'como_fazer': 'Separe orgânico e reciclável. Saco novo em cada lixeira.'},
         {'texto': 'Pia sem louça acumulada e escorredor organizado', 'tipo': 'conforme',
          'obrigatorio': True,
          'como_fazer': 'Lave o que estiver na pia (se for rotina do contrato) e deixe a cuba '
                        'limpa e seca.'},
         {'texto': 'Bancadas e mesas', 'tipo': 'conforme', 'obrigatorio': True,
          'como_fazer': 'Retire migalhas e passe pano com detergente neutro; depois álcool 70%.'},
         {'texto': 'Micro-ondas, geladeira e cafeteira por fora', 'tipo': 'conforme',
          'obrigatorio': True,
          'como_fazer': 'Pano úmido nas portas e puxadores. Por dentro só no dia programado.'},
         {'texto': 'Sabão, esponja e papel-toalha repostos?', 'tipo': 'sim_nao',
          'obrigatorio': True, 'problema_se': 'nao'},
         {'texto': 'Piso limpo e seco', 'tipo': 'conforme', 'obrigatorio': True,
          'como_fazer': 'Varra, passe pano com desengordurante e deixe a placa até secar.'},
         _DANO, _ONDE]},
    {'nome': 'Limpeza de recepção e escritório — padrão Trino',
     'descricao': 'Rotina das áreas de atendimento e trabalho: lixo, mesas, vidros e piso.',
     'itens': [
         {'texto': 'Lixeiras esvaziadas?', 'tipo': 'sim_nao', 'obrigatorio': True,
          'problema_se': 'nao'},
         {'texto': 'Balcão, mesas e cadeiras', 'tipo': 'conforme', 'obrigatorio': True,
          'como_fazer': 'Pano úmido com detergente neutro. Não mexa em papéis e objetos das '
                        'pessoas.'},
         {'texto': 'Vidros, portas e maçanetas', 'tipo': 'conforme', 'obrigatorio': True,
          'como_fazer': 'Limpa-vidros com pano de microfibra; álcool 70% nas maçanetas.'},
         {'texto': 'Piso e tapetes', 'tipo': 'conforme', 'obrigatorio': True,
          'como_fazer': 'Aspire os tapetes; varra e passe pano no piso.'},
         _DANO, _ONDE]},
    {'nome': 'Limpeza de vestiário — padrão Trino',
     'descricao': 'Rotina do vestiário: como o banheiro, mais bancos, armários e chuveiros.',
     'exige_foto_depois': True,
     'itens': [
         {'texto': 'Lixeiras esvaziadas e com saco novo?', 'tipo': 'sim_nao', 'obrigatorio': True,
          'problema_se': 'nao'},
         {'texto': 'Chuveiros e ralos', 'tipo': 'conforme', 'obrigatorio': True,
          'como_fazer': 'Escove o box com desinfetante e tire cabelo e sujeira do ralo.'},
         {'texto': 'Bancos e portas dos armários por fora', 'tipo': 'conforme',
          'obrigatorio': True, 'como_fazer': 'Pano úmido com desinfetante.'},
         {'texto': 'Vasos, pias e espelhos', 'tipo': 'conforme', 'obrigatorio': True},
         {'texto': 'Piso limpo e seco', 'tipo': 'conforme', 'obrigatorio': True,
          'como_fazer': 'Puxe a água com rodo, passe pano e deixe a placa até secar.'},
         _DANO, _ONDE]},
    {'nome': 'Área externa e calçada — padrão Trino',
     'descricao': 'Rotina da área externa: varrição, lixo, lixeiras e riscos.',
     'itens': [
         {'texto': 'Calçada e entrada varridas?', 'tipo': 'sim_nao', 'obrigatorio': True,
          'problema_se': 'nao'},
         {'texto': 'Bitucas, papéis e folhas recolhidos?', 'tipo': 'sim_nao', 'obrigatorio': True,
          'problema_se': 'nao'},
         {'texto': 'Lixeiras externas', 'tipo': 'conforme', 'obrigatorio': True,
          'como_fazer': 'Esvazie e troque o saco; lixeira cheia atrai bicho.'},
         {'texto': 'Canteiros e jardins sem lixo', 'tipo': 'conforme', 'obrigatorio': True},
         {'codigo': 'risco',
          'texto': 'Viu algum risco (buraco, piso solto, luz apagada, fio exposto)?',
          'tipo': 'sim_nao', 'obrigatorio': True, 'problema_se': 'sim',
          'como_fazer': 'Se sim, isole com cone ou fita se puder e conte onde abaixo.'},
         {'texto': 'O que e onde?', 'tipo': 'texto', 'obrigatorio': True,
          'mostrar_se': 'risco=sim'}]},
]


MODELOS.append(
    {'nome': 'Piso operacional, docas e armazém — padrão Trino',
     'descricao': 'Rotina do piso de operação: corredores livres, piso sem derramamento e '
                  'lixo no lugar. Atenção às empilhadeiras: use colete e não entre em '
                  'corredor com máquina operando.',
     'exige_foto_depois': True,
     'itens': [
         {'texto': 'Corredores e faixas de pedestre livres?', 'tipo': 'sim_nao',
          'obrigatorio': True, 'problema_se': 'nao',
          'como_fazer': 'Nada de palete, caixa ou filme no corredor nem sobre a faixa '
                        'amarela. Se tiver, avise o líder do turno.'},
         {'texto': 'Piso sem óleo, água ou produto derramado', 'tipo': 'conforme',
          'obrigatorio': True,
          'como_fazer': 'Derramamento: isole com cone, use o absorvente do kit e só depois '
                        'lave. Óleo nunca vai para o ralo.'},
         {'texto': 'Filme, papelão e lixo nos coletores certos', 'tipo': 'conforme',
          'obrigatorio': True,
          'como_fazer': 'Papelão dobrado no coletor de papelão; filme stretch no de plástico; '
                        'o resto no lixo comum.'},
         {'texto': 'Docas varridas e niveladoras sem detritos', 'tipo': 'conforme',
          'obrigatorio': True,
          'como_fazer': 'Varra a doca só com o caminhão fora ou a porta fechada.'},
         {'codigo': 'risco',
          'texto': 'Viu algum risco (palete quebrado, piso solto, luz apagada, vazamento)?',
          'tipo': 'sim_nao', 'obrigatorio': True, 'problema_se': 'sim',
          'como_fazer': 'Se sim, isole com cone e conte onde abaixo.'},
         {'texto': 'O que e onde?', 'tipo': 'texto', 'obrigatorio': True,
          'mostrar_se': 'risco=sim'}]})

_BANHEIRO = 'Limpeza de banheiro — padrão Trino'
_COPA = 'Limpeza de copa e cozinha — padrão Trino'
_RECEPCAO = 'Limpeza de recepção e escritório — padrão Trino'
_VESTIARIO = 'Limpeza de vestiário — padrão Trino'
_EXTERNA = 'Área externa e calçada — padrão Trino'
_PISO = 'Piso operacional, docas e armazém — padrão Trino'

# Rotas prontas. As frequências são o ponto de partida usual de mercado e o
# administrador ajusta na tela; a referência legal é a NR-24 (instalações
# sanitárias, vestiários e refeitórios em permanente estado de limpeza) e,
# para refeitório e copa, a RDC 216/2004 da ANVISA (boas práticas em serviços
# de alimentação).
ROTAS = [
    {'nome': 'Escritório corporativo — turno diurno', 'segmento': 'Escritório / corporativo',
     'descricao': 'Banheiros a cada 2 horas no expediente, copa depois de cada pico (manhã, '
                  'almoço e tarde), recepção na abertura e depois do almoço, salas uma vez '
                  'ao dia antes da chegada das pessoas.',
     'turno': 'Diurno', 'hora_inicio': '06:00', 'hora_fim': '18:00', 'tolerancia_min': 30,
     'dias_semana': '12345',
     'itens': [
         ('Administrativo', 'Banheiro masculino', _BANHEIRO, '08:00, 10:00, 12:00, 14:00, 16:00', 1),
         ('Administrativo', 'Banheiro feminino', _BANHEIRO, '08:00, 10:00, 12:00, 14:00, 16:00', 1),
         ('Administrativo', 'Copa', _COPA, '09:30, 13:30, 16:30', 1),
         ('Administrativo', 'Recepção', _RECEPCAO, '07:30, 13:00', 1),
         ('Administrativo', 'Salas e estações de trabalho', _RECEPCAO, '07:00', 1),
         ('Área externa', 'Entrada e calçada', _EXTERNA, '07:00', 1)]},
    {'nome': 'Centro de distribuição — turno A (manhã)',
     'segmento': 'Centro de distribuição / galpão',
     'descricao': 'Vestiários na troca de turno e no meio dele, banheiros da operação a cada '
                  '2 horas, refeitório antes e depois do almoço, piso e docas duas vezes no '
                  'turno, administrativo na abertura.',
     'turno': 'Turno A', 'hora_inicio': '06:00', 'hora_fim': '14:20', 'tolerancia_min': 30,
     'dias_semana': '123456',
     'itens': [
         ('Apoio', 'Vestiário masculino', _VESTIARIO, '06:30, 10:00, 13:45', 1),
         ('Apoio', 'Vestiário feminino', _VESTIARIO, '06:30, 10:00, 13:45', 1),
         ('Operação', 'Banheiro da operação', _BANHEIRO, '07:00, 09:00, 11:00, 13:00', 2),
         ('Apoio', 'Refeitório', _COPA, '10:30, 13:00', 1),
         ('Operação', 'Armazém e docas', _PISO, '08:00, 12:00', 1),
         ('Administrativo', 'Escritório administrativo', _RECEPCAO, '07:00', 1),
         ('Área externa', 'Portaria e pátio', _EXTERNA, '08:30', 1)]},
]


def semear_rotas():
    """Instala as rotas prontas que ainda não existem (precisa dos checklists
    da biblioteca). → nomes criados."""
    from facilities.rotas import rotas_prontas
    from facilities.rotas.models import RotaModelo
    criados = []
    for dados in ROTAS:
        if RotaModelo.query.filter_by(nome=dados['nome']).first():
            continue
        linhas = []
        for setor, ambiente, checklist, horarios, qtd in dados['itens']:
            m = ChecklistModelo.query.filter(ChecklistModelo.client_id.is_(None),
                                             ChecklistModelo.nome == checklist).first()
            linhas.append({'setor': setor, 'ambiente': ambiente,
                           'checklist_id': m.id if m else '', 'horarios': horarios,
                           'quantidade': qtd})
        rotas_prontas.salvar_modelo(None, dados, linhas)
        criados.append(dados['nome'])
    return criados


def semear(autor=None):
    """Instala na biblioteca os modelos que ainda não existem. → nomes criados."""
    from facilities.rotas import servico
    criados = []
    for dados in MODELOS:
        # Nome exato: o lower() do SQLite não conhece acento ("Área").
        if ChecklistModelo.query.filter(ChecklistModelo.client_id.is_(None),
                                        ChecklistModelo.nome == dados['nome']).first():
            continue
        m = servico.criar_modelo(None, {'nome': dados['nome'], 'descricao': dados['descricao']},
                                 autor)
        itens = servico.normalizar_itens(dados['itens'])
        servico.publicar(m, itens, {'descricao': dados['descricao'],
                                    'exige_foto_depois': dados.get('exige_foto_depois')}, autor)
        criados.append(m.nome)
    db.session.flush()
    return criados + semear_rotas()
