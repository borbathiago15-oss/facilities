// As visitas de supervisão do local (Fase 4b; a tela antiga é
// templates/visitas/local.html, com os mesmos textos, campos e classes). Os
// envios vão ao mesmo caminho da antiga abaixo de /api/v1 e chamam a mesma
// ação (visitas.telas.acao_*). A visita em si (o checklist do supervisor)
// continua no aplicativo antigo (/app/visitas/<id>).
import { Ir, Migalhas, RecadosDoEnvio, useFormulario } from '../cadastros/comum';
import type { DadosDasVisitas, Programada, VisitaRecente } from './tipos';

const API = '/api/v1/visitas';

/** Os campos da programação (a macro ``campos`` da antiga). */
export function CamposDaVisita({ p, sufixo, dados }: { p: Programada | null; sufixo: string; dados: DadosDasVisitas }) {
  return (
    <div className="row g-2">
      <div className="col-md-6"><label className="form-label small" htmlFor={`vn${sufixo}`}>Nome da visita</label>
        <input className="form-control" id={`vn${sufixo}`} name="nome" required maxLength={150} defaultValue={p ? p.nome : ''} placeholder="Ex.: Visita semanal de qualidade" /></div>
      <div className="col-md-6"><label className="form-label small" htmlFor={`vm${sufixo}`}>Checklist da visita</label>
        <select className="form-select" id={`vm${sufixo}`} name="modelo_id" required defaultValue={p ? p.modelo_id : undefined}>
          {dados.modelos.map((m) => <option value={m.id} key={m.id}>{m.nome}</option>)}</select></div>
      <div className="col-6 col-md-3"><label className="form-label small" htmlFor={`vi${sufixo}`}>A cada quantos dias</label>
        <input className="form-control" id={`vi${sufixo}`} name="intervalo_dias" type="number" min={1} max={365} required defaultValue={p ? p.intervalo_dias : 7} /></div>
      <div className="col-6 col-md-3"><label className="form-label small" htmlFor={`vp${sufixo}`}>Próxima visita</label>
        <input className="form-control" id={`vp${sufixo}`} name="proxima_em" type="date" required defaultValue={p ? p.proxima_em_iso : dados.hoje} /></div>
      <div className="col-md-6"><label className="form-label small" htmlFor={`vs${sufixo}`}>Quem faz</label>
        <select className="form-select" id={`vs${sufixo}`} name="supervisor_id" defaultValue={p && p.supervisor_id ? p.supervisor_id : ''}>
          <option value="">Qualquer supervisor do local</option>
          {dados.supervisores.map((s) => <option value={s.id} key={s.id}>{s.nome} ({s.perfil})</option>)}</select></div>
    </div>
  );
}

/** A cor do selo da visita recente (a mesma regra da antiga). */
export function classeDoSelo(v: VisitaRecente): string {
  if (v.status === 'feita' && v.n_nao_conformes) return 'text-bg-warning';
  if (v.status === 'feita') return 'text-bg-success';
  if (v.status === 'perdida') return 'text-bg-danger';
  return 'text-bg-light';
}

export function Visitas({ dados }: { dados: DadosDasVisitas }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const loc = dados.local;
  const temModelo = dados.modelos.length > 0;
  return (
    <div data-tela-pronta="visitas-local">
      <Migalhas itens={[[loc.nome, dados.links.checklists], ['Visitas de supervisão', null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Visitas de supervisão · {loc.nome}</h1>
      <p className="fc-sub">Na data, a visita abre sozinha e avisa quem faz. O supervisor faz o checklist no aplicativo; o que estiver não conforme abre um chamado para a gestão.</p>

      {dados.pode_montar && !temModelo && (
        <div className="alert alert-warning">Para programar uma visita, o local precisa de um checklist publicado (sem foto obrigatória). <Ir href={dados.links.checklists}>Checklists do local</Ir></div>
      )}

      <section className="fc-cartao mb-3" aria-labelledby="tit-prog">
        <h2 className="h6 fw-bold" id="tit-prog"><i className="bi bi-calendar2-week"></i> Programação</h2>
        {dados.programadas.length ? dados.programadas.map((p) => (
          <div className="border-top py-2" key={p.id}>
            <div className="d-flex flex-wrap gap-2 align-items-center">
              <span className="fw-semibold">{p.nome}</span>
              {!p.ativo && <span className="badge text-bg-secondary">desativada</span>}
              <span className="small text-muted">{p.modelo} · a cada {p.intervalo_dias} dia(s) · {p.supervisor || 'qualquer supervisor'}</span>
              {p.ativo && <span className="small ms-auto">próxima <strong>{p.proxima_em}</strong></span>}
            </div>
            {dados.pode_montar && (
              <details className="mt-1">
                <summary className="small fw-semibold">Editar</summary>
                <form method="post" className="mt-2" onSubmit={submeter(`${API}/programadas/${p.id}`)}>
                  <CamposDaVisita p={p} sufixo={String(p.id)} dados={dados} />
                  <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={ocupado}>Salvar</button>
                </form>
                <form method="post" className="mt-2" onSubmit={submeter(`${API}/programadas/${p.id}`)}>
                  <input type="hidden" name="ativo" value={p.ativo ? '0' : '1'} />
                  <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={ocupado}>{p.ativo ? 'Desativar' : 'Reativar'}</button>
                </form>
              </details>
            )}
          </div>
        )) : <p className="small text-muted">Nenhuma visita programada ainda.</p>}
        {dados.pode_montar && temModelo && (
          <details className="mt-2" open={!dados.programadas.length}>
            <summary className="fw-semibold">Programar visita</summary>
            <form method="post" className="mt-2" onSubmit={submeter(`${API}/locais/${loc.id}`)}>
              <CamposDaVisita p={null} sufixo="nova" dados={dados} />
              <button className="btn btn-primary fw-bold mt-2" type="submit" disabled={ocupado}>Programar</button>
            </form>
          </details>
        )}
      </section>

      <section className="fc-cartao" aria-labelledby="tit-rec">
        <h2 className="h6 fw-bold" id="tit-rec"><i className="bi bi-clock-history"></i> Visitas recentes</h2>
        {dados.recentes.length ? dados.recentes.map((v) => (
          <a className="d-flex flex-wrap gap-2 align-items-center border-top py-2 text-reset text-decoration-none" href={v.url} key={v.id}>
            <span className="fw-semibold">{v.nome}</span>
            <span className="small text-muted">até {v.vencimento}{v.quem_fez && ` · ${v.quem_fez}`}</span>
            <span className={`badge ${classeDoSelo(v)} ms-auto`}>{v.situacao_rotulo}{v.n_nao_conformes > 0 && ` · ${v.n_nao_conformes} não conforme(s)`}</span>
          </a>
        )) : <p className="small text-muted">Nenhuma visita ainda.</p>}
      </section>
    </div>
  );
}
