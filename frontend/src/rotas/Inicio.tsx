// A rotina dos locais: o início (um cartão por local), o local (checklists e
// rotas) e a biblioteca da Trino (Fase 3b; as telas antigas são
// templates/rotas/inicio.html, local.html e biblioteca.html, com os mesmos
// textos, campos e classes).
import { Ir, Migalhas, RecadosDoEnvio, useFormulario } from '../cadastros/comum';
import { API, CamposRota } from './comum';
import type { DadosDaBiblioteca, DadosDoInicio, DadosDoLocal } from './tipos';

export function Inicio({ dados }: { dados: DadosDoInicio }) {
  return (
    <div data-tela-pronta="rotas-inicio">
      <RecadosDoEnvio />
      <div className="fc-ola">
        <div>
          <h1 className="fc-titulo">Rotina dos locais</h1>
          <p className="fc-sub mb-0">Tudo o que se repete em cada local: as rotas e os checklists do dia, as preventivas, a equipe do posto e as visitas de supervisão. O pessoal do posto executa pelo aplicativo, lendo o QR.</p>
        </div>
        <Ir className="btn btn-outline-primary" href="/novo/rotas/biblioteca"><i className="bi bi-book" aria-hidden="true"></i> Biblioteca de checklists da Trino</Ir>
      </div>
      <div className="fc-locais">
        {dados.locais.length ? dados.locais.map((l) => (
          <section className="fc-cartao fc-local" aria-labelledby={`loc-${l.id}`} key={l.id}>
            <h2 className="fc-local-nome" id={`loc-${l.id}`}>{l.nome}{l.cliente && <> <small>{l.cliente}</small></>}</h2>
            <div className="fc-local-acoes">
              <Ir className="fc-local-acao" href={`/novo/rotas/locais/${l.id}/dia`}><i className="bi bi-calendar-check" aria-hidden="true"></i>Hoje</Ir>
              <Ir className="fc-local-acao" href={`/novo/rotas/locais/${l.id}`}><i className="bi bi-signpost-split" aria-hidden="true"></i>Rotas e checklists</Ir>
              <a className="fc-local-acao" href={l.links.preventiva}><i className="bi bi-calendar2-week" aria-hidden="true"></i>Preventivas</a>
              <a className="fc-local-acao" href={l.links.equipe}><i className="bi bi-people" aria-hidden="true"></i>Equipe</a>
              <a className="fc-local-acao" href={l.links.visitas}><i className="bi bi-clipboard-check" aria-hidden="true"></i>Visitas</a>
            </div>
          </section>
        )) : <div className="fc-cartao fc-vazio">Nenhum local na sua carteira.</div>}
      </div>
    </div>
  );
}

export function Local({ dados }: { dados: DadosDoLocal }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const loc = dados.local;
  return (
    <div data-tela-pronta="rotas-local">
      <Migalhas itens={[['Rotas', '/novo/rotas/'], [loc.nome, null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">{loc.nome}</h1>
      <p className="fc-sub">Primeiro os checklists (o que fazer), depois as rotas (onde, quando e quem).</p>
      <div className="d-flex flex-wrap gap-2 mb-3">
        <Ir className="btn btn-primary btn-sm" href={`/novo/rotas/locais/${loc.id}/dia`}><i className="bi bi-calendar-check"></i> Acompanhar hoje</Ir>
        {dados.ve_estrutura && <Ir className="btn btn-outline-secondary btn-sm" href={dados.links.estrutura}><i className="bi bi-diagram-3"></i> Pontos e QR do local</Ir>}
        <a className="btn btn-outline-secondary btn-sm" href={dados.links.preventiva}><i className="bi bi-calendar2-week"></i> Preventivas</a>
        <a className="btn btn-outline-secondary btn-sm" href={dados.links.equipe}><i className="bi bi-people"></i> Equipe</a>
        <a className="btn btn-outline-secondary btn-sm" href={dados.links.visitas}><i className="bi bi-clipboard-check"></i> Visitas de supervisão</a>
        <Ir className="btn btn-outline-secondary btn-sm" href={`/novo/rotas/locais/${loc.id}/feriados`}><i className="bi bi-calendar-x"></i> Feriados</Ir>
      </div>

      <section className="fc-cartao mb-3" aria-labelledby="tit-ck">
        <h2 className="h6 fw-bold" id="tit-ck"><i className="bi bi-ui-checks"></i> Checklists deste local</h2>
        {dados.modelos.length ? dados.modelos.map((m) => (
          <Ir className="d-flex flex-wrap gap-2 align-items-center border-top py-2 text-reset text-decoration-none" href={`/novo/rotas/modelos/${m.id}`} key={m.id}>
            <span className="fw-semibold">{m.nome}</span>
            {m.versao !== null ? <span className="badge text-bg-light">versão {m.versao}</span> : <span className="badge text-bg-warning">não publicado</span>}
            {m.copia && <span className="small text-muted">cópia da biblioteca</span>}
            <i className="bi bi-chevron-right ms-auto"></i>
          </Ir>
        )) : <p className="small text-muted">Nenhum checklist ainda. Copie um da biblioteca da Trino ou crie um novo.</p>}
        {dados.pode_montar && (
          <div className="row g-2 mt-2">
            {dados.biblioteca.length > 0 && (
              <form className="col-md-6 d-flex gap-2" method="post" onSubmit={submeter(`${API}/locais/${loc.id}/copiar`)}>
                <label className="visually-hidden" htmlFor="copiar">Checklist da biblioteca</label>
                <select className="form-select" id="copiar" name="modelo_id">{dados.biblioteca.map((b) => <option value={b.id} key={b.id}>{b.nome}</option>)}</select>
                <button className="btn btn-outline-primary text-nowrap" type="submit" disabled={ocupado}>Copiar da biblioteca</button>
              </form>
            )}
            <form className="col-md-6 d-flex gap-2" method="post" onSubmit={submeter(`${API}/locais/${loc.id}/modelos`)}>
              <label className="visually-hidden" htmlFor="novock">Nome do checklist novo</label>
              <input className="form-control" id="novock" name="nome" required maxLength={150} placeholder="Nome do checklist novo" />
              <button className="btn btn-outline-primary text-nowrap" type="submit" disabled={ocupado}>Criar</button>
            </form>
          </div>
        )}
      </section>

      <section className="fc-cartao" aria-labelledby="tit-rotas">
        <h2 className="h6 fw-bold" id="tit-rotas"><i className="bi bi-signpost-split"></i> Rotas</h2>
        {dados.rotas.length ? dados.rotas.map((r) => (
          <Ir className="d-flex flex-wrap gap-2 align-items-center border-top py-2 text-reset text-decoration-none" href={`/novo/rotas/${r.id}`} key={r.id}>
            <span className="fw-semibold">{r.nome}</span>
            <span className="small text-muted">{r.turno} · {r.inicio} às {r.fim} · {r.atividades} atividade(s)</span>
            {!r.ativa && <span className="badge text-bg-secondary">desativada</span>}
            <i className="bi bi-chevron-right ms-auto"></i>
          </Ir>
        )) : <p className="small text-muted">Nenhuma rota ainda.</p>}
        {dados.pode_montar && (
          <>
            <Ir className="btn btn-outline-primary fw-bold mt-2" href={`/novo/rotas/locais/${loc.id}/rota-pronta`}><i className="bi bi-magic" aria-hidden="true"></i> Usar uma rota pronta</Ir>{' '}
            <Ir className="btn btn-outline-primary fw-bold mt-2" href={`/novo/rotas/locais/${loc.id}/importar-plano`}><i className="bi bi-file-earmark-spreadsheet" aria-hidden="true"></i> Importar plano (planilha)</Ir>
            <details className="mt-2">
              <summary className="fw-semibold">Criar rota do zero</summary>
              <form method="post" className="mt-2" onSubmit={submeter(`${API}/locais/${loc.id}/rotas`)}>
                <CamposRota dias={dados.dias} />
                <button className="btn btn-primary fw-bold mt-2" type="submit" disabled={ocupado}>Criar rota</button>
              </form>
            </details>
          </>
        )}
      </section>
    </div>
  );
}

export function Biblioteca({ dados }: { dados: DadosDaBiblioteca }) {
  const { submeter, ocupado, aviso } = useFormulario();
  return (
    <div data-tela-pronta="rotas-biblioteca">
      <Migalhas itens={[['Rotas', '/novo/rotas/'], ['Biblioteca', null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Biblioteca da Trino</h1>
      <p className="fc-sub">Rotas prontas por tipo de local e os checklists padrão. Cada local recebe uma CÓPIA e ajusta à sua realidade, sem mudar os outros locais. Para aplicar, abra o local em Rotas.</p>
      {dados.pode_montar && (
        <>
          <form method="post" className="fc-cartao mb-3 d-flex flex-wrap gap-2 align-items-center" onSubmit={submeter(`${API}/biblioteca/modelos-prontos`)}>
            <div className="flex-grow-1"><b>Modelos prontos</b><div className="small text-muted">Checklists de banheiro, copa e cozinha, recepção e escritório, vestiário, área externa e piso de armazém — cada pergunta com o "como fazer" — e as rotas prontas de escritório e de centro de distribuição. Instalar de novo não duplica.</div></div>
            <button className="btn btn-outline-primary fw-bold" type="submit" disabled={ocupado}><i className="bi bi-magic" aria-hidden="true"></i> Instalar na biblioteca</button>
          </form>
          <details className="fc-cartao mb-3" open={!dados.modelos.length}>
            <summary className="fw-bold">Criar checklist na biblioteca</summary>
            <form method="post" className="mt-3" onSubmit={submeter(`${API}/biblioteca`)}>
              <label className="form-label small fw-semibold" htmlFor="bnome">Nome</label>
              <input className="form-control mb-2" id="bnome" name="nome" required maxLength={150} placeholder="Ex.: Limpeza de banheiro — padrão Trino" />
              <label className="form-label small fw-semibold" htmlFor="bdesc">Procedimento (aparece para quem lê o QR)</label>
              <textarea className="form-control mb-2" id="bdesc" name="descricao" rows={3}></textarea>
              <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Criar e montar as perguntas</button>
            </form>
          </details>
        </>
      )}
      <section className="mb-4" aria-labelledby="tit-rp">
        <div className="d-flex flex-wrap align-items-center gap-2 mb-2">
          <h2 className="h5 fw-bold mb-0" id="tit-rp">Rotas prontas</h2>
          {dados.pode_montar && <Ir className="btn btn-sm btn-outline-primary ms-auto" href="/novo/rotas/biblioteca/rotas/nova"><i className="bi bi-plus-lg" aria-hidden="true"></i> Nova rota pronta</Ir>}
        </div>
        <div className="fc-cartao p-0">
          {dados.rotas_prontas.length ? dados.rotas_prontas.map((r) => (
            <Ir className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2 text-reset text-decoration-none" href={`/novo/rotas/biblioteca/rotas/${r.id}`} key={r.id}>
              <span className="badge text-bg-light">{r.segmento}</span>
              <strong>{r.nome}</strong>
              <span className="small text-muted">{r.ambientes} tipo(s) de ambiente · {r.inicio} às {r.fim}</span>
              {!r.ativa && <span className="badge text-bg-secondary">desativada</span>}
              <i className="bi bi-chevron-right ms-auto"></i>
            </Ir>
          )) : <div className="fc-vazio">Nenhuma rota pronta ainda{dados.pode_montar && ' — use "Instalar na biblioteca" acima'}.</div>}
        </div>
      </section>
      <h2 className="h5 fw-bold">Checklists</h2>
      <div className="fc-cartao p-0">
        {dados.modelos.length ? dados.modelos.map((m) => (
          <Ir className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2 text-reset text-decoration-none" href={`/novo/rotas/modelos/${m.id}`} key={m.id}>
            <strong>{m.nome}</strong>
            {m.versao !== null ? <span className="badge text-bg-light">versão {m.versao}</span> : <span className="badge text-bg-warning">não publicado</span>}
            <i className="bi bi-chevron-right ms-auto"></i>
          </Ir>
        )) : <div className="fc-vazio">A biblioteca ainda está vazia.</div>}
      </div>
    </div>
  );
}
