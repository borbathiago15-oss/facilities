"""Ponto de entrada WSGI: ``gunicorn app:app``.

Também expõe ``db`` e os modelos do núcleo no topo, como o ``app.py`` do
Trino Intelligence: os testes da Passagem de Turno vieram de lá e falam com
``app.User``, ``app.Client`` e ``app.db``.
"""
from facilities import create_app
from facilities.extensions import db  # noqa: F401
from facilities.core.models import Client, Notification, User  # noqa: F401

app = create_app()
