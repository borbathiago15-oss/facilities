"""Extensões Flask compartilhadas (singletons).

Este módulo não importa o app: quem importa é a fábrica (``create_app``).
Assim os modelos de cada módulo declaram-se sobre o MESMO ``db`` — uma
metadata só, para o ``create_all`` dos testes e para o autogenerate do
Alembic — sem import circular.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
# Sem limite global: só as rotas marcadas (o login) são limitadas.
limiter = Limiter(key_func=get_remote_address, default_limits=[])
