"""O PDF do fechamento mensal da Passagem de Turno.

A especificação pedia WeasyPrint. **A casa não tem WeasyPrint** — não está em
``requirements.txt``, não está instalado, e ele depende de Pango/Cairo, que
não existem na imagem de produção. O Trino já desenha PDF com ReportLab
(``trino/web/sla_pdf.py``, ``trino/domains/reports/.../pdf_builder.py``), e é
o que se usa aqui: mesma identidade visual, mesma dependência já em produção,
zero risco de subir uma imagem que não builda.

A régua é a mesma do PDF de SLA, porque o leitor é o mesmo — gestor de
multinacional e diretoria:

* a primeira página responde sozinha (o scorecard da competência);
* nada de enfeite sem dado: cor só para situação, sempre com a palavra junto;
* número que não existe não vira zero — "sem base" é escrito por extenso.

Não há autorização nem consulta aqui. Entra o dicionário de
``diario_analitico.fechamento_mensal`` (o MESMO que alimenta a tela) e sai o
arquivo — é o que garante que o anexo do e-mail não discorde da tela.
"""
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from facilities import tempo
from facilities.passagem.analitico import rotulo_prioridade

NAVY = colors.HexColor('#0f172a')
MARCA = colors.HexColor('#9d202c')
TINTA = colors.HexColor('#111827')
TINTA_2 = colors.HexColor('#374151')
CINZA = colors.HexColor('#6b7280')
CINZA_CLARO = colors.HexColor('#9ca3af')
LINHA = colors.HexColor('#e5e7eb')
FUNDO = colors.HexColor('#f8fafc')

VERDE = colors.HexColor('#15803d')
AMBAR = colors.HexColor('#b45309')
VERMELHO = colors.HexColor('#b91c1c')
COR_FAIXA = {'ok': VERDE, 'alerta': AMBAR, 'critico': VERMELHO,
             'neutro': CINZA}
# A cor nunca carrega o sentido sozinha: impressão em preto e branco e
# daltonismo são a regra, não a exceção.
TEXTO_FAIXA = {'ok': '● No alvo', 'alerta': '◐ Atenção',
               'critico': '○ Crítico', 'neutro': '– Sem base'}

# A marca da capa é TEXTO. O logo com nome escrito que veio do Trino
# Intelligence dizia o nome DELE (foi retirado do projeto), e este documento
# vai para o cliente com o nome do Facilities. Texto também não depende de
# arquivo nenhum existir na imagem.
MARCA_DA_CAPA = 'GRUPO TRINO · FACILITIES'


def _plural(n, um, varios):
    """'1 turno' / '3 turnos': o relatório vai para o cliente, e 'turno(s)'
    é o rascunho de uma frase, não a frase."""
    return f'{n} {um if n == 1 else varios}'

def _esc(texto):
    """Escapa o que entra num ``Paragraph`` — um ``&`` cru derruba o parse."""
    return (str(texto if texto is not None else '')
            .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _pct(valor):
    if valor is None:
        return '—'
    return f'{valor:.1f}'.replace('.', ',') + '%'


def _estilos():
    base = getSampleStyleSheet()

    def e(nome, **kw):
        pai = kw.pop('parent', base['Normal'])
        return ParagraphStyle(nome, parent=pai, **kw)

    return {
        'capa_marca': e('capa_marca', fontSize=12, leading=16, textColor=NAVY,
                        fontName='Helvetica-Bold'),
        'capa_olho': e('capa_olho', fontSize=10, leading=14, textColor=MARCA,
                       fontName='Helvetica-Bold'),
        'capa_tit': e('capa_tit', fontSize=26, leading=30, textColor=NAVY,
                      fontName='Helvetica-Bold'),
        'capa_sub': e('capa_sub', fontSize=13, leading=18, textColor=TINTA_2),
        'capa_pe': e('capa_pe', fontSize=8.5, leading=12, textColor=CINZA),
        'secao': e('secao', fontSize=13, leading=17, textColor=NAVY,
                   fontName='Helvetica-Bold', spaceAfter=1),
        'secao_sub': e('secao_sub', fontSize=8.5, leading=12, textColor=CINZA),
        'rotulo': e('rotulo', fontSize=7, leading=9.5, textColor=CINZA,
                    fontName='Helvetica-Bold'),
        'th': e('th', fontSize=7.5, leading=10, textColor=colors.white,
                fontName='Helvetica-Bold'),
        'th_r': e('th_r', fontSize=7.5, leading=10, textColor=colors.white,
                  fontName='Helvetica-Bold', alignment=TA_RIGHT),
        'cel': e('cel', fontSize=8, leading=11, textColor=TINTA),
        'cel_r': e('cel_r', fontSize=8, leading=11, textColor=TINTA,
                   alignment=TA_RIGHT),
        'cel_b': e('cel_b', fontSize=8, leading=11, textColor=TINTA,
                   fontName='Helvetica-Bold'),
        'cel_p': e('cel_p', fontSize=7, leading=9.5, textColor=CINZA),
        'kpi': e('kpi', fontSize=20, leading=23, textColor=NAVY,
                 fontName='Helvetica-Bold'),
        'bordo_q': e('bordo_q', fontSize=7.5, leading=10, textColor=NAVY,
                     fontName='Helvetica-Bold'),
        'bordo_t': e('bordo_t', fontSize=8, leading=11.5, textColor=TINTA_2),
        'centro': e('centro', fontSize=9, leading=13, textColor=CINZA,
                    alignment=TA_CENTER),
    }


def _titulo(numero, texto, sub, est):
    return [Paragraph(f'{numero}. {_esc(texto)}', est['secao']),
            Paragraph(_esc(sub), est['secao_sub']),
            Spacer(1, 4 * mm)]


def _estilo_tabela(n_colunas, zebra_desde=1):
    return TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.2),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('LINEBELOW', (0, zebra_desde - 1), (-1, -1), 0.4, LINHA),
        ('ROWBACKGROUNDS', (0, zebra_desde), (-1, -1), [colors.white, FUNDO]),
    ])


def _cartao(rotulo, valor, nota, est, largura, cor=NAVY):
    """Um big number do scorecard, como mini-tabela de uma coluna.

    Sem moldura própria: a borda é desenhada pela faixa que o contém, senão
    cada cartão fecha na altura do próprio texto e os quatro saem desalinhados
    — quatro retângulos de alturas diferentes é a primeira coisa que o olho
    vê num documento que deveria transmitir cuidado.
    """
    estilo_valor = ParagraphStyle('kpi_cor', parent=est['kpi'], textColor=cor)
    dentro = Table(
        [[Paragraph(_esc(rotulo).upper(), est['rotulo'])],
         [Paragraph(_esc(valor), estilo_valor)],
         [Paragraph(_esc(nota), est['cel_p'])]],
        colWidths=[largura - 14])
    dentro.setStyle(TableStyle([
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    return dentro


def _capa(rel, est, largura, altura):
    fluxo = [Spacer(1, altura * 0.20),
             Paragraph(MARCA_DA_CAPA, est['capa_marca']),
             Spacer(1, 9 * mm)]
    fluxo += [
        # O nome do módulo, não o do pacote: "Diário Operacional" é como ele
        # nasceu, e o documento vai para o cliente com o nome que a tela usa.
        Paragraph('PASSAGEM DE TURNO', est['capa_olho']),
        Spacer(1, 2 * mm),
        Paragraph('Relatório Executivo Mensal', est['capa_tit']),
        Spacer(1, 5 * mm),
        # A área entra no cabeçalho: o relatório da Expedição e o do
        # Almoxarifado são documentos diferentes e vão parar na mesma
        # pasta.
        Paragraph(_esc(rel['cliente'] +
                       (' · ' + rel['area'] if rel.get('area') else '')),
                  est['capa_sub']),
        Paragraph(f"Competência {_esc(rel['competencia'])}", est['capa_sub']),
        Spacer(1, 10 * mm),
        # No mês em curso o período vai até hoje (ver ``fim_apurado`` em
        # ``fechamento_mensal``): a capa não pode prometer o mês inteiro.
        # Competência futura não tem período apurado nenhum.
        Paragraph(
            (f"Período apurado: {rel['inicio'].strftime('%d/%m/%Y')} a "
             f"{rel['fim_apurado'].strftime('%d/%m/%Y')}"
             f"{' (competência em andamento)' if rel.get('em_andamento') else ''}"
             if rel.get('fim_apurado') else
             "Competência ainda não iniciada")
            + f"<br/>"
            f"Emitido em {rel['emitido_em'].strftime('%d/%m/%Y às %H:%M')} "
            f"por {_esc(rel['emitido_por'])}", est['capa_pe']),
    ]
    return fluxo


def _scorecard(rel, est, largura):
    """Bloco 1 — os quatro números que respondem pelo mês."""
    turnos = rel['turnos']
    quebra = ' | '.join(f'{nome}: {qtd}' for nome, qtd in turnos['por_turno'])
    ader, pend, ocor = rel['aderencia'], rel['pendencias'], rel['ocorrencias']
    topo = (f"Mais frequente: {ocor['pareto'][0]['tipo']} "
            f"({ocor['pareto'][0]['qtd']})" if ocor['pareto']
            else 'Nenhum desvio registrado')

    # Uma coluna vazia e estreita entre os cartões faz o "gap" sem que o
    # espaço fique dentro da moldura de ninguém.
    respiro = 3.5 * mm
    col = (largura - 3 * respiro) / 4.0
    cartoes = [_cartao(r, v, n, est, col, c) for r, v, n, c in [
        ('Turnos concluídos', str(turnos['total']),
         quebra or 'Nenhum turno encerrado na competência', NAVY),
        ('Aderência global às rotinas', _pct(ader['pct']),
         f"{TEXTO_FAIXA[ader['faixa']]} · {ader['cumpridas']} de "
         f"{ader['exigidas']} atividades · meta {int(ader['meta'])}%",
         COR_FAIXA[ader['faixa']]),
        ('Eficácia na resolução de pendências', _pct(pend['pct']),
         f"{pend['resolvidas']} resolvidas de {pend['abertas']} abertas no mês",
         COR_FAIXA[pend['faixa']]),
        ('Ocorrências e desvios', str(ocor['total']), topo, NAVY),
    ]]
    celulas, larguras = [], []
    for i, cartao in enumerate(cartoes):
        if i:
            celulas.append('')
            larguras.append(respiro)
        celulas.append(cartao)
        larguras.append(col)

    faixa = Table([celulas], colWidths=larguras, hAlign='LEFT')
    estilo_faixa = [
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]
    for coluna in (0, 2, 4, 6):     # as colunas dos cartões, não os respiros
        estilo_faixa += [
            ('BOX', (coluna, 0), (coluna, 0), 0.6, LINHA),
            ('BACKGROUND', (coluna, 0), (coluna, 0), colors.white),
            ('LEFTPADDING', (coluna, 0), (coluna, 0), 7),
            ('RIGHTPADDING', (coluna, 0), (coluna, 0), 7),
            ('TOPPADDING', (coluna, 0), (coluna, 0), 7),
            ('BOTTOMPADDING', (coluna, 0), (coluna, 0), 7),
        ]
    faixa.setStyle(TableStyle(estilo_faixa))
    return _titulo(1, 'Scorecard consolidado do mês',
                   'O que a competência entregou, em quatro números',
                   est) + [faixa]


def _mapa_de_aderencia(rel, est, largura):
    """Bloco 2 — atividade a atividade, o que foi exigido e o que foi feito."""
    cab = [Paragraph('Atividade', est['th']),
           Paragraph('Exigida no mês', est['th_r']),
           Paragraph('Cumprida no mês', est['th_r']),
           Paragraph('% Aderência', est['th_r']),
           Paragraph('Status', est['th'])]
    linhas = [cab]
    estilo = _estilo_tabela(5)
    for i, r in enumerate(rel['rotinas'], start=1):
        cor = COR_FAIXA[r['faixa']]
        linhas.append([
            Paragraph(_esc(r['nome']), est['cel']),
            Paragraph(str(r['exigida']), est['cel_r']),
            Paragraph(str(r['cumprida']), est['cel_r']),
            Paragraph(_pct(r['pct']), est['cel_r']),
            Paragraph(TEXTO_FAIXA[r['faixa']], est['cel']),
        ])
        estilo.add('TEXTCOLOR', (3, i), (4, i), cor)
    if len(linhas) == 1:
        linhas.append([Paragraph('Nenhuma atividade obrigatória exigida na '
                                 'competência.', est['cel_p'])] + [''] * 4)
    larguras = [largura * f for f in (0.40, 0.14, 0.14, 0.14, 0.18)]
    tabela = Table(linhas, colWidths=larguras, repeatRows=1)
    tabela.setStyle(estilo)
    return _titulo(2, 'Mapa de aderência às rotinas obrigatórias',
                   'Onde a rotina do contrato está sendo cumprida — e onde não',
                   est) + [tabela]


def _pendencias(rel, est, largura):
    """Bloco 3 — o que um turno deixou para o outro, e o que voltou."""
    pend = rel['pendencias']
    fluxo = _titulo(3, 'Gestão de pendências da operação',
                    'Rastreabilidade entre turnos: o que foi baixado e o que '
                    'continua parado', est)

    cab = [Paragraph('Pendência', est['th']), Paragraph('Prioridade', est['th']),
           Paragraph('Turno de abertura', est['th']),
           Paragraph('Encerrada em', est['th']),
           Paragraph('Responsável', est['th'])]
    linhas = [cab]
    for linha in pend['lista_resolvidas']:
        p = linha['p']
        # Quem baixou a pendência é mais informativo do que quem estava
        # designado a ela — e é o nome que a gestão vai procurar.
        resp = linha.get('resolvida_por') or linha.get('responsavel') or '—'
        titulo = _esc(p.titulo)
        if p.referencia:
            titulo += f' <font color="#6b7280">· {_esc(p.referencia)}</font>'
        # O que foi feito. "Resolvida" sem isto é só o desaparecimento da
        # linha da fila, e não é a mesma coisa.
        if (linha.get('resolucao') or '').strip():
            titulo += (f'<br/><font size="7" color="#15803d">'
                       f'{_esc(linha["resolucao"])}</font>')
        turno = _esc(linha['turno'])
        if linha.get('passagens'):
            turno += (f"<br/><font size='7' color='#6b7280'>passou por "
                      f"{_plural(linha['passagens'], 'turno', 'turnos')}</font>")
        linhas.append([
            Paragraph(titulo, est['cel']),
            Paragraph(_esc(rotulo_prioridade(p.prioridade)), est['cel']),
            Paragraph(turno, est['cel']),
            # Grava-se em UTC, exibe-se em Brasília: sem tempo.fmt, a baixa
            # feita às 22h sai no PDF como do dia seguinte.
            Paragraph(tempo.fmt(p.resolved_at, '%d/%m/%Y %H:%M'), est['cel']),
            Paragraph(_esc(resp), est['cel']),
        ])
    if len(linhas) == 1:
        linhas.append([Paragraph('Nenhuma pendência resolvida no mês.',
                                 est['cel_p'])] + [''] * 4)
    t1 = Table(linhas, colWidths=[largura * f for f in
                                  (0.36, 0.12, 0.16, 0.18, 0.18)], repeatRows=1)
    t1.setStyle(_estilo_tabela(5))
    fluxo += [Paragraph(f"RESOLVIDAS · {pend['resolvidas']}", est['rotulo']),
              Spacer(1, 1.5 * mm), t1, Spacer(1, 6 * mm)]

    cab2 = [Paragraph('Pendência', est['th']), Paragraph('Prioridade', est['th']),
            Paragraph('Turno de origem', est['th']),
            Paragraph('Parada há', est['th_r'])]
    linhas2 = [cab2]
    estilo2 = _estilo_tabela(4)
    for i, linha in enumerate(pend['lista_em_aberto'], start=1):
        p = linha['p']
        titulo = _esc(p.titulo)
        if p.referencia:
            titulo += f' <font color="#6b7280">· {_esc(p.referencia)}</font>'
        if linha['anterior']:
            titulo += ' <font color="#b45309">· de competência anterior</font>'
        if p.descricao:
            titulo += f'<br/><font size="7" color="#6b7280">{_esc(p.descricao)}</font>'
        # A única pergunta que uma pendência parada há dias provoca.
        if (linha.get('ultima_tentativa') or '').strip():
            titulo += (f'<br/><font size="7" color="#4b5563">Última tentativa: '
                       f'{_esc(linha["ultima_tentativa"])}</font>')
        turno = _esc(linha['turno'])
        if linha.get('passagens'):
            turno += (f"<br/><font size='7' color='#6b7280'>passou por "
                      f"{_plural(linha['passagens'], 'turno', 'turnos')}</font>")
        linhas2.append([
            Paragraph(titulo, est['cel']),
            Paragraph(_esc(rotulo_prioridade(p.prioridade)), est['cel']),
            Paragraph(turno, est['cel']),
            Paragraph('hoje' if not linha['dias'] else _plural(linha['dias'], 'dia', 'dias'),
                      est['cel_r']),
        ])
        if (p.prioridade or '').lower() == 'alta':
            estilo2.add('TEXTCOLOR', (1, i), (1, i), VERMELHO)
    if len(linhas2) == 1:
        linhas2.append([Paragraph('Nenhuma pendência em aberto. Fila limpa.',
                                  est['cel_p'])] + [''] * 3)
    t2 = Table(linhas2, colWidths=[largura * f for f in (0.50, 0.14, 0.20, 0.16)],
               repeatRows=1)
    t2.setStyle(estilo2)
    fluxo += [Paragraph(f"CRÍTICAS / EM ABERTO · {len(pend['lista_em_aberto'])}",
                        est['rotulo']), Spacer(1, 1.5 * mm), t2]
    return fluxo


def _ocorrencias(rel, est, largura):
    """Bloco 4 — a matriz de desvios, um por linha, com referência."""
    cab = [Paragraph('Data / Turno', est['th']), Paragraph('Tipo', est['th']),
           Paragraph('Referência', est['th']), Paragraph('Descrição', est['th'])]
    linhas = [cab]
    for linha in rel['ocorrencias']['lista']:
        o = linha['o']
        # O dia do TURNO, o mesmo da tela — não o da digitação, que no 3º
        # Turno já é o dia seguinte.
        quando = tempo.fmt(linha.get('data'), '%d/%m/%Y')
        linhas.append([
            Paragraph(f"{quando}<br/><font size='7' color='#6b7280'>"
                      f"{_esc(linha['turno'])}</font>", est['cel']),
            Paragraph(_esc(o.tipo), est['cel']),
            Paragraph(_esc(o.referencia or '—'), est['cel']),
            Paragraph(_esc(o.descricao), est['cel']),
        ])
    if len(linhas) == 1:
        linhas.append([Paragraph('Nenhuma ocorrência registrada na competência.',
                                 est['cel_p'])] + [''] * 3)
    tabela = Table(linhas, colWidths=[largura * f for f in
                                      (0.15, 0.17, 0.16, 0.52)], repeatRows=1)
    tabela.setStyle(_estilo_tabela(4))

    sub = 'Todos os desvios lançados nas passagens de turno da competência'
    fluxo = _titulo(4, 'Matriz de ocorrências e não conformidades', sub, est)

    # Os pontos de atenção antes da estatística. O Pareto conta TIPOS e por
    # isso nivela: a avaria de palete e a suspensão de colaborador caem na
    # mesma barra quando são do mesmo tipo. Na reunião, estes se leem antes.
    atencao = rel['ocorrencias'].get('atencao') or []
    if atencao:
        linhas_at = []
        for linha in atencao:
            o = linha['o']
            quando = tempo.fmt(linha.get('data'), '%d/%m')
            ref = f" · {_esc(o.referencia)}" if o.referencia else ''
            linhas_at.append([
                Paragraph(f"{quando}<br/><font size='7' color='#6b7280'>"
                          f"{_esc(linha['turno'])}</font>", est['bordo_q']),
                Paragraph(f"<b>{_esc(o.tipo)}</b>{ref}<br/>"
                          f"{_esc(o.descricao)}", est['bordo_t']),
            ])
        t_at = Table(linhas_at, colWidths=[largura * 0.13, largura * 0.87])
        t_at.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, -2), 0.4, LINHA),
            ('LINEBEFORE', (1, 0), (1, -1), 1.2, AMBAR),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (1, 0), (1, -1), 7),
        ]))
        fluxo += [Paragraph(f'<b>Pontos de atenção da competência '
                            f'({len(atencao)})</b>', est['cel_p']),
                  Spacer(1, 1.5 * mm), t_at, Spacer(1, 3.5 * mm)]

    pareto = rel['ocorrencias']['pareto']
    if pareto:
        vitais = ' · '.join(f"{p['tipo']} ({p['qtd']})"
                            for p in pareto if p['vital'])
        fluxo += [Paragraph(f'Concentração (80% do volume): {_esc(vitais)}',
                            est['cel_p']), Spacer(1, 2.5 * mm)]
    return fluxo + [tabela]


def _bordo(rel, est, largura):
    """Bloco 5 — os fatos que o encarregado escreveu à mão."""
    fluxo = _titulo(5, 'Diário de bordo — fatos relevantes dos turnos',
                    'Observações dos encarregados; turnos que anotaram apenas '
                    '"sem observações" ficam de fora', est)
    if not rel['bordo']:
        return fluxo + [Paragraph('Nenhum fato relevante registrado nesta '
                                  'competência.', est['cel_p'])]
    linhas = []
    for f in rel['bordo']:
        linhas.append([
            Paragraph(f"{f['data'].strftime('%d/%m')}<br/>{_esc(f['turno'])}",
                      est['bordo_q']),
            Paragraph(_esc(f['texto']), est['bordo_t']),
        ])
    tabela = Table(linhas, colWidths=[largura * 0.13, largura * 0.87])
    tabela.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -2), 0.4, LINHA),
        ('LINEBEFORE', (1, 0), (1, -1), 1.2, NAVY),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (1, 0), (1, -1), 7),
    ]))
    return fluxo + [tabela]


def _moldura(rel):
    """Cabeçalho e rodapé: a página solta na reunião precisa ter dono."""
    legenda = (f"{rel['cliente']}"
               f"{(' · ' + rel['area']) if rel.get('area') else ''}"
               f" · {rel['competencia']}")

    def desenhar(canvas, doc):
        canvas.saveState()
        largura, altura = doc.pagesize
        canvas.setFillColor(NAVY)
        canvas.rect(0, altura - 4 * mm, largura, 4 * mm, stroke=0, fill=1)
        canvas.setFillColor(MARCA)
        canvas.rect(0, altura - 4.9 * mm, largura, 0.9 * mm, stroke=0, fill=1)

        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(CINZA)
        canvas.drawString(15 * mm, altura - 10 * mm,
                          'PASSAGEM DE TURNO · RELATÓRIO EXECUTIVO MENSAL')
        canvas.drawRightString(largura - 15 * mm, altura - 10 * mm, legenda)

        canvas.setStrokeColor(LINHA)
        canvas.setLineWidth(0.5)
        canvas.line(15 * mm, 10 * mm, largura - 15 * mm, 10 * mm)
        canvas.setFillColor(CINZA_CLARO)
        canvas.setFont('Helvetica', 6.5)
        canvas.drawString(15 * mm, 6 * mm, 'Grupo Trino · Trino Facilities · '
                                           'documento confidencial')
        canvas.drawRightString(largura - 15 * mm, 6 * mm, f'{doc.page}')
        canvas.restoreState()

    return desenhar


def _capa_moldura(canvas, doc):
    canvas.saveState()
    largura, _altura = doc.pagesize
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, largura, 10 * mm, stroke=0, fill=1)
    canvas.setFillColor(MARCA)
    canvas.rect(0, 10 * mm, largura, 1.6 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont('Helvetica', 8)
    canvas.drawString(15 * mm, 3.6 * mm,
                      'Documento confidencial · uso restrito ao cliente e ao '
                      'Grupo Trino')
    canvas.drawRightString(largura - 15 * mm, 3.6 * mm, 'grupotrino.com.br')
    canvas.restoreState()


def gerar(rel):
    """O fechamento em PDF — ``BytesIO`` pronto para o ``send_file``.

    Retrato A4: o documento é lido na tela e impresso em folha comum, e as
    tabelas daqui são estreitas (nenhuma tem doze colunas como o scorecard do
    SLA, que obrigou a paisagem).
    """
    buf = io.BytesIO()
    pagina = A4
    doc = SimpleDocTemplate(
        buf, pagesize=pagina, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=17 * mm, bottomMargin=14 * mm,
        title=(f"Passagem de Turno {rel['cliente']}"
               f"{(' ' + rel['area']) if rel.get('area') else ''}"
               f" — {rel['competencia']}"),
        author='Grupo Trino', subject='Relatório executivo mensal da Passagem '
                                      'de Turno')
    largura = pagina[0] - 30 * mm
    altura = pagina[1] - 31 * mm
    est = _estilos()

    fluxo = _capa(rel, est, largura, altura)
    fluxo.append(PageBreak())
    # Blocos 1 e 2 na mesma página: o scorecard e o mapa de rotinas são a
    # resposta de dois minutos que a diretoria vai ler.
    fluxo.extend(_scorecard(rel, est, largura))
    fluxo.append(Spacer(1, 8 * mm))
    fluxo.extend(_mapa_de_aderencia(rel, est, largura))
    fluxo.append(PageBreak())
    fluxo.extend(_pendencias(rel, est, largura))
    fluxo.append(PageBreak())
    fluxo.extend(_ocorrencias(rel, est, largura))
    fluxo.append(PageBreak())
    fluxo.extend(_bordo(rel, est, largura))

    doc.build(fluxo, onFirstPage=_capa_moldura, onLaterPages=_moldura(rel))
    buf.seek(0)
    return buf
