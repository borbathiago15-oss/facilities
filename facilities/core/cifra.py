"""Criptografia dos campos sensíveis no banco (pedido do dono, 30/10/2026).

Quem copiar o banco, um backup ou um log de consulta NÃO lê e-mail, telefone,
endereço, segredo da segunda etapa nem as chaves do aviso no celular: essas
colunas guardam o texto cifrado (Fernet: AES-128-CBC + HMAC-SHA256, com
carimbo de tempo e vetor aleatório a cada gravação). A chave fica FORA do
banco, na variável ``FIELD_ENCRYPTION_KEY`` (Railway), com cópia num cofre
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
_ARQUIVO_DEV = 'chave_dos_campos.key'

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
    """Liga a criptografia com a chave dada (e as antigas, só para ler)."""
    _estado['chaves'] = _ler_chaves(principal, antigas)


def configurar_app(app, sqlite, exigir_producao):
    """Chamado pela fábrica. Fora do SQLite de desenvolvimento, sem a chave o
    app NÃO sobe: subir sem ela gravaria dado que ninguém mais lê."""
    principal = (os.environ.get('FIELD_ENCRYPTION_KEY') or '').strip()
    antigas = os.environ.get('FIELD_ENCRYPTION_OLD_KEYS') or ''
    if not principal:
        if not sqlite or exigir_producao:
            raise ChaveAusente(
                'FIELD_ENCRYPTION_KEY não definida. Ela cifra e-mails, telefones, endereços e '
                'o segredo da segunda etapa no banco: sem ela o sistema não sobe. Gere com '
                '"flask chaves gerar", ponha no ambiente e guarde uma cópia no cofre offline.')
        # SQLite de desenvolvimento: uma chave local, guardada na pasta
        # instance/ (fora do git) para o banco de dev continuar legível.
        os.makedirs(app.instance_path, exist_ok=True)
        caminho = os.path.join(app.instance_path, _ARQUIVO_DEV)
        if not os.path.exists(caminho):
            with open(caminho, 'w') as f:
                f.write(gerar_chave())
            app.logger.warning('FIELD_ENCRYPTION_KEY não definida: chave de desenvolvimento '
                               'criada em %s.', caminho)
        with open(caminho) as f:
            principal = f.read().strip()
    configurar(principal, antigas)


def _chaves():
    if _estado['chaves'] is None:
        principal = (os.environ.get('FIELD_ENCRYPTION_KEY') or '').strip()
        if not principal:
            raise ChaveAusente('Criptografia dos campos sem chave (FIELD_ENCRYPTION_KEY).')
        configurar(principal, os.environ.get('FIELD_ENCRYPTION_OLD_KEYS') or '')
    return _estado['chaves']


def _fernet():
    return MultiFernet([Fernet(k.encode()) for k in _chaves()])


def cifrar(texto):
    if texto is None:
        return None
    return _fernet().encrypt(str(texto).encode()).decode()


def decifrar(valor):
    """Texto cifrado → texto. Valor que não é token (linha antiga, ainda não
    migrada) volta como está; token que nenhuma chave abre é ERRO — nunca
    devolver lixo em silêncio."""
    if valor is None:
        return None
    if not valor.startswith(_PREFIXO):
        return valor
    try:
        return _fernet().decrypt(valor.encode()).decode()
    except InvalidToken as e:
        raise ChaveAusente('Um campo cifrado não abre com nenhuma das chaves configuradas '
                           '(FIELD_ENCRYPTION_KEY / FIELD_ENCRYPTION_OLD_KEYS).') from e


def recifrar(valor):
    """Recifra com a chave principal (rodízio). Texto antigo é cifrado."""
    if valor is None:
        return None
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


def indice(email):
    """O índice cego do e-mail, com a chave principal (é o que se grava)."""
    if email is None:
        return None
    return _indice_com(_chaves()[0], normalizar_email(email))


def indices(email):
    """O índice com cada chave configurada — o que se PROCURA (durante um
    rodízio, a linha ainda pode estar com o índice da chave antiga)."""
    texto = normalizar_email(email)
    return [_indice_com(k, texto) for k in _chaves()]


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
