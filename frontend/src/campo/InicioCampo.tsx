// O início do aplicativo de campo ("Meu posto"): o turno de hoje por local,
// os avisos do público, o que a gestão pediu, o que ficou pendente e os
// chamados. Mesmos dados e regras da tela antiga (campo.rotas.contexto_inicio).
import type { Eu } from '../api';
import { AvisosCelular } from './AvisosCelular';
import type { InicioDoCampo, LocalDoTurno } from './tipos';

function plural(n: number, palavra: string) {
  return `${n} ${palavra}${n !== 1 ? 's' : ''}`;
}

function CartaoDoLocal({ l }: { l: LocalDoTurno }) {
  if (l.situacao === 'sem_chegada') {
    return (
      <a className="fc-cartao fc-local-turno mb-2" href={l.url} data-local={l.local_id} data-situacao={l.situacao}>
        <span className="fc-local-turno-nome">{l.local}</span>
        <span className="fc-local-turno-sub">
          {l.tarefas > 0 && `${plural(l.tarefas, 'tarefa')} hoje · `}Ao chegar, leia o QR da entrada ({l.entrada})
        </span>
        <span className="fc-local-turno-acao"><i className="bi bi-qr-code-scan" aria-hidden="true"></i> Ler o QR da entrada</span>
      </a>
    );
  }
  const chegou = l.situacao === 'chegou';
  return (
    <a className={`fc-cartao fc-local-turno mb-2${chegou ? ' fc-local-turno-aqui' : ''}`} href={l.url}
      data-local={l.local_id} data-situacao={l.situacao}>
      <span className="fc-local-turno-nome">{chegou ? `Você está no ${l.local}` : l.local}</span>
      <span className="fc-local-turno-sub">
        {chegou && `Chegou às ${l.chegou_as} · `}
        {l.tarefas > 0 ? `${l.abertas} de ${plural(l.tarefas, 'tarefa')} por fazer` : 'Nenhuma tarefa da rota hoje'}
      </span>
      <span className="fc-local-turno-acao"><i className="bi bi-list-check" aria-hidden="true"></i> Ver o turno</span>
    </a>
  );
}

function Lista<T extends { url: string }>({ titulo, icone, id, itens, vazio, linha }: {
  titulo: string; icone: string; id: string; itens: T[]; vazio: string;
  linha: (i: T) => [string, string];
}) {
  return (
    <section className="fc-cartao mb-3" aria-labelledby={id}>
      <h2 className="h6 fw-bold" id={id}><i className={`bi ${icone}`} aria-hidden="true"></i> {titulo}</h2>
      {itens.length === 0 ? <p className="small text-muted mb-0">{vazio}</p> : itens.map((i) => {
        const [principal, detalhe] = linha(i);
        return (
          <a className="fc-app-item" href={i.url} key={i.url + principal}>
            <span className="fw-semibold">{principal}</span>
            <span className="small text-muted">{detalhe}</span>
          </a>
        );
      })}
    </section>
  );
}

export function InicioCampo({ eu, dados }: { eu: Eu; dados: InicioDoCampo }) {
  const d = dados;
  return (
    <>
      <h1 className="fc-titulo">Olá, {eu.primeiro_nome}</h1>
      <p className="fc-sub">{d.hoje} · {eu.perfil}</p>

      <a className="btn btn-primary btn-lg w-100 fc-app-acao mb-3" href={d.links.ler_qr}>
        <i className="bi bi-qr-code-scan" aria-hidden="true"></i> Ler o QR do local
      </a>

      {d.turno.length > 0 && (
        <section className="mb-3" aria-labelledby="tit-turno">
          <h2 className="h6 fw-bold" id="tit-turno"><i className="bi bi-list-check" aria-hidden="true"></i> Meu turno de hoje</h2>
          {d.turno.map((l) => <CartaoDoLocal l={l} key={l.local_id} />)}
        </section>
      )}

      {d.material && (
        <a className="btn btn-outline-primary w-100 fc-app-acao mb-2" href={d.material}>
          <i className="bi bi-box-seam" aria-hidden="true"></i> Material: usei / está faltando
        </a>
      )}
      {d.equipe && (
        <a className="btn btn-outline-primary w-100 fc-app-acao mb-2" href={d.equipe}>
          <i className="bi bi-people" aria-hidden="true"></i> Equipe de hoje (presença)
        </a>
      )}
      {d.visitas && (
        <a className="btn btn-outline-primary w-100 fc-app-acao mb-3" href={d.visitas.url}>
          <i className="bi bi-clipboard-check" aria-hidden="true"></i> Visitas de supervisão{d.visitas.abertas > 0 && ` (${d.visitas.abertas})`}
        </a>
      )}

      {d.ocorrencias.length > 0 && (
        <section className="fc-cartao mb-3 border-warning" aria-labelledby="tit-ocor">
          <h2 className="h6 fw-bold" id="tit-ocor"><i className="bi bi-megaphone" aria-hidden="true"></i> Avisos do público ({d.ocorrencias.length})</h2>
          {d.ocorrencias.map((o) => (
            <a className="fc-app-item" href={o.url} key={o.id}>
              <span><span className="badge text-bg-warning">Checar aviso</span>{o.sua && <> <span className="badge text-bg-light">Sua</span></>}</span>
              {/* Local primeiro: dois locais podem ter ambientes de mesmo nome. */}
              <span className="fw-semibold">{o.local} · {o.ambiente} · {o.titulo}</span>
              <span className="small text-muted">{o.ponto} · {o.hora}{o.texto && ` · "${o.texto}"`}</span>
            </a>
          ))}
        </section>
      )}

      {!d.tem_locais ? (
        <div className="fc-cartao fc-vazio">Você ainda não tem local liberado. Peça ao seu supervisor ou à gestão.</div>
      ) : (
        <>
          <Lista titulo="Para hoje" icone="bi-calendar-check" id="tit-hoje" itens={d.tarefas}
            vazio="Nenhuma tarefa da gestão esperando você." linha={(t) => [t.titulo, `${t.turno} · ${t.data}`]} />
          <Lista titulo="Ficou pendente" icone="bi-hourglass-split" id="tit-pend" itens={d.pendencias}
            vazio="Nada pendente nos seus locais." linha={(p) => [p.titulo, `desde ${p.desde}`]} />
          {d.chamados && (
            <Lista titulo="Chamados abertos" icone="bi-tools" id="tit-ch" itens={d.chamados}
              vazio="Nenhum chamado aberto." linha={(c) => [c.titulo, c.prazo ? `prazo ${c.prazo}` : '']} />
          )}
          <AvisosCelular />
          {d.passagem && (
            <section className="fc-cartao" aria-labelledby="tit-locais">
              <h2 className="h6 fw-bold" id="tit-locais"><i className="bi bi-journal-check" aria-hidden="true"></i> Passagem de turno</h2>
              {d.passagem.map((l) => (
                <a className="fc-app-item" href={l.url} key={l.url}>
                  <span className="fw-semibold">{l.nome}</span>
                  <span className="small text-muted">Fazer a passagem de turno</span>
                </a>
              ))}
            </section>
          )}
        </>
      )}
    </>
  );
}
