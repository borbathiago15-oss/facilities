// As telas dos relatórios do cliente na gestão (Fase 4c; as antigas são
// templates/relatorios/inicio.html, cliente.html e o corpo de
// _relatorio.html, com os mesmos textos, campos e classes). Os envios vão ao
// mesmo caminho da antiga abaixo de /api/v1 e chamam a mesma ação
// (relatorios.telas.acao_agir). O PDF, o Excel e as fotos continuam servidos
// pelo servidor (só links); o portal do cliente continua o antigo.
import { Ir, Migalhas, RecadosDoEnvio, useFormulario } from '../cadastros/comum';
import type { CorpoDoRelatorio, DadosDoInicio, DadosDoRelatorio } from './tipos';

const API = '/api/v1/relatorios';

// ── Início: um por local e por mês ────────────────────────────────────────

export function InicioDosRelatorios({ dados }: { dados: DadosDoInicio }) {
  return (
    <div data-tela-pronta="relatorios">
      <RecadosDoEnvio />
      <div className="fc-ola"><div>
        <h1 className="fc-titulo">Relatório do cliente</h1>
        <p className="fc-sub mb-0">Um por local e por mês: a nota, as rotinas feitas, os chamados, o que foi corrigido e as fotos. Confira, troque as fotos se quiser e libere — o cliente vê no portal e baixa em PDF.</p>
      </div></div>
      <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
        <Ir className="btn btn-outline-secondary" href={dados.links.anterior} aria-label="Mês anterior"><i className="bi bi-chevron-left"></i></Ir>
        <span className="fw-bold">{dados.nome_do_mes}</span>
        <Ir className="btn btn-outline-secondary" href={dados.links.seguinte} aria-label="Mês seguinte"><i className="bi bi-chevron-right"></i></Ir>
      </div>
      <div className="fc-cartao p-0">
        {dados.locais.length ? dados.locais.map((l) => (
          <Ir className="fc-fila-item" href={l.url} key={l.id}>
            <span className={`badge ${l.liberado ? 'text-bg-success' : 'text-bg-light'}`}>{l.liberado ? 'Liberado' : 'Não liberado'}</span>
            <span className="fc-fila-tit"><span className="small text-muted">{l.cliente}</span>{l.nome}</span>
            <span className="small text-muted fc-fila-local">{l.liberado && `em ${l.liberado_em}`}</span>
            <i className="bi bi-chevron-right" aria-hidden="true"></i>
          </Ir>
        )) : <div className="fc-vazio">Nenhum local na sua carteira.</div>}
      </div>
    </div>
  );
}

// ── O corpo do relatório (o mesmo da tela da gestão e do portal) ──────────

export function CorpoDoRelatorioDoMes({ c, recado }: { c: CorpoDoRelatorio; recado: string }) {
  const ch = c.chamados;
  return (
    <>
      <section className="fc-cartao mb-3" aria-labelledby="r-nota">
        <h2 className="h6 fw-bold" id="r-nota">Nota do mês</h2>
        <div className="fc-rel-nota">
          <div className="fc-rel-grande">
            {c.nota ? <span className={`badge fc-nota fc-nota-${c.nota.faixa} fs-4`}>{c.nota.texto}</span> : <span className="text-muted">sem movimento no mês</span>}
            <div className="small text-muted mt-1">{c.variacao}</div>
          </div>
          {c.indicadores.map((i) => (
            <div className="fc-rel-ind" key={i.chave}><div className="small text-muted">{i.rotulo}</div><div className="fs-5 fw-bold">{i.pct}</div><div className="small text-muted">{i.base}</div></div>
          ))}
        </div>
      </section>
      {recado && <section className="fc-cartao mb-3 fc-rel-recado"><h2 className="h6 fw-bold">Recado da coordenação</h2><p className="mb-0 fc-texto-livre">{recado}</p></section>}

      <section className="fc-cartao p-0 mb-3" aria-labelledby="r-rot">
        <h2 className="h6 fw-bold px-3 pt-3" id="r-rot">Rotinas por ambiente</h2>
        <div className="fc-mes-rolar"><table className="table table-sm mb-0 align-middle">
          <thead><tr><th scope="col">Ambiente</th><th scope="col" className="text-end">Previstas</th><th scope="col" className="text-end">No prazo</th><th scope="col" className="text-end">Com atraso</th><th scope="col" className="text-end">Não feitas</th><th scope="col" className="text-end">Aderência</th></tr></thead>
          <tbody>{c.rotinas.length ? c.rotinas.map((r) => (
            <tr key={r.ambiente}><th scope="row" className="small">{r.ambiente}</th><td className="text-end">{r.previstas}</td><td className="text-end">{r.no_prazo}</td><td className="text-end">{r.com_atraso}</td><td className="text-end">{r.nao_feitas}</td><td className="text-end fw-semibold">{r.pct}</td></tr>
          )) : <tr><td colSpan={6} className="fc-vazio">Sem rotinas programadas no mês.</td></tr>}</tbody>
        </table></div>
      </section>

      <section className="fc-cartao mb-3" aria-labelledby="r-ch">
        <h2 className="h6 fw-bold" id="r-ch">Chamados</h2>
        <div className="d-flex flex-wrap gap-3 mb-2 small">
          <span><b className="fs-5">{ch.abertos}</b> aberto(s)</span><span><b className="fs-5">{ch.resolvidos}</b> resolvido(s)</span>
          <span><b className="fs-5">{ch.pct_no_prazo}</b> no prazo</span><span><b className="fs-5">{ch.tempo_medio}</b> tempo médio de solução</span>
          <span><b className="fs-5">{ch.pendentes_no_fim}</b> em aberto no fim do mês</span>
        </div>
        {ch.lista.length > 0 && (
          <>
            <div className="fc-mes-rolar"><table className="table table-sm mb-0 small">
              <thead><tr><th scope="col">Nº</th><th scope="col">Assunto</th><th scope="col">Tipo</th><th scope="col">Aberto</th><th scope="col">Resolvido</th><th scope="col">Situação</th></tr></thead>
              <tbody>{ch.lista.map((x) => (
                <tr key={x.numero}><td>{x.numero}</td><td>{x.titulo}</td><td>{x.categoria}</td><td>{x.aberto_em}</td><td>{x.resolvido_em}</td><td>{x.situacao}</td></tr>
              ))}</tbody>
            </table></div>
            {ch.lista_cortada && <p className="small text-muted mb-0 mt-1">A lista mostra os primeiros chamados; o Excel traz os mesmos números.</p>}
          </>
        )}
      </section>

      <div className="row g-3 mb-3">
        <div className="col-md-6"><section className="fc-cartao h-100"><h2 className="h6 fw-bold">O que não estava conforme</h2>
          <p className="small mb-1">{c.ncs.total} item(ns) não conforme(s) nos checklists; {c.ncs.corrigidas} já corrigido(s) por chamado.</p>
          {c.ncs.itens.length > 0 && <ol className="small mb-0">{c.ncs.itens.map(([item, vezes]) => <li key={item}>{item} <span className="text-muted">({vezes}×)</span></li>)}</ol>}
        </section></div>
        <div className="col-md-6"><section className="fc-cartao h-100"><h2 className="h6 fw-bold">Avisos do público, visitas e cobranças</h2>
          <ul className="small mb-0">
            <li>Avisos pelo QR: {c.ocorrencias.total} recebido(s), {c.ocorrencias.resolvidas} resolvido(s), {c.ocorrencias.pct_no_prazo} no prazo, tempo médio {c.ocorrencias.tempo_medio}.</li>
            <li>Visitas de supervisão: {c.visitas.feitas} de {c.visitas.programadas} feitas, {c.visitas.conformes} sem item não conforme.</li>
            <li>Cobranças: {c.cobrancas.abertas} aberta(s), {c.cobrancas.respondidas} respondida(s) ({c.cobrancas.no_prazo} no prazo), {c.cobrancas.encerradas} encerrada(s).</li>
          </ul>
        </section></div>
      </div>

      {c.elogios && (
        <section className="fc-cartao mb-3" aria-labelledby="r-elogios">
          <h2 className="h6 fw-bold" id="r-elogios">Elogios do público</h2>
          {c.elogios.total ? (
            <>
              <p className="small mb-2"><span className="fc-nota-estrelas"><i className="bi bi-star-fill" aria-hidden="true"></i> {c.elogios.media} de 5</span> · {c.elogios.total} avaliação(ões) pelo QR dos pontos no mês.</p>
              {c.elogios.comentarios.length > 0 && <ul className="small mb-0">{c.elogios.comentarios.map((x, n) => (
                <li key={n}>"{x.texto}" <span className="text-muted">({x.nota} {x.estrelas} · {x.onde} · {x.quando})</span></li>
              ))}</ul>}
            </>
          ) : <p className="small text-muted mb-0">Nenhuma avaliação pelo QR no mês.</p>}
        </section>
      )}

      <section className="fc-cartao mb-3" aria-labelledby="r-fotos">
        <h2 className="h6 fw-bold" id="r-fotos">Fotos do mês</h2>
        {c.fotos.length ? (
          <div className="fc-rel-fotos">{c.fotos.map((f) => (
            <figure className="m-0" key={f.ref}><a href={f.url} target="_blank" rel="noopener"><img src={f.url} alt={f.legenda} loading="lazy" /></a><figcaption className="small text-muted">{f.legenda}</figcaption></figure>
          ))}</div>
        ) : <p className="small text-muted mb-0">Sem fotos no mês.</p>}
      </section>
    </>
  );
}

// ── O relatório do mês na gestão ──────────────────────────────────────────

export function RelatorioDoCliente({ dados }: { dados: DadosDoRelatorio }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const loc = dados.local;
  const agir = (acao: string) => submeter(`${API}/cliente/${loc.id}/${dados.mes}/${acao}`);
  const e = dados.escolha;
  return (
    <div data-tela-pronta="relatorio-cliente">
      <Migalhas itens={[['Relatórios', dados.links.inicio], [loc.nome, null]]} />
      <RecadosDoEnvio />{aviso}
      <div className="fc-ola"><div>
        <h1 className="fc-titulo">{loc.nome}</h1>
        <p className="fc-sub mb-0">{dados.cliente && `${dados.cliente} · `}<span>{dados.nome_do_mes}</span> · {dados.liberado_em
          ? <span className="text-success fw-semibold">liberado ao cliente em {dados.liberado_em}</span>
          : 'ainda não liberado ao cliente'}</p>
      </div>
      <div className="d-flex flex-wrap gap-2">
        <a className="btn btn-outline-primary" href={dados.links.pdf}><i className="bi bi-file-earmark-pdf" aria-hidden="true"></i> PDF</a>
        <a className="btn btn-outline-primary" href={dados.links.xlsx}><i className="bi bi-file-earmark-spreadsheet" aria-hidden="true"></i> Excel</a>
      </div></div>

      {dados.pode_gerir && (
        <section className="fc-cartao mb-3 fc-rel-gestao" aria-labelledby="r-ges">
          <h2 className="h6 fw-bold" id="r-ges">Antes de liberar</h2>
          <ol className="small mb-2"><li>Confira os números abaixo.</li><li>Troque as fotos, se quiser (a amostra automática já vem escolhida).</li><li>Deixe um recado, se quiser.</li><li>Libere: o cliente passa a ver no portal.</li></ol>
          <form method="post" className="mb-2" onSubmit={agir('recado')}>
            <label className="form-label small fw-semibold" htmlFor="recado">Recado ao cliente (opcional)</label>
            <textarea className="form-control mb-2" id="recado" name="recado" rows={2} maxLength={1500} defaultValue={dados.recado} placeholder="Ex.: Em setembro reforçamos a limpeza do 2º andar por causa do evento."></textarea>
            <button className="btn btn-sm btn-outline-primary" type="submit" disabled={ocupado}>Salvar recado</button>
          </form>
          {dados.mes_fechado ? (
            <div className="d-flex flex-wrap gap-2">
              {dados.liberado_em ? (
                <>
                  {dados.mudou.length > 0 && (
                    <>
                      <div className="alert alert-warning small w-100 mb-0">
                        <strong>Os números mudaram depois da liberação.</strong> O cliente continua vendo a versão de {dados.liberado_em}.
                        <ul className="mb-1">{dados.mudou.map(([oQue, antes, agora]) => <li key={oQue}>{oQue}: {antes} → {agora}</li>)}</ul>
                        Se a correção deve chegar ao cliente, libere de novo.
                      </div>
                      <form method="post" onSubmit={agir('liberar')}><button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}><i className="bi bi-send-check" aria-hidden="true"></i> Liberar a versão atual</button></form>
                    </>
                  )}
                  <form method="post" onSubmit={agir('recolher')}><button className="btn btn-outline-danger" type="submit" disabled={ocupado}>Recolher do portal</button></form>
                </>
              ) : (
                <form method="post" onSubmit={agir('liberar')}><button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}><i className="bi bi-send-check" aria-hidden="true"></i> Liberar para o cliente</button></form>
              )}
            </div>
          ) : <p className="small text-muted mb-0">O mês ainda não acabou: a liberação abre no dia 1º do mês seguinte.</p>}
        </section>
      )}

      <CorpoDoRelatorioDoMes c={dados.corpo} recado={dados.recado} />

      {e && e.todas.length > 0 && (
        <section className="fc-cartao mb-3" aria-labelledby="r-esc">
          <h2 className="h6 fw-bold" id="r-esc">Escolher as fotos ({e.todas.length} no mês, até {e.fotos_max})</h2>
          <p className="small text-muted">{e.automatica ? 'Hoje vale a amostra automática.' : 'Hoje valem as fotos escolhidas pela gestão.'} Marque as que vão no relatório.</p>
          <form method="post" onSubmit={agir('fotos')}>
            <div className="fc-rel-escolha">
              {e.todas.map((f) => (
                <label className="fc-rel-opcao" key={f.ref}><input className="form-check-input" type="checkbox" name="foto" value={f.ref} defaultChecked={f.escolhida} />
                  <img src={f.url} alt="" loading="lazy" /><span className="small">{f.legenda}</span></label>
              ))}
            </div>
            <div className="d-flex flex-wrap gap-2 mt-2">
              <button className="btn btn-primary" type="submit" disabled={ocupado}>Salvar as fotos</button>
            </div>
          </form>
          {!e.automatica && (
            <form method="post" className="mt-2" onSubmit={agir('amostra')}><button className="btn btn-sm btn-outline-secondary" type="submit" disabled={ocupado}>Voltar para a amostra automática</button></form>
          )}
        </section>
      )}
    </div>
  );
}
