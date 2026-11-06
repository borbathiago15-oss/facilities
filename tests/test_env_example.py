"""O ``.env.example`` lista toda variável de ambiente que o sistema lê.

Varre o código do app e do agendador (``facilities/``, ``app.py``) e o
``docker-entrypoint.sh`` atrás das leituras do ambiente — ``os.environ``,
``os.getenv``, ``env.get`` e os ajudantes (``_flag``, ``_inteiro``...) — e
confere que cada nome aparece no ``.env.example`` da raiz. Variável nova sem
a linha no exemplo quebra este teste: quem configura o servidor descobre por
ali o que existe.

Leitura com nome montado na hora (``os.environ.get(nome)``) só vale dentro
dos ajudantes conhecidos; os nomes deles vêm das tuplas do próprio módulo.
"""
import ast
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Funções que recebem o NOME da variável como primeiro argumento, e o
# arquivo onde moram (outro arquivo pode ter um ``_numero`` que não lê o ambiente).
AJUDANTES = {'_flag': 'facilities/__init__.py', '_inteiro': 'facilities/core/banco.py',
             '_segundos': 'facilities/object_storage.py', '_numero': 'facilities/core/push.py'}
# Onde a leitura com nome variável é aceita (o nome vem de fora, conferido abaixo).
LEITURA_DINAMICA_OK = set(AJUDANTES) | {
    'configurar_app', '_chaves', 'get_storage', 'espelhar_no_r2', 'arquivo_do_ambiente',
    '_destino_r2', 'prazo', 'limites_das_tarefas', 'url_do_processo', 'processo',
}
_NOME = re.compile(r'^[A-Z][A-Z0-9_]+$')


def _arquivos_py():
    yield os.path.join(RAIZ, 'app.py')
    for pasta, _dirs, arquivos in os.walk(os.path.join(RAIZ, 'facilities')):
        for nome in arquivos:
            if nome.endswith('.py'):
                yield os.path.join(pasta, nome)


def _eh_ambiente(no):
    """``os.environ``, ``environ`` ou ``env`` (o parâmetro de core/banco.py)."""
    if isinstance(no, ast.Attribute) and no.attr == 'environ':
        return True
    return isinstance(no, ast.Name) and no.id in ('environ', 'env')


class _Coletor(ast.NodeVisitor):
    def __init__(self, arquivo):
        self.nomes, self.dinamicas, self._funcoes = set(), [], []
        self.ajudantes = {n for n, onde in AJUDANTES.items() if onde == arquivo}

    def visit_FunctionDef(self, no):
        self._funcoes.append(no.name)
        self.generic_visit(no)
        self._funcoes.pop()

    def _anotar(self, arg, onde):
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if _NOME.match(arg.value):
                self.nomes.add(arg.value)
        elif isinstance(arg, ast.JoinedStr):
            pass                                       # ex.: f'RETENCAO_{nome}' (abaixo)
        elif not (self._funcoes and self._funcoes[-1] in LEITURA_DINAMICA_OK):
            self.dinamicas.append(onde)

    def visit_Call(self, no):
        f = no.func
        onde = f'linha {no.lineno}'
        if no.args:
            if isinstance(f, ast.Attribute) and f.attr in ('get', 'pop', 'setdefault') \
                    and _eh_ambiente(f.value):
                self._anotar(no.args[0], onde)
            elif isinstance(f, ast.Attribute) and f.attr == 'getenv':
                self._anotar(no.args[0], onde)
            elif isinstance(f, ast.Name) and f.id in self.ajudantes:
                self._anotar(no.args[0], onde)
        self.generic_visit(no)

    def visit_Subscript(self, no):
        if _eh_ambiente(no.value):
            self._anotar(no.slice, f'linha {no.lineno}')
        self.generic_visit(no)


def _lidas_no_codigo():
    nomes, soltas = set(), []
    for caminho in _arquivos_py():
        with open(caminho, encoding='utf-8') as f:
            arvore = ast.parse(f.read(), caminho)
        c = _Coletor(os.path.relpath(caminho, RAIZ).replace(os.sep, '/'))
        c.visit(arvore)
        nomes |= c.nomes
        soltas += [f'{os.path.relpath(caminho, RAIZ)} {o}' for o in c.dinamicas]
    # Os nomes que os ajudantes montam ou recebem em tupla.
    from facilities import object_storage
    from facilities.core import banco, retencao
    nomes |= set(object_storage._R2_VARS) | set(object_storage._ARQUIVO_R2_VARS)
    nomes |= {variavel for _p, variavel, _v in banco.LIMITES_DAS_TAREFAS}
    nomes |= {f'RETENCAO_{k}' for k in retencao.PADRAO}
    with open(os.path.join(RAIZ, 'docker-entrypoint.sh'), encoding='utf-8') as f:
        nomes |= set(re.findall(r'\$\{([A-Z][A-Z0-9_]+)', f.read()))
    return nomes, soltas


def _no_exemplo():
    with open(os.path.join(RAIZ, '.env.example'), encoding='utf-8') as f:
        return set(re.findall(r'^#?\s*([A-Z][A-Z0-9_]+)=', f.read(), re.MULTILINE))


def test_toda_variavel_lida_esta_no_env_example():
    lidas, _ = _lidas_no_codigo()
    faltam = sorted(lidas - _no_exemplo())
    assert not faltam, f'Acrescente ao .env.example (com uma linha de comentário): {faltam}'


def test_leitura_com_nome_montado_so_nos_ajudantes_conhecidos():
    _, soltas = _lidas_no_codigo()
    assert not soltas, ('Leitura do ambiente com nome que o teste não enxerga — use o nome '
                        f'escrito, ou registre o ajudante em LEITURA_DINAMICA_OK: {soltas}')


def test_o_varredor_enxerga_as_variaveis_de_sempre():
    """Se o varredor quebrar, o teste de cima passaria sem conferir nada."""
    lidas, _ = _lidas_no_codigo()
    for nome in ('DATABASE_URL', 'SECRET_KEY', 'FIELD_ENCRYPTION_KEY', 'CIFRA_OPCIONAL',
                 'R2_BUCKET', 'DB_POOL_SIZE', 'GUNICORN_THREADS', 'RETENCAO_RODADA_DIAS',
                 'ANEXOS_ESPELHO_R2', 'PUSH_TIMEOUT'):
        assert nome in lidas, nome


def test_env_example_sem_valor_secreto():
    """Os valores ficam vazios (ou um padrão que não é segredo)."""
    secretas = re.compile(r'(KEY|SECRET|SENHA|PASSWORD|TOKEN)')
    with open(os.path.join(RAIZ, '.env.example'), encoding='utf-8') as f:
        for linha in f:
            m = re.match(r'^#?\s*([A-Z][A-Z0-9_]+)=(.*)$', linha.strip())
            if m and secretas.search(m.group(1)):
                assert m.group(2).strip() == '', f'{m.group(1)} deve ficar vazia no exemplo'


def test_env_fica_fora_do_git():
    with open(os.path.join(RAIZ, '.gitignore'), encoding='utf-8') as f:
        assert '.env' in [linha.strip() for linha in f]
