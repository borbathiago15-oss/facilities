"""Proxy TCP que imita um banco remoto (auditoria, Fase 3).

    python scripts/auditoria/proxy_latencia.py PORTA_LOCAL HOST:PORTA [--ms 5] [--buraco-negro]

``--ms``: atraso em CADA sentido (5 ms ida + 5 ms volta = ~10 ms de ida e
volta, como um Postgres gerenciado em outra zona). ``--buraco-negro``: aceita
a conexão TCP e nunca responde nem repassa nada (banco "pendurado").
O arquivo ``/tmp/claude-0/f3/buraco`` existindo liga o buraco negro em tempo
de execução (conexões novas E as já abertas param de andar).
"""
import argparse
import asyncio
import os
import time

BURACO = '/tmp/claude-0/f3/buraco'


def buraco_ligado(fixo):
    return fixo or os.path.exists(BURACO)


async def bombear(leitor, escritor, atraso, fixo):
    fila = asyncio.Queue()

    async def escrever():
        while True:
            quando, dados = await fila.get()
            if dados is None:
                break
            espera = quando + atraso - time.monotonic()
            if espera > 0:
                await asyncio.sleep(espera)
            while buraco_ligado(fixo):
                await asyncio.sleep(0.2)
            escritor.write(dados)
            await escritor.drain()
        escritor.close()

    tarefa = asyncio.create_task(escrever())
    try:
        while True:
            dados = await leitor.read(65536)
            if not dados:
                break
            await fila.put((time.monotonic(), dados))
    except (ConnectionError, OSError):
        pass
    await fila.put((0, None))
    try:
        await tarefa
    except (ConnectionError, OSError):
        pass


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('porta', type=int)
    ap.add_argument('destino')
    ap.add_argument('--ms', type=float, default=5.0)
    ap.add_argument('--buraco-negro', action='store_true')
    a = ap.parse_args()
    host, porta = a.destino.rsplit(':', 1)
    atraso = a.ms / 1000

    async def atender(leitor, escritor):
        if buraco_ligado(a.buraco_negro):
            await asyncio.sleep(10 ** 6)          # aceita e nunca responde
            return
        try:
            l2, e2 = await asyncio.open_connection(host, int(porta))
        except OSError:
            escritor.close()
            return
        await asyncio.gather(bombear(leitor, e2, atraso, a.buraco_negro),
                             bombear(l2, escritor, atraso, a.buraco_negro))

    srv = await asyncio.start_server(atender, '127.0.0.1', a.porta, backlog=1024)
    async with srv:
        await srv.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())
