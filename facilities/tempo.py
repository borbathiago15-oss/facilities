"""O fuso da operação — um lugar só para "que horas são" e "que dia é hoje".

O contêiner de produção roda em UTC. Sem isto, duas coisas quebravam depois
das 21h de Brasília, e os dois sintomas foram relatados juntos:

* ``date.today()`` já era o dia SEGUINTE. Um lançamento feito às 21h30 de
  31/08 caía em 01/09, e o relatório saía com "Gerado em 01/09 23:26" quando
  eram 20h26 do dia 31.
* ``created_at`` (gravado com ``datetime.utcnow``) aparecia cru na tela: o
  usuário cadastrado às 21h de 31/08 constava como criado em 01/09 — data
  futura no cadastro.

A regra da casa: **grava-se em UTC, exibe-se em Brasília.** Guardar UTC é o
certo (não depende de onde o contêiner roda, e sobrevive a mudança de fuso);
o que faltava era converter na saída, e perguntar as horas ao fuso certo.

Duas defesas, de propósito:

1. ``TZ=America/Sao_Paulo`` no Dockerfile faz ``date.today()`` e
   ``datetime.now()`` acertarem em TODO o sistema, inclusive nos logs.
2. As funções daqui não dependem da variável de ambiente. Onde o dia errado
   tem consequência para o usuário — validação de data futura, carimbo de
   relatório, exibição de histórico — usa-se ``hoje()``/``agora()``/``fmt()``,
   que acertam mesmo se alguém subir a aplicação sem o TZ.
"""
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    FUSO = ZoneInfo('America/Sao_Paulo')
except Exception:                       # imagem sem tzdata
    # O Brasil não tem horário de verão desde 2019, então o offset fixo é
    # exato — e é um fallback melhor do que cair em UTC em silêncio.
    FUSO = timezone(timedelta(hours=-3))


def agora():
    """Agora, no fuso da operação (datetime *aware*)."""
    return datetime.now(FUSO)


def hoje():
    """A data de hoje para quem usa o sistema — não a do relógio do contêiner."""
    return agora().date()


def local(dt):
    """Datetime gravado em UTC → *aware* no fuso da operação. None → None.

    Datetime que já vem com fuso é respeitado; o ingênuo é assumido UTC,
    que é como ``datetime.utcnow`` grava no banco.
    """
    if dt is None:
        return None
    if isinstance(dt, datetime):
        aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        return aware.astimezone(FUSO)
    return dt


def fmt(dt, formato='%d/%m/%Y %H:%M', vazio='—'):
    """Formata um datetime UTC no fuso da operação.

    É o que toda tela e todo relatório devem usar para carimbo de hora.
    ``date`` puro (sem hora) passa direto: não tem fuso para converter.
    """
    if dt is None:
        return vazio
    if isinstance(dt, datetime):
        return local(dt).strftime(formato)
    if isinstance(dt, date):
        return dt.strftime(formato)
    return str(dt)


def para_utc(dia, hora):
    """Data + hora de PAREDE em Brasília → datetime UTC ingênuo (como o banco grava).

    É o caminho de volta do ``local``: a rota diz "09:00" no fuso da operação,
    e a tarefa do dia guarda o instante em UTC.
    """
    return datetime.combine(dia, hora).replace(tzinfo=FUSO).astimezone(
        timezone.utc).replace(tzinfo=None)
