"""Chamados / ordens de serviço (em construção)."""
from flask import Blueprint, render_template
from flask_login import login_required

from facilities.core.acesso import module_required

bp = Blueprint('chamados', __name__, url_prefix='/chamados')
MODULO = 'chamados'


@bp.get('/')
@login_required
@module_required(MODULO)
def index():
    return render_template('base.html')
