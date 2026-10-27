"""GPS na leitura do QR (decisões do dono, 27/10/2026).

* O app manda, junto com a leitura, a posição do celular naquele instante
  (``{'lat', 'lng', 'precisao'}``) ou o motivo de não ter (``{'erro':
  'negado' | 'indisponivel'}``). Não há rastreio: só no momento do QR.
* O servidor compara com a posição do local (marcada pela gestão NO local)
  e guarda só a SITUAÇÃO, a distância e a precisão — nunca a coordenada da
  pessoa.
* Fora do local: a leitura é ACEITA e fica marcada; o supervisor do local
  recebe UM aviso por pessoa e dia. Dentro de galpão o GPS erra de 50 a 200 m:
  a precisão informada pelo celular entra a favor da pessoa (até 500 m).
* Sem GPS (negado, desligado, sem resposta): aceita e marca "sem GPS".
"""
import math
from datetime import datetime, timedelta

from facilities import tempo
from facilities.extensions import db

RAIO_PADRAO_M = 300
RAIO_MIN_M, RAIO_MAX_M = 50, 5000
FOLGA_MAX_M = 500             # a precisão do celular conta a favor até aqui

DENTRO = 'dentro'
FORA = 'fora'
SEM_GPS = 'sem_gps'
SEM_REFERENCIA = 'sem_referencia'
SITUACOES = {DENTRO: 'No local', FORA: 'Fora do local', SEM_GPS: 'Sem GPS',
             SEM_REFERENCIA: 'Local sem posição marcada'}


def distancia_m(lat1, lng1, lat2, lng2):
    """Distância em metros entre dois pontos (fórmula de haversine)."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _numero(v, minimo, maximo):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if minimo <= n <= maximo and not math.isnan(n) else None


def ler(bruto):
    """O que o app mandou → (lat, lng, precisão) ou None."""
    if not isinstance(bruto, dict):
        return None
    lat = _numero(bruto.get('lat'), -90, 90)
    lng = _numero(bruto.get('lng'), -180, 180)
    if lat is None or lng is None:
        return None
    precisao = _numero(bruto.get('precisao'), 0, 100000)
    return lat, lng, precisao


def raio_do_local(local):
    return local.raio_gps_m or RAIO_PADRAO_M


def avaliar(local, bruto):
    """→ (situação, distância em metros ou None, precisão em metros ou None)."""
    pos = ler(bruto)
    if pos is None:
        return SEM_GPS, None, None
    lat, lng, precisao = pos
    prec = int(round(precisao)) if precisao is not None else None
    if local is None or local.latitude is None or local.longitude is None:
        return SEM_REFERENCIA, None, prec
    d = distancia_m(float(local.latitude), float(local.longitude), lat, lng)
    folga = min(precisao or 0, FOLGA_MAX_M)
    situacao = DENTRO if d - folga <= raio_do_local(local) else FORA
    return situacao, int(round(d)), prec


def gravar(registro, local, bruto):
    """Grava a situação no registro (execução ou chegada) e devolve ela."""
    situacao, dist, prec = avaliar(local, bruto)
    registro.gps_situacao, registro.gps_distancia_m, registro.gps_precisao_m = \
        situacao, dist, prec
    return situacao


def texto(situacao, distancia=None):
    if situacao == FORA and distancia is not None:
        return f'Fora do local ({_km(distancia)})'
    if situacao == DENTRO and distancia is not None:
        return f'No local ({_km(distancia)})'
    return SITUACOES.get(situacao, '')


def _km(m):
    return f'{m / 1000:.1f} km'.replace('.', ',') if m >= 1000 else f'a {m} m'


def marcar_posicao(local, dados, autor, agora_utc=None):
    """A gestão, no local, marca a posição dele pelo celular."""
    from facilities.cadastros.servico import CadastroInvalido
    pos = ler({'lat': dados.get('lat'), 'lng': dados.get('lng'),
               'precisao': dados.get('precisao')})
    if pos is None:
        raise CadastroInvalido('Não chegou a posição do celular. Ligue a localização e toque '
                               'de novo, de dentro do local.')
    lat, lng, _prec = pos
    local.latitude, local.longitude = round(lat, 6), round(lng, 6)
    local.posicao_marcada_em = agora_utc or datetime.utcnow()
    local.posicao_marcada_por = getattr(autor, 'id', None)
    raio = str(dados.get('raio') or '').strip()
    if raio:
        if not raio.isdigit() or not RAIO_MIN_M <= int(raio) <= RAIO_MAX_M:
            raise CadastroInvalido(f'O raio vai de {RAIO_MIN_M} a {RAIO_MAX_M} metros.')
        local.raio_gps_m = int(raio)
    return local


def avisar_fora(user, local, onde, agora_utc=None):
    """Um aviso por pessoa, local e dia para quem supervisiona o local
    (supervisor; sem supervisor, o coordenador)."""
    from facilities.core.hierarquia import carteira
    from facilities.core.models import Notification, User
    from facilities.core.rotas import avisar as avisar_no_sino
    agora_utc = agora_utc or datetime.utcnow()
    titulo = f'Leitura fora do local: {user.name}'[:150]
    # O dia (local) da leitura vai na mensagem: é a chave do "um por dia",
    # também para a leitura que chega depois, guardada sem sinal.
    mensagem = f'{tempo.local(agora_utc).strftime("%d/%m")} · {local.name} · {onde}'[:300]
    prefixo = mensagem.split(' · ', 2)[0] + f' · {local.name} · '
    destinos = set()
    for papeis in (('supervisor',), ('pleno',)):
        for u in User.query.filter(User.role.in_(papeis), User.is_active.is_(True),
                                   User.is_deleted.is_(False)):
            cart = carteira(u)
            if cart is not None and local.id in cart:
                destinos.add(u.id)
        if destinos:
            break
    ja = {uid for (uid,) in db.session.query(Notification.user_id).filter(
        Notification.notification_type == 'gps_fora', Notification.title == titulo,
        Notification.message.like(prefixo.replace('%', r'\%') + '%'),
        Notification.created_at >= datetime.utcnow() - timedelta(days=40))}
    return avisar_no_sino(destinos - ja, titulo, mensagem,
                          f'/rotas/locais/{local.id}/dia', tipo='gps_fora',
                          client_id=local.id)
