"""Armazenamento de objetos (uploads/artefatos) — externo por padrão.

O disco do contêiner é efêmero; conteúdo do usuário (ex.: imagens da One Page)
não pode viver só nele. Este módulo abstrai um armazenamento simples com dois
backends:

- ``R2Storage``  — Cloudflare R2 (S3-compatível, via boto3). Usado em produção.
- ``LocalStorage`` — disco local. Fallback para desenvolvimento/testes.

A seleção é por ambiente (``STORAGE_BACKEND=local|r2``); sem configuração de R2,
cai no local automaticamente. As chaves (``key``) são caminhos lógicos como
``op_images/op1_123.png`` — no local viram arquivos sob a pasta base; no R2,
objetos sob o prefixo configurado.
"""
import io
import os


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
        from botocore.config import Config
        self.bucket = bucket
        self.prefix = prefix or ''
        self._client = boto3.client(
            's3', endpoint_url=endpoint,
            aws_access_key_id=access_key, aws_secret_access_key=secret_key,
            region_name='auto', config=Config(signature_version='s3v4'))

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


def get_storage(local_base_dir):
    """Retorna o backend conforme o ambiente.

    - ``STORAGE_BACKEND=r2`` (ou não definido, mas com todas as R2_* presentes)
      → R2Storage.
    - caso contrário → LocalStorage(``local_base_dir``).
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
    return LocalStorage(local_base_dir)
