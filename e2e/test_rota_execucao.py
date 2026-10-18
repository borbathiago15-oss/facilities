"""Fase 4A — a Ana executa a rota no aplicativo, no celular e no PC.

* lê o QR com a câmera → o ponto abre com a tarefa da hora → "Fazer agora"
  → responde, tira a foto de depois → Confirmar → "Concluída no prazo";
* sem sinal: confirma, fica guardado no aparelho e sobe UMA vez quando o
  sinal volta, marcado "feito sem sinal".
"""
import os

from conftest import abrir_contexto, entrar

AQUI = os.path.dirname(os.path.abspath(__file__))


def _foto(tmp_path):
    from camera import _qr_em_imagem
    caminho = tmp_path / 'depois.jpg'
    _qr_em_imagem('foto', 120).save(caminho, 'JPEG')
    return str(caminho)


def _execucoes(servidor):
    return servidor['sql']('SELECT e.sem_sinal, u.email, t.status FROM execucoes e '
                           'JOIN users u ON u.id = e.user_id JOIN tarefas_dia t ON t.id = e.tarefa_id')


def _fazer_checklist(pg, foto):
    pg.get_by_role('button', name='Fazer agora').first.click()
    pg.locator('label.fc-opcao', has_text='Sim').click()
    pg.set_input_files('[data-foto="depois"]', foto)
    pg.get_by_role('button', name='Confirmar').click()


def test_ana_le_o_qr_e_faz_o_checklist(servidor, navegador, perfil, tmp_path):
    url_do_qr = servidor['base'] + '/q/' + servidor['qr']
    b, ctx = abrir_contexto(navegador, perfil, camera_com=url_do_qr)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'ana@e2e.test')
        pg.goto(servidor['base'] + '/app/ler-qr')
        pg.wait_for_url('**/app/turno?ponto=*', timeout=20000)
        assert pg.get_by_role('heading', name='Porta do banheiro').is_visible()
        pg.wait_for_timeout(500)          # o selo de leitura volta do servidor
        _fazer_checklist(pg, _foto(tmp_path))
        pg.wait_for_selector('text=Registrado: Concluída no prazo', timeout=15000)
        assert _execucoes(servidor) == [(0, 'ana@e2e.test', 'concluida_no_prazo')]
        largura = pg.evaluate('document.documentElement.scrollWidth')
        assert largura <= pg.viewport_size['width']
    finally:
        b.close()


def test_sem_sinal_a_execucao_sobe_depois_uma_vez(servidor, navegador, perfil, tmp_path):
    b, ctx = abrir_contexto(navegador, perfil)
    try:
        pg = ctx.new_page()
        entrar(pg, servidor['base'], 'ana@e2e.test')
        pg.goto(servidor['base'] + '/app/turno?ponto=' + servidor['qr'])
        pg.wait_for_load_state('networkidle')
        ctx.set_offline(True)
        _fazer_checklist(pg, _foto(tmp_path))
        pg.wait_for_selector('text=ficou guardada no aparelho', timeout=15000)
        assert _execucoes(servidor) == []
        ctx.set_offline(False)
        pg.evaluate('window.TrinoFila.enviarAgora()')
        pg.wait_for_function("!document.querySelector('.fila-selo') || "
                             "document.querySelector('.fila-selo').hidden", timeout=15000)
        pg.evaluate('window.TrinoFila.enviarAgora()')
        pg.wait_for_timeout(1500)
        assert _execucoes(servidor) == [(1, 'ana@e2e.test', 'concluida_no_prazo')]
    finally:
        b.close()
