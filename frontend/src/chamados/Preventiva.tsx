// Os planos preventivos do local (Fase 4a; a tela antiga é
// templates/preventiva/local.html, com os mesmos textos, campos e classes).
// Os envios vão ao mesmo caminho da antiga abaixo de /api/v1 e chamam a
// mesma ação (preventiva.telas.acao_*).
import { Ir, Migalhas, RecadosDoEnvio, useFormulario } from '../cadastros/comum';
import type { DadosDaPreventiva, PlanoPreventivo } from './tipos';

const API = '/api/v1/preventiva';

/** O item desativado só vem no "Editar" do plano que ainda o usa (o seletor
 * não cai na primeira opção); no "Novo plano", só os ativos. */
const desativado = (x: { ativo: boolean }) => (x.ativo ? '' : ' (desativado)');

/** Os campos do plano (a macro ``campos`` da antiga): o novo e os de editar. */
export function CamposDoPlano({ p, sufixo, dados }: { p: PlanoPreventivo | null; sufixo: string; dados: DadosDaPreventiva }) {
  return (
    <div className="row g-2">
      <div className="col-md-6"><label className="form-label small" htmlFor={`nome${sufixo}`}>Nome do plano</label>
        <input className="form-control" id={`nome${sufixo}`} name="nome" required maxLength={150} defaultValue={p ? p.nome : ''} placeholder="Ex.: Limpeza do filtro do ar-condicionado" /></div>
      <div className="col-md-6"><label className="form-label small" htmlFor={`ponto${sufixo}`}>Onde o técnico lê o QR</label>
        <select className="form-select" id={`ponto${sufixo}`} name="ponto_id" required defaultValue={p ? p.ponto_id : undefined}>
          {dados.pontos.filter((pt) => pt.ativo || p?.ponto_id === pt.id).map((pt) => <option value={pt.id} key={pt.id}>{pt.rotulo}{desativado(pt)}</option>)}</select></div>
      <div className="col-md-6"><label className="form-label small" htmlFor={`modelo${sufixo}`}>Checklist que ele vai fazer</label>
        <select className="form-select" id={`modelo${sufixo}`} name="modelo_id" required defaultValue={p ? p.modelo_id : undefined}>
          {dados.modelos.filter((m) => m.ativo || p?.modelo_id === m.id).map((m) => <option value={m.id} key={m.id}>{m.nome}{desativado(m)}</option>)}</select></div>
      <div className="col-md-6"><label className="form-label small" htmlFor={`eq${sufixo}`}>Equipamento (opcional)</label>
        <select className="form-select" id={`eq${sufixo}`} name="equipamento_id" defaultValue={p && p.equipamento_id ? p.equipamento_id : ''}>
          <option value="">Nenhum</option>
          {dados.equipamentos.filter((e) => e.ativo || p?.equipamento_id === e.id).map((e) => <option value={e.id} key={e.id}>{e.nome}{desativado(e)}</option>)}</select></div>
      <div className="col-6 col-md-3"><label className="form-label small" htmlFor={`int${sufixo}`}>A cada quantos dias</label>
        <input className="form-control" id={`int${sufixo}`} name="intervalo_dias" type="number" min={1} max={730} required defaultValue={p ? p.intervalo_dias : 30} /></div>
      <div className="col-6 col-md-3"><label className="form-label small" htmlFor={`prox${sufixo}`}>Próximo vencimento</label>
        <input className="form-control" id={`prox${sufixo}`} name="proxima_em" type="date" required defaultValue={p ? p.proxima_em_iso : dados.hoje} /></div>
      <div className="col-6 col-md-3"><label className="form-label small" htmlFor={`ant${sufixo}`}>Abrir quantos dias antes</label>
        <input className="form-control" id={`ant${sufixo}`} name="antecedencia_dias" type="number" min={0} max={60} defaultValue={p ? p.antecedencia_dias : 0} /></div>
      <div className="col-6 col-md-3"><label className="form-label small" htmlFor={`pri${sufixo}`}>Prioridade</label>
        <select className="form-select" id={`pri${sufixo}`} name="prioridade" defaultValue={p ? p.prioridade : 'media'}>
          {dados.prioridades.map(([k, v]) => <option value={k} key={k}>{v}</option>)}</select></div>
      <div className="col-md-6"><label className="form-label small" htmlFor={`resp${sufixo}`}>Técnico responsável</label>
        <select className="form-select" id={`resp${sufixo}`} name="responsavel_id" defaultValue={p && p.responsavel_id ? p.responsavel_id : ''}>
          <option value="">Sem responsável (avisa a gestão)</option>
          {dados.tecnicos.map((t) => <option value={t.id} key={t.id}>{t.nome}</option>)}</select></div>
    </div>
  );
}

export function Preventiva({ dados }: { dados: DadosDaPreventiva }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const loc = dados.local;
  const podeCadastrar = dados.pontos.some((x) => x.ativo) && dados.modelos.some((x) => x.ativo);
  return (
    <div data-tela-pronta="preventiva">
      <Migalhas itens={[[loc.nome, dados.links.checklists], ['Preventivas', null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Preventivas · {loc.nome}</h1>
      <p className="fc-sub">O que se faz de tempos em tempos, sem esperar quebrar. Na data, o sistema abre a ordem de serviço sozinho; o técnico lê o QR do ponto e faz o checklist no aplicativo.</p>

      {dados.pode_montar && !podeCadastrar && (
        <div className="alert alert-warning">Para cadastrar um plano, o local precisa de pelo menos um ponto com QR e um checklist publicado.
          {' '}<Ir href={dados.links.pontos}>Pontos do local</Ir> · <Ir href={dados.links.checklists}>Checklists</Ir></div>
      )}

      <section className="fc-cartao mb-3" aria-labelledby="tit-planos">
        <h2 className="h6 fw-bold" id="tit-planos"><i className="bi bi-calendar2-week"></i> Planos deste local</h2>
        {dados.planos.length ? dados.planos.map((p) => (
          <div className="border-top py-2" key={p.id}>
            <div className="d-flex flex-wrap gap-2 align-items-center">
              <span className="fw-semibold">{p.nome}</span>
              {!p.ativo && <span className="badge text-bg-secondary">desativado</span>}
              <span className="small text-muted">{p.ponto}{p.equipamento && ` · ${p.equipamento}`} · a cada {p.intervalo_dias} dia(s)</span>
              {p.ativo && <span className="small ms-auto">próximo vencimento <strong>{p.proxima_em}</strong></span>}
            </div>
            <div className="small text-muted">Checklist: {p.modelo} · {p.prioridade_rotulo} · {p.responsavel || 'sem responsável'}</div>
            {p.ciclos.length > 0 && (
              <ul className="list-unstyled small mb-1 mt-1">
                {p.ciclos.map((c, i) => (
                  <li key={i}>Venceu {c.vencimento} ·{' '}
                    {c.chamado ? <><Ir href={c.chamado.url}>{c.chamado.numero}</Ir> — {c.chamado.status_rotulo}</> : 'sem ordem'}</li>
                ))}
              </ul>
            )}
            {dados.pode_montar && (
              <details className="mt-1">
                <summary className="small fw-semibold">Editar</summary>
                <form method="post" className="mt-2" onSubmit={submeter(`${API}/${p.id}`)}>
                  <CamposDoPlano p={p} sufixo={String(p.id)} dados={dados} />
                  <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={ocupado}>Salvar</button>
                </form>
                <form method="post" className="mt-2" onSubmit={submeter(`${API}/${p.id}`)}>
                  <input type="hidden" name="ativo" value={p.ativo ? '0' : '1'} />
                  <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={ocupado}>{p.ativo ? 'Desativar plano' : 'Reativar plano'}</button>
                </form>
              </details>
            )}
          </div>
        )) : <p className="small text-muted">Nenhum plano preventivo ainda.</p>}
      </section>

      {dados.pode_montar && podeCadastrar && (
        <section className="fc-cartao" aria-labelledby="tit-novo">
          <h2 className="h6 fw-bold" id="tit-novo"><i className="bi bi-plus-circle"></i> Novo plano</h2>
          <form method="post" onSubmit={submeter(`${API}/locais/${loc.id}`)}>
            <CamposDoPlano p={null} sufixo="novo" dados={dados} />
            <button className="btn btn-primary fw-bold mt-2" type="submit" disabled={ocupado}>Cadastrar plano</button>
          </form>
        </section>
      )}
    </div>
  );
}
