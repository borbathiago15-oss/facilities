"""As telas da gestão da Passagem de turno nas telas novas (Fase 2b):
o painel, o relatório mensal e a configuração dos modelos.

* sem login, 401 em JSON; as páginas novas pedem login como as antigas;
* os mesmos dados que a tela antiga escreve (``contexto_painel``,
  ``contexto_relatorio_mensal`` e ``contexto_configuracao``);
* a mesma porta, perfil a perfil: a configuração só com a permissão
  ``diario_config``; quem só lê (a diretoria) não recebe as ações;
* quem é de outro local não vê nada de A, nem pedindo o contrato de A;
* dentro das telas novas, os endereços da passagem apontam para elas.
"""
import html as html_mod
import json
import re

import pytest

from facilities import tempo
from tests import fabrica
from tests.test_telas_passagem import LOCAL_A, LOCAL_B, SEGREDO, cena  # noqa: F401


def _atributo(html, nome):
    m = re.search(nome + r"""='(.*?)'""", html, re.S)
    return json.loads(html_mod.unescape(m.group(1)))


def _script_json(html, ident):
    m = re.search(r'<script type="application/json" id="' + ident + r'">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def test_pede_login(client):
    for url in ('/api/v1/passagem/painel', '/api/v1/passagem/relatorio-mensal?client_id=1',
                '/api/v1/passagem/configuracao'):
        r = client.get(url)
        assert r.status_code == 401 and r.is_json, url
    for url in ('/novo/passagem-de-turno/', '/novo/passagem-de-turno/relatorio-mensal?client_id=1',
                '/novo/passagem-de-turno/configuracao'):
        r = client.get(url)
        assert r.status_code == 302 and '/login' in r.headers['Location'], url


@pytest.fixture()
def gestor(app_module, cena):  # noqa: F811
    """Um gestor (pleno) do local A, com a pendência da gestão e o chamado
    aberto a partir da ocorrência — o painel mostra "Ver OS"."""
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'passagem.gestor@trino.com', 'pleno', locais=[LOCAL_A],
                       nome='Gestor Passagem')
    c = fabrica.entrar(app_module, 'passagem.gestor@trino.com')
    r = c.post('/passagem-de-turno/api/pendencias', json={
        'client_id': cena['local'], 'titulo': f'Gestão {SEGREDO}', 'descricao': 'Conferir',
        'prioridade': 'alta'})
    assert r.status_code == 201, r.get_data(as_text=True)
    from facilities.passagem.models import DiarioOcorrencia
    with app_module.app.app_context():
        oc = DiarioOcorrencia.query.filter_by(turno_id=cena['turno']).one().id
    r = c.post(f'/passagem-de-turno/api/ocorrencias/{oc}/chamado')
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    return {**cena, 'gestor': c, 'ocorrencia': oc}


def test_painel_traz_os_dados_da_tela_antiga(app_module, gestor):
    c = gestor['gestor']
    q = f"?client_id={gestor['local']}&periodo=30d"
    r = c.get('/api/v1/passagem/painel' + q)
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    d = r.get_json()
    antigo = c.get('/passagem-de-turno/' + q).get_data(as_text=True)
    # Os gráficos e os modelos: o MESMO JSON que a tela antiga embute.
    graficos = _script_json(antigo, 'dop-graficos')
    assert d['dados']['pareto'] == graficos['pareto'] and graficos['pareto']
    assert d['dados']['turnos_comparativo'] == graficos['comparativo']
    assert d['dados']['burndown'] == graficos['burndown']
    assert d['modelos'] == _script_json(antigo, 'tt-modelos')
    assert d['client_id'] == gestor['local'] and d['periodo'] == '30d'
    assert d['dados']['periodo_label'] == 'Últimos 30 dias' and d['dados']['n_turnos'] == 1
    assert f"{d['dados']['inicio']} a {d['dados']['fim']}" in antigo
    assert d['dados']['aderencia']['pct'] == 100.0 and d['dados']['aderencia']['faixa'] == 'ok'
    assert d['dados']['areas_disponiveis'] == [{'id': gestor['area'], 'nome': 'Expedição'}]
    assert d['dados']['turnos_disponiveis'] == ['1º Turno', '2º Turno']
    # As ocorrências: a que já virou chamado mostra a OS, como a antiga.
    [o] = d['dados']['ocorrencias']
    assert o['descricao'] == f'Pallet {SEGREDO}' and o['gravidade'] == 'critica'
    assert o['quando'] == {'dia': tempo.hoje().strftime('%d/%m'), 'turno': '1º Turno'}
    assert o['chamado'] and f"Ver {o['chamado']['numero']}" in antigo
    # O chamado abre na tela nova (Fase 4a): o mesmo endereço abaixo de /novo.
    assert o['chamado']['url'].startswith('/novo/chamados/')
    assert o['chamado']['url'].removeprefix('/novo') in antigo
    # As críticas: as mesmas pendências, na mesma ordem.
    titulos = [x['titulo'] for x in d['dados']['criticas']]
    assert sorted(titulos) == sorted([f'Devolução {SEGREDO}', f'Gestão {SEGREDO}'])
    ids_antigos = [int(x) for x in re.findall(r'data-acao="resolverPendenciaDop" data-args="\[(\d+)\]"',
                                              antigo)]
    assert [x['id'] for x in d['dados']['criticas']] == ids_antigos
    assert d['dados']['n_criticas'] == 2
    # Os últimos turnos: os mesmos, com a área.
    assert [t['id'] for t in d['turnos']] == [
        int(x) for x in re.findall(r'href="/passagem-de-turno/turno/(\d+)"', antigo)]
    assert d['turnos'][0]['area'] == 'Expedição' and d['turnos'][0]['status'] == 'encerrado'
    # O que o gestor pode: as mesmas perguntas da tela antiga.
    assert d['pode_gravar'] and d['pode_chamado'] and d['pode_ver_chamado']
    assert d['e_gestao'] and d['pode_configurar']
    assert 'data-bs-target="#modalTarefaTurno"' in antigo
    # Dentro das telas novas, os endereços da passagem são os novos.
    assert d['links'] == {
        'nova_passagem': f"/novo/passagem-de-turno/turno?client_id={gestor['local']}",
        'relatorio': f"/novo/passagem-de-turno/relatorio-mensal?client_id={gestor['local']}",
        'configurar': f"/novo/passagem-de-turno/configuracao?client_id={gestor['local']}",
        'ver_turno': '/novo/passagem-de-turno/turno/'}


def test_painel_com_o_recorte_da_query_string(app_module, gestor):
    """Área de fora vira "todas", turno e período passam como na antiga."""
    c = gestor['gestor']
    d = c.get(f"/api/v1/passagem/painel?client_id={gestor['local']}&periodo=custom"
              f"&de=2000-01-01&ate=2000-01-02&turno=2º Turno&area_id=999999").get_json()
    assert d['periodo'] == 'custom' and d['de'] == '2000-01-01' and d['ate'] == '2000-01-02'
    assert d['turno_sel'] == '2º Turno' and d['area_sel'] == d['todas_as_areas'] == 0
    assert d['dados']['n_turnos'] == 0 and d['dados']['ocorrencias'] == [] and d['turnos'] == []
    assert d['dados']['inicio'] == '01/01/2000' and d['dados']['fim'] == '02/01/2000'
    d = c.get(f"/api/v1/passagem/painel?client_id={gestor['local']}&periodo=xpto").get_json()
    assert d['periodo'] == '7d'


def test_relatorio_traz_os_dados_da_tela_antiga(app_module, gestor):
    c = gestor['gestor']
    hoje = tempo.hoje()
    q = f"?client_id={gestor['local']}&mes={hoje.month}&ano={hoje.year}&area_id={gestor['area']}"
    r = c.get('/api/v1/passagem/relatorio-mensal' + q)
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    d = r.get_json()
    antigo = c.get('/passagem-de-turno/relatorio-mensal' + q).get_data(as_text=True)
    rel = d['rel']
    assert d['cliente'] == {'id': gestor['local'], 'nome': LOCAL_A}
    assert d['mes'] == hoje.month and d['ano'] == hoje.year and d['area_sel'] == gestor['area']
    assert rel['area'] == 'Expedição' and f"Competência {rel['competencia']}" in antigo
    assert rel['turnos'] == {'total': 1, 'por_turno': [['1º Turno', 1]]}
    assert rel['aderencia']['pct'] == 100.0 and rel['aderencia']['meta'] == 95.0
    assert rel['ocorrencias']['total'] == 1
    assert rel['ocorrencias']['mais_frequente'] == {'tipo': 'Avaria', 'qtd': 1}
    assert [x['descricao'] for x in rel['ocorrencias']['atencao']] == [f'Pallet {SEGREDO}']
    assert rel['ocorrencias']['lista'][0]['data'] == hoje.strftime('%d/%m/%Y')
    em_aberto = [x['titulo'] for x in rel['pendencias']['lista_em_aberto']]
    assert sorted(em_aberto) == sorted([f'Devolução {SEGREDO}', f'Gestão {SEGREDO}'])
    assert [x['nome'] for x in rel['rotinas']] == ['Doca limpa']
    assert rel['bordo'] == [{'data': hoje.strftime('%d/%m/%Y'), 'turno': '1º Turno',
                             'texto': f'Observação {SEGREDO}'}]
    for texto in em_aberto + ['Doca limpa', f'Pallet {SEGREDO}', f'Observação {SEGREDO}',
                              rel['emitido_em'], rel['emitido_por']]:
        assert html_mod.escape(texto, quote=False) in antigo
    assert [n for n, _ in d['meses']] == list(range(1, 13)) and hoje.year in d['anos']
    # O PDF continua no servidor: o link é o da rota antiga, com a área da tela.
    assert d['links']['pdf'] == (f"/passagem-de-turno/relatorio-mensal?client_id={gestor['local']}"
                                 f"&mes={hoje.month}&ano={hoje.year}&format=pdf"
                                 f"&area_id={gestor['area']}")
    assert html_mod.escape(d['links']['pdf']) in antigo
    r = c.get(d['links']['pdf'])
    assert r.status_code == 200 and r.mimetype == 'application/pdf'
    assert d['links']['painel'] == f"/novo/passagem-de-turno/?client_id={gestor['local']}"


def test_relatorio_recusa_como_a_tela_antiga(app_module, gestor):
    c = gestor['gestor']
    for q in ('', f"?client_id={gestor['local']}&mes=0", f"?client_id={gestor['local']}&ano=1999",
              f"?client_id={gestor['local']}&mes=abc"):
        r = c.get('/api/v1/passagem/relatorio-mensal' + q)
        assert r.status_code == c.get('/passagem-de-turno/relatorio-mensal' + q).status_code == 400
        assert r.is_json and r.get_json()['error']


def test_configuracao_traz_os_dados_da_tela_antiga(app_module, gestor):
    c = gestor['gestor']
    q = f"?client_id={gestor['local']}&editar={gestor['cfg']}"
    r = c.get('/api/v1/passagem/configuracao' + q)
    assert r.status_code == 200 and r.headers['Cache-Control'] == 'no-store'
    d = r.get_json()
    antigo = c.get('/passagem-de-turno/configuracao' + q).get_data(as_text=True)
    assert d['configs'] == _atributo(antigo, 'data-configs')
    assert d['areas'] == _atributo(antigo, 'data-areas')
    assert d['areas'] == [{'id': gestor['area'], 'nome': 'Expedição', 'ativo': True, 'modelos': 1}]
    assert d['usos'] == {str(gestor['cfg']): 1}
    assert f'data-id="{gestor["cfg"]}" data-usos="1"' in antigo
    assert d['editar'] == gestor['cfg'] and d['client_id'] == gestor['local']
    assert [m['chave'] for m in d['modelos_prontos']] == re.findall(
        r'name="servico" value="([^"]+)"', antigo)
    assert d['links']['modelos_prontos'] == '/passagem-de-turno/modelos-prontos'
    assert d['links']['painel'] == f"/novo/passagem-de-turno/?client_id={gestor['local']}"


def test_configuracao_mostra_o_recado_dos_modelos_prontos(app_module, gestor):
    """O "Criar modelos" é o formulário de sempre (redireciona); o recado
    dele, que a antiga mostra no topo, chega à nova pela API."""
    c = gestor['gestor']
    r = c.post('/passagem-de-turno/modelos-prontos',
               data={'client_id': gestor['local'], 'servico': 'limpeza'})
    assert r.status_code == 302
    d = c.get(f"/api/v1/passagem/configuracao?client_id={gestor['local']}").get_json()
    assert d['recados'][0]['tipo'] == 'success' and 'Modelo(s) criado(s)' in d['recados'][0]['texto']
    assert any(m['nome'].startswith('Limpeza') for m in d['configs'])
    # De uma vez só: o recado não volta.
    assert c.get(f"/api/v1/passagem/configuracao?client_id={gestor['local']}").get_json()['recados'] == []


PAPEIS = ['visualizador', 'encarregado', 'tecnico', 'supervisor', 'pleno', 'gerente']


@pytest.mark.parametrize('papel', PAPEIS + ['supervisor+config'])
def test_a_porta_e_a_mesma_da_tela_antiga(app_module, cena, papel):  # noqa: F811
    """O mesmo código de resposta nas telas antigas, nas páginas novas e na
    API; a configuração só com ``diario_config`` (concedida ou de gestão)."""
    base, conceder = papel.split('+')[0], '+config' in papel
    with app_module.app.app_context():
        extra = {'permissions_json': json.dumps(['diario_config'])} if conceder else {}
        fabrica.pessoa(app_module, f'porta2b.{base}@trino.com', base, locais=[LOCAL_A], **extra)
    c = fabrica.entrar(app_module, f'porta2b.{base}@trino.com')
    hoje = tempo.hoje()
    q = f"?client_id={cena['local']}"
    qr = q + f'&mes={hoje.month}&ano={hoje.year}'
    for antiga, nova, api in (
            ('/passagem-de-turno/' + q, '/novo/passagem-de-turno/' + q, '/api/v1/passagem/painel' + q),
            ('/passagem-de-turno/relatorio-mensal' + qr, '/novo/passagem-de-turno/relatorio-mensal' + qr,
             '/api/v1/passagem/relatorio-mensal' + qr),
            ('/passagem-de-turno/configuracao' + q, '/novo/passagem-de-turno/configuracao' + q,
             '/api/v1/passagem/configuracao' + q)):
        r_antiga = c.get(antiga)
        r_api = c.get(api)
        if r_antiga.status_code == 302:
            # Sem a permissão fina: a página volta ao início com um aviso; a
            # API responde 403 em JSON, como as outras APIs do módulo.
            assert r_api.status_code == 403, (papel, api)
            r_nova = c.get(nova)
            assert r_nova.status_code == 302, (papel, nova)
            assert r_nova.headers['Location'] == r_antiga.headers['Location']
        else:
            assert r_api.status_code == r_antiga.status_code, (papel, api)
            assert c.get(nova).status_code in (
                (200, 503) if r_antiga.status_code == 200 else (r_antiga.status_code,)), (papel, nova)
        if r_api.status_code != 200:
            assert r_api.is_json and SEGREDO not in r_api.get_data(as_text=True)
    pode_config = c.get('/api/v1/passagem/configuracao' + q).status_code == 200
    assert pode_config == (base in ('pleno', 'gerente') or conceder), papel
    # As ações do painel: as mesmas que a tela antiga oferece a este perfil.
    r = c.get('/api/v1/passagem/painel' + q)
    if r.status_code == 200:
        d = r.get_json()
        antigo = c.get('/passagem-de-turno/' + q).get_data(as_text=True)
        assert d['pode_gravar'] == ('Nova passagem' in antigo), papel
        assert d['pode_chamado'] == ('dopAbrirChamado' in antigo), papel
        assert d['e_gestao'] == ('#modalPendencia' in antigo), papel
        assert d['pode_configurar'] == ('bi-sliders' in antigo), papel
        assert d['pode_configurar'] == pode_config, papel
        if base == 'visualizador':
            # A diretoria só lê: nenhuma ação de gravar, e o servidor recusa.
            assert not (d['pode_gravar'] or d['pode_chamado'] or d['e_gestao'])
            [p] = [x for x in d['dados']['criticas']]
            assert c.post(f"/passagem-de-turno/api/pendencias/{p['id']}/resolver",
                          json={'resolucao': 'x'}).status_code == 403


def test_quem_e_de_outro_local_nao_ve_a_gestao_de_a(app_module, gestor):
    with app_module.app.app_context():
        fabrica.pessoa(app_module, 'passagem.gestorb@trino.com', 'pleno', locais=[LOCAL_B])
    c = fabrica.entrar(app_module, 'passagem.gestorb@trino.com')
    q = f"?client_id={gestor['local']}"
    # O painel e a configuração abrem no local de B, sem nada de A.
    for url in ('/api/v1/passagem/painel' + q, '/api/v1/passagem/configuracao' + q):
        r = c.get(url)
        assert r.status_code == 200 and SEGREDO not in r.get_data(as_text=True), url
        d = r.get_json()
        assert d['client_id'] != gestor['local'] and [x['nome'] for x in d['clients']] == [LOCAL_B]
    d = c.get('/api/v1/passagem/configuracao' + q + f"&editar={gestor['cfg']}").get_json()
    assert d['configs'] == [] or all(x['client_id'] != gestor['local'] for x in d['configs'])
    # O relatório de A: 403, antes de qualquer consulta.
    r = c.get('/api/v1/passagem/relatorio-mensal' + q)
    assert r.status_code == 403 and r.is_json and SEGREDO not in r.get_data(as_text=True)
    assert c.get('/novo/passagem-de-turno/relatorio-mensal' + q).status_code in (200, 503)


def test_a_nova_passagem_e_a_leitura_voltam_ao_painel_novo(app_module, cena):  # noqa: F811
    c = cena['ana']
    painel = f"/novo/passagem-de-turno/?client_id={cena['local']}"
    assert c.get(f"/api/v1/passagem/turno?client_id={cena['local']}").get_json()['links']['painel'] == painel
    assert c.get(f"/api/v1/passagem/turno/{cena['turno']}").get_json()['links']['painel'] == painel
    # As telas antigas e o menu não mudam.
    assert 'href="/passagem-de-turno/?client_id=' in c.get(
        f"/passagem-de-turno/turno/{cena['turno']}").get_data(as_text=True)
    menu = [i['url'] for g in c.get('/api/v1/eu').get_json()['menu'] for i in g['itens']]
    assert '/passagem-de-turno/' in menu and not any(u.startswith('/novo/passagem') for u in menu)
