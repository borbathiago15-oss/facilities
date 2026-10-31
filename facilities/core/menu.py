"""O menu do sistema: quem vê cada item. Fonte ÚNICA das duas telas — o
``_menu.html`` (Jinja) e a casca das telas novas em React (``/api/v1/eu``).

Cada item aparece só para quem pode abrir a tela — a mesma regra da rota
(esconder não é a trava; a trava é a rota).

Um item é ``(endpoint, rótulo, ícone, prefixos)``: ``prefixos`` diz em que
telas ele fica aceso — endpoints que começam assim; ``=x`` só o endpoint
``x``; ``-x`` nunca em ``x``. Vazio: só no próprio endpoint.
"""
from flask import url_for

def _aceso(endpoint, prefixos, ep):
    if not prefixos:
        return ep == endpoint
    if any(p.startswith('-') and ep == p[1:] for p in prefixos):
        return False
    for p in prefixos:
        if p.startswith('-'):
            continue
        if p.startswith('='):
            if ep == p[1:]:
                return True
        elif ep.startswith(p):
            return True
    return False


def grupos(user):
    """Os grupos do menu desta pessoa, na ordem da tela."""
    r = user._effective_role()
    if r == 'cliente':
        return [{'titulo': 'Portal', 'fixo': True, 'itens': [
            ('portal.inicio', 'Seus locais', 'bi-buildings',
             ('=portal.inicio', '=portal.local', '=portal.chamado')),
            ('portal.cobrancas', 'Cobranças', 'bi-megaphone',
             ('=portal.cobrancas', '=portal.cobranca')),
            ('portal.relatorios', 'Relatórios', 'bi-file-earmark-bar-graph',
             ('=portal.relatorios', '=portal.relatorio')),
        ]}]

    ve_painel = r in ('master', 'gerente', 'pleno', 'supervisor', 'visualizador')
    ve_chamados = user.can_view('chamados')
    ve_passagem = user.can_view('diario_operacional')
    ve_rotina = user.e_gestao() or r in ('supervisor', 'visualizador')
    ve_cadastros = user.e_gestao() or r == 'visualizador'
    saida = []

    hoje = [('core.inicio', 'Início', 'bi-house-door', ())]
    if ve_painel:
        hoje += [('paineis.painel', 'Painel', 'bi-speedometer2', ()),
                 ('relatorios.inicio', 'Relatórios', 'bi-file-earmark-bar-graph',
                  ('relatorios.',))]
    if ve_chamados:
        hoje += [('demandas.painel', 'Demandas', 'bi-inboxes', ('demandas.',)),
                 ('cobrancas.lista', 'Cobranças do cliente', 'bi-megaphone', ('cobrancas.',))]
    saida.append({'titulo': 'Hoje', 'fixo': True, 'itens': hoje})

    operacao = []
    if ve_chamados:
        operacao.append(('chamados.index', 'Chamados', 'bi-tools', ('chamados.',)))
    if ve_passagem:
        operacao.append(('diario_operacional.index', 'Passagem de turno', 'bi-journal-text',
                         ('diario_operacional.',)))
    if ve_rotina:
        operacao.append(('rotas.inicio', 'Rotina dos locais', 'bi-signpost-split',
                         ('rotas.', 'preventiva.', 'equipes.', 'visitas.')))
    if operacao:
        saida.append({'titulo': 'Operação', 'aberto_fora_de': ('cadastros.', 'admin.',
                                                               'montagem.', '=rotas.biblioteca',
                                                               '=rotas.modelo'),
                      'itens': operacao})

    if ve_painel:
        saida.append({'titulo': 'Recursos', 'aberto_em': ('materiais.',), 'itens': [
            ('materiais.catalogo', 'Materiais e estoque', 'bi-box-seam', ('materiais.',))]})

    if ve_cadastros:
        # Na ordem em que se monta um contrato (empresa → cliente → estados →
        # locais → estrutura e QR → pessoas → checklists).
        cad = []
        if r in ('master', 'gerente', 'pleno'):
            cad += [('centros.clientes', 'Áreas e rotas dos clientes', 'bi-diagram-2',
                     ('centros.',)),
                    ('montagem.inicio', 'Novo contrato', 'bi-magic',
                     ('montagem.', '-montagem.convites')),
                    ('montagem.convites', 'Convites', 'bi-person-plus', ())]
        if r == 'master':
            cad += [('cadastros.empresas', 'Empresas do grupo', 'bi-building', ()),
                    ('cadastros.clientes', 'Clientes', 'bi-briefcase', ()),
                    ('cadastros.estados', 'Estados em uso', 'bi-map', ()),
                    ('admin.contratos', 'Locais', 'bi-geo-alt', ())]
        cad.append(('cadastros.inicio', 'Estrutura e QR dos locais', 'bi-diagram-3',
                    ('=cadastros.inicio', '=cadastros.local', '=cadastros.ponto',
                     '=cadastros.trilha', '=cadastros.trilha_local')))
        if r == 'master':
            cad.append(('admin.usuarios', 'Pessoas e acessos', 'bi-people', ()))
        if ve_rotina:
            cad.append(('rotas.biblioteca', 'Biblioteca de checklists', 'bi-book', ()))
        saida.append({'titulo': 'Cadastros', 'sempre_aberto': True, 'itens': cad})
        if r == 'master':
            saida.append({'titulo': 'Configuração', 'aberto_em': ('integracao.',), 'itens': [
                ('integracao.chaves', 'Integração', 'bi-plug', ('integracao.',))]})

    saida.append({'titulo': '', 'fixo': True, 'itens': [
        ('campo.inicio', 'Aplicativo de campo', 'bi-phone', ())]})
    return saida


def montar(user, ep=''):
    """O menu pronto para mostrar: url de cada item e o que está aceso/aberto."""
    ep = ep or ''
    saida = []
    for g in grupos(user):
        itens = [{'endpoint': e, 'rotulo': rot, 'icone': ic, 'url': url_for(e),
                  'ativo': _aceso(e, pref, ep), 'acende_em': list(pref) or [f'={e}']}
                 for e, rot, ic, pref in g['itens']]
        if g.get('fixo'):
            aberto = True
        elif g.get('sempre_aberto'):
            aberto = True
        elif 'aberto_fora_de' in g:
            aberto = not _aceso('', g['aberto_fora_de'], ep)
        else:
            aberto = _aceso('', g.get('aberto_em', ()), ep)
        saida.append({'titulo': g['titulo'], 'fixo': bool(g.get('fixo')), 'aberto': aberto,
                      'itens': itens})
    return saida
