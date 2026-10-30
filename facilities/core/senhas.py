"""Regras da senha: além do tamanho mínimo, recusa a senha óbvia (a primeira
que um robô tenta) e mantém o hash sempre no padrão atual.

A senha nunca é guardada: só o hash scrypt (``User.set_password``). Quando o
padrão sobe (um custo maior no futuro, ou um hash antigo de outro formato),
``precisa_refazer`` avisa no login e o hash é refeito com a senha que a
pessoa acabou de digitar — ninguém precisa trocar nada.
"""
from werkzeug.security import generate_password_hash

# As mais tentadas em vazamentos públicos, e as óbvias daqui.
COMUNS = frozenset('''
12345678 123456789 1234567890 87654321 11111111 00000000 12341234 11223344
password password1 password123 senha123 senha1234 senhasenha mudar123 mudar1234
qwerty123 qwertyui abc12345 abcd1234 a1b2c3d4 iloveyou admin123 admin1234
brasil123 trino123 trino1234 grupotrino facilities facilities1 bemvindo
'''.split())

# O prefixo do hash no padrão atual (método + parâmetros do scrypt).
_PADRAO = generate_password_hash('x').rsplit('$', 2)[0]


def problema(senha, email=''):
    """O motivo de recusar a senha nova (texto para a tela), ou ``None``."""
    s = (senha or '').strip().lower()
    usuario = (email or '').split('@')[0].lower()
    if s in COMUNS:
        return 'Essa senha é das primeiras que alguém tenta. Escolha outra.'
    if len(set(s)) <= 2:
        return 'Use uma senha com letras e números variados, não o mesmo caractere repetido.'
    if s in ('0123456789', '9876543210') or s.isdigit() and s in '01234567890123456789':
        return 'Sequência de números é fácil de adivinhar. Escolha outra.'
    if email and (s == (email or '').lower() or (len(usuario) >= 4 and usuario in s)):
        return 'Use uma senha diferente do seu e-mail.'
    return None


def precisa_refazer(hash_guardado):
    return bool(hash_guardado) and hash_guardado.rsplit('$', 2)[0] != _PADRAO
