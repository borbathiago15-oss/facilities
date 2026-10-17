"""Passagem de Turno: o turno, as pendências e as ocorrências.

As rotas ficam aqui; as CONTAS ficam em ``facilities.passagem.analitico``,
que não importa Flask. A separação é o que permite testar cada fórmula (aderência,
Pareto, burn-down) sem subir tela nem sessão, e deixa num lugar só o custo de
banco do dashboard.

**O nome.** Nasceu "Diário Operacional", que descrevia o formato e não o
trabalho: ninguém na operação diz "vou preencher o diário", diz "vou passar o
turno". O módulo chama-se pelo gesto que ele registra, como a Torre de Comando
um nível acima. O pacote e as tabelas continuam ``diario_*`` — é o mesmo
módulo do Trino Intelligence, de onde veio, e os nomes iguais deixam trazer
correções de lá para cá sem tradução.
"""
import json
import re
from datetime import date, datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from facilities import tempo
from facilities.extensions import db
from facilities.passagem import analitico
from facilities.core.acesso import module_required, permissao_requerida
from facilities.passagem.models import (
    DiarioConfiguracao, DiarioTurno, DiarioPendencia, DiarioOcorrencia,
    DiarioAnexo, DiarioPendenciaEvento, DiarioArea,
    OCORRENCIA_NORMAL, OCORRENCIA_CRITICA,
)

bp = Blueprint('diario_operacional', __name__, url_prefix='/passagem-de-turno')
MODULO = 'diario_operacional'

# O valor da opção "Geral (sem área)" no seletor de área da nova passagem:
# os modelos sem área ativa num contrato que já tem áreas (ver ``turno``).
# Texto, e não número, para nunca colidir com o id de uma área cadastrada.
AREA_SEM_CADASTRO = 'sem-area'

MESES_LONGOS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
                'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro',
                'Dezembro']


def _json(text, default):
    try:
        value = json.loads(text or '')
        return value
    except Exception:
        return default


def _clientes_visiveis():
    from facilities.core.acesso import clientes_visiveis as helper
    return helper()


def _client_allowed(client_id):
    from facilities.core.acesso import require_client
    require_client(client_id)


def perguntas_do_modelo(atividades, campos):
    """As duas listas do modelo viram UMA — as perguntas do turno.

    O banco guarda dois JSON separados desde a Fase 1: ``atividades_json``
    (a rotina, que se responde sim/não e conta para a aderência) e
    ``campos_json`` (número ou texto, que só se registra). Isso é uma
    distinção do MOTOR, não de quem preenche: para o encarregado é tudo
    "a pergunta que eu respondo no fim do turno", e é assim que a tela passa
    a mostrar.

    A distinção continua existindo por baixo porque ela tem consequência —
    "quantos pedidos separou" não é cumprido nem descumprido, e por isso não
    entra na conta da aderência. O que muda é que a ORDEM passa a ser do
    modelo, não do acaso de estar numa lista ou na outra: ``ordem`` viaja
    dentro do próprio JSON, sem coluna nova.

    Devolve dicionários com ``tipo``: ``sim_nao`` para a rotina, e
    ``numero``/``texto``/``texto_longo``/``escolha`` para o resto. A
    ``escolha`` carrega junto as suas ``opcoes``.
    """
    juntas = []
    for i, a in enumerate(atividades or []):
        if not isinstance(a, dict):
            a = {'nome': str(a)}
        juntas.append({
            'nome': a.get('nome') or a.get('codigo') or '',
            'codigo': a.get('codigo') or a.get('nome') or '',
            'tipo': 'sim_nao',
            'obrigatorio': a.get('obrigatorio') is not False,
            'ordem': a.get('ordem', i),
        })
    base = len(juntas)
    for i, c in enumerate(campos or []):
        if not isinstance(c, dict):
            continue
        juntas.append({
            'nome': c.get('nome') or c.get('codigo') or '',
            'codigo': c.get('codigo') or c.get('nome') or '',
            'tipo': c.get('tipo') or 'texto',
            'obrigatorio': c.get('obrigatorio') is True,
            # Só a `escolha` usa, mas viaja sempre para a tela não precisar
            # perguntar o tipo antes de ler.
            'opcoes': [o for o in (c.get('opcoes') or []) if str(o).strip()],
            'ordem': c.get('ordem', base + i),
        })
    juntas.sort(key=lambda p: (p['ordem'], p['nome']))
    return [p for p in juntas if p['nome']]


# Os tipos de resposta que a tela do encarregado sabe desenhar. ``sim_nao`` é
# a rotina (vai para ``atividades_json`` e conta na aderência); o resto só
# registra (``campos_json``).
TIPOS_DE_PERGUNTA = ('sim_nao', 'numero', 'texto', 'texto_longo', 'escolha')


class PerguntaInvalida(ValueError):
    """Pergunta com um tipo de resposta que ninguém sabe desenhar → 400."""


def separar_perguntas(perguntas, anteriores=None):
    """O caminho de volta: a lista única → as duas do banco, com a ordem.

    Guardar a ordem dentro de cada item é o que permite intercalar rotina e
    campo na tela sem uma coluna nova (e sem migração para uma mudança que é
    de apresentação).

    **Tipo vazio ou desconhecido não vira Sim/Não.** Era o que acontecia: o
    editor não oferecia "escolha", o seletor de tipo ficava em branco, e
    salvar o modelo sem mexer em nada transformava o semáforo da "Situação
    geral do turno" numa rotina Sim/Não obrigatória — sem as opções, e
    passando a pesar na aderência. Agora, com ``anteriores`` (as perguntas
    que o modelo já tinha, por código), a pergunta que já existia guarda o
    tipo e as opções dela; a pergunta nova com tipo inválido é recusada
    (``PerguntaInvalida``). Só a pergunta SEM a chave ``tipo`` continua
    sendo Sim/Não — é o formato antigo, de quem nunca mandou tipo.
    """
    anteriores = anteriores or {}
    atividades, campos = [], []
    for i, p in enumerate(perguntas or []):
        if not isinstance(p, dict):
            continue
        nome = (p.get('nome') or '').strip()
        if not nome:
            continue
        codigo = p.get('codigo') or nome
        item = {'nome': nome, 'codigo': codigo, 'ordem': i}
        antes = anteriores.get(codigo)
        tipo = p.get('tipo', 'sim_nao')
        tipo = tipo.strip() if isinstance(tipo, str) else ''
        if tipo not in TIPOS_DE_PERGUNTA:
            if antes is None:
                raise PerguntaInvalida(
                    f'A pergunta "{nome}" está sem um tipo de resposta válido. '
                    f'Escolha Sim / Não, Número, Texto, Texto longo ou Escolha.')
            tipo = antes['tipo']
        if tipo == 'sim_nao':
            item['obrigatorio'] = p.get('obrigatorio') is not False
            atividades.append(item)
        else:
            item['tipo'] = tipo
            item['obrigatorio'] = p.get('obrigatorio') is True
            if item['tipo'] == 'escolha':
                # O semáforo do recado de WhatsApp — 🟢 NORMAL, 🟡 ATENÇÃO,
                # 🔴 CRÍTICO — só vira dado se as opções forem do MODELO.
                # Escolha sem opção não é escolha: vira texto, para a tela
                # não desenhar um seletor vazio. Quem não manda ``opcoes``
                # (a tela antiga, ainda guardada no navegador) não as apaga.
                brutas = (p['opcoes'] if 'opcoes' in p
                          else (antes or {}).get('opcoes'))
                if isinstance(brutas, str):
                    brutas = brutas.splitlines()
                opcoes = [str(o).strip() for o in (brutas or [])
                          if str(o).strip()]
                if opcoes:
                    item['opcoes'] = opcoes
                else:
                    item['tipo'] = 'texto'
            campos.append(item)
    return atividades, campos


def _config_payload(cfg):
    atividades = _json(cfg.atividades_json, [])
    campos = _json(cfg.campos_json, [])
    return {
        'id': cfg.id,
        'client_id': cfg.client_id,
        'nome': cfg.nome,
        'area_id': cfg.area_id,
        'descricao': cfg.descricao or '',
        'turnos': _json(cfg.turnos_json, []),
        # Mantidas para quem já lê por aqui; a tela usa `perguntas`.
        'campos': campos,
        'atividades': atividades,
        'perguntas': perguntas_do_modelo(atividades, campos),
        'tipos_ocorrencia': _json(cfg.tipos_ocorrencia_json, []),
        'ativo': bool(cfg.ativo),
    }


def _turno_payload(t):
    return {
        'id': t.id,
        'client_id': t.client_id,
        'configuracao_id': t.configuracao_id,
        'data_turno': t.data_turno.isoformat(),
        'turno': t.turno,
        'status': t.status,
        'dados': _json(t.dados_json, {}),
        'observacao': t.observacao or '',
        'created_by': t.created_by,
        'created_at': t.created_at.isoformat() if t.created_at else None,
        'submitted_at': t.submitted_at.isoformat() if t.submitted_at else None,
    }


def _data_arg(nome):
    """``?de=2026-09-01`` → ``date``. Texto inválido vira None, não erro 500."""
    bruto = (request.args.get(nome) or '').strip()
    if not bruto:
        return None
    try:
        return date.fromisoformat(bruto[:10])
    except ValueError:
        return None


@bp.get('/')
@login_required
@module_required(MODULO)
def index():
    """A torre de controle da operação: recorte no topo, indicadores abaixo.

    O recorte (cliente, período e turno) vem da query string e atravessa
    TUDO o que a tela mostra — cartões, gráficos e listas saem da mesma
    chamada a ``analitico.painel``, para que nenhum número da tela discorde
    de outro por ter sido calculado com uma janela diferente.
    """
    clients = _clientes_visiveis()
    client_id = request.args.get('client_id', type=int)
    if client_id and client_id not in [c.id for c in clients]:
        client_id = None
    if not client_id and clients:
        client_id = clients[0].id

    periodo = (request.args.get('periodo') or '7d').strip()
    if periodo not in analitico.PERIODOS:
        periodo = '7d'
    turno = (request.args.get('turno') or 'todos').strip() or 'todos'
    # Área do contrato (Expedição, Almoxarifado, CD...). Área que não é DESTE
    # contrato cai em "todas" — o filtro não pode esvaziar a tela por causa
    # de uma URL velha, nem vazar a área de outro cliente por um id chutado.
    area_id = request.args.get('area_id', type=int) or analitico.TODAS_AS_AREAS
    if client_id and area_id != analitico.TODAS_AS_AREAS:
        if area_id not in [a.id for a in analitico.areas_do_contrato(client_id)]:
            area_id = analitico.TODAS_AS_AREAS

    dados = None
    turnos = []
    if client_id:
        dados = analitico.painel(client_id, periodo=periodo,
                                 de=_data_arg('de'), ate=_data_arg('ate'),
                                 turno=turno, area_id=area_id)
        # Os últimos turnos lançados continuam na tela: o Encarregado abre o
        # dashboard para conferir se a passagem dele entrou.
        q = (DiarioTurno.query
             .filter(DiarioTurno.client_id == client_id,
                     DiarioTurno.data_turno >= dados['inicio'],
                     DiarioTurno.data_turno <= dados['fim']))
        ids_area = analitico._configs_da_area(client_id, area_id)
        if ids_area is not None:
            q = q.filter(DiarioTurno.configuracao_id.in_(ids_area or [0]))
        lancados = (q.order_by(DiarioTurno.data_turno.desc(),
                               DiarioTurno.id.desc()).limit(30).all())
        # De qual ÁREA é cada passagem da lista — em duas consultas fixas,
        # senão seriam 30 idas ao banco para escrever 30 rótulos.
        por_cfg = dict(DiarioConfiguracao.query
                       .with_entities(DiarioConfiguracao.id,
                                      DiarioConfiguracao.area_id)
                       .filter(DiarioConfiguracao.id.in_(
                           [t.configuracao_id for t in lancados] or [0])).all())
        nomes_de_area = dict(DiarioArea.query
                             .with_entities(DiarioArea.id, DiarioArea.nome)
                             .filter(DiarioArea.id.in_(
                                 [a for a in por_cfg.values() if a] or [0])).all())
        turnos = [{'t': t,
                   'area': nomes_de_area.get(por_cfg.get(t.configuracao_id)) or ''}
                  for t in lancados]

    # As ocorrências da lista que JÁ viraram chamado: a linha troca "Abrir
    # chamado" por "Ver OS-00012 (Em atendimento)". O gestor relê a lista
    # todo dia e precisa saber, sem clicar, o que já está com a manutenção —
    # o botão igual em toda linha levava, no segundo clique, a uma OS que
    # ele nem sabia que existia. Uma consulta para a lista inteira.
    pode_ver_chamado = current_user.can_view('chamados')
    chamados_abertos = {}
    if dados and dados['ocorrencias'] and pode_ver_chamado:
        chamados_abertos = _chamados_das_ocorrencias([o.id for o in dados['ocorrencias']])

    hoje = tempo.hoje()
    # Os modelos ativos, com os turnos de cada um: é o que a gestão escolhe
    # ao atribuir tarefa a um turno. Vai como dado e não como HTML porque a
    # troca de área tem de trocar a lista de turnos sem recarregar a tela.
    modelos = [{'id': c.id, 'nome': c.nome,
                'turnos': _json(c.turnos_json, [])}
               for c in (DiarioConfiguracao.query
                         .filter_by(client_id=client_id, ativo=True)
                         .order_by(DiarioConfiguracao.nome).all()
                         if client_id else [])]
    return render_template(
        'diario_operacional/dashboard.html', clients=clients,
        client_id=client_id, dados=dados, turnos=turnos, modelos=modelos,
        periodo=periodo, turno_sel=turno, periodos=analitico.PERIODOS,
        area_sel=area_id, todas_as_areas=analitico.TODAS_AS_AREAS,
        de=request.args.get('de', ''), ate=request.args.get('ate', ''),
        hoje=hoje, mes_corrente=hoje.month, ano_corrente=hoje.year,
        # Os dois botões de ação do painel perguntam o que a ROTA vai
        # perguntar: quem só LÊ a Passagem (a diretoria) não vê "Abrir
        # chamado" nem "marcar resolvida" — o POST passa pelo
        # `module_required`, que exige poder gravar no módulo.
        pode_gravar=current_user.can_access(MODULO),
        pode_chamado=(current_user.can_access('chamados')
                      and current_user.can_access(MODULO)),
        pode_ver_chamado=pode_ver_chamado,
        chamados_das_ocorrencias=chamados_abertos)


def _chamados_das_ocorrencias(ids):
    """``{ocorrencia_id: chamado}`` — a mesma porta dos chamados.

    A regra (chamado cancelado não conta, e a ocorrência volta a poder virar
    chamado) é de ``chamados.servico``; aqui só se pergunta a ele.
    """
    from facilities.chamados import servico as chamados
    return chamados.chamados_das_ocorrencias(ids)


@bp.get('/configuracao')
@login_required
@permissao_requerida('diario_config')
@module_required(MODULO)
def configuracao():
    """O cadastro do modelo de passagem — a régua de cada contrato.

    Mesma ideia do SLA Contratual: cada contrato cobra o que foi combinado
    com AQUELE cliente. Aqui o que se cadastra é o que o encarregado vai
    preencher no fim do turno — quais rotinas, quais campos, quais turnos e
    quais tipos de ocorrência.

    Sem ``client_id`` a tela caía vazia e o seletor de contrato não fazia
    nada: escolher o contrato não recarregava, e salvar enviava o contrato
    novo com os dados do antigo na tela. Agora o contrato vem sempre
    resolvido, e a troca é uma navegação.
    """
    clients = _clientes_visiveis()
    client_id = request.args.get('client_id', type=int)
    if client_id and client_id not in [c.id for c in clients]:
        client_id = None
    if not client_id and clients:
        client_id = clients[0].id

    configs = []
    if client_id:
        configs = (DiarioConfiguracao.query
                   .filter_by(client_id=client_id)
                   .order_by(DiarioConfiguracao.ativo.desc(),
                             DiarioConfiguracao.nome).all())
    # Quantos turnos já foram lançados por cada modelo: é o que diz se
    # apagar/desativar um deles mexe em histórico.
    usos = {}
    if configs:
        from sqlalchemy import func as _f
        usos = dict(DiarioTurno.query
                    .with_entities(DiarioTurno.configuracao_id, _f.count())
                    .filter(DiarioTurno.configuracao_id.in_([c.id for c in configs]))
                    .group_by(DiarioTurno.configuracao_id).all())

    # As áreas do contrato, com quantos modelos cada uma ampara — é o que diz
    # se desativar uma delas deixa passagem órfã.
    areas, usos_de_area = [], {}
    if client_id:
        areas = analitico.areas_do_contrato(client_id, apenas_ativas=False)
        if areas:
            from sqlalchemy import func as _f
            usos_de_area = dict(
                DiarioConfiguracao.query
                .with_entities(DiarioConfiguracao.area_id, _f.count())
                .filter(DiarioConfiguracao.area_id.in_([a.id for a in areas]))
                .group_by(DiarioConfiguracao.area_id).all())

    editar = request.args.get('editar', type=int)
    return render_template('diario_operacional/configuracao.html', modelos_prontos=_modelos_prontos(),
                           clients=clients, client_id=client_id,
                           configs=[_config_payload(c) for c in configs],
                           areas=[{'id': a.id, 'nome': a.nome,
                                   'ativo': bool(a.ativo),
                                   'modelos': usos_de_area.get(a.id, 0)}
                                  for a in areas],
                           usos=usos, editar=editar)


def _area_do_contrato(client_id, area_id):
    """O id de área validado CONTRA o contrato, ou ``None``.

    Aceitar o id cru deixaria um modelo da PepsiCo apontar para uma área do
    Novo Atacarejo — e aí o filtro de área de um contrato mostraria a
    passagem do outro.
    """
    if not area_id:
        return None
    a = DiarioArea.query.get(int(area_id))
    return a.id if (a is not None and a.client_id == int(client_id)) else None



def _modelos_prontos():
    from facilities.passagem.modelos_prontos import MODELOS
    return MODELOS


@bp.post('/modelos-prontos')
@login_required
@permissao_requerida('diario_config')
@module_required(MODULO)
def usar_modelos_prontos():
    """Cria as áreas e os modelos prontos escolhidos (formulário da configuração)."""
    from flask import flash, redirect, url_for
    from facilities.passagem import modelos_prontos
    client_id = request.form.get('client_id', type=int)
    _client_allowed(client_id)
    servicos = [s for s in request.form.getlist('servico') if s in modelos_prontos.MODELOS]
    destino = url_for('diario_operacional.configuracao', client_id=client_id)
    if not servicos:
        flash('Escolha ao menos um serviço.', 'warning')
        return redirect(destino)
    criados = modelos_prontos.semear(client_id, servicos, criado_por=current_user.id)
    db.session.commit()
    if criados:
        flash('Modelo(s) criado(s): ' + ', '.join(criados) + '. Ajuste o que precisar.',
              'success')
    else:
        flash('Esses modelos já existiam neste contrato — nada foi duplicado.', 'info')
    return redirect(destino)

@bp.post('/api/areas')
@login_required
@permissao_requerida('diario_config')
@module_required(MODULO)
def criar_area():
    """Cadastra uma área do contrato.

    Existe para não ser preciso cadastrar um CLIENTE novo só para dividir a
    operação em áreas — o que duplicaria contrato, centro de custo e
    carteira. O Novo Atacarejo Moreno tem cerca de dez áreas; são dez linhas
    aqui, não dez clientes.
    """
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    _client_allowed(client_id)
    nome = (data.get('nome') or '').strip()[:120]
    if not nome:
        return jsonify({'error': 'Informe o nome da área.'}), 400
    # Nome repetido no MESMO contrato é o que a tela de cadastro existe para
    # impedir: com vinte encarregados lançando, "Expedição" e "expedição"
    # viram duas áreas e o painel passa a mostrar duas onde existe uma.
    ja = (DiarioArea.query
          .filter(DiarioArea.client_id == int(client_id),
                  db.func.lower(DiarioArea.nome) == nome.lower()).first())
    if ja is not None:
        return jsonify({'error': f'Este contrato já tem a área "{ja.nome}".'}), 409
    a = DiarioArea(client_id=int(client_id), nome=nome,
                   ativo=bool(data.get('ativo', True)),
                   created_by=current_user.id)
    db.session.add(a)
    db.session.commit()
    return jsonify({'id': a.id, 'nome': a.nome, 'ativo': a.ativo}), 201


@bp.put('/api/areas/<int:area_id>')
@login_required
@permissao_requerida('diario_config')
@module_required(MODULO)
def atualizar_area(area_id):
    """Renomeia ou desativa uma área.

    NÃO existe apagar: a área desativada some dos seletores e continua
    amparando as passagens já lançadas por ela. Apagar levaria histórico
    junto, e é a mesma razão pela qual o modelo de passagem também só se
    desativa.
    """
    a = DiarioArea.query.get_or_404(area_id)
    _client_allowed(a.client_id)
    data = request.get_json(silent=True) or {}
    if 'nome' in data:
        nome = (data.get('nome') or '').strip()[:120]
        if not nome:
            return jsonify({'error': 'Informe o nome da área.'}), 400
        ja = (DiarioArea.query
              .filter(DiarioArea.client_id == a.client_id,
                      DiarioArea.id != a.id,
                      db.func.lower(DiarioArea.nome) == nome.lower()).first())
        if ja is not None:
            return jsonify({'error': f'Este contrato já tem a área '
                                     f'"{ja.nome}".'}), 409
        a.nome = nome
    if 'ativo' in data:
        a.ativo = bool(data['ativo'])
    db.session.commit()
    return jsonify({'id': a.id, 'nome': a.nome, 'ativo': a.ativo})


def _atividades_e_campos(data):
    """Lê ``perguntas`` (a lista única da tela) ou, se não vier, o par antigo.

    A tela nova manda uma lista só; integrações e testes antigos mandam
    ``atividades``/``campos``. Aceitar os dois evita quebrar quem já chama.
    """
    if 'perguntas' in data:
        return separar_perguntas(data.get('perguntas') or [])
    return data.get('atividades') or [], data.get('campos') or []


@bp.post('/api/configuracoes')
@login_required
@permissao_requerida('diario_config')
@module_required(MODULO)
def criar_configuracao():
    data = request.get_json(silent=True) or {}
    client_id = data.get('client_id')
    _client_allowed(client_id)
    try:
        atividades, campos = _atividades_e_campos(data)
    except PerguntaInvalida as ex:
        return jsonify({'error': str(ex)}), 400
    cfg = DiarioConfiguracao(
        client_id=int(client_id),
        area_id=_area_do_contrato(client_id, data.get('area_id')),
        nome=(data.get('nome') or '').strip(),
        descricao=(data.get('descricao') or '').strip(),
        turnos_json=json.dumps(data.get('turnos') or [], ensure_ascii=False),
        campos_json=json.dumps(campos, ensure_ascii=False),
        atividades_json=json.dumps(atividades, ensure_ascii=False),
        tipos_ocorrencia_json=json.dumps(data.get('tipos_ocorrencia') or [], ensure_ascii=False),
        ativo=bool(data.get('ativo', True)),
        created_by=current_user.id,
    )
    if not cfg.nome:
        return jsonify({'error': 'Informe o nome da configuração.'}), 400
    db.session.add(cfg)
    db.session.commit()
    return jsonify(_config_payload(cfg)), 201


@bp.put('/api/configuracoes/<int:config_id>')
@login_required
@permissao_requerida('diario_config')
@module_required(MODULO)
def atualizar_configuracao(config_id):
    cfg = DiarioConfiguracao.query.get_or_404(config_id)
    _client_allowed(cfg.client_id)
    data = request.get_json(silent=True) or {}
    if 'perguntas' in data:
        # As perguntas que o modelo JÁ tem, por código: a que chegar sem
        # tipo (ou com um tipo que a tela não conhecia) guarda o dela — e a
        # escolha guarda as opções — em vez de virar Sim/Não obrigatória.
        anteriores = {q['codigo']: q for q in perguntas_do_modelo(
            _json(cfg.atividades_json, []), _json(cfg.campos_json, []))}
        try:
            atividades, campos = separar_perguntas(data.get('perguntas') or [],
                                                   anteriores)
        except PerguntaInvalida as ex:
            return jsonify({'error': str(ex)}), 400
    cfg.nome = (data.get('nome') or cfg.nome).strip()
    if 'area_id' in data:
        cfg.area_id = _area_do_contrato(cfg.client_id, data.get('area_id'))
    cfg.descricao = (data.get('descricao') or '').strip()
    if 'perguntas' in data:
        cfg.atividades_json = json.dumps(atividades, ensure_ascii=False)
        cfg.campos_json = json.dumps(campos, ensure_ascii=False)
    for attr, key in [('turnos_json', 'turnos'), ('campos_json', 'campos'),
                      ('atividades_json', 'atividades'),
                      ('tipos_ocorrencia_json', 'tipos_ocorrencia')]:
        if key in data:
            setattr(cfg, attr, json.dumps(data[key] or [], ensure_ascii=False))
    if 'ativo' in data:
        cfg.ativo = bool(data['ativo'])
    db.session.commit()
    return jsonify(_config_payload(cfg))


def _area_efetiva(area_id, ativas):
    """A área do modelo para a tela e para a conta: ``None`` se desativada.

    Desativar uma área não mexe nos modelos (nada se apaga) — eles continuam
    ativos, com o ``area_id`` antigo. A tela não oferece área desativada, e
    esses modelos passam a aparecer junto com os modelos sem área; a chave
    da área precisa dizer o mesmo, senão a tela junta o que a conta separa.
    """
    return area_id if area_id and area_id in ativas else None


def _chave_da_area(configuracao_id, area_id):
    """A ÁREA de um modelo, como texto: ``area-<id>`` ou ``contrato-0``.

    Área é ``DiarioConfiguracao.area_id``. O modelo sem área (contrato que
    nunca dividiu a operação, ou modelo antigo) é da área "do contrato":
    a tela oferece esses modelos juntos e escolhe o modelo pelo turno, então
    o "turno anterior" do T2 é o T1, ainda que cada um tenha o seu modelo.

    É texto com prefixo para a área cadastrada nunca colidir com a área do
    contrato. A tela usa a MESMA regra (``chaveDaArea`` em
    diario_operacional.js) para saber qual bloco mostrar. A regra em si mora em
    ``analitico.chave_da_area`` — a mesma que decide quem "recebe" uma
    pendência —, aqui só vira texto para o HTML.
    """
    tipo, ident = analitico.chave_da_area(area_id, configuracao_id)
    return f'{tipo}-{ident}'


def _o_que_o_turno_anterior_deixou(client_id, configs):
    """Por ÁREA: a última passagem encerrada de cada uma — o que o turno de trás viu.

    A tela mostrava só as pendências, e pendência é o que ficou POR FAZER.
    O que já aconteceu — a avaria registrada, a doca travada, a foto da rua
    bagunçada — só existia no dashboard, a três toques de distância. No
    celular, no começo do turno, três toques significam que ninguém lê.

    **Por área, não por contrato.** O bloco mostrava a última passagem do
    contrato INTEIRO: o encarregado do Almoxarifado chegava e lia que "o
    turno anterior deixou" a doca travada da Expedição — e a passagem do
    Almoxarifado, que era a dele, ficava escondida atrás da outra. Agora cada
    área que a pessoa pode escolher (``configs``, os modelos ativos da tela)
    ganha o seu bloco, e a tela mostra o da área escolhida.

    A passagem conta para a área do modelo que a lançou, e entram TODOS os
    modelos daquela área, ativos ou não: o modelo que a Expedição usava até
    o mês passado continua sendo da Expedição.

    Devolve uma lista de ``{'chave', 'area', 'turno', ...}`` na ordem dos
    modelos. A área sem passagem encerrada vem com ``turno=None`` (a tela diz
    "nenhuma passagem nesta área ainda"). Lista VAZIA quando nenhuma área tem
    passagem (contrato novo): aí a tela simplesmente não desenha o bloco.

    Custo fixo de banco — sete consultas, tenha o contrato duas áreas ou
    dez —, porque isto roda toda vez que alguém abre a tela de passagem.
    """
    if not client_id or not configs:
        return []
    from sqlalchemy import and_, func, or_
    from sqlalchemy.orm import lazyload

    # A área de cada modelo do contrato (de todos, inclusive os inativos) —
    # a EFETIVA: modelo de área desativada é da área do contrato, como na
    # tela (ver ``_area_efetiva``). A situação da área vem na mesma consulta.
    area_do_modelo = {cid: (aid if ativa else None)
                      for cid, aid, ativa in DiarioConfiguracao.query
                      .outerjoin(DiarioArea,
                                 DiarioArea.id == DiarioConfiguracao.area_id)
                      .with_entities(DiarioConfiguracao.id,
                                     DiarioConfiguracao.area_id, DiarioArea.ativo)
                      .filter(DiarioConfiguracao.client_id == client_id)
                      .all()}
    chave_do_modelo = {cid: _chave_da_area(cid, aid)
                       for cid, aid in area_do_modelo.items()}
    chaves = []
    for c in configs:
        ch = _chave_da_area(c.id, area_do_modelo.get(c.id))
        if ch not in chaves:
            chaves.append(ch)
    modelos = [cid for cid, ch in chave_do_modelo.items() if ch in chaves]

    # O último DIA encerrado de cada modelo; o último turno da área sai dos
    # turnos desses dias. Mesma ordem de antes — data, depois ordem de
    # lançamento —, só que dentro da área.
    ultimo_dia = (DiarioTurno.query
                  .with_entities(DiarioTurno.configuracao_id,
                                 func.max(DiarioTurno.data_turno))
                  .filter(DiarioTurno.client_id == client_id,
                          DiarioTurno.status == 'encerrado',
                          DiarioTurno.configuracao_id.in_(modelos or [0]))
                  .group_by(DiarioTurno.configuracao_id).all())
    if not ultimo_dia:
        return []
    # ``lazyload('*')``: o turno carrega anexos e correções em ``selectin``
    # por padrão, e aqui seriam duas consultas a mais para os candidatos que
    # nem vão para a tela. Os anexos do escolhido vêm logo abaixo.
    candidatos = (DiarioTurno.query
                  .options(lazyload('*'))
                  .filter(DiarioTurno.client_id == client_id,
                          DiarioTurno.status == 'encerrado',
                          or_(*[and_(DiarioTurno.configuracao_id == cid,
                                     DiarioTurno.data_turno == dia)
                                for cid, dia in ultimo_dia]))
                  .all())
    ultimo = {}
    for t in candidatos:
        ch = chave_do_modelo.get(t.configuracao_id)
        atual = ultimo.get(ch)
        if atual is None or (t.data_turno, t.id) > (atual.data_turno, atual.id):
            ultimo[ch] = t

    ids = [t.id for t in ultimo.values()]
    ocorrencias, anexos = {}, {}
    for o in (DiarioOcorrencia.query.filter(DiarioOcorrencia.turno_id.in_(ids))
              .order_by(DiarioOcorrencia.id.asc()).all()):
        ocorrencias.setdefault(o.turno_id, []).append(o)
    for a in (DiarioAnexo.query.filter(DiarioAnexo.turno_id.in_(ids))
              .order_by(DiarioAnexo.id.asc()).all()):
        anexos.setdefault(a.turno_id, []).append(a)
    from facilities.core.models import User
    autores = dict(User.query.with_entities(User.id, User.name)
                   .filter(User.id.in_([t.created_by for t in ultimo.values()]
                                       or [0])).all())
    # O nome da área vai no cabeçalho do bloco: é o que confirma, a quem lê,
    # que aquilo é da área que ele escolheu e não de outra.
    ids_de_area = [area_do_modelo.get(t.configuracao_id) for t in ultimo.values()]
    nomes_de_area = dict(DiarioArea.query
                         .with_entities(DiarioArea.id, DiarioArea.nome)
                         .filter(DiarioArea.id.in_([a for a in ids_de_area if a]
                                                   or [0])).all())

    blocos = []
    for ch in chaves:
        t = ultimo.get(ch)
        if t is None:
            blocos.append({'chave': ch, 'turno': None})
            continue
        oc, ax = ocorrencias.get(t.id, []), anexos.get(t.id, [])
        blocos.append({
            'chave': ch, 'turno': t, 'ocorrencias': oc, 'anexos': ax,
            'autor': autores.get(t.created_by) or '',
            'area': nomes_de_area.get(area_do_modelo.get(t.configuracao_id)) or '',
            # Quanto o bloco tem a dizer: se for zero, a tela mostra uma
            # linha só em vez de um acordeão vazio.
            'tem_o_que_ler': bool(oc or (t.observacao or '').strip() or ax)})
    return blocos


# Quantos dias para trás a tela de passagem sabe quais turnos já foram
# encerrados. Uma semana cobre o caso real — o 3º turno que vira a meia-noite
# e é lançado com a data de ontem, a passagem esquecida de sexta lançada na
# segunda — sem mandar o histórico inteiro do contrato para o celular.
DIAS_DE_TURNOS_ENCERRADOS = 7


def _turnos_ja_encerrados(client_id, configs, hoje):
    """``{'<modelo>': {'<AAAA-MM-DD>': ['1º Turno', ...]}}`` — o que já fechou.

    A tela pré-selecionava SEMPRE o primeiro turno do modelo. O encarregado
    do 2º Turno abria a passagem já no 1º — que o colega tinha encerrado de
    manhã —, preenchia tudo, enviava e levava um 409 ("já foi encerrada")
    no fim do expediente. Com isto a tela pré-seleciona o primeiro turno que
    AINDA está em aberto naquela data.

    É por MODELO porque é por modelo que o servidor recusa (a chave da
    passagem é contrato + modelo + dia + turno): o 1º Turno encerrado da
    Expedição não fecha o 1º Turno do Almoxarifado.
    """
    if not client_id or not configs:
        return {}
    from datetime import timedelta
    linhas = (DiarioTurno.query
              .with_entities(DiarioTurno.configuracao_id,
                             DiarioTurno.data_turno, DiarioTurno.turno)
              .filter(DiarioTurno.client_id == client_id,
                      DiarioTurno.status == 'encerrado',
                      DiarioTurno.configuracao_id.in_([c.id for c in configs]),
                      DiarioTurno.data_turno >= hoje - timedelta(
                          days=DIAS_DE_TURNOS_ENCERRADOS),
                      DiarioTurno.data_turno <= hoje + timedelta(days=1))
              .all())
    mapa = {}
    for cid, dia, nome in linhas:
        do_dia = mapa.setdefault(str(cid), {}).setdefault(dia.isoformat(), [])
        if nome not in do_dia:
            do_dia.append(nome)
    return mapa


@bp.get('/turno')
@login_required
@module_required(MODULO)
def turno():
    """Nova passagem de turno.

    Abre com o que o sistema JÁ SABE preenchido — quem está lançando e em que
    operação — e deixa para a pessoa só o que ela precisa decidir: a data, o
    turno e as respostas. Cada pergunta a responder vem do modelo daquele
    contrato, do mesmo jeito que a régua do SLA Contratual é de cada contrato.
    """
    clients = _clientes_visiveis()
    client_id = request.args.get('client_id', type=int) or (clients[0].id if clients else None)
    if client_id and client_id not in [c.id for c in clients]:
        client_id = None
    configs = (DiarioConfiguracao.query
               .filter_by(client_id=client_id, ativo=True)
               .order_by(DiarioConfiguracao.nome).all()) if client_id else []
    pending = analitico.fila_de_pendencias(client_id) if client_id else []
    contrato = next((c for c in clients if c.id == client_id), None)
    # As áreas ATIVAS do contrato — TODAS elas, para TODO encarregado daquele
    # contrato. No Novo Atacarejo Moreno são vinte pessoas e cerca de dez
    # áreas, e as vinte enxergam as dez.
    #
    # Isto é decisão, não falta de controle: na operação real o encarregado
    # RODA entre áreas — cobre uma falta, muda de setor, assume a Expedição
    # numa semana e o Almoxarifado na outra. Amarrar cada pessoa a uma área
    # viraria um chamado para o Master a cada troca, e no dia da falta a
    # passagem simplesmente não seria lançada.
    #
    # A rastreabilidade não depende desse vínculo: cada passagem grava quem
    # lançou (``created_by``) e em qual área (via ``configuracao_id``), então
    # o histórico continua dizendo que foi o Paulo Cezar quem fechou a
    # Expedição na terça e o Almoxarifado na quinta.
    #
    # A área se SELECIONA, nunca se digita: com vinte pessoas escrevendo à
    # mão, "Expedição" e "expedicao" viram duas áreas na mesma semana.
    areas = analitico.areas_do_contrato(client_id) if client_id else []
    ativas = {a.id for a in areas}
    efetiva = {c.id: _area_efetiva(c.area_id, ativas) for c in configs}
    # Só entram as áreas que têm modelo ativo — oferecer uma área sem modelo
    # levaria a pessoa a uma tela sem pergunta nenhuma.
    com_modelo = {a for a in efetiva.values() if a}
    areas = [{'id': a.id, 'nome': a.nome} for a in areas if a.id in com_modelo]
    # Contrato que se dividiu em áreas mas manteve modelos ativos sem área
    # (o modelo antigo, o de uma área desativada): eles ganham uma opção
    # própria no seletor. Sem ela sumiam da tela — o seletor só oferecia as
    # áreas, e ninguém conseguia lançar a passagem desses modelos.
    if areas and any(a is None for a in efetiva.values()):
        areas.append({'id': AREA_SEM_CADASTRO, 'nome': 'Geral (sem área)'})
    hoje = tempo.hoje()
    # Qual bloco "o turno anterior deixou" já sai visível: o da área que o
    # seletor abre escolhida (a primeira), ou o do primeiro modelo quando o
    # contrato não tem área. O JS acerta o resto assim que a tela carrega.
    if areas:
        anterior_inicial = _chave_da_area(None, areas[0]['id'])
    elif configs:
        anterior_inicial = _chave_da_area(configs[0].id, efetiva[configs[0].id])
    else:
        anterior_inicial = ''
    return render_template(
        'diario_operacional/turno.html', clients=clients, client_id=client_id,
        contrato=contrato,
        # O centro de custo é o do contrato — é por ele que a operação se
        # reconhece no Razão e no financeiro, e é o que o encarregado espera
        # ver escrito no cabeçalho da passagem.
        centro_custo=(contrato.cost_center or '') if contrato else '',
        configs=[dict(_config_payload(c), area_id=efetiva[c.id]) for c in configs],
        pending=pending, areas=areas,
        anteriores=_o_que_o_turno_anterior_deixou(client_id, configs),
        anterior_inicial=anterior_inicial,
        encerrados=_turnos_ja_encerrados(client_id, configs, hoje),
        hoje=hoje.isoformat())


@bp.post('/api/turnos')
@login_required
@module_required(MODULO)
def salvar_turno():
    data = request.get_json(silent=True) or {}
    client_id = int(data.get('client_id'))
    _client_allowed(client_id)
    cfg = DiarioConfiguracao.query.get_or_404(int(data.get('configuracao_id')))
    if cfg.client_id != client_id or not cfg.ativo:
        return jsonify({'error': 'Configuração inválida para este cliente.'}), 400
    try:
        data_turno = date.fromisoformat(data.get('data_turno'))
    except Exception:
        return jsonify({'error': 'Data do turno inválida.'}), 400
    turno_nome = (data.get('turno') or '').strip()
    if not turno_nome:
        return jsonify({'error': 'Informe o turno.'}), 400

    dados = data.get('dados') or {}
    if not isinstance(dados, dict):
        return jsonify({'error': 'Dados do turno inválidos.'}), 400
    # A chave do congelamento é do SERVIDOR: o que o navegador mandar com
    # esse nome é descartado, senão bastaria forjar uma lista vazia para
    # zerar a exigência do turno e sair com 100% de aderência.
    dados.pop(analitico.CHAVE_EXIGIDAS, None)
    dados.pop(analitico.CHAVE_ENVIO, None)
    # A hora do aparelho também: ela só entra pelo campo de fora de `dados`,
    # e só depois de conferida (ver `hora_do_aparelho`).
    dados.pop(CHAVE_ENCERRADO_NO_APARELHO, None)
    envio = envio_valido(data.get('envio_id'))

    # Uma passagem por contrato, MODELO, dia e turno — salvar rascunho e depois
    # encerrar é a MESMA passagem, não duas.
    #
    # Antes cada envio criava uma linha nova: quem clicava "Salvar rascunho" e
    # depois "Encerrar turno" deixava para trás um turno aberto que nunca
    # fechava, e a tela mostrava o T1 de hoje duas vezes, todo dia. Também é
    # isto que dá ao anexo um turno estável para se prender.
    #
    # O MODELO entra na chave porque um contrato tem mais de uma ÁREA, e cada
    # área tem a sua passagem. Na PepsiCo Fábrica Recife, o 1º Turno de
    # 21/09/2026 tem uma passagem da Expedição e outra do Almoxarifado, com
    # responsáveis diferentes. Sem o modelo na chave, a segunda batia em 409
    # ("o 1º Turno de 21/09/2026 já foi encerrado") e o encarregado do
    # Almoxarifado simplesmente não conseguia lançar.
    t = (DiarioTurno.query
         .filter_by(client_id=client_id, configuracao_id=cfg.id,
                    data_turno=data_turno, turno=turno_nome)
         .order_by(DiarioTurno.id.desc()).first())
    if (t is not None and t.status == 'encerrado' and envio
            and t.created_by == current_user.id
            and _json(t.dados_json, {}).get(analitico.CHAVE_ENVIO) == envio):
        # O MESMO envio chegando de novo: o celular sem sinal mandou, o
        # servidor gravou, e a resposta se perdeu no caminho. Responder 409
        # aqui diria ao autor que o turno dele "já foi encerrado" por alguém
        # — quando foi por ele mesmo. Nada é regravado.
        return jsonify(dict(_turno_payload(t), repetido=True)), 200
    if t is not None and t.status == 'encerrado':
        # Encerrada não se sobrescreve. Quem lançou errado CORRIGE, com
        # motivo e rastro, em /api/turnos/<id>/corrigir — ver o bloco
        # "Corrigir a passagem já encerrada".
        return jsonify({'error': f'A passagem de {cfg.nome} — {turno_nome} de '
                                 f'{data_turno.strftime("%d/%m/%Y")} já foi '
                                 f'encerrada. Se foi você que a lançou, abra-a '
                                 f'e use "Corrigir".'}), 409
    if t is not None and t.created_by != current_user.id:
        # O rascunho é de quem o abriu. Antes disto, qualquer um com acesso
        # ao contrato salvava por cima do rascunho alheio — e o dono perdia
        # o que tinha digitado sem nunca saber por quê.
        from facilities.core.models import User
        dono = User.query.get(t.created_by)
        quem = (getattr(dono, 'name', None) or getattr(dono, 'email', None)
                or 'outra pessoa')
        return jsonify({'error': f'O rascunho desta passagem foi aberto por '
                                 f'{quem}. Peça que ele encerre, ou lance a '
                                 f'sua em outro turno.'}), 403
    if t is None:
        t = DiarioTurno(client_id=client_id, configuracao_id=cfg.id,
                        data_turno=data_turno, turno=turno_nome, status='aberto',
                        dados_json='{}', created_by=current_user.id)
        db.session.add(t)
    t.configuracao_id = cfg.id
    if envio:
        dados[analitico.CHAVE_ENVIO] = envio
    t.dados_json = json.dumps(dados, ensure_ascii=False)
    t.observacao = (data.get('observacao') or '').strip()
    db.session.flush()

    # Ao reenviar, o navegador manda a lista inteira de novo. Somar cegamente
    # duplicaria tudo o que já entrou no rascunho; apagar e recriar destruiria
    # a pendência que alguém já baixou. Então só entra o que ainda não existe
    # neste turno.
    ja_pend = {(p.titulo or '').strip().lower()
               for p in DiarioPendencia.query.filter_by(turno_id=t.id).all()}
    for p in data.get('pendencias') or []:
        titulo = (p.get('titulo') or '').strip()
        if titulo and titulo.lower() not in ja_pend:
            ja_pend.add(titulo.lower())
            db.session.add(DiarioPendencia(client_id=client_id, turno_id=t.id,
                titulo=titulo, descricao=(p.get('descricao') or '').strip(),
                referencia=(p.get('referencia') or '').strip()[:120] or None,
                prioridade=p.get('prioridade') or 'media', created_by=current_user.id))
    ja_ocor = {((o.tipo or '').strip().lower(), (o.referencia or '').strip().lower(),
                (o.descricao or '').strip().lower())
               for o in DiarioOcorrencia.query.filter_by(turno_id=t.id).all()}
    for o in data.get('ocorrencias') or []:
        descricao = (o.get('descricao') or '').strip()
        tipo = (o.get('tipo') or 'Outros').strip()
        ref = (o.get('referencia') or '').strip()
        chave = (tipo.lower(), ref.lower(), descricao.lower())
        if descricao and chave not in ja_ocor:
            ja_ocor.add(chave)
            # Qualquer coisa fora do vocabulário vira 'normal'. Aceitar o que
            # veio no corpo deixaria a Torre de Comando mostrar um bloco de
            # pontos de atenção com uma gravidade que ninguém sabe ler.
            grav = (o.get('gravidade') or '').strip().lower()
            if grav != OCORRENCIA_CRITICA:
                grav = OCORRENCIA_NORMAL
            db.session.add(DiarioOcorrencia(client_id=client_id, turno_id=t.id,
                tipo=tipo, referencia=ref, descricao=descricao,
                gravidade=grav, created_by=current_user.id))
    if data.get('finalizar'):
        t.status = 'encerrado'
        t.submitted_at = datetime.utcnow()
        # Congela a régua do dia junto com o turno. Rascunho não congela: ele
        # ainda vai ser encerrado, e é no encerramento que se decide o que
        # valia. Ver `analitico.exigidas_do_turno` para o porquê.
        obrigatorias = [a for a in _json(cfg.atividades_json, [])
                        if isinstance(a, dict) and a.get('obrigatorio') is not False]
        dados[analitico.CHAVE_EXIGIDAS] = [
            {'codigo': a.get('codigo') or a.get('nome') or '',
             'nome': a.get('nome') or a.get('codigo') or '—'}
            for a in obrigatorias]
        # A hora em que a pessoa TOCOU em "Encerrar", dita pelo aparelho. Sem
        # sinal, o encerramento espera na fila e chega horas depois — e o
        # `submitted_at` (hora de CHEGADA, que é a da auditoria e não muda)
        # sozinho faria parecer que o turno foi fechado atrasado.
        no_aparelho = hora_do_aparelho(data.get('encerrado_no_aparelho'),
                                       t.submitted_at)
        if no_aparelho:
            dados[CHAVE_ENCERRADO_NO_APARELHO] = no_aparelho
        t.dados_json = json.dumps(dados, ensure_ascii=False)
        # As tarefas da gestão ANTES da trilha e do aviso: a pendência que
        # nasce delas é DESTE turno (não pode ganhar "recebida" do próprio
        # turno que a abriu) e tem de entrar na conta da prioridade alta.
        # É o servidor que decide, então vale também para o encerramento que
        # chega pela fila do aparelho, sem a confirmação da tela.
        _tarefas_no_encerramento(t)
        _registrar_passagem_das_abertas(t)
        # O encerramento acontece UMA vez (encerrada não volta a salvar por
        # aqui), então o aviso não se repete. Só a de prioridade alta vira
        # aviso: a pendência comum o turno seguinte vê ao abrir a passagem.
        db.session.flush()
        altas = (DiarioPendencia.query
                 .filter_by(turno_id=t.id, prioridade='alta', status='aberta').count())
        if altas:
            # "Prioridade alta", e não "crítica": é o nome que o formulário dá
            # (Baixa/Média/Alta). Quem recebe o aviso abre a passagem e
            # procura a palavra que leu — e "crítica" não está escrita lá.
            _avisar(_time_do_piso(client_id, cfg.id, exceto=current_user.id),
                    f'{t.turno} de {t.data_turno.strftime("%d/%m")} encerrado com '
                    f'{altas} pendência{"s" if altas > 1 else ""} de prioridade alta',
                    'Abra a passagem para ver o que ficou para o seu turno.',
                    _link_do_turno(client_id), client_id)
        _avisar_pendencias_paradas(client_id)
    db.session.commit()
    # Quantas pendências ESTA passagem deixou em aberto: é o número que a
    # tela escreve na confirmação ("2 pendências ficaram para o próximo
    # turno"). No celular o painel é longo, e sem a frase a pessoa não sabia
    # se o encerramento tinha entrado.
    deixadas = DiarioPendencia.query.filter_by(turno_id=t.id, status='aberta').count()
    return jsonify(dict(_turno_payload(t), pendencias_deixadas=deixadas)), 201


def _registrar_passagem_das_abertas(t):
    """No fechamento, anota que este turno recebeu as pendências que continuam abertas.

    É o evento que não custa digitação a ninguém. O encarregado que herdou a
    devolução, passou o turno atrás do processo e não achou não precisa
    escrever nada: ao encerrar, fica registrado que o turno dele recebeu e
    não resolveu. Sem isto, "passou por seis turnos" seria só uma conta de
    calendário — e a fila ficaria indistinguível de uma pendência que
    ninguém sequer olhou.

    Ficam de fora as que ESTE turno abriu: quem abre não está carregando
    nada, está entregando. E uma pendência não ganha dois eventos do mesmo
    turno — reencerrar não infla a trilha.

    Ficam de fora também as de OUTRA ÁREA. O Almoxarifado que encerra o 1º
    Turno não herdou a devolução que a Expedição deixou: quem a herda é o
    turno seguinte da Expedição. Antes, toda passagem do contrato gravava
    "recebida" em tudo, e a trilha dizia "passou por 25 turnos" de uma
    pendência que só cinco turnos da Expedição carregaram. A pendência sem
    turno de origem (aberta pela gestão) é do contrato: qualquer área a
    carrega. A regra é ``analitico.area_carrega`` — a mesma que a contagem
    da trilha usa.
    """
    # ``turno_id != t.id`` sozinho descartaria as pendências avulsas: em SQL,
    # ``NULL != 5`` não é verdadeiro, é NULO. A pendência que o gestor abriu
    # pelo dashboard não tem turno de origem e é carregada como qualquer
    # outra — precisa do OR explícito para entrar na trilha.
    from sqlalchemy import or_
    abertas = (DiarioPendencia.query
               .filter(DiarioPendencia.client_id == t.client_id,
                       DiarioPendencia.status == 'aberta',
                       or_(DiarioPendencia.turno_id.is_(None),
                           DiarioPendencia.turno_id != t.id))
               .all())
    if not abertas:
        return
    # A área de cada pendência é a do turno que a abriu; uma consulta só
    # para todas, não uma por pendência.
    area = analitico.area_do_turno(t)
    origens = analitico.areas_dos_turnos({p.turno_id for p in abertas if p.turno_id})
    # Pendência de passagem ainda em RASCUNHO não foi entregue a ninguém: o
    # turno que a escreveu nem encerrou. Ela fica fora dos indicadores até o
    # encerramento (diario_analitico._fora_do_rascunho) e, pela mesma razão,
    # outro turno não "recebe" o que ainda não lhe foi passado.
    em_rascunho = {tid for (tid,) in db.session.query(DiarioTurno.id)
                   .filter(DiarioTurno.id.in_({p.turno_id for p in abertas if p.turno_id}),
                           DiarioTurno.status != 'encerrado')} if origens else set()
    # Pela mesma razão, a do "Não deu" que ainda espera a passagem dela. E,
    # do outro lado, a do "Não deu" que já esperou demais é carregada mesmo
    # presa a um rascunho que ninguém encerrou (ver
    # ``analitico.pendencias_de_tarefa_vencidas``) — a mesma régua dos
    # indicadores.
    esperando = set(db.session.execute(
        analitico.pendencias_aguardando_passagem(t.client_id)).scalars())
    vencidas = set(db.session.execute(
        analitico.pendencias_de_tarefa_vencidas(t.client_id)).scalars())
    abertas = [p for p in abertas
               if (p.turno_id not in em_rascunho or p.id in vencidas)
               and p.id not in esperando
               and analitico.area_carrega(analitico.area_de_origem(p.turno_id, origens),
                                          area)]
    if not abertas:
        return
    ja = {e.pendencia_id for e in DiarioPendenciaEvento.query
          .filter(DiarioPendenciaEvento.turno_id == t.id,
                  DiarioPendenciaEvento.pendencia_id.in_([p.id for p in abertas]))
          .all()}
    for p in abertas:
        if p.id not in ja:
            db.session.add(DiarioPendenciaEvento(
                pendencia_id=p.id, turno_id=t.id, tipo='recebida',
                created_by=current_user.id))


@bp.get('/turno/<int:turno_id>')
@login_required
@module_required(MODULO)
def ver_turno(turno_id):
    """A passagem já lançada, para leitura — com as fotos que a acompanham.

    Sem esta tela o anexo seria um buraco: o encarregado prende a foto do 5S
    e ninguém nunca mais a vê. É por aqui que o supervisor confere a prova do
    que foi (ou não foi) feito no turno.
    """
    t = _turno_autorizado(turno_id)
    cfg = DiarioConfiguracao.query.get(t.configuracao_id)
    dados = _json(t.dados_json, {})
    do_modelo = [a for a in (_json(cfg.atividades_json, []) if cfg else [])
                 if isinstance(a, dict)]

    # A régua congelada manda; só turno antigo (ou rascunho, que ainda não
    # congelou) cai na configuração de hoje — e aí só as obrigatórias, que é
    # a mesma régua que ``analitico.exigidas_do_turno`` usa na aderência.
    #
    # Lista congelada VAZIA também é régua: o modelo não tinha rotina
    # obrigatória no dia do encerramento. Tratá-la como "não congelou" punha
    # o checklist de HOJE na tela, com o aviso de turno antigo, para um turno
    # que a aderência mede como "nada exigido".
    congelado = dados.get(analitico.CHAVE_EXIGIDAS)
    if isinstance(congelado, list):
        atividades = [a for a in congelado if isinstance(a, dict)]
        congelada = True
    else:
        atividades = [a for a in do_modelo if a.get('obrigatorio') is not False]
        congelada = False

    anexos = {}
    for a in DiarioAnexo.query.filter_by(turno_id=t.id).order_by(DiarioAnexo.id).all():
        anexos.setdefault(a.atividade_codigo or '', []).append(a)
    # Os códigos que já ganharam lugar na tela. O anexo cujo código não
    # aparece em lugar nenhum não pode simplesmente sumir — ver o fim.
    usados = set()

    def _linha(codigo, nome, opcional):
        valor = dados.get(analitico.PREFIXO_ATIVIDADE + codigo)
        feito = bool(valor.get('concluido')) if isinstance(valor, dict) else bool(valor)
        nota = valor.get('observacao', '') if isinstance(valor, dict) else ''
        usados.add(codigo)
        return {'codigo': codigo, 'nome': nome or codigo or '—',
                'feito': feito, 'observacao': (nota or '').strip(),
                'opcional': opcional, 'anexos': anexos.get(codigo, [])}

    linhas = []
    for a in atividades:
        codigo = a.get('codigo') or a.get('nome') or ''
        linhas.append(_linha(codigo, a.get('nome'), opcional=False))

    # As rotinas OPCIONAIS respondidas. A tela só mostrava a régua congelada
    # — que guarda apenas as obrigatórias —, então a rotina opcional que o
    # encarregado marcou, e a foto que ele prendeu a ela, sumiam da leitura:
    # a prova estava no banco e ninguém a via. Elas aparecem marcadas como
    # "opcional", depois das obrigatórias, e NÃO entram na régua: a aderência
    # continua sendo só o que era exigido.
    exigidos = {linha['codigo'] for linha in linhas}
    nome_no_modelo, ordem_no_modelo = {}, {}
    for i, a in enumerate(do_modelo):
        codigo = a.get('codigo') or a.get('nome') or ''
        nome_no_modelo.setdefault(codigo, a.get('nome') or codigo)
        ordem_no_modelo.setdefault(codigo, i)
    opcionais = [k[len(analitico.PREFIXO_ATIVIDADE):] for k in dados
                 if isinstance(k, str) and k.startswith(analitico.PREFIXO_ATIVIDADE)]
    opcionais = [c for c in opcionais if c and c not in exigidos]
    # Na ordem do modelo; a rotina que já saiu do modelo vai para o fim, com
    # o próprio código como nome — é o que restou dela.
    opcionais.sort(key=lambda c: ordem_no_modelo.get(c, len(ordem_no_modelo)))
    for codigo in opcionais:
        linhas.append(_linha(codigo, nome_no_modelo.get(codigo), opcional=True))

    campos = []
    for c in (_json(cfg.campos_json, []) if cfg else []):
        if isinstance(c, dict):
            codigo = c.get('codigo') or c.get('nome') or ''
            # A tela de lançamento oferece foto em TODA pergunta, não só na
            # rotina — então o campo também carrega as suas.
            fotos = [] if codigo in usados else anexos.get(codigo, [])
            usados.add(codigo)
            campos.append({'nome': c.get('nome') or codigo,
                           'valor': dados.get(codigo, ''), 'anexos': fotos})

    # O anexo de uma pergunta que já não existe (campo tirado do modelo
    # depois do turno) vai para as provas gerais do turno: com o nome do
    # arquivo, ainda se reconhece; escondido, seria prova perdida.
    orfaos = [a for codigo, lista in anexos.items()
              if codigo and codigo not in usados for a in lista]
    anexos_gerais = sorted(anexos.get('', []) + orfaos, key=lambda a: a.id)

    from facilities.core.models import Client, User
    # Corrigir é do AUTOR, e só enquanto o turno seguinte não fechou. A tela
    # decide isso aqui e não em JavaScript: botão que aparece e depois recusa
    # ensina a pessoa a não confiar na tela.
    pode_corrigir = (t.status == 'encerrado'
                     and t.created_by == current_user.id
                     and _janela_de_correcao_aberta(t))
    return render_template(
        'diario_operacional/ver_turno.html', turno=t,
        cliente=Client.query.get(t.client_id), configuracao=cfg,
        linhas=linhas, campos=campos, congelada=congelada,
        anexos_gerais=anexos_gerais,
        pode_corrigir=pode_corrigir,
        correcoes=list(t.correcoes or []),
        quem_corrigiu={u.id: (u.name or u.email) for u in User.query.filter(
            User.id.in_([c.created_by for c in (t.correcoes or [])] or [0]))},
        # Quem prendeu cada foto, quando NÃO foi o autor da passagem (a gestão
        # também anexa): a foto da gestão não pode ser lida como parte do que
        # o autor assinou.
        quem_anexou={u.id: (u.name or u.email) for u in User.query.filter(
            User.id.in_(list({a.uploaded_by for lista in anexos.values() for a in lista
                              if a.uploaded_by and a.uploaded_by != t.created_by})
                        or [0]))},
        autor=User.query.get(t.created_by),
        pendencias=[{'p': p, 'trilha': analitico.trilha_da_pendencia(p.id)}
                    for p in DiarioPendencia.query.filter_by(turno_id=t.id)
                    .order_by(DiarioPendencia.id).all()],
        ocorrencias=DiarioOcorrencia.query.filter_by(turno_id=t.id)
                    .order_by(DiarioOcorrencia.id).all())


@bp.post('/api/pendencias')
@login_required
@module_required(MODULO)
def criar_pendencia_gestor():
    if current_user._effective_role() not in ('master', 'pleno'):
        return jsonify({'error': 'Somente gestor pode criar pendência para a operação.'}), 403
    data = request.get_json(silent=True) or {}
    client_id = int(data.get('client_id'))
    _client_allowed(client_id)
    titulo = (data.get('titulo') or '').strip()
    if not titulo:
        return jsonify({'error': 'Informe a pendência.'}), 400
    # O responsável é uma PESSOA DESTE CONTRATO. Aceitar qualquer id gravava
    # como responsável quem nem abre o contrato (ou um id que não existe —
    # no Postgres, um erro 500 na hora de gravar).
    responsavel = None
    if data.get('assigned_to'):
        try:
            responsavel = int(data['assigned_to'])
        except (TypeError, ValueError):
            responsavel = None
        if responsavel is None or not _ve_o_contrato(responsavel, client_id):
            return jsonify({'error': 'O responsável escolhido não trabalha neste '
                                     'contrato (ou não está mais ativo). Escolha '
                                     'alguém do contrato.'}), 400
    prazo = None
    if data.get('due_date'):
        try:
            prazo = date.fromisoformat(str(data['due_date'])[:10])
        except ValueError:
            return jsonify({'error': 'Prazo inválido.'}), 400
    p = DiarioPendencia(client_id=client_id, titulo=titulo,
                        descricao=(data.get('descricao') or '').strip(),
                        prioridade=data.get('prioridade') or 'media',
                        assigned_to=responsavel, due_date=prazo,
                        created_by=current_user.id)
    db.session.add(p)
    if p.prioridade == 'alta':
        # O responsável já foi conferido acima: ativo e com o contrato.
        destino = ([p.assigned_to] if p.assigned_to and p.assigned_to != current_user.id
                   else _time_do_piso(client_id, exceto=current_user.id))
        _avisar(destino, 'Pendência crítica', p.titulo, _link_do_turno(client_id),
                client_id)
    db.session.commit()
    return jsonify({'id': p.id, 'status': p.status}), 201


@bp.get('/relatorio-mensal')
@login_required
@module_required(MODULO)
def relatorio_mensal():
    """O fechamento da competência: em tela, ou em PDF com ``?format=pdf``.

    A TELA e o PDF leem do mesmo ``analitico.fechamento_mensal`` — é o que
    impede o anexo do e-mail de discordar do que a diretoria acabou de ver
    na tela.

    RBAC: ``require_client`` resolve a carteira. Master passa; qualquer outro
    perfil só abre contrato que é dele, e o contrato de fora vira 403 antes
    de qualquer consulta.
    """
    from flask import abort, send_file

    from facilities.core.models import Client

    from facilities.core.acesso import require_client

    client_id = request.args.get('client_id', type=int)
    if not client_id:
        abort(400, 'Informe o contrato (client_id).')
    require_client(client_id)
    cliente = Client.query.get_or_404(client_id)

    hoje = tempo.hoje()

    def _competencia(nome, padrao, minimo, maximo):
        """Ausente → padrão. Presente e fora da régua → 400, não silêncio.

        ``or padrao`` não serve: ``?mes=0`` é falsy e viraria o mês corrente
        sem ninguém perceber que o pedido era outro.
        """
        bruto = (request.args.get(nome) or '').strip()
        if not bruto:
            return padrao
        try:
            valor = int(bruto)
        except ValueError:
            abort(400, 'Competência inválida.')
        if not minimo <= valor <= maximo:
            abort(400, 'Competência inválida.')
        return valor

    ano = _competencia('ano', hoje.year, 2000, hoje.year + 1)
    mes = _competencia('mes', hoje.month, 1, 12)

    # O relatório da Expedição e o do Almoxarifado são documentos diferentes,
    # com responsáveis diferentes. Sem o recorte sairia um só, com a média
    # dos dois — e média de coisas incomparáveis não diz nada a ninguém.
    areas = analitico.areas_do_contrato(client_id, apenas_ativas=False)
    area_id = request.args.get('area_id', type=int) or analitico.TODAS_AS_AREAS
    if area_id != analitico.TODAS_AS_AREAS and area_id not in [a.id for a in areas]:
        area_id = analitico.TODAS_AS_AREAS
    nome_da_area = next((a.nome for a in areas if a.id == area_id), '')

    rel = analitico.fechamento_mensal(client_id, ano, mes, hoje=hoje,
                                      area_id=area_id)
    rel['cliente'] = cliente.name
    rel['area'] = nome_da_area
    rel['emitido_em'] = tempo.agora()
    rel['emitido_por'] = current_user.name

    if (request.args.get('format') or '').lower() == 'pdf':
        from facilities.passagem import pdf as diario_pdf
        rotulo = cliente.name + (f' {nome_da_area}' if nome_da_area else '')
        limpo = ''.join(ch if ch.isalnum() else '-' for ch in rotulo)
        # "CD Eletro - PB" virava "CD-Eletro---PB": cada espaço e o traço do
        # meio davam um hífen. Hífens seguidos viram um só — o nome do arquivo
        # é o que se lê na pasta de downloads e no anexo do e-mail.
        limpo = re.sub(r'-{2,}', '-', limpo).strip('-')
        return send_file(
            diario_pdf.gerar(rel), mimetype='application/pdf',
            as_attachment=True,
            download_name=f'Passagem-de-Turno-{limpo}-{mes:02d}-{ano}.pdf')

    # Os 12 meses do seletor da tela, com o nome por extenso.
    meses = list(enumerate(MESES_LONGOS, start=1))
    # Os anos: até o seguinte (o servidor aceita, e em dezembro é o janeiro
    # que vem) e sempre o ano pedido. Sem a opção dele, o seletor mostrava
    # o primeiro da lista, e a próxima troca de mês ou de área — que envia o
    # formulário sozinha — levava o relatório para cinco anos atrás.
    anos = sorted(set(range(hoje.year - 4, hoje.year + 2)) | {ano})
    return render_template('diario_operacional/relatorio_mensal.html',
                           rel=rel, cliente=cliente, meses=meses, anos=anos,
                           mes=mes, ano=ano,
                           areas=[{'id': a.id, 'nome': a.nome} for a in areas],
                           area_sel=area_id,
                           todas_as_areas=analitico.TODAS_AS_AREAS)


# ─────────────────────────────────────────────────────────────────────────
# Anexo na observação da atividade — a prova que acompanha o turno
# ─────────────────────────────────────────────────────────────────────────

ANEXOS_POR_ENVIO = 8


_ENVIO_VALIDO = re.compile(r'^[A-Za-z0-9-]{8,64}$')


def envio_valido(valor):
    """A marca que o app põe em cada envio, ou ``None``.

    Só letras, números e hífen: ela vira parte do nome do arquivo guardado,
    então nada que o navegador mande pode escapar do formato.
    """
    valor = (valor or '').strip() if isinstance(valor, str) else ''
    return valor if _ENVIO_VALIDO.match(valor) else None


def _turno_autorizado(turno_id):
    """O turno, se ele é de um contrato da carteira de quem pede."""
    from facilities.core.acesso import require_client

    t = DiarioTurno.query.get_or_404(turno_id)
    require_client(t.client_id)
    return t


# ─────────────────────────────────────────────────────────────────────────
# A tarefa que a gestão manda para um turno
# ─────────────────────────────────────────────────────────────────────────
#
# O que faltava: o gestor do contrato sabia pedir a ROTINA (o checklist, que
# vale todo dia) e não sabia pedir a EXCEÇÃO — "no 2º turno de quinta,
# confira a temperatura da câmara depois da manutenção". Isso viajava por
# WhatsApp, e o que voltava era "ok", que não entra em série nenhuma.
#
# Três decisões moram aqui:
#
# 1. QUEM PEDE DIZ A FORMA DA RESPOSTA. Quem pede é quem sabe o que vai
#    fazer com o dado. "Ok" e "-18,4" custam o mesmo para digitar e valem
#    coisas completamente diferentes três meses depois.
# 2. O ENCARREGADO TEM DUAS SAÍDAS. Fez, ou virou pendência. Sem a segunda,
#    quem não conseguiu fazer só teria a opção de mentir ou deixar em
#    branco — e é o segundo caso que a gestão mais precisa enxergar.
# 3. "VIROU PENDÊNCIA" CRIA PENDÊNCIA DE VERDADE. Não um estado morto nesta
#    tabela: uma ``DiarioPendencia``, que atravessa turnos, entra na fila do
#    próximo encarregado e sobe para a Torre de Comando como qualquer outra.


# ─────────────────────────────────────────────────────────────────────────
# Avisos para o time de piso (sininho — e, por ele, o celular)
# ─────────────────────────────────────────────────────────────────────────
#
# O aviso entra na MESMA transação do que ele avisa: se a gravação falhar,
# não sai aviso de uma tarefa que não existe. E o celular recebe o que cai no
# sininho (ver trino/domains/notifications/application/despacho.py) — por
# isso aqui basta gravar a notificação.

JANELA_DO_PISO_DIAS = 30
LIMITE_DO_PISO = 50


# Os perfis que fazem a passagem no chão: o encarregado do posto e o técnico
# de manutenção, que passa o turno da equipe dele. No Trino o encarregado era
# o único perfil de piso; aqui, sem o técnico, o contrato de manutenção
# atendido só por técnicos não recebia aviso nenhum.
PERFIS_DO_PISO = ('encarregado', 'tecnico')


def _pode_receber(u, client_id):
    """Ativo, age na Passagem e tem o contrato HOJE — a régua de todo aviso.

    A carteira é a do ``require_client`` (``acesso.allowed_client_ids_or_none``):
    o administrador e quem tem "todos os contratos" passam; o resto, só com
    o contrato vinculado. Conferida na hora do envio, e não na hora em que a
    pessoa entrou na lista: quem lançou passagem semana passada e saiu do
    contrato ontem não pode continuar recebendo título de tarefa e de
    pendência de um contrato que já não abre.
    """
    from facilities.core.acesso import allowed_client_ids_or_none
    if u is None or not u.is_active or u.is_deleted:
        return False
    if not u.can_access(MODULO):
        return False
    permitidos = allowed_client_ids_or_none(u)
    return permitidos is None or int(client_id) in permitidos


def _time_do_piso(client_id, configuracao_id=None, exceto=None):
    """Quem está no chão desta operação: o pessoal de piso do contrato
    (encarregados e técnicos) e quem lançou passagem desta área nos últimos
    30 dias.

    Não há cadastro de "quem trabalha em qual turno" — então vale quem de
    fato lança. Um gestor que nunca lançou passagem não recebe aviso de piso.

    O piso "do contrato" é quem o tem na carteira: vinculado, ou com "todos
    os contratos" (o volante que cobre qualquer posto) — a mesma régua do
    ``require_client``, que já o deixa lançar em qualquer contrato.

    "Desta área" é a ÁREA do modelo, não o modelo: no CD com um modelo por
    turno, quem lança o T2 noutro modelo é justamente quem herda o que o T1
    deixou (a mesma régua de ``analitico.area_carrega``).
    """
    from datetime import timedelta
    from sqlalchemy import or_
    from facilities.core.models import User
    ids = set()
    piso = (User.query
            .filter(User.role.in_(PERFIS_DO_PISO),
                    or_(User.clients.any(id=client_id), User.all_clients.is_(True)),
                    User.is_active.is_(True), User.is_deleted.isnot(True))
            .all())
    ids |= {u.id for u in piso}
    desde = datetime.utcnow() - timedelta(days=JANELA_DO_PISO_DIAS)
    q = DiarioTurno.query.with_entities(DiarioTurno.created_by).filter(
        DiarioTurno.client_id == client_id, DiarioTurno.created_at >= desde)
    if configuracao_id:
        chaves = analitico.chaves_dos_modelos(client_id)
        alvo = chaves.get(configuracao_id)
        # O que a área do contrato deixa é de todas as áreas
        # (``analitico.area_carrega``): o aviso vai a quem lança em qualquer
        # uma, como o da pendência aberta pela gestão.
        if alvo != analitico.AREA_DO_CONTRATO:
            da_area = [cid for cid, ch in chaves.items() if ch == alvo] or [configuracao_id]
            q = q.filter(DiarioTurno.configuracao_id.in_(da_area))
    ids |= {uid for (uid,) in q.distinct().all() if uid}
    ids.discard(exceto)
    if ids:
        # Quem lançou no último mês só fica se AINDA tem o contrato (e
        # continua ativo): a lista de lançamentos lembra quem saiu.
        ids = {u.id for u in User.query.filter(User.id.in_(ids)).all()
               if _pode_receber(u, client_id)}
    return sorted(ids)[:LIMITE_DO_PISO]


def _ve_o_contrato(user_id, client_id):
    """Ativo, age na Passagem e tem o contrato — a mesma carteira do
    ``require_client`` (que honra "todos os contratos")."""
    from facilities.core.models import User
    return _pode_receber(db.session.get(User, user_id), client_id)


def _avisar(user_ids, titulo, mensagem, link, client_id):
    """Grava a notificação na sessão atual; o commit é de quem chamou.

    Só recebe quem tem o contrato HOJE (``_pode_receber``). A conferência
    mora AQUI, e não em cada chamador, para nenhum aviso novo esquecê-la: o
    gestor que pediu a tarefa e depois saiu do contrato também não pode
    continuar lendo a resposta do turno no sino.
    """
    from facilities.core.models import Notification, User
    ids = {uid for uid in user_ids if uid}
    if not ids:
        return
    for u in User.query.filter(User.id.in_(ids)).order_by(User.id).all():
        if _pode_receber(u, client_id):
            db.session.add(Notification(
                user_id=u.id, notification_type='passagem_turno',
                title=titulo[:150], message=mensagem, link=link, status='unread'))


def _link_do_turno(client_id):
    return f'/passagem-de-turno/turno?client_id={client_id}'


# ── Pendência parada ─────────────────────────────────────────────────────
#
# A pendência que atravessa turnos sem ninguém resolver é o que a gestão do
# contrato mais precisa ver — e o que ela menos vê, porque não está na
# passagem. Ao ENCERRAR um turno (é quando a pendência "atravessa" mais um),
# quem passou do limite avisa o responsável do contrato. Uma vez só, por
# pendência e por pessoa.
#
# A conta é a MESMA da tela ("passou por N turnos", em
# analitico.passagens_das_pendencias): turnos distintos na trilha, e só os
# da ÁREA de onde a pendência veio. Duas contas diferentes para a mesma
# frase dariam aviso de "3 turnos" com a tela dizendo 2. E a conta por área
# é o que impede o falso alarme: num contrato com três áreas, um único 1º
# Turno (uma passagem de cada área) já somava três, e o aviso saía sem que
# a Expedição tivesse deixado a pendência dela parada turno nenhum.

TURNOS_PARA_AVISAR_PARADA = 3
# Teto de sanidade, não recorte: todos os plenos do contrato recebem. Um
# limite baixo, escolhido pela ordem de cadastro, deixaria de fora o gestor
# de verdade e avisaria quem entrou primeiro no sistema.
LIMITE_GESTORES_AVISADOS = LIMITE_DO_PISO


def _gestores_do_contrato(client_id):
    """Quem responde pelo contrato: o responsável cadastrado nele; sem
    responsável, os plenos vinculados. Nunca "todos os Masters" — o Master é
    global e receberia a pendência parada de todos os contratos da casa.

    O responsável vale se ainda enxerga o contrato pela régua do
    ``require_client`` — o gestor regional com "todos os contratos" é
    responsável de verdade, e antes ficava de fora por não ter o vínculo
    explícito. Já na falta de responsável entram só os VINCULADOS: o regional
    receberia o aviso de todos os contratos da casa, a mesma conta que os
    chamados fazem (``chamados.servico.gestores_do_contrato``)."""
    from facilities.core.models import Client, User
    cli = Client.query.get(client_id)
    if cli is not None and cli.responsible_user_id and \
            _ve_o_contrato(cli.responsible_user_id, client_id):
        return [cli.responsible_user_id]
    plenos = (User.query
              .filter(User.clients.any(id=client_id), User.role == 'pleno',
                      User.is_active.is_(True), User.is_deleted.isnot(True))
              .order_by(User.id).limit(LIMITE_GESTORES_AVISADOS).all())
    return [u.id for u in plenos]


def link_da_pendencia(client_id, pendencia_id):
    return f'/passagem-de-turno/turno?client_id={client_id}#pendencia-{pendencia_id}'


def _avisar_pendencias_paradas(client_id):
    """Chamado no encerramento do turno, depois de registrada a passagem."""
    from facilities.core.models import Notification
    db.session.flush()
    abertas = DiarioPendencia.query.filter_by(client_id=client_id, status='aberta').all()
    if not abertas:
        return
    passagens = analitico.passagens_das_pendencias(abertas)
    paradas = [p for p in abertas if passagens.get(p.id, 0) >= TURNOS_PARA_AVISAR_PARADA]
    if not paradas:
        return
    gestores = [g for g in _gestores_do_contrato(client_id) if g != current_user.id]
    if not gestores:
        return
    links = {p.id: link_da_pendencia(client_id, p.id) for p in paradas}
    ja = {(n.user_id, n.link) for n in Notification.query.filter(
        Notification.user_id.in_(gestores), Notification.link.in_(list(links.values())))}
    for p in paradas:
        n_turnos = passagens[p.id]
        aberta = tempo.fmt(p.created_at, '%d/%m')   # no fuso de Brasília
        for g in gestores:
            if (g, links[p.id]) in ja:
                continue
            _avisar([g], f'Pendência parada há {n_turnos} turnos: {p.titulo}',
                    f'Aberta em {aberta}, prioridade '
                    f'{analitico.rotulo_prioridade(p.prioridade).lower()}. Passou por '
                    f'{n_turnos} passagens sem solução — veja a trilha e cobre um dono.',
                    links[p.id], client_id)


def _gestor_do_contrato():
    """Quem atribui tarefa a turno: master e pleno, não o piso.

    O encarregado não se manda tarefa — a assimetria é o ponto do recurso.
    """
    return current_user.is_authenticated and current_user.sees_client_data()


@bp.post('/api/tarefas-turno')
@login_required
@module_required(MODULO)
def criar_tarefa_turno():
    """O gestor atribui: área, data, turno, o que fazer e como responder."""
    from facilities.passagem.models import (
        DiarioTarefaTurno, FORMAS_DE_RESPOSTA, RESPOSTA_SIM_NAO)

    if not _gestor_do_contrato():
        return jsonify({'error': 'Só a gestão do contrato atribui tarefa a '
                                 'turno.'}), 403

    data = request.get_json(silent=True) or {}
    try:
        client_id = int(data.get('client_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Contrato inválido.'}), 400
    _client_allowed(client_id)

    cfg = DiarioConfiguracao.query.get_or_404(int(data.get('configuracao_id')))
    if cfg.client_id != client_id or not cfg.ativo:
        return jsonify({'error': 'Área inválida para este contrato.'}), 400

    titulo = (data.get('titulo') or '').strip()
    if not titulo:
        return jsonify({'error': 'Escreva o que precisa ser feito no turno.'}), 400
    turno_nome = (data.get('turno') or '').strip()
    if not turno_nome:
        return jsonify({'error': 'Informe o turno.'}), 400
    try:
        dia = date.fromisoformat(str(data.get('data_turno'))[:10])
    except ValueError:
        return jsonify({'error': 'Data do turno inválida.'}), 400

    # Tarefa para uma passagem já ENCERRADA não tem quem a responda: a tela
    # do turno não volta a abrir para ela, e a tarefa ficaria "pendente" para
    # sempre — o gestor achando que pediu, o piso sem nunca ter visto. A
    # chave é a mesma da passagem: contrato, MODELO, dia e turno.
    encerrada = (DiarioTurno.query
                 .filter_by(client_id=client_id, configuracao_id=cfg.id,
                            data_turno=dia, turno=turno_nome,
                            status='encerrado')
                 .first())
    if encerrada is not None:
        return jsonify({'error': 'Esse turno já foi encerrado — escolha '
                                 'outro.'}), 409

    forma = (data.get('forma_resposta') or '').strip()
    if forma not in FORMAS_DE_RESPOSTA:
        forma = RESPOSTA_SIM_NAO

    t = DiarioTarefaTurno(
        client_id=client_id, configuracao_id=cfg.id, data_turno=dia,
        turno=turno_nome, titulo=titulo[:300],
        descricao=(data.get('descricao') or '').strip() or None,
        forma_resposta=forma, criada_por=current_user.id)
    db.session.add(t)
    _avisar(_time_do_piso(client_id, cfg.id, exceto=current_user.id),
            f'Tarefa para o {turno_nome} de {dia.strftime("%d/%m")}',
            t.titulo, _link_do_turno(client_id), client_id)
    db.session.commit()
    return jsonify({'ok': True, 'id': t.id}), 201


def _tarefas_do_turno(client_id, configuracao_id, dia, turno_nome):
    """O que a gestão mandou para ESTA passagem. Uma consulta."""
    from facilities.passagem.models import (
        DiarioTarefaTurno)
    if not (client_id and configuracao_id and dia and turno_nome):
        return []
    return (DiarioTarefaTurno.query
            .filter_by(client_id=client_id, configuracao_id=configuracao_id,
                       data_turno=dia, turno=turno_nome)
            .order_by(DiarioTarefaTurno.id).all())


@bp.get('/api/tarefas-turno')
@login_required
@module_required(MODULO)
def listar_tarefas_turno():
    """As tarefas de um turno — a tela do encarregado busca por aqui.

    É um GET e não parte do HTML porque a passagem escolhe área, data e
    turno DEPOIS de a página carregar: renderizar no servidor exigiria
    recarregar a tela a cada troca de área.
    """
    from facilities.passagem.models import (
        FORMAS_DE_RESPOSTA)
    client_id = request.args.get('client_id', type=int)
    if not client_id:
        return jsonify({'tarefas': []})
    _client_allowed(client_id)
    try:
        dia = date.fromisoformat((request.args.get('data_turno') or '')[:10])
    except ValueError:
        return jsonify({'tarefas': []})

    lista = _tarefas_do_turno(client_id,
                              request.args.get('configuracao_id', type=int),
                              dia, (request.args.get('turno') or '').strip())
    return jsonify({'tarefas': [
        {'id': t.id, 'titulo': t.titulo, 'descricao': t.descricao or '',
         'forma_resposta': t.forma_resposta,
         'forma_rotulo': FORMAS_DE_RESPOSTA.get(t.forma_resposta, ''),
         'status': t.status, 'resposta': t.resposta or ''}
        for t in lista]})


@bp.post('/api/tarefas-turno/<int:tarefa_id>/responder')
@login_required
@module_required(MODULO)
def responder_tarefa_turno(tarefa_id):
    """Fez (com a resposta) ou virou pendência (que nasce de verdade)."""
    from facilities.passagem.models import (
        DiarioTarefaTurno, TAREFA_TURNO_PENDENTE, TAREFA_TURNO_FEITA,
        TAREFA_TURNO_VIROU_PENDENCIA, RESPOSTA_SIM_NAO, RESPOSTA_NUMERO)

    t = DiarioTarefaTurno.query.get_or_404(tarefa_id)
    _client_allowed(t.client_id)
    if t.status != TAREFA_TURNO_PENDENTE:
        return jsonify({'error': 'Esta tarefa já foi respondida.'}), 409

    data = request.get_json(silent=True) or {}
    virou = bool(data.get('virou_pendencia'))
    texto = (data.get('resposta') or '').strip()

    if virou:
        # O motivo é obrigatório aqui pela mesma razão de sempre: "não deu"
        # sem dizer o que houve não ajuda o turno seguinte em nada.
        if not texto:
            return jsonify({'error': 'Diga por que não foi possível fazer.'}), 400
        # Se a passagem desta chave já existe (o rascunho salvo mais cedo), a
        # pendência nasce LIGADA a ela: é dali que ela veio, e é assim que
        # aparece em "Pendências deixadas", com origem, em vez de cair na
        # fila como se a gestão a tivesse aberto. Sem passagem ainda, fica
        # sem turno — e o encerramento faz a ligação (`_tarefas_no_encerramento`).
        passagem = (DiarioTurno.query
                    .filter_by(client_id=t.client_id,
                               configuracao_id=t.configuracao_id,
                               data_turno=t.data_turno, turno=t.turno)
                    .order_by(DiarioTurno.id.desc()).first())
        p = DiarioPendencia(
            client_id=t.client_id, titulo=t.titulo[:200],
            turno_id=passagem.id if passagem is not None else None,
            descricao=f'Tarefa da gestão que não pôde ser feita no '
                      f'{t.turno} de {t.data_turno.strftime("%d/%m/%Y")}.\n\n'
                      f'{texto}',
            prioridade='alta', created_by=current_user.id)
        db.session.add(p)
        db.session.flush()
        t.pendencia_id = p.id
        t.status = TAREFA_TURNO_VIROU_PENDENCIA
    else:
        if not texto:
            return jsonify({'error': 'Responda antes de marcar como feita.'}), 400
        if t.forma_resposta == RESPOSTA_NUMERO:
            # Só confere que HÁ número: a operação escreve "-18,4 na sonda 2",
            # e recusar isso faria a pessoa apagar o contexto para passar.
            if not re.search(r'-?\d', texto):
                return jsonify({'error': 'Esta tarefa pede um número na '
                                         'resposta.'}), 400
        if t.forma_resposta == RESPOSTA_SIM_NAO:
            if texto.strip().lower() not in ('sim', 'não', 'nao'):
                return jsonify({'error': 'Responda sim ou não.'}), 400
        t.status = TAREFA_TURNO_FEITA

    t.resposta = texto
    t.respondida_por = current_user.id
    t.respondida_em = datetime.utcnow()
    if t.criada_por and t.criada_por != current_user.id:
        # Fecha o laço: quem pediu fica sabendo sem precisar abrir a tela.
        _avisar([t.criada_por],
                ('Tarefa virou pendência: ' if virou else 'Tarefa feita: ') + t.titulo,
                f'{t.turno} de {t.data_turno.strftime("%d/%m")} — {texto[:200]}',
                f'/passagem-de-turno/?client_id={t.client_id}', t.client_id)
    db.session.commit()
    return jsonify({'ok': True, 'id': t.id, 'status': t.status,
                    'pendencia_id': t.pendencia_id})


# A resposta que fica gravada na tarefa que o turno encerrou sem responder.
# É texto e não um status novo de propósito: o desfecho É "virou pendência"
# (a pendência existe e atravessa turnos), e um quarto status obrigaria toda
# tela que lê a tarefa a aprender um caso a mais para dizer a mesma coisa.
RESPOSTA_NAO_RESPONDIDA = 'Não respondida no turno'


def _tarefas_no_encerramento(t):
    """O que a gestão pediu para esta passagem, acertado no encerramento.

    Duas coisas, ambas pela chave da passagem (contrato, modelo, dia e turno):

    1. **A pendência do "Não deu" que ficou sem turno.** Respondida antes de
       a passagem existir no banco (o encarregado ainda não tinha salvo
       nada), ela nasceu sem turno de origem — e caía na fila como se a
       gestão a tivesse aberto: sem origem, fora de "Pendências deixadas" e
       fora da conta do aviso de prioridade alta. Ela é DESTE turno, e ganha
       o vínculo agora. Só a que está sem turno: origem já gravada não muda
       de dono.
    2. **A tarefa que ninguém respondeu.** Encerrar sem dizer "fiz" nem "não
       deu" deixava a tarefa "pendente" para sempre, numa passagem que não
       volta a abrir — o gestor achando que pediu, ninguém cobrando. Ela
       vira pendência de prioridade ALTA deste turno (o pedido continua de
       pé para o turno seguinte), e quem pediu fica sabendo.

    A tela pede confirmação antes de encerrar assim, mas quem decide é o
    servidor: o encerramento que chega pela fila do aparelho, horas depois,
    não passou pela tela e precisa do mesmo desfecho.

    O commit é de quem chamou — tudo entra na transação do encerramento.
    """
    from facilities.passagem.models import (
        TAREFA_TURNO_PENDENTE, TAREFA_TURNO_VIROU_PENDENCIA)

    tarefas = _tarefas_do_turno(t.client_id, t.configuracao_id,
                                t.data_turno, t.turno)
    if not tarefas:
        return

    ids = [x.pendencia_id for x in tarefas if x.pendencia_id]
    if ids:
        for p in (DiarioPendencia.query
                  .filter(DiarioPendencia.id.in_(ids),
                          DiarioPendencia.turno_id.is_(None)).all()):
            p.turno_id = t.id

    dia_longo = t.data_turno.strftime('%d/%m/%Y')
    dia_curto = t.data_turno.strftime('%d/%m')
    for x in tarefas:
        if x.status != TAREFA_TURNO_PENDENTE:
            continue
        descricao = (f'A gestão pediu esta tarefa para o {t.turno} de '
                     f'{dia_longo}, e o turno foi encerrado sem resposta — '
                     f'nem "fiz", nem "não deu". O pedido continua de pé.')
        if (x.descricao or '').strip():
            descricao += f'\n\nO pedido: {x.descricao.strip()}'
        p = DiarioPendencia(
            client_id=t.client_id, turno_id=t.id,
            titulo=f'Tarefa não respondida: {x.titulo}'[:200],
            descricao=descricao, prioridade='alta',
            created_by=current_user.id)
        db.session.add(p)
        db.session.flush()
        x.pendencia_id = p.id
        x.status = TAREFA_TURNO_VIROU_PENDENCIA
        x.resposta = RESPOSTA_NAO_RESPONDIDA
        # `respondida_por`/`respondida_em` ficam vazios: ninguém respondeu.
        # Quem encerrou está na pendência (`created_by`), com a hora.
        if x.criada_por and x.criada_por != current_user.id:
            # O mesmo canal da resposta da tarefa ("Tarefa feita: …"): quem
            # pediu fecha o laço sem precisar abrir a tela.
            _avisar([x.criada_por], f'Tarefa não respondida: {x.titulo}',
                    f'{t.turno} de {dia_curto} encerrado sem resposta — virou '
                    f'pendência de prioridade alta.',
                    f'/passagem-de-turno/?client_id={t.client_id}', t.client_id)
    db.session.flush()


# ── A hora do aparelho ───────────────────────────────────────────────────
#
# Sem sinal, o encerramento vai para a fila do aparelho e só chega quando a
# conexão volta — às vezes horas depois. O `submitted_at` é a hora de
# CHEGADA: é a da auditoria e não muda. O que faltava era a outra, a hora em
# que a pessoa tocou em "Encerrar", para a tela não acusar de atraso quem
# fechou o turno na hora certa num corredor sem 4G.
#
# A hora do aparelho é do APARELHO, e relógio de celular erra (bateria
# trocada, fuso manual, data de 2001). Por isso ela é conferida contra a de
# chegada e, fora da janela, simplesmente não é guardada — o encerramento
# NUNCA é recusado por causa dela: recusar faria a passagem de quem tem o
# relógio errado não entrar nunca.

CHAVE_ENCERRADO_NO_APARELHO = '_encerrado_no_aparelho'
APARELHO_ADIANTADO_MAX_MIN = 5
APARELHO_ATRASADO_MAX_H = 72
# Abaixo disso a diferença é a viagem normal do envio, não uma fila: a tela
# mostra só a hora de encerramento, como sempre mostrou.
APARELHO_DIFERENCA_VISIVEL_MIN = 5


def hora_do_aparelho(bruto, chegada=None):
    """O ISO que o aparelho mandou → ISO em UTC, ou ``None`` se não serve.

    Serve se: é uma data ISO com fuso, não está mais de 5 minutos à frente
    da chegada (relógio adiantado) e não está mais de 72 horas atrás dela
    (relógio parado ou com a data errada: uma passagem não espera três dias
    na fila). Hora sem fuso é recusada: "06:10" sem dizer de onde não diz
    que horas eram.
    """
    from datetime import timedelta, timezone

    if not isinstance(bruto, str) or not bruto.strip():
        return None
    texto = bruto.strip()[:40]
    if texto[-1:] in ('Z', 'z'):
        texto = texto[:-1] + '+00:00'
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    ref = chegada or datetime.utcnow()
    try:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)
        if dt > ref + timedelta(minutes=APARELHO_ADIANTADO_MAX_MIN):
            return None
        if dt < ref - timedelta(hours=APARELHO_ATRASADO_MAX_H):
            return None
        return dt.replace(tzinfo=timezone.utc).isoformat()
    except (OverflowError, ValueError):
        # "0001-01-01T00:00:00+05:00" passa no fromisoformat e estoura na
        # conversão para UTC: relógio absurdo é hora inválida, não erro 500
        # no encerramento — a passagem tem de entrar mesmo assim.
        return None


@bp.app_template_global('encerramento_no_aparelho')
def encerramento_no_aparelho(turno):
    """Para o cabeçalho da passagem: as duas horas, quando a fila as separou.

    Devolve ``None`` quando não há hora do aparelho guardada ou quando ela
    bate com a chegada (até 5 min) — aí a tela segue com a linha de sempre.
    ``mesmo_dia`` diz se dá para escrever só HH:MM: a fila que atravessou a
    meia-noite precisa da data, senão "22:10 · chegou às 07:05" parece o
    contrário do que foi.
    """
    from datetime import timedelta, timezone

    if turno is None or turno.submitted_at is None:
        return None
    dados = _json(turno.dados_json, {})
    bruto = dados.get(CHAVE_ENCERRADO_NO_APARELHO) if isinstance(dados, dict) else None
    if not bruto:
        return None
    try:
        dt = datetime.fromisoformat(str(bruto))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    chegada = turno.submitted_at
    if abs(chegada - dt) <= timedelta(minutes=APARELHO_DIFERENCA_VISIVEL_MIN):
        return None
    return {'aparelho': dt, 'chegada': chegada,
            'mesmo_dia': tempo.local(dt).date() == tempo.local(chegada).date()}


# ─────────────────────────────────────────────────────────────────────────
# Corrigir a passagem já encerrada
# ─────────────────────────────────────────────────────────────────────────
#
# O dilema, em uma frase: a passagem encerrada é a PROVA do que foi
# informado ao turno seguinte, e quem lançou no turno errado às 6h da manhã
# não pode ficar com o erro para sempre.
#
# Liberar a edição destrói a prova — passaria a dar para reescrever ontem.
# Travar tudo ensina a operação a não registrar, porque registrar errado
# passa a ser pior do que não registrar. A saída é a terceira: CORRIGE-SE
# COM RASTRO. O valor novo vale, o antigo fica guardado em
# ``DiarioTurnoCorrecao``, e a tela diz que houve correção.

CAMPOS_CORRIGIVEIS = ('data_turno', 'turno', 'observacao', 'dados')


def _janela_de_correcao_aberta(t):
    """Ainda dá para corrigir? Só até o turno SEGUINTE ser encerrado.

    Depois disso os números desta passagem já alimentaram o painel, já
    subiram para a Torre de Comando e alguém já agiu em cima deles — mudar a
    base por baixo de uma decisão tomada é pior do que conviver com o erro.

    A conta é pelo ``submitted_at`` do mesmo contrato e MESMO MODELO: a
    Expedição e o Almoxarifado passam turno em paralelo, e o fechamento de
    uma não pode fechar a janela da outra.
    """
    posterior = DiarioTurno.query.filter(
        DiarioTurno.client_id == t.client_id,
        DiarioTurno.configuracao_id == t.configuracao_id,
        DiarioTurno.id != t.id,
        DiarioTurno.status == 'encerrado')
    if t.submitted_at is not None:
        posterior = posterior.filter(
            DiarioTurno.submitted_at.isnot(None),
            DiarioTurno.submitted_at > t.submitted_at)
    else:
        # Passagem antiga, de antes do carimbo: cai na ordem de criação.
        posterior = posterior.filter(DiarioTurno.id > t.id)
    return posterior.first() is None


@bp.post('/api/turnos/<int:turno_id>/corrigir')
@login_required
@module_required(MODULO)
def corrigir_turno(turno_id):
    """Corrige a passagem encerrada — só o autor, e só com motivo.

    **Só o autor, sem exceção — nem o master.** Foi decisão do dono do
    produto, tomada sabendo o preço: se o encarregado sair da empresa, o erro
    dele fica. Em troca, o que está escrito na passagem foi escrito por quem
    a assina, e isso é o que faz o documento valer numa discussão com o
    cliente. Quem mexer nisto depois, mexa sabendo que o preço foi escolhido.

    NÃO alcança pendência nem ocorrência já lançadas. Elas seguem as regras
    do próprio módulo: a devolução que a Tarde já baixou não pode sumir
    porque a Manhã corrigiu a passagem — a baixa dela sumiria junto.

    Mudou o dia ou o turno: a passagem passa a ser a encerrada da NOVA
    chave, e o que a gestão pediu para ela é acertado como no encerramento
    (``_tarefas_no_encerramento``) — o "Não deu" sem turno daquela chave
    ganha a origem e a tarefa sem resposta vira pendência. Sem isto, o
    encarregado que encerrou como 2º Turno e corrigiu para o 1º deixava o
    "Não deu" do 1º sem passagem e a tarefa dele pendente para sempre.
    """
    from facilities.core.acesso import require_client
    from facilities.passagem.models import (
        DiarioTurnoCorrecao)

    t = DiarioTurno.query.get_or_404(turno_id)
    require_client(t.client_id)

    if t.created_by != current_user.id:
        return jsonify({'error': 'Só quem lançou a passagem pode corrigi-la. '
                                 'Peça a correção a quem a encerrou.'}), 403
    if t.status != 'encerrado':
        return jsonify({'error': 'Esta passagem ainda está em rascunho — '
                                 'edite-a normalmente.'}), 409
    if not _janela_de_correcao_aberta(t):
        return jsonify({'error': 'O turno seguinte já foi encerrado, e os '
                                 'números desta passagem já alimentaram o '
                                 'painel. Registre o acerto numa ocorrência '
                                 'do turno de hoje.'}), 409

    data = request.get_json(silent=True) or {}
    motivo = (data.get('motivo') or '').strip()
    if not motivo:
        return jsonify({'error': 'Diga em uma linha o que estava errado.'}), 400

    antes, campos = {}, []

    nova_data, novo_turno = t.data_turno, t.turno
    if data.get('data_turno'):
        try:
            nova_data = date.fromisoformat(str(data['data_turno'])[:10])
        except ValueError:
            return jsonify({'error': 'Data do turno inválida.'}), 400
    if (data.get('turno') or '').strip():
        novo_turno = data['turno'].strip()

    if (nova_data, novo_turno) != (t.data_turno, t.turno):
        # Mover para cima de uma passagem que já existe fundiria duas
        # realidades numa linha só.
        choque = (DiarioTurno.query
                  .filter(DiarioTurno.client_id == t.client_id,
                          DiarioTurno.configuracao_id == t.configuracao_id,
                          DiarioTurno.data_turno == nova_data,
                          DiarioTurno.turno == novo_turno,
                          DiarioTurno.id != t.id).first())
        if choque is not None:
            return jsonify({'error': f'Já existe passagem de {novo_turno} em '
                                     f'{nova_data.strftime("%d/%m/%Y")} neste '
                                     f'modelo.'}), 409
        if nova_data != t.data_turno:
            antes['data_turno'] = t.data_turno.isoformat()
            campos.append('data')
            t.data_turno = nova_data
        if novo_turno != t.turno:
            antes['turno'] = t.turno
            campos.append('turno')
            t.turno = novo_turno

    if 'observacao' in data:
        nova = (data.get('observacao') or '').strip()
        if nova != (t.observacao or ''):
            antes['observacao'] = t.observacao or ''
            campos.append('observação')
            t.observacao = nova

    if isinstance(data.get('dados'), dict):
        novos = data['dados']
        antigos = _json(t.dados_json, {})
        # A régua congelada é do SERVIDOR e não se corrige: ela registra o
        # que era exigido no dia, e reescrevê-la mudaria a nota do turno
        # sem que ninguém tivesse feito nada diferente.
        congelada = antigos.get(analitico.CHAVE_EXIGIDAS)
        if congelada is not None:
            novos = dict(novos)
            novos[analitico.CHAVE_EXIGIDAS] = congelada
        # A marca do envio também é do servidor: sem ela, um reenvio atrasado
        # do celular, chegando depois da correção, viraria um falso conflito.
        # A hora do aparelho idem: é o que o celular disse no toque de
        # encerrar, e uma correção não pode apagá-la nem forjá-la.
        novos = dict(novos)
        for chave in (analitico.CHAVE_ENVIO, CHAVE_ENCERRADO_NO_APARELHO):
            novos.pop(chave, None)
            if antigos.get(chave) is not None:
                novos[chave] = antigos[chave]
        if novos != antigos:
            antes['dados'] = t.dados_json
            campos.append('respostas')
            t.dados_json = json.dumps(novos, ensure_ascii=False)

    if not campos:
        return jsonify({'error': 'Nada mudou nesta correção.'}), 400

    db.session.add(DiarioTurnoCorrecao(
        turno_id=t.id, motivo=motivo, campos=', '.join(campos)[:200],
        antes_json=json.dumps(antes, ensure_ascii=False),
        created_by=current_user.id))
    if 'data' in campos or 'turno' in campos:
        db.session.flush()
        _tarefas_no_encerramento(t)
    db.session.commit()
    return jsonify({'ok': True, 'id': t.id, 'campos': campos})


@bp.post('/api/turnos/<int:turno_id>/anexos')
@login_required
@module_required(MODULO)
def anexar_no_turno(turno_id):
    """Imagem ou PDF preso à observação de uma atividade do turno.

    "O 5S não foi feito" é uma frase; a foto da rua bagunçada é a prova. No
    armazém a segunda é o que encerra a discussão na reunião seguinte.

    A validação é a MESMA dos anexos de ação e de SLA — extensão na lista,
    assinatura de bytes conferida e limite de tamanho —, importada de lá em
    vez de reescrita: renomear um executável para .pdf não pode colocá-lo no
    armazenamento, e essa regra não pode ter duas versões na casa.

    ``atividade`` é o código da linha do checklist. Vazio = observação geral
    do turno.

    **Quem anexa: o autor da passagem, ou a gestão do contrato.** A passagem
    é o documento que o autor assina; antes, qualquer colega do contrato
    prendia uma "prova" na linha "Varrer" da passagem encerrada de outro, e a
    tela a mostrava como parte do documento. O autor continua anexando
    DEPOIS de encerrar: sem sinal, as fotos sobem pela fila do aparelho só
    depois do encerramento — recusar ali perderia a prova de quem fez certo.
    """
    import uuid

    from flask import current_app as flask_app
    from werkzeug.utils import secure_filename

    from facilities.core.anexos import (ANEXO_ASSINATURA as _ACAO_ANEXO_ASSINATURA,
                                         ANEXO_MAX as ACAO_ANEXO_MAX,
                                         ANEXO_TIPOS as ACAO_ANEXO_TIPOS, storage)
    _storage = storage()

    t = _turno_autorizado(turno_id)
    if t.created_by != current_user.id and not current_user.sees_client_data():
        return jsonify({'error': 'Só quem lançou esta passagem, ou a gestão do '
                                 'contrato, pode anexar fotos e arquivos a ela.'}), 403
    arquivos = [f for f in request.files.getlist('arquivo') if f and f.filename]
    if not arquivos:
        return jsonify({'error': 'Escolha ao menos um arquivo.'}), 400
    if len(arquivos) > ANEXOS_POR_ENVIO:
        return jsonify({'error': f'São {len(arquivos)} arquivos e o limite por '
                                 f'envio é {ANEXOS_POR_ENVIO}.'}), 400

    atividade = (request.form.get('atividade') or '').strip()[:120] or None
    # Com a marca do envio, o nome do arquivo guardado deixa de ser sorteado e
    # passa a ser previsível — é isso que deixa reenviar sem duplicar: o
    # celular que perdeu a resposta manda de novo, e o arquivo que já está
    # aqui é reconhecido pelo nome.
    envio = envio_valido(request.form.get('envio'))

    gravados, recusados, ja_estavam = [], [], []

    def recusar(nome, motivo, http=400):
        recusados.append({'nome': nome, 'motivo': motivo, 'http': http})

    for posicao, f in enumerate(arquivos):
        nome = secure_filename(f.filename) or 'arquivo'
        ext = nome.rsplit('.', 1)[-1].lower() if '.' in nome else ''
        if ext not in ACAO_ANEXO_TIPOS:
            recusar(nome, 'Tipo não aceito. Vale PDF e imagem (png, jpg, webp)')
            continue
        if envio:
            chave = f'diario/anexos/t{t.id}_{envio}_{posicao}.{ext}'
            existente = DiarioAnexo.query.filter_by(turno_id=t.id,
                                                    storage_key=chave).first()
            if existente is not None:
                ja_estavam.append(existente)
                continue
        else:
            chave = f'diario/anexos/t{t.id}_{uuid.uuid4().hex}.{ext}'
        dados = f.read()
        if not dados:
            recusar(nome, 'O arquivo está vazio')
            continue
        if len(dados) > ACAO_ANEXO_MAX:
            recusar(nome, f'O arquivo excede {ACAO_ANEXO_MAX // (1024 * 1024)} MB')
            continue
        assinaturas = _ACAO_ANEXO_ASSINATURA.get(ext)
        if assinaturas and not any(dados.startswith(a) for a in assinaturas):
            recusar(nome, f'O conteúdo do arquivo não é um {ext.upper()} de verdade')
            continue

        try:
            _storage.save(chave, dados, content_type=ACAO_ANEXO_TIPOS[ext])
        except Exception:
            flask_app.logger.exception(
                'falha ao gravar anexo do turno %s', t.id)
            recusar(nome, 'Não foi possível guardar o arquivo. Tente de novo',
                    http=502)
            continue

        a = DiarioAnexo(turno_id=t.id, atividade_codigo=atividade,
                        storage_key=chave, nome=nome[:200],
                        mime=ACAO_ANEXO_TIPOS[ext], tamanho=len(dados),
                        uploaded_by=current_user.id)
        db.session.add(a)
        gravados.append(a)

    if gravados:
        db.session.commit()
    if not gravados and not ja_estavam:
        # Um arquivo só: a frase do motivo é a resposta inteira, como nas
        # outras telas de anexo da casa.
        unico = recusados[0]
        return jsonify({'error': unico['motivo'] + '.'}), unico['http']

    return jsonify({'ok': True,
                    'anexos': [a.to_dict() for a in gravados + ja_estavam],
                    'repetidos': len(ja_estavam),
                    'recusados': [{'nome': r['nome'], 'motivo': r['motivo']}
                                  for r in recusados]}), 201


@bp.get('/anexos/<int:anexo_id>')
@login_required
@module_required(MODULO)
def baixar_anexo(anexo_id):
    """O arquivo em si. A carteira manda aqui como manda no resto."""
    import io

    from flask import send_file

    from facilities.core.anexos import storage

    _storage = storage()

    a = DiarioAnexo.query.get_or_404(anexo_id)
    _turno_autorizado(a.turno_id)
    try:
        dados = _storage.load(a.storage_key)
    except Exception:
        return jsonify({'error': 'Arquivo não encontrado no armazenamento.'}), 404
    # Imagem abre no navegador (é o que se quer ao conferir a foto do 5S);
    # o resto desce como anexo.
    inline = (a.mime or '').startswith('image/')
    return send_file(io.BytesIO(dados), mimetype=a.mime or 'application/octet-stream',
                     as_attachment=not inline, download_name=a.nome)


@bp.delete('/anexos/<int:anexo_id>')
@login_required
@module_required(MODULO)
def excluir_anexo(anexo_id):
    """Remove o anexo — no rascunho, quem subiu ou o administrador; na
    passagem encerrada, só o administrador.

    Apagar é apagar: foto trocada ou do turno errado precisa sumir, e deixar
    "inativa" manteria a prova errada à vista de quem consulta.

    Mas a passagem ENCERRADA é o documento assinado (corrigir é só com
    motivo e trilha, em ``corrigir_turno``): apagar a foto dela, sem rastro,
    seria reescrever o que foi entregue ao turno seguinte. Ali só o
    administrador apaga — o caso real é a foto errada que alguém precisa
    tirar do ar, e é a ele que a recusa manda pedir.
    """
    from flask import current_app as flask_app

    from facilities.core.anexos import storage
    _storage = storage()

    a = DiarioAnexo.query.get_or_404(anexo_id)
    t = _turno_autorizado(a.turno_id)
    administrador = current_user._effective_role() == 'master'
    if t.status == 'encerrado' and not administrador:
        return jsonify({'error': 'Esta passagem já foi encerrada, e o anexo faz '
                                 'parte dela. Se a foto está errada, peça ao '
                                 'administrador para excluir.'}), 403
    if a.uploaded_by != current_user.id and not administrador:
        return jsonify({'error': 'Só quem anexou (ou o administrador) pode '
                                 'excluir.'}), 403
    chave = a.storage_key
    db.session.delete(a)
    db.session.commit()
    try:
        _storage.delete(chave)
    except Exception:
        # O registro já saiu; o arquivo órfão no storage é problema menor do
        # que devolver erro para quem viu o anexo sumir da tela.
        flask_app.logger.warning('anexo %s removido do banco, arquivo %s ficou',
                                 anexo_id, chave)
    return jsonify({'ok': True, 'id': anexo_id})


@bp.post('/api/ocorrencias/<int:ocorrencia_id>/chamado')
@login_required
@module_required(MODULO)
def abrir_chamado(ocorrencia_id):
    """Ocorrência da passagem → chamado de manutenção, sem redigitar nada.

    É a mesma porta da tela de chamados (``chamados.servico``): contrato,
    área do modelo, descrição e referência vêm da ocorrência; a crítica entra
    com prioridade alta. Idempotente — o botão fica numa lista que o gestor
    relê todo dia, e o segundo clique leva ao chamado do primeiro.

    As recusas saem SEMPRE em JSON, com a frase para a tela: o botão do painel
    lê a resposta como JSON, e um 403 em HTML deixava o botão desabilitado
    sem mensagem nenhuma. A recusa por regra do chamado (``RecusaChamado`` —
    por exemplo, a ocorrência de uma passagem ainda em rascunho) leva o
    status que o serviço decidiu.
    """
    from facilities.core.acesso import allowed_client_ids_or_none
    from facilities.chamados import servico as chamados

    o = db.session.get(DiarioOcorrencia, ocorrencia_id)
    if o is None:
        return jsonify({'error': 'Ocorrência não encontrada. A tela pode estar '
                                 'desatualizada: recarregue a página.'}), 404
    permitidos = allowed_client_ids_or_none()
    if permitidos is not None and o.client_id not in permitidos:
        return jsonify({'error': 'Esta ocorrência é de um contrato que não está '
                                 'entre os seus contratos.'}), 403
    if not current_user.can_access('chamados'):
        return jsonify({'error': 'Seu perfil não abre chamado.'}), 403
    try:
        ch, criado = chamados.abrir_de_ocorrencia(current_user, o)
    except chamados.RecusaChamado as ex:
        db.session.rollback()
        return jsonify({'error': ex.mensagem}), ex.status
    db.session.commit()
    return jsonify({'ok': True, 'id': ch.id, 'numero': ch.numero, 'criado': criado,
                    'url': f'/chamados/{ch.id}'}), (201 if criado else 200)


def _turno_do_lancamento(p, data):
    """De qual passagem partiu a ação — quando há uma.

    A tela de nova passagem resolve pendência ANTES de o turno existir no
    banco (o encarregado ainda não salvou nada). Nesse caso o evento fica sem
    ``turno_id``, e está certo assim: ele ainda carrega quem e quando, que é
    o que a trilha precisa para ser lida. Inventar um turno seria pior que
    não ter nenhum.

    Quando o turno JÁ existe — rascunho salvo mais cedo, ou ação disparada da
    tela de um turno — o vínculo é feito. O id só vale se for do mesmo
    contrato da pendência; o par data+turno é procurado porque é o que a tela
    de lançamento sabe dizer de si mesma.
    """
    turno_id = data.get('turno_id')
    if turno_id:
        t = DiarioTurno.query.get(int(turno_id))
        return t.id if (t is not None and t.client_id == p.client_id) else None
    nome = (data.get('turno') or '').strip()
    try:
        dia = date.fromisoformat(data.get('data_turno') or '')
    except (TypeError, ValueError):
        return None
    if not nome:
        return None
    q = DiarioTurno.query.filter_by(client_id=p.client_id, data_turno=dia, turno=nome)
    # Com duas áreas no contrato, o "1º Turno de hoje" existe duas vezes — um
    # por modelo. Sem o modelo, a baixa feita na tela da Expedição podia ser
    # amarrada à passagem do Almoxarifado, e a trilha mostrava o turno errado.
    # A tela manda o modelo escolhido; chamada antiga, sem ele, segue como era.
    try:
        cfg_id = int(data.get('configuracao_id') or 0)
    except (TypeError, ValueError):
        cfg_id = 0
    if cfg_id:
        q = q.filter_by(configuracao_id=cfg_id)
    t = q.order_by(DiarioTurno.id.desc()).first()
    return t.id if t is not None else None


@bp.post('/api/pendencias/<int:pending_id>/resolver')
@login_required
@module_required(MODULO)
def resolver_pendencia(pending_id):
    """Baixa a pendência dizendo o que foi feito.

    A nota é OBRIGATÓRIA. Antes o botão só virava a chave: gravava o status e
    a hora, e mais nada. No fim do mês a pendência aparecia resolvida sem que
    ninguém soubesse se trocaram a mangueira da empilhadeira ou se alguém
    apertou o botão para limpar a tela — e um "resolver" que não custa nada
    vira, em duas semanas, um botão de limpar a tela.
    """
    p = DiarioPendencia.query.get_or_404(pending_id)
    _client_allowed(p.client_id)
    data = request.get_json(silent=True) or {}
    resolucao = (data.get('resolucao') or '').strip()
    if not resolucao:
        return jsonify({'error': 'Diga em uma linha o que foi feito para '
                                 'resolver.'}), 400
    if p.status == 'resolvida':
        return jsonify({'error': 'Esta pendência já foi resolvida.'}), 409
    p.status = 'resolvida'
    p.resolved_at = datetime.utcnow()
    p.resolved_by = current_user.id
    p.resolucao = resolucao
    db.session.add(DiarioPendenciaEvento(
        pendencia_id=p.id, turno_id=_turno_do_lancamento(p, data),
        tipo='resolvida', texto=resolucao, created_by=current_user.id))
    db.session.commit()
    return jsonify({'ok': True, 'id': p.id, 'status': p.status,
                    'resolucao': p.resolucao})


@bp.post('/api/pendencias/<int:pending_id>/nota')
@login_required
@module_required(MODULO)
def anotar_na_pendencia(pending_id):
    """"Continua" — o que se tentou e por que não deu.

    É a linha que faz o turno seguinte não recomeçar do zero: sem ela, o
    próximo encarregado liga de novo para o mesmo CD de origem que este já
    ligou. Fica na trilha; não muda o status.
    """
    p = DiarioPendencia.query.get_or_404(pending_id)
    _client_allowed(p.client_id)
    if p.status != 'aberta':
        return jsonify({'error': 'Esta pendência não está mais aberta.'}), 409
    data = request.get_json(silent=True) or {}
    texto = (data.get('texto') or '').strip()
    if not texto:
        return jsonify({'error': 'Escreva o que foi tentado.'}), 400
    ev = DiarioPendenciaEvento(
        pendencia_id=p.id, turno_id=_turno_do_lancamento(p, data),
        tipo='tentativa', texto=texto, created_by=current_user.id)
    db.session.add(ev)
    db.session.commit()
    return jsonify({'ok': True, 'id': p.id, 'evento': ev.id})
