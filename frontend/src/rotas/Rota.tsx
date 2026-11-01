// A rota: as atividades (onde, o quê e quando), a escala (quem executa) e o
// turno (Fase 3b; a tela antiga é templates/rotas/rota.html com
// _campos_item.html e _campos_rota.html).
import { Ir, Migalhas, RecadosDoEnvio, useFormulario } from '../cadastros/comum';
import { API, CamposRota, nomesDosDias } from './comum';
import type { DadosDaRota, ItemDaRota } from './tipos';

function CamposItem({ item, dados }: { item: ItemDaRota | null; dados: DadosDaRota }) {
  const sfx = item ? String(item.id) : 'novo';
  const r = dados.rota;
  return (
    <div className="row g-2">
      {item ? (
        <div className="col-md-5"><label className="form-label small fw-semibold" htmlFor={`ip${sfx}`}>Ponto (com QR)</label>
          <select className="form-select" id={`ip${sfx}`} name="ponto_id" required defaultValue={String(item.ponto_id)}>{dados.pontos.map((p) => <option value={p.id} key={p.id}>{p.setor} · {p.ambiente} · {p.nome}</option>)}</select></div>
      ) : (
        <fieldset className="col-12">
          <legend className="form-label small fw-semibold mb-1">Pontos (com QR) — marque um ou vários: todos recebem o mesmo checklist e os mesmos horários</legend>
          <div className="fc-pontos-lote">
            {dados.pontos.map((p) => <label className="fc-ponto-opcao" key={p.id}><input className="form-check-input" type="checkbox" name="ponto_id" value={p.id} /> <span>{p.ambiente} · {p.nome}<small>{p.setor}</small></span></label>)}
          </div>
        </fieldset>
      )}
      <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor={`im${sfx}`}>Checklist</label>
        <select className="form-select" id={`im${sfx}`} name="modelo_id" required defaultValue={item ? String(item.modelo_id) : undefined}>{dados.modelos.map((m) => <option value={m.id} key={m.id}>{m.nome}</option>)}</select></div>
      <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor={`io${sfx}`}>Ordem{!item && ' (do primeiro)'}</label>
        <input className="form-control" id={`io${sfx}`} name="ordem" inputMode="numeric" defaultValue={item ? String(item.ordem) : ''} /></div>
      <div className="col-md-7"><label className="form-label small fw-semibold" htmlFor={`ih${sfx}`}>Horários fixos</label>
        <input className="form-control" id={`ih${sfx}`} name="horarios" defaultValue={item ? item.horarios : ''} placeholder="Ex.: 07:00, 09:00, 11:00, 13:00" /></div>
      <div className="col-md-5"><label className="form-label small fw-semibold" htmlFor={`if${sfx}`}>e/ou a cada (minutos)</label>
        <input className="form-control" id={`if${sfx}`} name="frequencia_min" type="number" min={15} max={720} defaultValue={item && item.frequencia_min ? item.frequencia_min : ''} placeholder="Ex.: 60 (de hora em hora)" /></div>
      <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor={`it${sfx}`}>Tempo previsto (minutos)</label>
        <input className="form-control" id={`it${sfx}`} name="tempo_previsto_min" type="number" min={1} max={480} defaultValue={item && item.tempo_previsto_min ? item.tempo_previsto_min : ''} placeholder="Ex.: 30" /></div>
      <fieldset className="col-md-5"><legend className="form-label small fw-semibold mb-1">Só nestes dias (vazio = todos os dias da rota)</legend>
        <div className="d-flex flex-wrap gap-1">{dados.dias.filter(([k]) => r.dias_semana.includes(k)).map(([k, v]) => (
          <label className="border rounded px-2 py-1 small" key={k}><input type="checkbox" name="dias_semana" value={k} defaultChecked={!!item && !!item.dias_semana && item.dias_semana.includes(k)} /> {v}</label>
        ))}</div></fieldset>
      <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor={`ipd${sfx}`}>Horários diferentes num dia</label>
        <input className="form-control" id={`ipd${sfx}`} name="horarios_por_dia" defaultValue={item ? item.horarios_por_dia.map(([d, hs]) => `${d}: ${hs}`).join('; ') : ''} placeholder="Ex.: sáb: 07:00, 09:30" /></div>
    </div>
  );
}

/** A linha de resumo de uma atividade, como a tela antiga escreve. */
function resumo(it: ItemDaRota, dias: DadosDaRota['dias']): string {
  const partes: string[] = [];
  let horas = '';
  if (it.horarios) horas += `Horários: ${it.horarios}`;
  if (it.horarios && it.frequencia_min) horas += ' · ';
  if (it.frequencia_min) horas += `a cada ${it.frequencia_min} min`;
  if (horas) partes.push(horas);
  if (it.tempo_previsto_min) partes.push(`· ${it.tempo_previsto_min} min previstos`);
  if (it.dias_semana) partes.push(`· só ${nomesDosDias(it.dias_semana, dias)}`);
  for (const [d, hs] of it.horarios_por_dia) partes.push(`· ${d}: ${hs}`);
  partes.push(`· hoje: ${it.hoje.length ? it.hoje.join(', ') : 'nenhum'}`);
  return partes.join(' ');
}

export function Rota({ dados }: { dados: DadosDaRota }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const r = dados.rota;
  const base = `${API}/${r.id}`;
  const pode = dados.pode_montar;
  return (
    <div data-tela-pronta="rotas-rota">
      <Migalhas itens={[['Rotas', '/novo/rotas/'], [r.local.nome, `/novo/rotas/locais/${r.local.id}`], [r.nome, null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">{r.nome}</h1>
      <p className="fc-sub">{r.turno} · {r.inicio} às {r.fim}{r.intervalo_inicio && r.intervalo_fim && ` · intervalo ${r.intervalo_inicio} às ${r.intervalo_fim}`} · tolerância de {r.tolerancia_min} min · {nomesDosDias(r.dias_semana, dados.dias)}{!r.ativa && <> · <strong>desativada</strong></>}</p>
      {r.observacoes && (
        <section className="fc-cartao mb-3" aria-labelledby="tit-obs">
          <h2 className="h6 fw-bold" id="tit-obs"><i className="bi bi-info-circle"></i> Observações do plano</h2>
          <p className="small mb-0 fc-texto-livre">{r.observacoes}</p>
        </section>
      )}

      <section className="fc-cartao mb-3" aria-labelledby="tit-ativ">
        <h2 className="h6 fw-bold" id="tit-ativ"><i className="bi bi-list-check"></i> Atividades (onde, o quê e quando)</h2>
        {dados.itens.length ? dados.itens.map((it) => (
          <div className={`border-top py-2${it.ativo ? '' : ' text-muted'}`} key={it.id} data-atividade={it.id}>
            <div className="d-flex flex-wrap gap-2 align-items-center">
              <span className="fw-semibold">{it.ponto}</span>
              <span className="small">{it.modelo}</span>
              {!it.ativo && <span className="badge text-bg-secondary">fora da rota</span>}
            </div>
            <div className="small text-muted">{resumo(it, dados.dias)}</div>
            {pode && (
              <details className="mt-1"><summary className="small">Alterar</summary>
                <form method="post" className="mt-2" onSubmit={submeter(`${base}/itens/${it.id}`)}>
                  <CamposItem item={it} dados={dados} />
                  <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={ocupado}>Salvar</button>
                </form>
                <form method="post" className="mt-2" onSubmit={submeter(`${base}/itens/${it.id}`)}>
                  <input type="hidden" name="ativo" value={it.ativo ? '0' : '1'} />
                  <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={ocupado}>{it.ativo ? 'Tirar da rota' : 'Voltar para a rota'}</button>
                </form>
              </details>
            )}
          </div>
        )) : <p className="small text-muted">Nenhuma atividade ainda.</p>}
        {pode && (!dados.pontos.length || !dados.modelos.length ? (
          <div className="alert alert-warning small mt-2">Para incluir atividades, o local precisa de {!dados.pontos.length && <Ir href={dados.links.estrutura}>pontos com QR</Ir>}{!dados.pontos.length && !dados.modelos.length && ' e de '}{!dados.modelos.length && <Ir href={`/novo/rotas/locais/${r.local.id}`}>checklist publicado</Ir>}.</div>
        ) : (
          <details className="mt-2" open={!dados.itens.length}><summary className="fw-semibold">+ Incluir pontos na rota</summary>
            <form method="post" className="mt-2" onSubmit={submeter(`${base}/itens`)}>
              <CamposItem item={null} dados={dados} />
              <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={ocupado}>Incluir</button>
            </form>
          </details>
        ))}
      </section>

      <section className="fc-cartao mb-3" aria-labelledby="tit-esc">
        <h2 className="h6 fw-bold" id="tit-esc"><i className="bi bi-person-badge"></i> Quem executa (escala)</h2>
        {dados.escalas.length ? dados.escalas.map((e) => (
          <div className="d-flex flex-wrap gap-2 align-items-center border-top py-2" key={e.id}>
            <span className="fw-semibold">{e.nome}</span>
            <span className="small text-muted">{nomesDosDias(e.dias_semana, dados.dias)} · desde {e.desde}{e.ate && ` até ${e.ate}`}</span>
            {pode && (
              <form method="post" className="ms-auto m-0" onSubmit={submeter(`${base}/escalas/${e.id}/encerrar`)}>
                <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={ocupado}>Encerrar escala</button>
              </form>
            )}
          </div>
        )) : <p className="small text-muted">Ninguém escalado: as tarefas aparecem para todo o pessoal do local.</p>}
        {pode && (
          <details className="mt-2"><summary className="fw-semibold">+ Escalar pessoa</summary>
            <form method="post" className="mt-2" onSubmit={submeter(`${base}/escalas`)}>
              <div className="row g-2">
                <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor="epes">Pessoa</label>
                  <select className="form-select" id="epes" name="user_id" required defaultValue=""><option value="">Escolha</option>{dados.pessoas.map((p) => <option value={p.id} key={p.id}>{p.nome} — {p.perfil}</option>)}</select></div>
                <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="eini">A partir de</label><input className="form-control" id="eini" name="data_inicio" type="date" defaultValue={dados.hoje} required /></div>
                <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="efim">Até (opcional)</label><input className="form-control" id="efim" name="data_fim" type="date" /></div>
                <fieldset className="col-md-4"><legend className="form-label small fw-semibold mb-1">Dias</legend>
                  <div className="d-flex flex-wrap gap-1">{dados.dias.map(([k, v]) => <label className="border rounded px-2 py-1 small" key={k}><input type="checkbox" name="dias_semana" value={k} defaultChecked={r.dias_semana.includes(k)} /> {v}</label>)}</div></fieldset>
              </div>
              <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={ocupado}>Escalar</button>
            </form>
          </details>
        )}
      </section>

      {pode && (
        <details className="fc-cartao mb-3"><summary className="fw-bold">Alterar a rota (turno, horário, tolerância, dias)</summary>
          <form method="post" className="mt-3" onSubmit={submeter(base)}>
            <CamposRota r={r} dias={dados.dias} />
            <button className="btn btn-primary fw-bold mt-2" type="submit" disabled={ocupado}>Salvar</button>
          </form>
          <form method="post" className="mt-3" onSubmit={submeter(`${base}/ativo`)}>
            <input type="hidden" name="ativo" value={r.ativa ? '0' : '1'} />
            <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={ocupado}>{r.ativa ? 'Desativar a rota' : 'Reativar a rota'}</button>
          </form>
        </details>
      )}
    </div>
  );
}
