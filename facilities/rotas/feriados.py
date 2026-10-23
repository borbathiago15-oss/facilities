"""Feriados (decisões do dono, 23/10/2026).

* Valem os feriados NACIONAIS (calculados aqui, iguais para todos) e os do
  LOCAL, que a gestão cadastra (estaduais, municipais, ponto facultativo do
  cliente — ex.: 2 de Julho na Bahia).
* Cada rota diz se funciona em feriado (``Rota.funciona_em_feriado``).
  Desligada, o agendador não gera tarefa dela no feriado; ligada (o padrão,
  hospital e CD), segue normal.
* Carnaval e Corpus Christi são ponto facultativo, não feriado nacional: o
  local que para nesses dias cadastra.

O commit é de quem chama.
"""
from datetime import date, timedelta

from facilities.extensions import db
from facilities.rotas.models import Feriado

# Lei 662/1949 (com 6.802/1980 e 14.759/2023): os feriados nacionais de data fixa.
FIXOS = {
    (1, 1): 'Confraternização Universal',
    (4, 21): 'Tiradentes',
    (5, 1): 'Dia do Trabalho',
    (9, 7): 'Independência do Brasil',
    (10, 12): 'Nossa Senhora Aparecida',
    (11, 2): 'Finados',
    (11, 15): 'Proclamação da República',
    (11, 20): 'Dia Nacional de Zumbi e da Consciência Negra',
    (12, 25): 'Natal',
}


class FeriadoInvalido(ValueError):
    """Mensagem pronta para a tela."""


def pascoa(ano):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher, calendário gregoriano)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    mes = (h + m - 7 * n + 114) // 31
    dia = (h + m - 7 * n + 114) % 31 + 1
    return date(ano, mes, dia)


def nacionais(ano):
    """{data: nome} dos feriados nacionais do ano."""
    saida = {date(ano, m, d): nome for (m, d), nome in FIXOS.items()}
    saida[pascoa(ano) - timedelta(days=2)] = 'Sexta-feira Santa'
    return saida


def locais_em_feriado(client_ids, dia):
    """Quais destes locais estão em feriado no ``dia`` (numa consulta só)."""
    ids = set(client_ids)
    if not ids:
        return set()
    if dia in nacionais(dia.year):
        return ids
    return {cid for (cid,) in db.session.query(Feriado.client_id).filter(
        Feriado.client_id.in_(list(ids)), Feriado.data == dia)}


def do_ano(local_id, ano):
    """Os feriados que valem no local no ano, em ordem: [(data, nome, Feriado|None)].
    ``None`` = nacional (não se remove)."""
    lista = [(d, nome, None) for d, nome in nacionais(ano).items()]
    lista += [(f.data, f.nome, f) for f in Feriado.query.filter(
        Feriado.client_id == local_id, Feriado.data >= date(ano, 1, 1),
        Feriado.data <= date(ano, 12, 31))]
    return sorted(lista, key=lambda x: x[0])


def cadastrar(local, dados, autor):
    from datetime import datetime
    try:
        dia = datetime.strptime((dados.get('data') or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        raise FeriadoInvalido('Escolha a data do feriado.')
    nome = (dados.get('nome') or '').strip()[:80]
    if not nome:
        raise FeriadoInvalido('Dê um nome ao feriado (ex.: Independência da Bahia).')
    if dia in nacionais(dia.year):
        raise FeriadoInvalido(f'{dia.strftime("%d/%m/%Y")} já é feriado nacional '
                              f'({nacionais(dia.year)[dia]}).')
    if Feriado.query.filter_by(client_id=local.id, data=dia).first() is not None:
        raise FeriadoInvalido(f'{dia.strftime("%d/%m/%Y")} já está cadastrado neste local.')
    f = Feriado(client_id=local.id, data=dia, nome=nome, criado_por=getattr(autor, 'id', None))
    db.session.add(f)
    db.session.flush()
    return f


def remover(local, fid):
    """O feriado cadastrado por engano sai (é configuração, não histórico)."""
    f = db.session.get(Feriado, fid)
    if f is None or f.client_id != local.id:
        raise FeriadoInvalido('Feriado não encontrado neste local.')
    db.session.delete(f)
    return f
