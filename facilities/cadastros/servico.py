"""Todas as regras dos cadastros. As rotas só leem o formulário e chamam aqui.

As regras, em uma frase cada:

* Nada se apaga; desativar um nível desativa o que está abaixo dele (cada um
  com o seu evento na trilha). Reativar não reativa os filhos: quem reativa
  escolhe o que volta.
* Não se cria nem se reativa nada debaixo de um nível desativado.
* Nome repetido no mesmo nível é recusado sem olhar maiúsculas e minúsculas
  ("Copa" e "copa" são o mesmo ambiente), inclusive contra os desativados —
  a mensagem manda reativar o antigo, para o histórico não se partir em dois.
* Mover só dentro do mesmo local: o histórico (checklists, chamados) é do
  local, e um ambiente que muda de local levaria o histórico junto.
* Toda gravação deixa um evento na trilha com o antes e o depois. O commit é
  de quem chama.
"""
import json
from datetime import date, datetime

from facilities.extensions import db
from facilities.core.models import Client, User
from facilities.cadastros.models import (ENTIDADES, Ambiente, CadastroEvento, Contratante,
                                         Empresa, Equipamento, Estado, PontoInspecao, Setor)

# Quem pode ser o gerente responsável por um cliente (D43): o perfil gerente.
PERFIS_DE_GERENTE = ('gerente',)


class CadastroInvalido(ValueError):
    """Erro com mensagem pronta para a tela."""


# ── Trilha ────────────────────────────────────────────────────────────────

_FORA_DA_FOTO = {'created_at', 'password_hash'}


def foto(obj):
    """As colunas do registro, num dicionário que vira JSON."""
    if obj is None:
        return None
    dados = {}
    for col in obj.__table__.columns:
        if col.name in _FORA_DA_FOTO:
            continue
        valor = getattr(obj, col.key)
        if isinstance(valor, (datetime, date)):
            valor = valor.isoformat()
        dados[col.name] = valor
    return dados


def registrar(entidade, obj, acao, antes, autor, client_id=None):
    db.session.flush()
    db.session.add(CadastroEvento(
        entidade=entidade, entidade_id=obj.id, client_id=client_id, acao=acao,
        antes_json=json.dumps(antes, ensure_ascii=False) if antes is not None else None,
        depois_json=json.dumps(foto(obj), ensure_ascii=False),
        user_id=getattr(autor, 'id', None)))


def eventos(entidade=None, entidade_id=None, client_id=None, limite=200):
    q = CadastroEvento.query
    if entidade:
        q = q.filter(CadastroEvento.entidade == entidade)
    if entidade_id:
        q = q.filter(CadastroEvento.entidade_id == entidade_id)
    if client_id:
        q = q.filter(CadastroEvento.client_id == client_id)
    return q.order_by(CadastroEvento.criado_em.desc(), CadastroEvento.id.desc()).limit(limite).all()


def diferencas(evento):
    """[(campo, antes, depois)] do que mudou num evento (para a tela)."""
    antes = json.loads(evento.antes_json) if evento.antes_json else {}
    depois = json.loads(evento.depois_json) if evento.depois_json else {}
    campos = [c for c in depois if c != 'id' and antes.get(c) != depois.get(c)]
    return [(c, antes.get(c), depois.get(c)) for c in campos]


# ── Ajudantes ─────────────────────────────────────────────────────────────

def _texto(dados, campo, limite, obrigatorio=None):
    valor = (dados.get(campo) or '').strip()[:limite]
    if obrigatorio and not valor:
        raise CadastroInvalido(obrigatorio)
    return valor or None


def _id(dados, campo):
    bruto = str(dados.get(campo) or '').strip()
    return int(bruto) if bruto.isdigit() else None


def _nome_livre(modelo, nome, atual=None, **pai):
    """Recusa nome repetido no mesmo nível (sem olhar maiúsculas)."""
    q = modelo.query.filter(db.func.lower(modelo.nome) == nome.lower())
    for coluna, valor in pai.items():
        q = q.filter(getattr(modelo, coluna) == valor)
    if atual is not None and atual.id is not None:
        q = q.filter(modelo.id != atual.id)
    outro = q.first()
    if outro is None:
        return
    if not outro.is_active:
        raise CadastroInvalido(f'Já existe "{outro.nome}" aqui, desativado. '
                               'Reative o cadastro antigo em vez de criar outro.')
    raise CadastroInvalido(f'Já existe "{outro.nome}" aqui.')


def _do_local(modelo, oid, local, rotulo):
    obj = db.session.get(modelo, oid) if oid else None
    if obj is None or obj.client_id != local.id:
        raise CadastroInvalido(f'Escolha um {rotulo} deste local.')
    return obj


# ── Empresa, estado e cliente ─────────────────────────────────────────────

def salvar_empresa(empresa, dados, autor):
    nova = empresa is None
    antes = foto(empresa)
    empresa = empresa or Empresa(is_active=True)
    nome = _texto(dados, 'nome', 120, 'Informe o nome da empresa.')
    if nova or nome.lower() != (empresa.nome or '').lower():
        outra = Empresa.query.filter(db.func.lower(Empresa.nome) == nome.lower()).first()
        if outra is not None and outra.id != empresa.id:
            raise CadastroInvalido('Já existe uma empresa com este nome.')
    empresa.nome = nome
    empresa.cnpj = _texto(dados, 'cnpj', 18)
    if nova:
        db.session.add(empresa)
    registrar('empresa', empresa, 'criado' if nova else 'alterado', antes, autor)
    return empresa


def definir_estado_ativo(estado, ativo, autor):
    if bool(estado.is_active) == bool(ativo):
        return estado
    if not ativo:
        em_uso = Client.query.filter(Client.estado_id == estado.id,
                                     Client.is_deleted.is_(False),
                                     Client.is_active.is_(True)).count()
        if em_uso:
            raise CadastroInvalido(f'{estado.nome} tem {em_uso} local(is) ativo(s). '
                                   'Mude o estado deles antes de desativar.')
    antes = foto(estado)
    estado.is_active = bool(ativo)
    registrar('estado', estado, 'reativado' if ativo else 'desativado', antes, autor)
    return estado


def gerentes_possiveis():
    return (User.query.filter(User.is_deleted.is_(False), User.is_active.is_(True),
                              User.role.in_(PERFIS_DE_GERENTE))
            .order_by(User.name).all())


def _gerente_valido(gid):
    if gid is None:
        return None
    u = db.session.get(User, gid)
    if u is None or u.is_deleted or not u.is_active or u.role not in PERFIS_DE_GERENTE:
        raise CadastroInvalido('O gerente responsável precisa ser uma pessoa ativa com '
                               'o perfil Gerente.')
    return gid


def salvar_contratante(contratante, dados, autor):
    nova = contratante is None
    antes = foto(contratante)
    contratante = contratante or Contratante(is_active=True)
    nome = _texto(dados, 'nome', 120, 'Informe o nome do cliente.')
    empresa = db.session.get(Empresa, _id(dados, 'empresa_id') or 0)
    if empresa is None:
        raise CadastroInvalido('Escolha a empresa do grupo que atende este cliente.')
    if not empresa.is_active and empresa.id != contratante.empresa_id:
        raise CadastroInvalido('Esta empresa está desativada.')
    _nome_livre(Contratante, nome, contratante, empresa_id=empresa.id)
    contratante.nome = nome
    contratante.empresa_id = empresa.id
    contratante.centro_custo = _texto(dados, 'centro_custo', 50)
    contratante.gerente_id = _gerente_valido(_id(dados, 'gerente_id'))
    contratante.prazos_ocorrencia_json = _prazos_de_ocorrencia(dados)
    contratante.prazos_chamado_json = _regua_de_chamado(dados)
    if nova:
        db.session.add(contratante)
    registrar('contratante', contratante, 'criado' if nova else 'alterado', antes, autor)
    return contratante


def _prazos_de_ocorrencia(dados):
    """Prazo (minutos) por tipo de ocorrência do QR público; vazio = sem prazo."""
    from facilities.rotas.models import TIPOS_OCORRENCIA_PUBLICA
    prazos = {}
    for tipo, rotulo in TIPOS_OCORRENCIA_PUBLICA.items():
        bruto = str(dados.get(f'prazo_{tipo}') or '').strip()
        if not bruto:
            continue
        if not bruto.isdigit() or not 5 <= int(bruto) <= 7 * 24 * 60:
            raise CadastroInvalido(f'Prazo de "{rotulo}": em minutos, de 5 a 10080 (7 dias).')
        prazos[tipo] = int(bruto)
    return json.dumps(prazos, sort_keys=True) if prazos else None


def _regua_de_chamado(dados):
    """Horas por prioridade (D9); vazio = a régua padrão naquela prioridade."""
    from facilities.chamados.models import PRIORIDADES
    regua = {}
    for prioridade, rotulo in PRIORIDADES.items():
        bruto = str(dados.get(f'regua_{prioridade}') or '').strip()
        if not bruto:
            continue
        if not bruto.isdigit() or not 1 <= int(bruto) <= 90 * 24:
            raise CadastroInvalido(f'Prazo de chamado "{rotulo}": em horas, de 1 a 2160 '
                                   '(90 dias).')
        regua[prioridade] = int(bruto)
    return json.dumps(regua, sort_keys=True) if regua else None


def regua_de(contratante):
    return json.loads(contratante.prazos_chamado_json) \
        if contratante and contratante.prazos_chamado_json else {}


def prazos_de(contratante):
    return json.loads(contratante.prazos_ocorrencia_json) \
        if contratante and contratante.prazos_ocorrencia_json else {}


def definir_ativo_simples(entidade, obj, ativo, autor):
    """Empresa e cliente: desativar não mexe nos locais (eles têm vida própria)."""
    if bool(obj.is_active) == bool(ativo):
        return obj
    antes = foto(obj)
    obj.is_active = bool(ativo)
    registrar(entidade, obj, 'reativado' if ativo else 'desativado', antes, autor)
    return obj


def vincular_local(local, dados, autor):
    """O cliente e o estado do local, vindos do formulário de locais.

    Campos vazios ficam vazios: o local antigo, sem cliente, continua valendo.
    """
    cid = _id(dados, 'contratante_id')
    eid = _id(dados, 'estado_id')
    if cid is not None:
        c = db.session.get(Contratante, cid)
        if c is None or (not c.is_active and c.id != local.contratante_id):
            raise CadastroInvalido('Escolha um cliente ativo.')
    if eid is not None:
        e = db.session.get(Estado, eid)
        if e is None or (not e.is_active and e.id != local.estado_id):
            raise CadastroInvalido('Escolha um estado ativo (Cadastros › Estados).')
    local.contratante_id = cid
    local.estado_id = eid


def registrar_local(local, antes, autor, nova=False):
    acao = 'criado' if nova else 'alterado'
    if not nova and antes and antes.get('is_active') != bool(local.is_active):
        acao = 'reativado' if local.is_active else 'desativado'
    registrar('local', local, acao, antes, autor, client_id=local.id)


# ── Árvore do local ───────────────────────────────────────────────────────

def salvar_setor(local, setor, dados, autor):
    nova = setor is None
    antes = foto(setor)
    nome = _texto(dados, 'nome', 120, 'Informe o nome do setor.')
    setor = setor or Setor(client_id=local.id, is_active=True)
    _nome_livre(Setor, nome, setor, client_id=local.id)
    setor.nome = nome
    if nova:
        db.session.add(setor)
    registrar('setor', setor, 'criado' if nova else 'alterado', antes, autor, local.id)
    return setor


def salvar_ambiente(local, ambiente, dados, autor):
    nova = ambiente is None
    antes = foto(ambiente)
    nome = _texto(dados, 'nome', 120, 'Informe o nome do ambiente.')
    setor = _do_local(Setor, _id(dados, 'setor_id'), local, 'setor')
    mudou_setor = not nova and setor.id != ambiente.setor_id
    if (nova or mudou_setor) and not setor.is_active:
        raise CadastroInvalido('Este setor está desativado.')
    ambiente = ambiente or Ambiente(client_id=local.id, is_active=True)
    _nome_livre(Ambiente, nome, ambiente, setor_id=setor.id)
    ambiente.nome = nome
    ambiente.setor_id = setor.id
    ambiente.descricao = _texto(dados, 'descricao', 300)
    if nova:
        db.session.add(ambiente)
    acao = 'criado' if nova else ('movido' if mudou_setor else 'alterado')
    registrar('ambiente', ambiente, acao, antes, autor, local.id)
    return ambiente


def salvar_equipamento(local, equipamento, dados, autor):
    nova = equipamento is None
    antes = foto(equipamento)
    nome = _texto(dados, 'nome', 120, 'Informe o nome do equipamento.')
    ambiente = _do_local(Ambiente, _id(dados, 'ambiente_id'), local, 'ambiente')
    mudou = not nova and ambiente.id != equipamento.ambiente_id
    if (nova or mudou) and not ambiente.is_active:
        raise CadastroInvalido('Este ambiente está desativado.')
    equipamento = equipamento or Equipamento(client_id=local.id, is_active=True)
    equipamento.nome = nome
    equipamento.ambiente_id = ambiente.id
    equipamento.patrimonio = _texto(dados, 'patrimonio', 50)
    equipamento.fabricante = _texto(dados, 'fabricante', 80)
    equipamento.modelo = _texto(dados, 'modelo', 80)
    if nova:
        db.session.add(equipamento)
    acao = 'criado' if nova else ('movido' if mudou else 'alterado')
    registrar('equipamento', equipamento, acao, antes, autor, local.id)
    return equipamento


def salvar_ponto(local, ponto, dados, autor):
    nova = ponto is None
    antes = foto(ponto)
    nome = _texto(dados, 'nome', 120, 'Informe o nome do ponto.')
    ambiente = _do_local(Ambiente, _id(dados, 'ambiente_id'), local, 'ambiente')
    mudou = not nova and ambiente.id != ponto.ambiente_id
    if (nova or mudou) and not ambiente.is_active:
        raise CadastroInvalido('Este ambiente está desativado.')
    eq_id = _id(dados, 'equipamento_id')
    if eq_id is not None:
        eq = _do_local(Equipamento, eq_id, local, 'equipamento')
        if eq.ambiente_id != ambiente.id:
            raise CadastroInvalido('O equipamento precisa estar no mesmo ambiente do ponto.')
    ponto = ponto or PontoInspecao(client_id=local.id, is_active=True)
    _nome_livre(PontoInspecao, nome, ponto, ambiente_id=ambiente.id)
    ponto.nome = nome
    ponto.ambiente_id = ambiente.id
    ponto.equipamento_id = eq_id
    ponto.descricao = _texto(dados, 'descricao', 300)
    if nova:
        db.session.add(ponto)
    acao = 'criado' if nova else ('movido' if mudou else 'alterado')
    registrar('ponto', ponto, acao, antes, autor, local.id)
    return ponto


# entidade → (modelo, pai como atributo, filhos como atributos)
ARVORE = {
    'setor': (Setor, None, ('ambientes',)),
    'ambiente': (Ambiente, 'setor', ('equipamentos', 'pontos')),
    'equipamento': (Equipamento, 'ambiente', ()),
    'ponto': (PontoInspecao, 'ambiente', ()),
}
_ENTIDADE_DO_FILHO = {'ambientes': 'ambiente', 'equipamentos': 'equipamento',
                      'pontos': 'ponto'}


def item_do_local(entidade, oid, local):
    if entidade not in ARVORE:
        raise CadastroInvalido('Cadastro desconhecido.')
    return _do_local(ARVORE[entidade][0], oid, local, ENTIDADES[entidade].lower())


def definir_ativo(entidade, obj, ativo, autor):
    """Desativa (com os filhos, em cascata) ou reativa (só o próprio)."""
    modelo, pai, filhos = ARVORE[entidade]
    if bool(obj.is_active) == bool(ativo):
        return obj
    if ativo:
        dono = getattr(obj, pai) if pai else None
        if dono is not None and not dono.is_active:
            raise CadastroInvalido(f'Reative primeiro "{dono.nome}", que está acima deste.')
    antes = foto(obj)
    obj.is_active = bool(ativo)
    registrar(entidade, obj, 'reativado' if ativo else 'desativado', antes, autor, obj.client_id)
    if not ativo:
        for atributo in filhos:
            for filho in getattr(obj, atributo):
                if filho.is_active:
                    definir_ativo(_ENTIDADE_DO_FILHO[atributo], filho, False, autor)
    return obj


def arvore(local, com_inativos=False):
    """Os setores do local, cada um com os seus ambientes (e o que há neles)."""
    q = Setor.query.filter(Setor.client_id == local.id)
    if not com_inativos:
        q = q.filter(Setor.is_active.is_(True))
    return q.order_by(Setor.nome).all()


def ponto_pelo_codigo(codigo):
    codigo = (codigo or '').strip()
    if not codigo or len(codigo) > 32:
        return None
    return PontoInspecao.query.filter_by(codigo_qr=codigo).first()
