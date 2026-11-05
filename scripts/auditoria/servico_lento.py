"""Serviços externos FALSOS e lentos (auditoria, Fase 3): push, R2 (S3) e SMTP.

    python scripts/auditoria/servico_lento.py --http 9900 --smtp 9925 --atraso 5

HTTP (push e S3): responde 201/200 a qualquer pedido depois de ``--atraso``
segundos (o serviço de push lento ou o R2 engasgado). SMTP: aceita a conexão
e não diz nada (o servidor de e-mail pendurado). Conta os pedidos em
``/tmp/claude-0/f3/servico_lento.log``. Nunca fala com a internet.
"""
import argparse
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = '/tmp/claude-0/f3/servico_lento.log'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--http', type=int, default=9900)
    ap.add_argument('--smtp', type=int, default=9925)
    ap.add_argument('--atraso', type=float, default=5)
    a = ap.parse_args()

    class Lento(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def _responder(self, codigo):
            n = int(self.headers.get('Content-Length') or 0)
            if n:
                self.rfile.read(n)
            time.sleep(a.atraso)
            with open(LOG, 'a') as f:
                f.write(f'{time.time():.1f} {self.command} {self.path[:60]}\n')
            corpo = b'' if self.command != 'GET' else b'x'
            self.send_response(codigo)
            self.send_header('Content-Length', str(len(corpo)))
            self.send_header('ETag', '"f3"')
            self.end_headers()
            self.wfile.write(corpo)

        def do_POST(self):
            self._responder(201)

        def do_PUT(self):
            self._responder(200)

        def do_GET(self):
            self._responder(200)

        def do_HEAD(self):
            self._responder(200)

        def log_message(self, *x):
            pass

    srv = ThreadingHTTPServer(('127.0.0.1', a.http), Lento)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('127.0.0.1', a.smtp))
    s.listen(512)
    presos = []
    while True:
        c, _ = s.accept()
        presos.append(c)                 # aceita e fica calado


if __name__ == '__main__':
    main()
