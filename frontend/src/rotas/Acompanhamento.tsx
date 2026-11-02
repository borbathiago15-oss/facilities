// O acompanhamento: os feriados do local, o dia (tarefas, ocorrências e
// elogios do público, chegadas, presenças, atividades fora da rota) e a
// execução de um checklist, com a correção e o chamado da não conformidade
// (Fase 3b; as telas antigas são templates/rotas/feriados.html, dia.html e
// execucao.html).
import { useNavigate } from 'react-router';
import { Ir, Migalhas, RecadosDoEnvio, useFormulario } from '../cadastros/comum';
import { pct } from '../passagem/gestao';
import { API, SeloGps } from './comum';
import type { DadosDaExecucao, DadosDoDia, DadosDosFeriados } from './tipos';

export function Feriados({ dados }: { dados: DadosDosFeriados }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const loc = dados.local;
  const ano = dados.ano;
  const base = `/novo/rotas/locais/${loc.id}/feriados`;
  return (
    <div data-tela-pronta="rotas-feriados">
      <Migalhas itens={[['Rotas', '/novo/rotas/'], [loc.nome, `/novo/rotas/locais/${loc.id}`], ['Feriados', null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Feriados de {ano}</h1>
      <p className="fc-sub">Nos feriados, a rota que <strong>não funciona em feriado</strong> não gera tarefa. Os nacionais já vêm prontos; cadastre aqui os do estado, da cidade e os dias em que o cliente fecha.</p>
      <div className="d-flex flex-wrap gap-2 mb-3">
        <Ir className="btn btn-outline-secondary btn-sm" href={`${base}?ano=${ano - 1}`}><i className="bi bi-chevron-left" aria-hidden="true"></i> {ano - 1}</Ir>
        <Ir className="btn btn-outline-secondary btn-sm" href={`${base}?ano=${ano + 1}`}>{ano + 1} <i className="bi bi-chevron-right" aria-hidden="true"></i></Ir>
      </div>
      <div className="fc-cartao mb-3">
        <h2 className="h6 fw-bold">Rotas que param nos feriados</h2>
        {dados.rotas_param.length
          ? <p className="small mb-0">{dados.rotas_param.join(', ')}.</p>
          : <p className="small text-muted mb-0">Todas as rotas deste local funcionam em feriado. Para uma rota parar, desmarque "Funciona em feriado" na tela da rota.</p>}
      </div>
      {dados.pode_montar && (
        <div className="fc-cartao mb-3">
          <h2 className="h6 fw-bold">Cadastrar feriado do local</h2>
          <form method="post" className="row g-2 align-items-end" onSubmit={submeter(`${API}/locais/${loc.id}/feriados`)}>
            <div className="col-sm-4"><label className="form-label small fw-semibold" htmlFor="fdata">Data</label>
              <input className="form-control" id="fdata" name="data" type="date" required /></div>
            <div className="col-sm-5"><label className="form-label small fw-semibold" htmlFor="fnome">Nome</label>
              <input className="form-control" id="fnome" name="nome" required maxLength={80} placeholder="Ex.: Independência da Bahia" /></div>
            <div className="col-sm-3"><button className="btn btn-primary fw-bold w-100" type="submit" disabled={ocupado}>Cadastrar</button></div>
          </form>
        </div>
      )}
      <div className="fc-cartao p-0">
        {dados.lista.map((f, n) => (
          <div className={`border-top px-3 py-2 d-flex flex-wrap gap-2 align-items-center${f.passou ? ' text-muted' : ''}`} key={n}>
            <strong className="nx-num">{f.data}</strong>
            <span>{f.nome}</span>
            <span className={`badge ${f.id ? 'text-bg-light' : 'text-bg-secondary'}`}>{f.id ? 'deste local' : 'nacional'}</span>
            {f.id && dados.pode_montar && (
              <form method="post" className="ms-auto m-0" onSubmit={submeter(`${API}/locais/${loc.id}/feriados/${f.id}/remover`)}>
                <button className="btn btn-outline-danger btn-sm" type="submit" disabled={ocupado}>Remover</button>
              </form>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function textoDaPresenca(p: DadosDoDia['presencas'][number]): string {
  if (p.status === 'confirmada') return `Confirmada às ${p.respondida}`;
  if (p.status === 'sem_resposta') return `Sem resposta${p.respondida ? ` (respondeu às ${p.respondida})` : ''}`;
  if (p.status === 'dispensada') return 'Dispensada (falta lançada)';
  if (p.status === 'nao_enviada') return 'Não enviada (o sistema atrasou)';
  return 'Aguardando';
}

function classeDaPresenca(status: string): string {
  if (status === 'confirmada') return 'text-bg-success';
  if (status === 'sem_resposta') return 'text-bg-danger';
  return 'text-bg-light';
}

export function Dia({ dados }: { dados: DadosDoDia }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const navegar = useNavigate();
  const loc = dados.local;
  const a = dados.aderencia;
  const verDia = (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    const d = new FormData(ev.currentTarget).get('data') || '';
    navegar(`/rotas/locais/${loc.id}/dia?data=${encodeURIComponent(String(d))}`);
  };
  return (
    <div data-tela-pronta="rotas-dia">
      <Migalhas itens={[['Rotas', '/novo/rotas/'], [loc.nome, `/novo/rotas/locais/${loc.id}`], [dados.data_br, null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">{loc.nome} — {dados.data_br}</h1>
      <form className="d-flex gap-2 mb-3" method="get" onSubmit={verDia}>
        <label className="visually-hidden" htmlFor="fdata">Dia</label>
        <input className="form-control w-auto" id="fdata" type="date" name="data" defaultValue={dados.data} />
        <button className="btn btn-outline-primary" type="submit">Ver o dia</button>
      </form>
      <div className="fc-cartao mb-3 d-flex flex-wrap gap-4">
        <div><div className="small text-muted">Aderência à rota</div><div className="fs-3 fw-bold">{pct(a.pct)}</div></div>
        <div><div className="small text-muted">No prazo / já venceram</div><div className="fs-3 fw-bold">{a.no_prazo} / {a.base}</div></div>
        <div><div className="small text-muted">Previstas no dia</div><div className="fs-3 fw-bold">{dados.tarefas.length}</div></div>
      </div>
      <div className="fc-cartao p-0">
        {dados.tarefas.length ? dados.tarefas.map((t) => {
          const ex = t.execucao;
          return (
            <div className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2" key={t.id}>
              <span className="fw-bold">{t.hora}</span>
              <span>{t.ambiente} · {t.ponto}</span>
              <span className="small text-muted">{t.modelo} · {t.rota}</span>
              <span className={`badge fc-sit fc-sit-${t.situacao}`}>{t.situacao_rotulo}</span>
              <span className="small ms-auto">
                {ex ? (
                  <>
                    <Ir href={`/novo/rotas/execucoes/${ex.id}`}>{ex.pessoa} · {ex.inicio}–{ex.fim}{ex.sem_sinal && ' · hora do celular'}{ex.nao_conformes > 0 && ` · ${ex.nao_conformes} não conforme(s)`}</Ir> <SeloGps gps={ex.gps} />
                    {ex.adiantada && <> <span className="badge text-bg-info">Adiantada</span> <span className="text-muted">{ex.motivo_troca}{ex.motivo_troca_texto && `: ${ex.motivo_troca_texto}`}</span></>}
                  </>
                ) : t.nao_realizada ? (
                  <>{t.nao_realizada.motivo}{t.nao_realizada.texto && `: ${t.nao_realizada.texto}`}{t.nao_realizada.chamado && <> · <Ir href={t.nao_realizada.chamado}>chamado</Ir></>}</>
                ) : (t.pessoa || 'sem escala')}
              </span>
            </div>
          );
        }) : <div className="fc-vazio">Nenhuma tarefa prevista neste dia.</div>}
      </div>
      <h2 className="h6 fw-bold mt-3">Ocorrências do QR público</h2>
      <div className="fc-cartao p-0 mb-3">
        {dados.ocorrencias.length ? dados.ocorrencias.map((o) => (
          <div className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2" key={o.id}>
            <span className="fw-bold">{o.hora}</span>
            <span>{o.ambiente} · {o.ponto}</span>
            <span className="fw-semibold">{o.titulo}</span>
            {o.responsavel && <span className="small text-muted">tarefa de {o.responsavel}</span>}
            {o.texto && <span className="small text-muted">"{o.texto}"</span>}
            {o.foto && <a className="small" href={o.foto} target="_blank" rel="noopener">foto</a>}
            <span className={`badge fc-sit fc-ocor-${o.status}`}>{o.situacao}</span>
            {o.atrasada ? <span className="badge text-bg-danger">fora do prazo ({o.prazo})</span>
              : (o.prazo && o.status !== 'resolvida' && <span className="small text-muted">prazo {o.prazo}</span>)}
            <span className="ms-auto small">
              {o.resolvida ? <>{o.resolvida.quem} · {o.resolvida.hora}{o.resolvida.resolucao && `: ${o.resolvida.resolucao}`}</>
                : dados.pode_atender && (
                  <form method="post" className="d-inline-flex gap-1 m-0" onSubmit={submeter(`${API}/ocorrencias/${o.id}/resolver`)}>
                    <input type="hidden" name="data" value={dados.data} />
                    <label className="visually-hidden" htmlFor={`res${o.id}`}>O que foi feito</label>
                    <input className="form-control form-control-sm" id={`res${o.id}`} name="resolucao" placeholder="O que foi feito" maxLength={300} />
                    <button className="btn btn-sm btn-outline-success" type="submit" disabled={ocupado}>Resolvida</button>
                  </form>
                )}
            </span>
          </div>
        )) : <div className="fc-vazio">Nenhuma ocorrência do público neste dia.</div>}
      </div>
      <h2 className="h6 fw-bold mt-3">Elogios do público</h2>
      <div className="fc-cartao p-0 mb-3">
        {dados.elogios.length ? dados.elogios.map((e) => (
          <div className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2" key={e.id}>
            <span className="fw-bold">{e.hora}</span>
            <span>{e.ambiente} · {e.ponto}</span>
            <span className="fc-nota-estrelas" aria-label={`${e.nota} de 5 estrelas`}>{[0, 1, 2, 3, 4].map((i) => <i className={`bi ${i < e.nota ? 'bi-star-fill' : 'bi-star'}`} aria-hidden="true" key={i}></i>)}</span>
            {e.texto && <span className="small text-muted">"{e.texto}"</span>}
            {e.responsavel && <span className="ms-auto small text-muted">equipe: {e.responsavel}</span>}
          </div>
        )) : <div className="fc-vazio">Nenhum elogio neste dia.</div>}
      </div>

      {dados.chegadas.length > 0 && (
        <>
          <h2 className="h6 fw-bold mt-3">Chegadas</h2>
          <div className="fc-cartao p-0 mb-3">
            {dados.chegadas.map((c) => (
              <div className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2" key={c.id}>
                <span className="fw-bold">{c.hora}</span>
                <span>{c.pessoa}</span>
                {!c.com_camera && <span className="small text-muted">liberada pela gestão</span>}
                <SeloGps gps={c.gps} />
              </div>
            ))}
          </div>
        </>
      )}
      {dados.presencas.length > 0 && (
        <>
          <h2 className="h6 fw-bold mt-3">Confirmações de presença</h2>
          <div className="fc-cartao p-0 mb-3">
            {dados.presencas.map((c) => (
              <div className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2" key={c.id}>
                <span className="fw-bold">{c.hora}</span><span>{c.pessoa}</span><span className="small text-muted">{c.rota}</span>
                <span className={`ms-auto badge ${classeDaPresenca(c.status)}`}>{textoDaPresenca(c)}</span>
              </div>
            ))}
          </div>
        </>
      )}
      {dados.extras.length > 0 && (
        <>
          <h2 className="h6 fw-bold mt-3">Atividades fora da rota</h2>
          <div className="fc-cartao p-0">
            {dados.extras.map((ex) => (
              <Ir className="d-flex flex-wrap gap-2 border-bottom px-3 py-2 text-reset" href={`/novo/rotas/execucoes/${ex.id}`} key={ex.id}>
                <span className="fw-bold">{ex.hora}</span><span>{ex.ponto}</span><span className="small text-muted">{ex.modelo} · {ex.pessoa}</span><SeloGps gps={ex.gps} />
                {ex.motivo_troca && <span className="small">Fora da rota · {ex.motivo_troca}{ex.motivo_troca_texto && `: ${ex.motivo_troca_texto}`}</span>}
              </Ir>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function Execucao({ dados }: { dados: DadosDaExecucao }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const ex = dados.execucao;
  return (
    <div data-tela-pronta="rotas-execucao">
      <Migalhas itens={[['Rotas', '/novo/rotas/'], ['Dia', `/novo/rotas/locais/${ex.client_id}/dia?data=${ex.dia}`], ['Execução', null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">{ex.ambiente} · {ex.ponto}</h1>
      <p className="fc-sub">{ex.modelo} (versão {ex.versao}){ex.extra && ' · fora da rota'}</p>
      <div className="fc-cartao mb-3">
        <div className="row small">
          <div className="col-6 col-md-3"><div className="text-muted">Quem fez</div><div className="fw-semibold">{ex.pessoa}</div></div>
          <div className="col-6 col-md-3"><div className="text-muted">QR lido</div><div className="fw-semibold">{ex.lido_em}</div></div>
          <div className="col-6 col-md-3"><div className="text-muted">Concluído</div><div className="fw-semibold">{ex.concluida_em}</div></div>
          <div className="col-6 col-md-3"><div className="text-muted">Registro</div><div className="fw-semibold">{ex.sem_sinal ? `Horário do celular (sem sinal ou sem leitura do QR pela câmera), recebido ${ex.recebida_em}` : 'Horário do sistema'}</div></div>
        </div>
        {ex.gps && <p className="small mt-2 mb-0"><span className="text-muted">Localização na leitura do QR:</span> <strong className={ex.gps.situacao === 'fora' ? 'text-danger' : ''}>{ex.gps.texto}</strong>{ex.gps.precisao ? <> <span className="text-muted">(precisão do celular: {ex.gps.precisao} m)</span></> : null}</p>}
        {ex.tarefa && <p className="small mt-2 mb-0">Tarefa das {ex.tarefa.hora} da rota "{ex.tarefa.rota}"{ex.adiantada && ', adiantada'}.</p>}
        {ex.motivo_troca && <p className="small mt-1 mb-0">{ex.tarefa ? 'Adiantada' : 'Fora da rota'} — motivo: {ex.motivo_troca}{ex.motivo_troca_texto && `: ${ex.motivo_troca_texto}`}</p>}
      </div>
      <div className="fc-cartao mb-3">
        <h2 className="h6 fw-bold">Respostas</h2>
        <ul className="mb-0">
          {dados.respostas.map((r) => (
            <li key={r.codigo}>{r.texto}: <strong>{r.resposta}</strong>{r.corrigida && <> <span className="small text-muted">(corrigido; original: {r.original})</span></>}</li>
          ))}
        </ul>
        {ex.observacao && <p className="mt-2 mb-0"><strong>Observação:</strong> {ex.observacao}</p>}
      </div>
      {dados.fotos.length > 0 && (
        <div className="fc-cartao mb-3">
          <h2 className="h6 fw-bold">Fotos</h2>
          <div className="d-flex flex-wrap gap-2">
            {dados.fotos.map((f) => (
              <figure className="m-0" key={f.id}><a href={f.url} target="_blank" rel="noopener"><img className="fc-miniatura" src={f.url} alt={`Foto ${f.momento}`} /></a>
                <figcaption className="small text-muted">{f.rotulo}</figcaption></figure>
            ))}
          </div>
        </div>
      )}
      {dados.nao_conformidades.length > 0 && (
        <div className="fc-cartao mb-3">
          <h2 className="h6 fw-bold text-danger">Não conformidades</h2>
          {dados.nao_conformidades.map((nc) => (
            <div className="d-flex flex-wrap gap-2 align-items-center border-top py-2" key={nc.id}>
              <span><span className="badge text-bg-light" title="Use este número no plano de ação do Intelligence">NC-{nc.id}</span> {nc.item_texto}: <strong>{nc.resposta}</strong></span>
              {nc.chamado ? <Ir className="ms-auto" href={nc.chamado}>Ver o chamado</Ir> : (
                <form method="post" className="ms-auto m-0" onSubmit={submeter(`${API}/nao-conformidades/${nc.id}/chamado`)}>
                  <button className="btn btn-sm btn-outline-danger" type="submit" disabled={ocupado}>Abrir chamado</button>
                </form>
              )}
            </div>
          ))}
        </div>
      )}
      {dados.correcoes.length > 0 && (
        <div className="fc-cartao mb-3">
          <h2 className="h6 fw-bold">Correções</h2>
          {dados.correcoes.map((c, n) => <p className="small mb-1" key={n}>{c.quando} · {c.autor}: {c.motivo}</p>)}
        </div>
      )}
      {dados.pode_corrigir && (
        <details className="fc-cartao"><summary className="fw-bold">Corrigir uma resposta</summary>
          <p className="small text-muted mt-2">A resposta original não se apaga: a correção fica registrada com o seu nome e o motivo.</p>
          <form method="post" onSubmit={submeter(`${API}/execucoes/${ex.id}/corrigir`)}>
            {dados.itens.map((it) => (
              <div key={it.codigo}>
                <label className="form-label small" htmlFor={`r_${it.codigo}`}>{it.texto}</label>
                <input className="form-control mb-2" id={`r_${it.codigo}`} name={`r_${it.codigo}`} defaultValue={it.valor} />
              </div>
            ))}
            <label className="form-label small fw-semibold" htmlFor="cmotivo">Motivo da correção</label>
            <input className="form-control mb-2" id="cmotivo" name="motivo" required minLength={5} maxLength={500} />
            <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Registrar correção</button>
          </form>
        </details>
      )}
    </div>
  );
}
