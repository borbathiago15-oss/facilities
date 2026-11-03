"""API das telas novas da conta, dos avisos e do Início (Fase 6a da migração
para React).

As telas, nos mesmos endereços das antigas, abaixo de ``/novo``:

* ``/novo/`` (o Início da gestão: o que espera a pessoa hoje, o que resolver
  primeiro, os atalhos e os primeiros passos do administrador);
* ``/novo/avisos`` (os avisos da própria pessoa: abrir e "Marcar todos como
  lidos");
* ``/novo/conta/seguranca`` (a segunda etapa: ativar e desativar) e
  ``/novo/trocar-senha``.

Cada página tem a mesma porta da antiga (``login_required`` e as travas da
sessão: quem ainda precisa trocar a senha ou ativar a segunda etapa é levado
às telas antigas, as únicas que as travas abrem — ver ``docs/REACT.md``). Os
dados vêm da MESMA função que monta a tela antiga (``core.rotas.contexto_*``
e ``core.auth.preparar_codigo``); os envios chamam a MESMA ação
(``acao_*``: a regra, o commit, a rotação da sessão e o recado).

O segredo da segunda etapa (o texto e o QR): nunca vem numa leitura
(``GET``). Só a resposta do ``POST`` que o prepara o traz (``no-store``,
sem recado), o mesmo segredo que a tela antiga mostra (guardado na sessão
até ativar); a tela nova o guarda só no estado do componente.

Os envios de senha (trocar a senha, ativar e desligar o código) contam o erro da
senha atual no MESMO contador das telas antigas (``failed_login_count``, no
banco): cinco erros, somando as duas telas, bloqueiam a conta e derrubam a
sessão. Nenhuma dessas rotas antigas tem limite do Flask-Limiter; as novas
também não.
"""
from flask import jsonify, url_for
from flask_login import current_user, login_required

from facilities import tempo
from facilities.core import auth
from facilities.core import rotas as core
from facilities.core.models import MODULO_CHAMADOS
from facilities.telas import _casca, api, bp
from facilities.telas.cadastros import _dados, _feito, _hora, _sem_cache, nova


# ── As páginas (a casca), com a porta das antigas ─────────────────────────

@bp.get('/novo/')
@login_required
def inicio():
    return _casca()


@bp.get('/novo/avisos')
@login_required
def avisos():
    return _casca()


@bp.get('/novo/conta/seguranca')
@login_required
def conta_seguranca():
    return _casca()


@bp.get('/novo/trocar-senha')
@login_required
def conta_trocar_senha():
    return _casca()


# ── O Início ──────────────────────────────────────────────────────────────

@api.get('/inicio')
@login_required
def api_inicio():
    c = core.contexto_inicio()
    u = current_user
    papel = u._effective_role()
    tipos, situacoes = c['tipos'], c['situacoes']
    admin = papel == 'master'
    return _sem_cache({
        'primeiro_nome': (u.name or '').split(' ')[0],
        'data': tempo.agora().strftime('%d/%m/%Y'),
        'perfil': u.perfil_rotulo,
        'locais_na_carteira': (len(u.clients) if papel != 'master' and not u.all_clients
                               else None),
        'abrir_chamado': (nova(url_for('chamados.novo')) if u.can_access(MODULO_CHAMADOS)
                          else None),
        'numeros': [{**x, 'url': nova(x['url'])} for x in c['numeros']],
        'primeiro': [{'situacao': i['situacao'], 'situacao_rotulo': situacoes[i['situacao']],
                      'tipo_rotulo': tipos[i['tipo']], 'numero': i['numero'] or '',
                      'titulo': i['titulo'], 'local': i['local'],
                      'prazo': _hora(i['prazo'], '%d/%m %H:%M') if i['prazo'] else '',
                      'link': nova(i['link'])} for i in c['primeiro']],
        'fila': nova(url_for('demandas.painel')),
        'atalhos': [{**x, 'url': nova(x['url'])} for x in c['atalhos']],
        'administrador': ({
            'empresas': nova(url_for('cadastros.empresas')),
            'clientes': nova(url_for('cadastros.clientes')),
            'estados': nova(url_for('cadastros.estados')),
            'locais': nova(url_for('admin.contratos')),
            'pessoas': nova(url_for('admin.usuarios')),
        } if admin else None),
    })


# ── Os avisos ─────────────────────────────────────────────────────────────

@api.get('/avisos')
@login_required
def api_avisos():
    c = core.contexto_avisos()
    from facilities.core.models import Notification
    return _sem_cache({
        'avisos': [{'id': a.id, 'titulo': a.title, 'mensagem': a.message or '',
                    'nao_lido': a.status == 'unread', 'em': _hora(a.created_at) or ''}
                   for a in c['avisos']],
        # O "Marcar todos como lidos" da antiga aparece com qualquer não lido
        # (o número do sino), não só os 50 da lista.
        'nao_lidos': Notification.query.filter_by(user_id=current_user.id,
                                                  status='unread').count(),
    })


@api.post('/avisos/<int:aviso_id>/abrir')
@login_required
def api_abrir_aviso(aviso_id):
    return _feito(core.acao_abrir_aviso(aviso_id))


@api.post('/avisos/ler-todos')
@login_required
def api_ler_todos():
    return _feito(core.acao_ler_todos())


# ── A segunda etapa ───────────────────────────────────────────────────────

def _derrubada(destino):
    """A senha atual errada bloqueou a conta e a sessão caiu: o recado fica
    guardado para a tela de login (como na antiga), e a tela nova vai até
    ela."""
    return jsonify({'destino': destino, 'error': auth.MSG_LOGIN_RECUSADO}), 400


@api.get('/conta/seguranca')
@login_required
def api_seguranca():
    # Só o estado: o segredo nunca vem numa leitura.
    return _sem_cache({'ativo': bool(current_user.totp_ativo)})


@api.post('/conta/seguranca/codigo-novo')
@login_required
def api_seguranca_codigo_novo():
    """O segredo e o QR para o aplicativo autenticador — os mesmos que a tela
    antiga mostra (o da sessão, até ativar). Só nesta resposta."""
    novo = auth.preparar_codigo()
    resp = jsonify({'novo': novo})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@api.post('/conta/seguranca/ativar')
@login_required
def api_ativar_codigo():
    destino, derrubou = auth.acao_ativar_codigo(_dados())
    if derrubou:
        return _derrubada(destino)
    return _feito(destino)


@api.post('/conta/seguranca/desativar')
@login_required
def api_desativar_codigo():
    destino, derrubou = auth.acao_desativar_codigo(_dados())
    if derrubou:
        return _derrubada(destino)
    return _feito(destino)


# ── Trocar a senha ────────────────────────────────────────────────────────

@api.get('/trocar-senha')
@login_required
def api_trocar_senha_dados():
    return _sem_cache({'primeiro_acesso': bool(current_user.must_change_password),
                       'minimo': auth.SENHA_MINIMA})


@api.post('/trocar-senha')
@login_required
def api_trocar_senha():
    resultado, destino = auth.acao_trocar_senha(_dados())
    if resultado == 'derrubou':
        return _derrubada(destino)
    return _feito(destino)


# A conta de cliente (com o portal e a segunda etapa) abre, das telas
# antigas, a segurança, a troca de senha e os avisos (``_LIVRES_DO_CLIENTE``,
# sem o desativar: no perfil dela a segunda etapa é obrigatória, e a rota
# antiga responde 403). As novas abrem o mesmo.
ENDPOINTS_DO_CLIENTE = frozenset(
    {f'telas.{n}' for n in ('avisos', 'conta_seguranca', 'conta_trocar_senha')}
    | {f'api_v1.{n}' for n in ('api_avisos', 'api_abrir_aviso', 'api_ler_todos',
                               'api_seguranca', 'api_seguranca_codigo_novo',
                               'api_ativar_codigo', 'api_trocar_senha_dados',
                               'api_trocar_senha')})
