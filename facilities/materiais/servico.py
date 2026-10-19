"""As regras de materiais (Fase 7). O commit é de quem chama.

* Catálogo: nome único, unidade obrigatória, preço OPCIONAL (F7-1). Quem
  cuida do catálogo é a gestão.
* Estoque por local: entrada e ajuste são da gestão; consumo é de quem
  executa (aplicativo, site ou na OS). O saldo nunca fica negativo, salvo
  com autorização do GESTOR DO CONTRATO e justificativa (F7-2).
* Pedido de insumo: um aviso do posto ao gestor do contrato, com prazo de
  48 h (ou o do cliente); a compra é em outro sistema — aqui o gestor só
  marca que viu (F7-3).
* Custo operacional = soma do valor dos CONSUMOS no período, por local,
  cliente e estado. Supervisor, gestão e diretoria veem; cliente, encarregado
  e técnico, não (F7-4). Nunca alimenta o DRE (D37).
"""
from collections import OrderedDict
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from facilities import tempo
from facilities.extensions import db
from facilities.core.models import Client
from facilities.materiais.models import (AJUSTE, CONSUMO, ENTRADA, PEDIDO_ABERTO, PEDIDO_VISTO,
                                         SAIDA, Consumo, Material, MovimentoEstoque,
                                         PedidoInsumo, fmt_qtd)

PERFIS_QUE_VEEM_CUSTO = ('master', 'gerente', 'pleno', 'supervisor', 'visualizador')
PERFIS_QUE_CONSOMEM = ('encarregado', 'tecnico', 'supervisor', 'pleno', 'gerente', 'master')
PRAZO_PEDIDO_PADRAO_H = 48
CENTAVO = Decimal('0.01')
MILESIMO = Decimal('0.001')
MAX_QTD = Decimal('999999999.999')


class RegraDoMaterial(ValueError):
    def __init__(self, mensagem, codigo=400):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo


def ve_custo(user):
    return user._effective_role() in PERFIS_QUE_VEEM_CUSTO


def _id(dados, campo):
    bruto = str(dados.get(campo) or '').strip()
    return int(bruto) if bruto.isdigit() else 0


def decimal_de(bruto, rotulo, casas=MILESIMO, positivo=True, obrigatorio=True):
    """ "1,5" ou "1.5" → Decimal('1.500'). Aceita a vírgula de quem digita."""
    texto = str(bruto if bruto is not None else '').strip().replace(' ', '')
    if not texto:
        if obrigatorio:
            raise RegraDoMaterial(f'Informe {rotulo}.')
        return None
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        valor = Decimal(texto).quantize(casas, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise RegraDoMaterial(f'{rotulo[0].upper()}{rotulo[1:]}: use só números (ex.: 1,5).')
    if not valor.is_finite() or abs(valor) > MAX_QTD:
        raise RegraDoMaterial(f'{rotulo[0].upper()}{rotulo[1:]}: número grande demais.')
    if positivo and valor <= 0:
        raise RegraDoMaterial(f'{rotulo[0].upper()}{rotulo[1:]}: precisa ser maior que zero.')
    return valor


def reais(v):
    """Decimal → "R$ 1.234,56"."""
    if v is None:
        return '—'
    q = Decimal(v).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    inteiro, _, cent = f'{abs(q):,.2f}'.partition('.')
    return ('-' if q < 0 else '') + 'R$ ' + inteiro.replace(',', '.') + ',' + cent


# ── Catálogo ──────────────────────────────────────────────────────────────

def salvar_material(mat, dados):
    nome = (dados.get('nome') or '').strip()[:120]
    unidade = (dados.get('unidade') or '').strip()[:20]
    if not nome or not unidade:
        raise RegraDoMaterial('Informe o nome do material e a unidade (ex.: L, kg, un, cx).')
    outro = Material.query.filter(db.func.lower(Material.nome) == nome.lower()).first()
    if outro is not None and (mat is None or outro.id != mat.id):
        raise RegraDoMaterial('Já existe um material com este nome.')
    preco = decimal_de(dados.get('preco_unitario'), 'o preço', CENTAVO, obrigatorio=False)
    mat = mat or Material()
    mat.nome, mat.unidade, mat.preco_unitario = nome, unidade, preco
    if mat.id is None:
        db.session.add(mat)
    db.session.flush()
    return mat


# ── Estoque ───────────────────────────────────────────────────────────────

def saldo(client_id, material_id):
    total = (db.session.query(db.func.coalesce(db.func.sum(MovimentoEstoque.quantidade), 0))
             .filter(MovimentoEstoque.client_id == client_id,
                     MovimentoEstoque.material_id == material_id).scalar())
    return Decimal(total).quantize(MILESIMO)


def saldos(client_id):
    """{material_id: saldo} do local (só os que já tiveram movimento)."""
    linhas = (db.session.query(MovimentoEstoque.material_id,
                               db.func.sum(MovimentoEstoque.quantidade))
              .filter(MovimentoEstoque.client_id == client_id)
              .group_by(MovimentoEstoque.material_id).all())
    return {m: Decimal(q).quantize(MILESIMO) for m, q in linhas}


def e_gestor_do_contrato(user, client_id):
    from facilities.chamados.servico import gestores_do_contrato
    return user._effective_role() == 'master' or user.id in gestores_do_contrato(client_id)


def _travar(client_id):
    """Dois consumos ao mesmo tempo no mesmo local esperam um ao outro (o
    saldo conferido é o de agora). No SQLite (testes) a cláusula é ignorada."""
    db.session.execute(db.select(Client.id).where(Client.id == client_id)
                       .with_for_update(key_share=True))


def _carteira(user, client_id):
    from facilities.core.acesso import allowed_client_ids_or_none
    permitidos = allowed_client_ids_or_none(user)
    if permitidos is not None and client_id not in permitidos:
        raise RegraDoMaterial('Este local não está entre os seus.', 403)


def movimentar(user, local, dados, tipo, agora_utc=None, chamado=None, rota=None):
    """Lança entrada, consumo, saída ou ajuste. → o movimento."""
    agora_utc = agora_utc or datetime.utcnow()
    _carteira(user, local.id)
    if tipo in (ENTRADA, AJUSTE, SAIDA) and not user.e_gestao():
        raise RegraDoMaterial('Entrada, saída e ajuste de estoque são da gestão.', 403)
    if tipo == CONSUMO and user._effective_role() not in PERFIS_QUE_CONSOMEM:
        raise RegraDoMaterial('Seu perfil não lança consumo.', 403)
    mat = db.session.get(Material, _id(dados, 'material_id'))
    if mat is None or not mat.is_active:
        raise RegraDoMaterial('Escolha um material do catálogo.')
    if tipo == AJUSTE:
        qtd = decimal_de(dados.get('quantidade'), 'a quantidade', positivo=False)
        if qtd == 0:
            raise RegraDoMaterial('Ajuste de zero não muda nada.')
    else:
        qtd = decimal_de(dados.get('quantidade'), 'a quantidade')
    delta = qtd if tipo in (ENTRADA, AJUSTE) else -qtd
    motivo = (dados.get('motivo') or '').strip()[:300] or None
    if tipo in (SAIDA, AJUSTE) and not motivo:
        raise RegraDoMaterial('Diga o motivo (ex.: produto vencido, contagem do inventário).')
    _travar(local.id)
    autorizado = None
    if delta < 0:
        atual = saldo(local.id, mat.id)
        if atual + delta < 0:
            if not dados.get('autorizar_negativo'):
                raise RegraDoMaterial(
                    f'Saldo insuficiente: há {fmt_qtd(atual)} {mat.unidade} de {mat.nome} neste '
                    'local. Peça reposição — ou o gestor do contrato autoriza o saldo negativo.',
                    409)
            if not e_gestor_do_contrato(user, local.id):
                raise RegraDoMaterial('Só o gestor do contrato autoriza saldo negativo.', 403)
            if not motivo:
                raise RegraDoMaterial('Para deixar o saldo negativo, escreva a justificativa.')
            autorizado = user.id
    preco = mat.preco_unitario
    valor = (abs(delta) * preco).quantize(CENTAVO, rounding=ROUND_HALF_UP) \
        if preco is not None else None
    mov = MovimentoEstoque(client_id=local.id, material_id=mat.id, tipo=tipo, quantidade=delta,
                           preco_unitario=preco, valor=valor,
                           data=tempo.local(agora_utc).date(), motivo=motivo,
                           autorizado_por=autorizado, user_id=user.id, criado_em=agora_utc)
    db.session.add(mov)
    db.session.flush()
    if tipo == CONSUMO:
        db.session.add(Consumo(movimento_id=mov.id, client_id=local.id,
                               chamado_id=chamado.id if chamado else None,
                               rota_id=rota.id if rota else None))
        db.session.flush()
    return mov


def consumir(user, local, dados, agora_utc=None):
    """O consumo do aplicativo / site: ligado a uma OS ou a uma rota do local
    (opcional)."""
    from facilities.chamados.models import STATUS_ENCERRADOS, Chamado
    from facilities.rotas.models import Rota
    chamado = rota = None
    if _id(dados, 'chamado_id'):
        chamado = db.session.get(Chamado, _id(dados, 'chamado_id'))
        if chamado is None or chamado.client_id != local.id:
            raise RegraDoMaterial('Escolha uma ordem de serviço deste local.')
        if chamado.status in STATUS_ENCERRADOS:
            raise RegraDoMaterial(f'A ordem {chamado.numero} já está encerrada.', 409)
    if _id(dados, 'rota_id'):
        rota = db.session.get(Rota, _id(dados, 'rota_id'))
        if rota is None or rota.client_id != local.id:
            raise RegraDoMaterial('Escolha uma rota deste local.')
    return movimentar(user, local, dados, CONSUMO, agora_utc, chamado=chamado, rota=rota)


def consumos_do_chamado(chamado_id):
    return (Consumo.query.filter_by(chamado_id=chamado_id)
            .join(MovimentoEstoque, MovimentoEstoque.id == Consumo.movimento_id)
            .order_by(MovimentoEstoque.criado_em).all())


# ── Pedido de insumo ──────────────────────────────────────────────────────

def prazo_do_pedido_h(client_id):
    c = db.session.get(Client, client_id)
    contratante = getattr(c, 'contratante', None)
    horas = getattr(contratante, 'prazo_pedido_insumo_horas', None)
    return horas if horas and horas > 0 else PRAZO_PEDIDO_PADRAO_H


def pedir(user, local, dados, foto=None, agora_utc=None):
    from facilities.chamados.servico import gestores_do_contrato
    from facilities.core import push
    from facilities.core.rotas import avisar
    agora_utc = agora_utc or datetime.utcnow()
    _carteira(user, local.id)
    if user._effective_role() not in PERFIS_QUE_CONSOMEM:
        raise RegraDoMaterial('Seu perfil não faz pedido de insumo.', 403)
    mat = None
    if _id(dados, 'material_id'):
        mat = db.session.get(Material, _id(dados, 'material_id'))
        if mat is None or not mat.is_active:
            raise RegraDoMaterial('Escolha um material do catálogo (ou descreva no texto).')
    qtd = decimal_de(dados.get('quantidade'), 'a quantidade', obrigatorio=False)
    texto = (dados.get('texto') or '').strip()[:300] or None
    if mat is None and not texto:
        raise RegraDoMaterial('Diga o que está faltando: escolha o material ou escreva.')
    p = PedidoInsumo(client_id=local.id, material_id=mat.id if mat else None, quantidade=qtd,
                     texto=texto, user_id=user.id, criado_em=agora_utc, status=PEDIDO_ABERTO,
                     prazo=agora_utc + timedelta(hours=prazo_do_pedido_h(local.id)))
    db.session.add(p)
    db.session.flush()
    if foto is not None:
        _guardar_foto(p, foto)
    quem = gestores_do_contrato(local.id)
    titulo = f'Pedido de insumo · {local.name}'
    quem = avisar(quem, titulo, f'{p.resumo} — pedido por {user.name}.', '/materiais/pedidos',
                  tipo='insumo', client_id=local.id)
    push.avisar(quem, titulo, p.resumo, '/materiais/pedidos', marca=f'pedido-{p.id}')
    return p


def _guardar_foto(pedido, arquivo):
    import uuid
    from werkzeug.utils import secure_filename
    from facilities.core.anexos import (ANEXO_ASSINATURA, ANEXO_MAX, ANEXO_TIPOS,
                                        imagem_aceitavel, storage)
    nome = secure_filename(arquivo.filename or '') or 'foto'
    ext = nome.rsplit('.', 1)[-1].lower() if '.' in nome else ''
    dados = arquivo.read(ANEXO_MAX + 1)
    if (ext not in ('png', 'jpg', 'jpeg', 'webp') or not dados or len(dados) > ANEXO_MAX
            or not any(dados.startswith(a) for a in ANEXO_ASSINATURA[ext])
            or not imagem_aceitavel(dados, ext)):
        raise RegraDoMaterial('A foto não é imagem (ou é grande demais). Tire de novo.')
    chave = f'pedidos_insumo/{pedido.id}/{uuid.uuid4().hex}.{ext}'
    storage().save(chave, dados, ANEXO_TIPOS[ext])
    pedido.foto_key, pedido.foto_mime = chave, ANEXO_TIPOS[ext]


def marcar_visto(user, pedido, agora_utc=None):
    if not e_gestor_do_contrato(user, pedido.client_id):
        raise RegraDoMaterial('Quem marca o pedido como visto é o gestor do contrato.', 403)
    if pedido.status == PEDIDO_VISTO:
        return pedido
    pedido.status = PEDIDO_VISTO
    pedido.visto_por, pedido.visto_em = user.id, agora_utc or datetime.utcnow()
    return pedido


def pedidos_abertos(client_ids):
    return (PedidoInsumo.query.filter(PedidoInsumo.client_id.in_(list(client_ids) or [-1]),
                                      PedidoInsumo.status == PEDIDO_ABERTO)
            .order_by(PedidoInsumo.criado_em).all())


# ── Custo operacional ─────────────────────────────────────────────────────

def custo(client_ids, de, ate):
    """O custo dos consumos no período, por local, cliente e estado.

    Todas as somas saem das MESMAS linhas (por local), então o total por
    cliente e por estado é a soma exata dos locais. Material sem preço conta
    em ``sem_preco`` (quantos consumos ficaram fora do custo).
    """
    q = (db.session.query(MovimentoEstoque.client_id,
                          db.func.coalesce(db.func.sum(MovimentoEstoque.valor), 0),
                          db.func.sum(db.case((MovimentoEstoque.valor.is_(None), 1), else_=0)),
                          db.func.count(MovimentoEstoque.id))
         .filter(MovimentoEstoque.tipo == CONSUMO, MovimentoEstoque.data >= de,
                 MovimentoEstoque.data <= ate))
    if client_ids is not None:
        q = q.filter(MovimentoEstoque.client_id.in_(list(client_ids) or [-1]))
    por_local = {cid: (Decimal(v).quantize(CENTAVO), int(sem or 0), int(n))
                 for cid, v, sem, n in q.group_by(MovimentoEstoque.client_id).all()}
    locais = {c.id: c for c in Client.query.filter(Client.id.in_(list(por_local) or [-1]))}
    linhas_local, por_cliente, por_estado = [], OrderedDict(), OrderedDict()
    total = Decimal('0.00')
    sem_preco = 0
    for cid, (valor, sem, n) in sorted(por_local.items(), key=lambda x: locais[x[0]].name):
        loc = locais[cid]
        cliente = loc.contratante.nome if getattr(loc, 'contratante', None) else 'Sem cliente'
        estado = loc.estado.sigla if getattr(loc, 'estado', None) else '—'
        linhas_local.append({'local': loc, 'cliente': cliente, 'estado': estado,
                             'valor': valor, 'consumos': n, 'sem_preco': sem})
        por_cliente[cliente] = por_cliente.get(cliente, Decimal('0.00')) + valor
        por_estado[estado] = por_estado.get(estado, Decimal('0.00')) + valor
        total += valor
        sem_preco += sem
    return {'locais': linhas_local, 'clientes': por_cliente, 'estados': por_estado,
            'total': total, 'sem_preco': sem_preco}


def consumo_do_mes(client_id, de, ate):
    """A conferência do mês de um local: cada material com quantidade e valor."""
    linhas = (db.session.query(MovimentoEstoque.material_id,
                               db.func.sum(MovimentoEstoque.quantidade),
                               db.func.sum(MovimentoEstoque.valor),
                               db.func.count(MovimentoEstoque.id))
              .filter(MovimentoEstoque.client_id == client_id,
                      MovimentoEstoque.tipo == CONSUMO,
                      MovimentoEstoque.data >= de, MovimentoEstoque.data <= ate)
              .group_by(MovimentoEstoque.material_id).all())
    mats = {m.id: m for m in Material.query.filter(Material.id.in_([x[0] for x in linhas] or [-1]))}
    saida = [{'material': mats[m], 'quantidade': -Decimal(q).quantize(MILESIMO),
              'valor': Decimal(v).quantize(CENTAVO) if v is not None else None, 'vezes': n}
             for m, q, v, n in linhas]
    return sorted(saida, key=lambda x: x['material'].nome)
