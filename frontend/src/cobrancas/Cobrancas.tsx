// As cobranças do cliente vistas pela equipe (Fase 5; as antigas são
// templates/portal/interno_lista.html, interno_avisos_qr.html e
// interno_ver.html, com os mesmos textos, campos e classes). A resposta vai
// ao mesmo caminho da antiga abaixo de /api/v1 e chama a mesma ação
// (portal.telas.acao_responder). Os avisos pelo QR levam ao dia do local na
// rotina nova.
import { Ir, Migalhas, RecadosDoEnvio, useFormulario } from '../cadastros/comum';
import { AbasDasCobrancas, AvisosPeloQr, Filtros, Trilha } from '../portal/comum';
import type { DadosDosAvisos } from '../portal/tipos';
import type { DadosDaCobranca, DadosDaLista, DadosDaListaOuAvisos } from './tipos';

export function ListaDasCobrancas({ dados }: { dados: DadosDaListaOuAvisos }) {
  return dados.aba === 'qr' ? <AvisosDaEquipe dados={dados} /> : <Lista dados={dados} />;
}

function AvisosDaEquipe({ dados }: { dados: DadosDosAvisos }) {
  return (
    <div data-tela-pronta="cobrancas-avisos-qr">
      <RecadosDoEnvio />
      <h1 className="fc-titulo">Cobranças do cliente</h1>
      <p className="fc-sub">O que o público avisou pelo QR dos pontos. Cada aviso vira a tarefa "Checar aviso" de quem está escalado no ponto; sem ninguém escalado, vai para o supervisor.</p>
      <AbasDasCobrancas abas={dados.abas} ativa="qr" />
      <Filtros filtros={dados.filtros} />
      <AvisosPeloQr avisos={dados.avisos} />
    </div>
  );
}

function Lista({ dados }: { dados: DadosDaLista }) {
  return (
    <div data-tela-pronta="cobrancas">
      <RecadosDoEnvio />
      <h1 className="fc-titulo">Cobranças do cliente</h1>
      <p className="fc-sub">O que o cliente pediu pelo portal, com a data que ele escolheu. A coordenação responde; só o cliente encerra ou reabre.</p>
      <AbasDasCobrancas abas={dados.abas} ativa="cobrancas" />
      <Filtros filtros={dados.filtros} />
      <div className="fc-cartao p-0">
        {dados.itens.length ? dados.itens.map((c) => (
          <Ir className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2 text-reset text-decoration-none" href={c.url} key={c.id}>
            <span className={`badge ${c.situacao.classe}`}>{c.situacao.texto}</span>
            <span className="small fw-semibold">{c.numero}</span>
            <span className="fw-semibold">{c.titulo}</span>
            <span className="small text-muted">{c.local} · {c.autor}</span>
            <span className="small ms-auto">prazo {c.prazo}</span>
          </Ir>
        )) : <div className="fc-vazio">Nenhuma cobrança aqui.</div>}
      </div>
    </div>
  );
}

export function CobrancaDaEquipe({ dados }: { dados: DadosDaCobranca }) {
  const { submeter, ocupado, aviso } = useFormulario();
  return (
    <div data-tela-pronta="cobranca">
      <Migalhas itens={[['Cobranças do cliente', dados.links.lista], [dados.numero, null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">{dados.numero} · {dados.titulo}</h1>
      <p className="fc-sub">{dados.local} · pedida por {dados.autor} · <span className="fw-semibold">{dados.situacao}</span> · prazo {dados.prazo}{dados.reaberturas > 0 && ` · reaberta ${dados.reaberturas} vez(es)`}</p>
      {dados.pode_responder ? (
        <div className="fc-cartao fc-estreito mb-3">
          <form method="post" onSubmit={submeter(`/api/v1/cobrancas/${dados.id}/responder`)}>
            <label className="form-label small fw-semibold" htmlFor="rtex">Resposta para o cliente</label>
            <textarea className="form-control mb-2" id="rtex" name="texto" rows={4} maxLength={4000} required></textarea>
            <p className="form-text">O cliente vê o texto assinado como "Coordenação", sem o seu nome.</p>
            <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Responder</button>
          </form>
        </div>
      ) : dados.status === 'aberta' ? (
        <div className="alert alert-info">Quem responde é a coordenação ou a supervisão do local.</div>
      ) : dados.status === 'respondida' ? (
        <div className="alert alert-info">Respondida. Esperando o cliente confirmar ou reabrir.</div>
      ) : null}
      <Trilha eventos={dados.eventos} />
    </div>
  );
}
