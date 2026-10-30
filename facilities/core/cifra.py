"""Criptografia dos campos sensíveis no banco (pedido do dono, 30/10/2026).

É OPCIONAL e não depende de hospedagem: liga com ``FIELD_ENCRYPTION_KEY`` no
ambiente de qualquer servidor onde o sistema e o banco estiverem (Railway,
servidor da empresa, outra nuvem). Sem a chave, os campos ficam em texto
aberto, como antes. Para ligar num banco que já tem dado: pôr a chave e
rodar ``flask chaves girar``.

Com a cifra ligada, quem copiar o banco, um backup ou um log de consulta NÃO lê e-mail, telefone,
endereço, segredo da segunda etapa nem as chaves do aviso no celular: essas
colunas guardam o texto cifrado (Fernet: AES-128-CBC + HMAC-SHA256, com
carimbo de tempo e vetor aleatório a cada gravação). A chave fica FORA do
banco, na variável ``FIELD_ENCRYPTION_KEY`` do servidor, com cópia num cofre
offline — sem ela, o dado cifrado não volta. Ver ``docs/SEGURANCA_DADOS.md``.

Senha não entra aqui: ela nunca é guardada, só o hash (scrypt) — e hash não
tem volta, nem com a chave.

**Índice cego.** O texto cifrado muda a cada gravação, então não dá para
procurar ``WHERE email = ...``. Para o login achar a conta, a coluna irmã
``email_index`` guarda um HMAC-SHA256 do e-mail normalizado, com uma chave
derivada da chave dos campos. Igual entra igual sai, e quem só tem o banco
não refaz o HMAC. Regra: **nunca filtrar, ordenar nem agrupar em SQL por uma
coluna ``Cifrado``** — filtre pelo índice, ou depois de ler.

**Rodízio de chave.** Chave nova em ``FIELD_ENCRYPTION_KEY`` e a anterior em
``FIELD_ENCRYPTION_OLD_KEYS`` (separadas por vírgula): tudo continua sendo
lido e o login procura o índice de todas as chaves. Depois,
``flask chaves girar`` recifra tudo e refaz os índices com a chave nova; só
então a antiga sai do ambiente.
"""
import base64
import hashlib
import hmac
import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy.ext.hybrid import Comparator, hybrid_property
from sqlalchemy.sql import operators
from sqlalchemy.types import Text, TypeDecorator

# Todo token Fernet começa com o byte de versão 0x80 → "gAAAAA" em base64.
_PREFIXO = 'gAAAAA'

_estado = {'chaves': None}


class ChaveAusente(RuntimeError):
    pass


def gerar_chave():
    return Fernet.generate_key().decode()


def _ler_chaves(texto_principal, texto_antigas=''):
    brutas = [texto_principal.strip()] + [k.strip() for k in (texto_antigas or '').split(',')
                                          if k.strip()]
    chaves = []
    for k in brutas:
        try:
            Fernet(k.encode())
        except (ValueError, TypeError) as e:
            raise ChaveAusente(
                'FIELD_ENCRYPTION_KEY (ou uma das FIELD_ENCRYPTION_OLD_KEYS) não é uma chave '
                'válida. Gere uma com "flask chaves gerar".') from e
        chaves.append(k)
    return chaves


def configurar(principal, antigas=''):
    """Liga a criptografia com a chave dada (e as antigas, só para ler).
    Sem chave principal, a cifra fica DESLIGADA (texto aberto)."""
    principal = (principal or '').strip()
    if not principal:
        if (antigas or '').strip():
            raise ChaveAusente('FIELD_ENCRYPTION_OLD_KEYS sem FIELD_ENCRYPTION_KEY: defina a '
                               'chave principal.')
        _estado['chaves'] = []
        return
    _estado['chaves'] = _ler_chaves(principal, antigas)


def configurar_app(app):
    """Chamado pela fábrica. A cifra é OPCIONAL (decisão do dono, 30/10/2026:
    ligar quando quiser, em qualquer servidor onde o banco estiver): com
    ``FIELD_ENCRYPTION_KEY`` no ambiente ela vale; sem, o sistema sobe com os
    campos em texto aberto, como antes, e avisa no log."""
    configurar(os.environ.get('FIELD_ENCRYPTION_KEY') or '',
               os.environ.get('FIELD_ENCRYPTION_OLD_KEYS') or '')
    if not ligada():
        app.logger.warning('FIELD_ENCRYPTION_KEY não definida: e-mails, telefones, endereços e '
                           'o segredo da segunda etapa ficam em TEXTO ABERTO no banco. Para '
                           'ligar a cifra, veja docs/SEGURANCA_DADOS.md.')


def _chaves():
    if _estado['chaves'] is None:
        configurar(os.environ.get('FIELD_ENCRYPTION_KEY') or '',
                   os.environ.get('FIELD_ENCRYPTION_OLD_KEYS') or '')
    return _estado['chaves']


def ligada():
    """A cifra está ligada (há chave)?"""
    return bool(_chaves())


def _fernet():
    return MultiFernet([Fernet(k.encode()) for k in _chaves()])


def cifrar(texto):
    """Texto → cifrado. Com a cifra desligada, grava o texto como veio."""
    if texto is None:
        return None
    if not ligada():
        return str(texto)
    return _fernet().encrypt(str(texto).encode()).decode()


def decifrar(valor):
    """Texto cifrado → texto. Valor que não é token (gravado com a cifra
    desligada, ou antes dela) volta como está; token que nenhuma chave abre
    — ou token com a cifra desligada — é ERRO: nunca devolver lixo em
    silêncio."""
    if valor is None:
        return None
    if not valor.startswith(_PREFIXO):
        return valor
    if not ligada():
        raise ChaveAusente('O banco tem campos cifrados, mas FIELD_ENCRYPTION_KEY não está '
                           'definida: ponha de volta a chave usada (está no cofre).')
    try:
        return _fernet().decrypt(valor.encode()).decode()
    except InvalidToken as e:
        raise ChaveAusente('Um campo cifrado não abre com nenhuma das chaves configuradas '
                           '(FIELD_ENCRYPTION_KEY / FIELD_ENCRYPTION_OLD_KEYS).') from e


def recifrar(valor):
    """Com a chave principal: texto aberto é cifrado, cifrado é recifrado
    (ligar a cifra e rodízio são o mesmo comando). Desligada: fica como está."""
    if valor is None:
        return None
    if not ligada():
        return valor
    if not valor.startswith(_PREFIXO):
        return cifrar(valor)
    return _fernet().rotate(valor.encode()).decode()


def esta_cifrado(valor):
    return valor is None or valor.startswith(_PREFIXO)


def _chave_indice(chave_fernet):
    bruta = base64.urlsafe_b64decode(chave_fernet.encode())
    return hmac.new(bruta, b'facilities-indice-cego-v1', hashlib.sha256).digest()


def normalizar_email(email):
    return (email or '').strip().lower()


def _indice_com(chave, texto):
    return hmac.new(_chave_indice(chave), texto.encode(), hashlib.sha256).hexdigest()


def _indice_aberto(texto):
    # Cifra desligada: um hash simples, só para a busca funcionar igual.
    # Ligar a cifra (``flask chaves girar``) troca pelo HMAC com a chave.
    return hashlib.sha256(b'facilities-indice-aberto-v1:' + texto.encode()).hexdigest()


def indice(email):
    """O índice do e-mail que se GRAVA: HMAC com a chave principal, ou o
    hash simples com a cifra desligada."""
    if email is None:
        return None
    texto = normalizar_email(email)
    chaves = _chaves()
    return _indice_com(chaves[0], texto) if chaves else _indice_aberto(texto)


def indices(email):
    """O que se PROCURA: o índice com cada chave configurada e o da cifra
    desligada (a linha pode ser de antes de ligar, ou de antes do rodízio)."""
    texto = normalizar_email(email)
    return [_indice_com(k, texto) for k in _chaves()] + [_indice_aberto(texto)]


class Cifrado(TypeDecorator):
    """Coluna de texto guardada cifrada. Lê e grava texto normal no Python."""
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return cifrar(value)

    def process_result_value(self, value, dialect):
        return decifrar(value)


class ComparaPeloIndice(Comparator):
    """``Modelo.email == x`` (e ``filter_by(email=x)``) vira a busca pelo
    índice cego: comparar o texto cifrado nunca acharia nada."""

    def operate(self, op, *other, **kw):
        if op is operators.eq:
            return self.expression.in_(indices(other[0]))
        if op is operators.ne:
            return ~self.expression.in_(indices(other[0]))
        if op is operators.in_op:
            return self.expression.in_([i for v in other[0] for i in indices(v)])
        raise TypeError('Campo cifrado: em SQL só dá para comparar com ==, != ou in_ '
                        '(nada de ordenar, LIKE ou maiúsculas).')


def email_cifrado(coluna, indice_col):
    """A propriedade ``email`` de um modelo: lê/grava o texto (a coluna é
    ``Cifrado``), mantém o índice cego em dia e compara pelo índice."""
    nome, nome_indice = coluna, indice_col

    def ler(self):
        return getattr(self, nome)

    def gravar(self, valor):
        setattr(self, nome, valor)
        setattr(self, nome_indice, indice(valor))

    prop = hybrid_property(ler, gravar)
    return prop.comparator(lambda cls: ComparaPeloIndice(getattr(cls, nome_indice)))
