"""Armazenamento de objetos (uploads/artefatos) — externo por padrão.

O disco do contêiner é efêmero; conteúdo do usuário (ex.: imagens da One Page)
não pode viver só nele. Este módulo abstrai um armazenamento simples com dois
backends:

- ``R2Storage``  — Cloudflare R2 (S3-compatível, via boto3). Usado em produção.
- ``LocalStorage`` — disco local. Fallback para desenvolvimento/testes.

A seleção é por ambiente (``STORAGE_BACKEND=local|r2``); sem configuração de R2,
cai no local automaticamente — mas só onde quem chama permite (o Facilities
permite no SQLite de desenvolvimento; com Postgres, o disco local só com
``STORAGE_BACKEND=local`` escrito). As chaves (``key``) são caminhos lógicos como
``op_images/op1_123.png`` — no local viram arquivos sob a pasta base; no R2,
objetos sob o prefixo configurado.
"""
import io
import os


def _segundos(nome, padrao):
    try:
        return max(1, int(float(os.environ.get(nome) or padrao)))
    except ValueError:
        return padrao


def config_do_cliente():
    """Tempos limite do boto3 (auditoria, Fase 4): o padrão do botocore é 60 s
    para conectar, 60 s para ler e novas tentativas — um R2 engasgado
    segurava a requisição por minutos. ``R2_CONNECT_TIMEOUT`` (3),
    ``R2_READ_TIMEOUT`` (10) e ``R2_TENTATIVAS`` (2 novas tentativas depois da primeira)."""
    from botocore.config import Config
    return Config(signature_version='s3v4',
                  connect_timeout=_segundos('R2_CONNECT_TIMEOUT', 3),
                  read_timeout=_segundos('R2_READ_TIMEOUT', 10),
                  retries={'max_attempts': _segundos('R2_TENTATIVAS', 2), 'mode': 'standard'})


class StorageError(Exception):
    """Falha de armazenamento (não expor detalhes ao usuário final)."""


class NotFound(StorageError):
    """Objeto inexistente."""


class LocalStorage:
    """Backend em disco local (dev/fallback)."""

    def __init__(self, base_dir):
        self.base = base_dir

    def _path(self, key):
        return os.path.join(self.base, key)

    def save(self, key, data, content_type=None):
        p = self._path(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as fh:
            fh.write(data)

    def load(self, key):
        try:
            with open(self._path(key), 'rb') as fh:
                return fh.read()
        except FileNotFoundError as ex:
            raise NotFound(key) from ex

    def delete(self, key):
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass

    def exists(self, key):
        return os.path.exists(self._path(key))


class R2Storage:
    """Backend Cloudflare R2 (S3-compatível) via boto3."""

    def __init__(self, endpoint, access_key, secret_key, bucket, prefix=''):
        import boto3
        self.bucket = bucket
        self.prefix = prefix or ''
        self._client = boto3.client(
            's3', endpoint_url=endpoint,
            aws_access_key_id=access_key, aws_secret_access_key=secret_key,
            region_name='auto', config=config_do_cliente())

    def _key(self, key):
        return f'{self.prefix}{key}'

    def save(self, key, data, content_type=None):
        extra = {'ContentType': content_type} if content_type else {}
        self._client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data, **extra)

    def load(self, key):
        from botocore.exceptions import ClientError
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=self._key(key))
            return obj['Body'].read()
        except ClientError as ex:
            code = ex.response.get('Error', {}).get('Code')
            if code in ('NoSuchKey', '404', 'NotFound'):
                raise NotFound(key) from ex
            raise StorageError(str(ex)) from ex

    def delete(self, key):
        self._client.delete_object(Bucket=self.bucket, Key=self._key(key))

    def exists(self, key):
        from botocore.exceptions import ClientError
        try:
            self._client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except ClientError:
            return False


_R2_VARS = ('R2_ENDPOINT', 'R2_ACCESS_KEY_ID', 'R2_SECRET_ACCESS_KEY', 'R2_BUCKET')


def get_storage(local_base_dir, local_implicito=True):
    """Retorna o backend conforme o ambiente.

    - ``STORAGE_BACKEND=r2`` (ou não definido, mas com todas as R2_* presentes)
      → R2Storage.
    - ``STORAGE_BACKEND=local`` → LocalStorage(``local_base_dir``).
    - nada definido → LocalStorage, se ``local_implicito``; senão ERRO.

    ``local_implicito=False`` é o modo produção: faltando uma R2_* (ou com o
    nome dela escrito errado), antes caía no disco do contêiner sem uma linha
    de log — as fotos sumiam no próximo reinício e o anexo dava 404. Agora o
    boot para e diz o que falta.
    """
    backend = os.environ.get('STORAGE_BACKEND', '').strip().lower()
    r2_ready = all(os.environ.get(v) for v in _R2_VARS)
    if backend == 'r2' or (backend == '' and r2_ready):
        missing = [v for v in _R2_VARS if not os.environ.get(v)]
        if missing:
            raise StorageError(f'R2 selecionado, mas faltam variáveis: {", ".join(missing)}')
        return R2Storage(
            os.environ['R2_ENDPOINT'], os.environ['R2_ACCESS_KEY_ID'],
            os.environ['R2_SECRET_ACCESS_KEY'], os.environ['R2_BUCKET'],
            prefix=os.environ.get('R2_PREFIX', ''))
    if backend not in ('', 'local'):
        raise StorageError(f'STORAGE_BACKEND={backend!r} desconhecido: use r2 ou local.')
    if backend == '' and not local_implicito:
        faltam = [v for v in _R2_VARS if not os.environ.get(v)]
        raise StorageError(
            'Anexos sem destino: faltam ' + ', '.join(faltam) + '. Sem elas os '
            'arquivos iriam para o disco local do servidor, que se perde a cada '
            'reinício. Defina as variáveis do R2 — ou STORAGE_BACKEND=local, se '
            'o disco local for mesmo o destino (com volume persistente).')
    return LocalStorage(local_base_dir)


def espelhar_no_r2(base_dir):
    """Cópia de segurança do disco para o R2 (``flask anexos espelhar``):
    percorre ``base_dir`` e envia o que o bucket ainda não tem, com a mesma
    chave relativa. Idempotente: rodar de novo só manda o que é novo.
    Precisa das variáveis ``R2_*``. Devolve (copiados, já existiam, erros)."""
    import mimetypes
    faltam = [v for v in _R2_VARS if not os.environ.get(v)]
    if faltam:
        raise StorageError('Espelho no R2 pede as variáveis ' + ', '.join(faltam) + '.')
    r2 = R2Storage(os.environ['R2_ENDPOINT'], os.environ['R2_ACCESS_KEY_ID'],
                   os.environ['R2_SECRET_ACCESS_KEY'], os.environ['R2_BUCKET'],
                   prefix=os.environ.get('R2_PREFIX', ''))
    base = os.path.abspath(base_dir)
    copiados = ja = erros = 0
    for raiz, _dirs, arquivos in os.walk(base):
        for nome in arquivos:
            caminho = os.path.join(raiz, nome)
            chave = os.path.relpath(caminho, base).replace(os.sep, '/')
            try:
                if r2.exists(chave):
                    ja += 1
                    continue
                with open(caminho, 'rb') as f:
                    r2.save(chave, f.read(), mimetypes.guess_type(nome)[0])
                copiados += 1
            except Exception:
                erros += 1
    return copiados, ja, erros


# ── Arquivo das fotos antigas (decisão do dono, 01/11/2026) ───────────────
#
# As fotos passadas do prazo saem do armazenamento principal para um destino
# de arquivo, configurado SÓ pelo ambiente (nunca digitado na tela):
#
# * ``ARQUIVO_R2_ENDPOINT``, ``ARQUIVO_R2_ACCESS_KEY_ID``,
#   ``ARQUIVO_R2_SECRET_ACCESS_KEY``, ``ARQUIVO_R2_BUCKET`` (e o opcional
#   ``ARQUIVO_R2_PREFIX``): um bucket do Cloudflare R2 SEPARADO do principal;
# * ``ARQUIVO_FOTOS_PASTA``: uma pasta do servidor. Serve para testar o
#   caminho; no mesmo disco das fotos não libera espaço nenhum.
#
# Quem lê não muda: ``ComArquivo`` procura no principal e, se não achar,
# no arquivo. Toda tela, antiga ou nova, continua mostrando a foto.

_ARQUIVO_R2_VARS = ('ARQUIVO_R2_ENDPOINT', 'ARQUIVO_R2_ACCESS_KEY_ID',
                    'ARQUIVO_R2_SECRET_ACCESS_KEY', 'ARQUIVO_R2_BUCKET')


class ComArquivo:
    """O armazenamento que o app usa: grava no principal; lê do principal e,
    se a chave não estiver lá (foto arquivada), do arquivo. Apagar apaga nos
    dois (quem apaga quer o arquivo fora de vez: a retenção, a troca da
    logo, o anexo retirado da passagem).

    ``arquivo`` é ``None`` quando não há destino configurado (ou ele foi
    recusado: ``info['problema']`` diz por quê)."""

    def __init__(self, principal, arquivo=None, info=None):
        self.principal = principal
        self.arquivo = arquivo
        self.info = info or {'tipo': None, 'rotulo': '', 'mesmo_disco': False,
                             'problema': None}

    def save(self, key, data, content_type=None):
        self.principal.save(key, data, content_type)

    def load(self, key):
        try:
            return self.principal.load(key)
        except NotFound:
            if self.arquivo is None:
                raise
            return self.arquivo.load(key)

    def delete(self, key):
        self.principal.delete(key)
        if self.arquivo is not None:
            self.arquivo.delete(key)

    def exists(self, key):
        if self.principal.exists(key):
            return True
        return self.arquivo is not None and self.arquivo.exists(key)


def _disco(caminho):
    """O dispositivo onde ``caminho`` (ou a pasta existente mais próxima
    acima dele) mora."""
    p = os.path.abspath(caminho)
    while not os.path.exists(p):
        acima = os.path.dirname(p)
        if acima == p:
            return None
        p = acima
    return os.stat(p).st_dev


def _dentro(a, b):
    a, b = os.path.abspath(a), os.path.abspath(b)
    return os.path.commonpath([a, b]) in (a, b)


def arquivo_do_ambiente(principal):
    """O destino do arquivo, lido do ambiente → (storage ou None, info).

    Nunca derruba o boot: configuração incompleta ou perigosa vira
    ``info['problema']`` (a tela mostra) e o arquivo fica indisponível. É
    recusado o destino que é o MESMO lugar do principal — arquivar ali
    gravaria a cópia por cima do original e depois apagaria os dois."""
    info = {'tipo': None, 'rotulo': '', 'mesmo_disco': False, 'problema': None}
    r2 = {v: (os.environ.get(v) or '').strip() for v in _ARQUIVO_R2_VARS}
    pasta = (os.environ.get('ARQUIVO_FOTOS_PASTA') or '').strip()
    algum_r2 = any(r2.values())
    if algum_r2 and pasta:
        info['problema'] = ('Há dois destinos no ambiente (ARQUIVO_FOTOS_PASTA e as '
                            'ARQUIVO_R2_*). Deixe só um.')
        return None, info
    if algum_r2:
        info['tipo'] = 'r2'
        faltam = [v for v, x in r2.items() if not x]
        if faltam:
            info['problema'] = 'Faltam as variáveis ' + ', '.join(faltam) + '.'
            return None, info
        bucket = r2['ARQUIVO_R2_BUCKET']
        info['rotulo'] = f'Cloudflare R2, bucket {bucket}'
        if (isinstance(principal, R2Storage) and principal.bucket == bucket
                and (os.environ.get('R2_ENDPOINT') or '').strip() == r2['ARQUIVO_R2_ENDPOINT']):
            info['problema'] = ('O bucket do arquivo é o mesmo das fotos do dia a dia. '
                                'Crie um bucket separado para o arquivo.')
            return None, info
        try:
            return R2Storage(r2['ARQUIVO_R2_ENDPOINT'], r2['ARQUIVO_R2_ACCESS_KEY_ID'],
                             r2['ARQUIVO_R2_SECRET_ACCESS_KEY'], bucket,
                             prefix=os.environ.get('ARQUIVO_R2_PREFIX', '')), info
        except Exception as ex:                 # noqa: BLE001 — vira aviso na tela
            info['problema'] = f'Não foi possível preparar o bucket do arquivo ({type(ex).__name__}).'
            return None, info
    if not pasta:
        return None, info
    info['tipo'] = 'pasta'
    pasta = os.path.abspath(pasta)
    info['rotulo'] = f'Pasta {pasta} no servidor'
    if isinstance(principal, LocalStorage):
        base = principal.base
        if _dentro(pasta, base):
            info['problema'] = ('A pasta do arquivo não pode ficar dentro da pasta das fotos '
                                '(nem conter ela). Use uma pasta ao lado, por exemplo '
                                f'{os.path.join(os.path.dirname(os.path.abspath(base)), "arquivo-fotos")}.')
            return None, info
        if not os.path.isdir(base):
            info['problema'] = ('Este servidor não enxerga a pasta das fotos '
                                f'({os.path.abspath(base)}): o arquivo só roda onde ela está.')
            return None, info
        info['mesmo_disco'] = _disco(pasta) == _disco(base)
    # Num contêiner, pasta fora do volume das fotos some no próximo deploy —
    # com as fotos arquivadas dentro. Outro disco só com a confirmação
    # escrita de quem configurou.
    if not info['mesmo_disco'] and os.environ.get('ARQUIVO_FOTOS_PASTA_OUTRO_DISCO', '') != '1':
        info['problema'] = ('A pasta do arquivo está em outro disco que o das fotos. Se esse '
                            'disco é permanente (não some num novo deploy), confirme com '
                            'ARQUIVO_FOTOS_PASTA_OUTRO_DISCO=1.')
        return None, info
    return LocalStorage(pasta), info
