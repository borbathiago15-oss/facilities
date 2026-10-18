"""O painel por perfil (Fase 8): a nota de cada local da carteira e o que
está atrasado. O supervisor vê os locais dele; coordenador, gerente e
diretoria veem a carteira agrupada por cliente."""
from flask import Blueprint, render_template, request
from flask_login import current_user, login_required
from werkzeug.exceptions import Forbidden

from facilities.core.acesso import clientes_visiveis
from facilities.paineis import servico

bp = Blueprint('paineis', __name__)

PERFIS_DO_PAINEL = ('master', 'gerente', 'pleno', 'supervisor', 'visualizador')


def ve_painel(user):
    return user._effective_role() in PERFIS_DO_PAINEL


@bp.get('/painel')
@login_required
def painel():
    from facilities import demandas
    if not ve_painel(current_user):
        raise Forbidden('O painel é da supervisão, da gestão e da diretoria.')
    de, ate = servico.ler_periodo(request.args, maximo_dias=366)
    locais = clientes_visiveis()
    linhas = servico.notas(locais, de, ate)
    atrasadas = {}
    for item in demandas.demandas([c.id for c in locais]):
        if item['situacao'] == 'atrasada':
            atrasadas[item['client_id']] = atrasadas.get(item['client_id'], 0) + 1
    agrupar = current_user._effective_role() != 'supervisor'
    return render_template('paineis/painel.html', de=de, ate=ate, linhas=linhas,
                           grupos=servico.por_cliente(linhas) if agrupar else None,
                           resumo=servico.resumo(linhas), atrasadas=atrasadas,
                           faixas=servico.FAIXAS, indicadores=servico.INDICADORES,
                           faixa_critica=servico.FAIXA_CRITICA, faixa_boa=servico.FAIXA_BOA)
