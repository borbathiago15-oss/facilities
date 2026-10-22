"""Retenção: o que o agendador apaga depois de um prazo (auditoria N-06 e
N-20). Só três coisas, todas de pouco valor depois do prazo:

* a FOTO de ocorrência do público resolvida há mais de ``FOTO_OCORRENCIA_DIAS``
  (o registro fica; só o arquivo sai — é o que enche o armazenamento);
* registros de acesso da API de integração com mais de ``ACESSO_API_DIAS``;
* registros de rodada do agendador com mais de ``RODADA_DIAS`` (uma linha a
  cada 5 minutos: 105 mil por ano).

Nada do que a operação lançou (execuções, chamados, passagens, fotos da
equipe) é tocado aqui. Os prazos vêm do ambiente (``RETENCAO_*``) e ``0``
desliga aquele item.
"""
import os
from datetime import datetime, timedelta


PADRAO = {'FOTO_OCORRENCIA_DIAS': 90, 'ACESSO_API_DIAS': 365, 'RODADA_DIAS': 90}
LOTE = 200


def prazo(nome):
    bruto = os.environ.get(f'RETENCAO_{nome}', '')
    try:
        return int(bruto) if bruto.strip() else PADRAO[nome]
    except ValueError:
        return PADRAO[nome]


def aplicar(agora_utc=None):
    """Uma passada, em lotes pequenos (o agendador roda a cada 5 minutos: o
    que sobrar sai na próxima). Devolve um resumo para o registro."""
    from facilities.core.anexos import storage
    from facilities.integracao.models import IntegracaoAcesso
    from facilities.rotas.models import OCORRENCIA_RESOLVIDA, AgendadorExecucao, OcorrenciaPublica
    agora_utc = agora_utc or datetime.utcnow()
    resumo = {'fotos': 0, 'acessos': 0, 'rodadas': 0}

    dias = prazo('FOTO_OCORRENCIA_DIAS')
    if dias > 0:
        limite = agora_utc - timedelta(days=dias)
        velhas = (OcorrenciaPublica.query
                  .filter(OcorrenciaPublica.status == OCORRENCIA_RESOLVIDA,
                          OcorrenciaPublica.foto_key.isnot(None),
                          OcorrenciaPublica.resolvida_em.isnot(None),
                          OcorrenciaPublica.resolvida_em < limite)
                  .limit(LOTE).all())
        for oc in velhas:
            try:
                storage().delete(oc.foto_key)
            except Exception:
                # Arquivo já sumiu ou armazenamento fora: o registro fica
                # como está e a próxima rodada tenta de novo.
                continue
            oc.foto_key = None
            oc.foto_mime = None
            resumo['fotos'] += 1

    dias = prazo('ACESSO_API_DIAS')
    if dias > 0:
        limite = agora_utc - timedelta(days=dias)
        resumo['acessos'] = (IntegracaoAcesso.query.filter(IntegracaoAcesso.em < limite)
                             .delete(synchronize_session=False))

    dias = prazo('RODADA_DIAS')
    if dias > 0:
        limite = agora_utc - timedelta(days=dias)
        resumo['rodadas'] = (AgendadorExecucao.query
                             .filter(AgendadorExecucao.iniciada_em < limite)
                             .delete(synchronize_session=False))
    return resumo
