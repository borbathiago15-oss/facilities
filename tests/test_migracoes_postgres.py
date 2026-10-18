"""As migrações num Postgres de verdade: ida → volta → ida com dados, sem
perder linha nenhuma (``scripts/ensaio_migracoes_postgres.py``).

Roda só com ``TEST_MIGRACOES_URL`` apontando para um banco SÓ DESTE ENSAIO
(ele é zerado; precisa de "test" no nome) — nunca o mesmo banco da suíte.
"""
import os

import pytest

URL = os.environ.get('TEST_MIGRACOES_URL', '').strip()


@pytest.mark.skipif(not URL, reason='defina TEST_MIGRACOES_URL para ensaiar as migrações')
def test_ida_volta_ida_nao_perde_dado():
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts'))
    from ensaio_migracoes_postgres import ensaiar
    digitais = ensaiar(URL)
    assert digitais['pontos_inspecao'][0] == 1 and digitais['estados'][0] == 27
