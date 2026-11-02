// A equipe do local e a grade do mês (Fase 4b; as telas antigas são
// templates/equipes/local.html e mes.html, com os mesmos textos, campos e
// classes). Os envios vão ao mesmo caminho da antiga abaixo de /api/v1 e
// chamam a mesma ação (equipes.telas.acao_*).
import { Ir, Migalhas, RecadosDoEnvio, useFormulario } from '../cadastros/comum';
import type { Celula, DadosDaEquipe, DadosDoMes } from './tipos';

const API = '/api/v1/equipes';

export function Equipe({ dados }: { dados: DadosDaEquipe }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const loc = dados.local;
  const opcoesDeLogin = dados.logins.map((u) => <option value={u.id} key={u.id}>{u.nome} ({u.email})</option>);
  const opcoesDeRota = dados.rotas.map((r) => <option value={r.id} key={r.id}>{r.nome}</option>);
  return (
    <div data-tela-pronta="equipe-local">
      <Migalhas itens={[[loc.nome, dados.links.local], ['Equipe', null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Equipe · {loc.nome}</h1>
      <p className="fc-sub">Quem trabalha aqui, em qual posto e em que dias. O supervisor lança no aplicativo quem veio, quem faltou e quem cobriu.</p>
      <div className="d-flex flex-wrap gap-2 mb-3">
        <Ir className="btn btn-primary btn-sm" href={dados.links.mes}><i className="bi bi-calendar3"></i> Conferir o mês</Ir>
        <Ir className="btn btn-outline-secondary btn-sm" href={dados.links.visitas}><i className="bi bi-clipboard-check"></i> Visitas de supervisão</Ir>
      </div>

      <section className="fc-cartao mb-3" aria-labelledby="tit-func">
        <h2 className="h6 fw-bold" id="tit-func"><i className="bi bi-people"></i> Funcionários</h2>
        {dados.funcionarios.length ? dados.funcionarios.map((f) => (
          <div className="border-top py-2" key={f.id}>
            <div className="d-flex flex-wrap gap-2 align-items-center">
              <span className="fw-semibold">{f.nome}</span>
              {f.funcao && <span className="small text-muted">{f.funcao}</span>}
              {f.matricula && <span className="small text-muted">matrícula {f.matricula}</span>}
              {f.usa_app ? <span className="badge text-bg-light">usa o aplicativo</span> : <span className="badge text-bg-light">sem login</span>}
              {!f.ativo && <span className="badge text-bg-secondary">desligado</span>}
            </div>
            {dados.pode_montar && (
              <details className="mt-1">
                <summary className="small fw-semibold">Editar</summary>
                <form method="post" className="row g-2 mt-1" onSubmit={submeter(`${API}/funcionarios/${f.id}`)}>
                  <div className="col-md-4"><label className="form-label small" htmlFor={`fn${f.id}`}>Nome</label><input className="form-control" id={`fn${f.id}`} name="nome" required maxLength={120} defaultValue={f.nome} /></div>
                  <div className="col-md-3"><label className="form-label small" htmlFor={`ff${f.id}`}>Função</label><input className="form-control" id={`ff${f.id}`} name="funcao" maxLength={80} defaultValue={f.funcao} /></div>
                  <div className="col-md-2"><label className="form-label small" htmlFor={`fm${f.id}`}>Matrícula</label><input className="form-control" id={`fm${f.id}`} name="matricula" maxLength={30} defaultValue={f.matricula} /></div>
                  <div className="col-md-3"><label className="form-label small" htmlFor={`fu${f.id}`}>Login no aplicativo</label>
                    <select className="form-select" id={`fu${f.id}`} name="user_id" defaultValue={f.user_id ?? ''}><option value="">Sem login</option>{opcoesDeLogin}</select></div>
                  <div className="col-12"><button className="btn btn-primary btn-sm fw-bold" type="submit" disabled={ocupado}>Salvar</button></div>
                </form>
                <form method="post" className="mt-2" onSubmit={submeter(`${API}/funcionarios/${f.id}`)}>
                  <input type="hidden" name="ativo" value={f.ativo ? '0' : '1'} />
                  <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={ocupado}>{f.ativo ? 'Desligar' : 'Reativar'}</button>
                </form>
              </details>
            )}
          </div>
        )) : <p className="small text-muted">Nenhum funcionário ainda.</p>}
        {dados.pode_montar && (
          <details className="mt-2" open={!dados.funcionarios.length}>
            <summary className="fw-semibold">Cadastrar funcionário</summary>
            <form method="post" className="row g-2 mt-1" onSubmit={submeter(`${API}/locais/${loc.id}/funcionarios`)}>
              <div className="col-md-4"><label className="form-label small" htmlFor="nfn">Nome</label><input className="form-control" id="nfn" name="nome" required maxLength={120} /></div>
              <div className="col-md-3"><label className="form-label small" htmlFor="nff">Função</label><input className="form-control" id="nff" name="funcao" maxLength={80} placeholder="Ex.: ASG" /></div>
              <div className="col-md-2"><label className="form-label small" htmlFor="nfm">Matrícula</label><input className="form-control" id="nfm" name="matricula" maxLength={30} /></div>
              <div className="col-md-3"><label className="form-label small" htmlFor="nfu">Login no aplicativo</label>
                <select className="form-select" id="nfu" name="user_id"><option value="">Sem login</option>{opcoesDeLogin}</select></div>
              <div className="col-12"><button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Cadastrar</button></div>
            </form>
          </details>
        )}
      </section>

      <section className="fc-cartao mb-3" aria-labelledby="tit-postos">
        <h2 className="h6 fw-bold" id="tit-postos"><i className="bi bi-pin-map"></i> Postos</h2>
        {dados.postos.length ? dados.postos.map((p) => (
          <div className="border-top py-2" key={p.id}>
            <div className="d-flex flex-wrap gap-2 align-items-center">
              <span className="fw-semibold">{p.nome}</span>
              <span className="small text-muted">{p.hora_inicio} às {p.hora_fim}{p.rota && ` · rota "${p.rota}"`}</span>
              {!p.ativo && <span className="badge text-bg-secondary">desativado</span>}
            </div>
            {dados.pode_montar && (
              <details className="mt-1">
                <summary className="small fw-semibold">Editar</summary>
                <form method="post" className="row g-2 mt-1" onSubmit={submeter(`${API}/postos/${p.id}`)}>
                  <div className="col-md-4"><label className="form-label small" htmlFor={`pn${p.id}`}>Nome</label><input className="form-control" id={`pn${p.id}`} name="nome" required maxLength={120} defaultValue={p.nome} /></div>
                  <div className="col-6 col-md-2"><label className="form-label small" htmlFor={`pi${p.id}`}>Início</label><input className="form-control" id={`pi${p.id}`} name="hora_inicio" type="time" required defaultValue={p.hora_inicio} /></div>
                  <div className="col-6 col-md-2"><label className="form-label small" htmlFor={`pf${p.id}`}>Fim</label><input className="form-control" id={`pf${p.id}`} name="hora_fim" type="time" required defaultValue={p.hora_fim} /></div>
                  <div className="col-md-4"><label className="form-label small" htmlFor={`pr${p.id}`}>Rota do posto (opcional)</label>
                    <select className="form-select" id={`pr${p.id}`} name="rota_id" defaultValue={p.rota_id ?? ''}><option value="">Nenhuma</option>{opcoesDeRota}</select></div>
                  <div className="col-12"><button className="btn btn-primary btn-sm fw-bold" type="submit" disabled={ocupado}>Salvar</button></div>
                </form>
                <form method="post" className="mt-2" onSubmit={submeter(`${API}/postos/${p.id}`)}>
                  <input type="hidden" name="ativo" value={p.ativo ? '0' : '1'} />
                  <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={ocupado}>{p.ativo ? 'Desativar' : 'Reativar'}</button>
                </form>
              </details>
            )}
          </div>
        )) : <p className="small text-muted">Nenhum posto ainda.</p>}
        {dados.pode_montar && (
          <details className="mt-2" open={!dados.postos.length}>
            <summary className="fw-semibold">Cadastrar posto</summary>
            <form method="post" className="row g-2 mt-1" onSubmit={submeter(`${API}/locais/${loc.id}/postos`)}>
              <div className="col-md-4"><label className="form-label small" htmlFor="npn">Nome</label><input className="form-control" id="npn" name="nome" required maxLength={120} placeholder="Ex.: Limpeza 2º andar — manhã" /></div>
              <div className="col-6 col-md-2"><label className="form-label small" htmlFor="npi">Início</label><input className="form-control" id="npi" name="hora_inicio" type="time" required defaultValue="07:00" /></div>
              <div className="col-6 col-md-2"><label className="form-label small" htmlFor="npf">Fim</label><input className="form-control" id="npf" name="hora_fim" type="time" required defaultValue="15:00" /></div>
              <div className="col-md-4"><label className="form-label small" htmlFor="npr">Rota do posto (opcional)</label>
                <select className="form-select" id="npr" name="rota_id"><option value="">Nenhuma</option>{opcoesDeRota}</select></div>
              <div className="col-12"><p className="form-text mt-0">Com a rota escolhida, quem cobrir uma falta recebe as tarefas da rota daquele dia.</p>
                <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Cadastrar</button></div>
            </form>
          </details>
        )}
      </section>

      <section className="fc-cartao" aria-labelledby="tit-esc">
        <h2 className="h6 fw-bold" id="tit-esc"><i className="bi bi-calendar-week"></i> Escala em vigor</h2>
        {dados.escalas.length ? dados.escalas.map((e) => (
          <div className="border-top py-2 d-flex flex-wrap gap-2 align-items-center" key={e.id}>
            <span className="fw-semibold">{e.funcionario}</span>
            <span className="small text-muted">{e.posto} · {e.dias}· desde {e.data_inicio}{e.data_fim && ` até ${e.data_fim}`}</span>
            {dados.pode_montar && (
              <form method="post" className="d-flex gap-2 ms-auto" onSubmit={submeter(`${API}/escalas/${e.id}/encerrar`)}>
                <label className="visually-hidden" htmlFor={`ef${e.id}`}>Último dia</label>
                <input className="form-control form-control-sm" id={`ef${e.id}`} name="data_fim" type="date" required defaultValue={dados.hoje} />
                <button className="btn btn-outline-secondary btn-sm text-nowrap" type="submit" disabled={ocupado}>Encerrar</button>
              </form>
            )}
          </div>
        )) : <p className="small text-muted">Ninguém escalado ainda.</p>}
        {dados.pode_montar && dados.funcionarios.length > 0 && dados.postos.length > 0 && (
          <details className="mt-2" open={!dados.escalas.length}>
            <summary className="fw-semibold">Lançar escala</summary>
            <form method="post" className="row g-2 mt-1" onSubmit={submeter(`${API}/locais/${loc.id}/escalas`)}>
              <div className="col-md-4"><label className="form-label small" htmlFor="esf">Funcionário</label>
                <select className="form-select" id="esf" name="funcionario_id" required>
                  {dados.funcionarios.filter((f) => f.ativo).map((f) => <option value={f.id} key={f.id}>{f.nome}</option>)}</select></div>
              <div className="col-md-4"><label className="form-label small" htmlFor="esp">Posto</label>
                <select className="form-select" id="esp" name="posto_id" required>
                  {dados.postos.filter((p) => p.ativo).map((p) => <option value={p.id} key={p.id}>{p.nome} ({p.hora_inicio}–{p.hora_fim})</option>)}</select></div>
              <div className="col-6 col-md-2"><label className="form-label small" htmlFor="esi">Começa em</label><input className="form-control" id="esi" name="data_inicio" type="date" required defaultValue={dados.hoje} /></div>
              <div className="col-6 col-md-2"><label className="form-label small" htmlFor="esfim">Termina em (opcional)</label><input className="form-control" id="esfim" name="data_fim" type="date" /></div>
              <fieldset className="col-12">
                <legend className="form-label small mb-1">Dias da semana</legend>
                <div className="d-flex flex-wrap gap-3">
                  {dados.dias.map(([k, v]) => (
                    <label className="d-flex gap-1 align-items-center" key={k}><input type="checkbox" name={`dia_${k}`} value="1" defaultChecked={'12345'.includes(k)} /> {v}</label>
                  ))}
                </div>
              </fieldset>
              <div className="col-12"><button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Lançar escala</button></div>
            </form>
          </details>
        )}
      </section>
    </div>
  );
}

function CelulaDoMes({ c }: { c: Celula }) {
  if (!c) return null;
  if (c.tipo === 'previsto') return <span className="text-muted small" title={c.titulo}>{c.letra}</span>;
  return <span className={`fc-pres fc-pres-${c.tipo}`} title={c.titulo}>{c.letra}</span>;
}

export function Mes({ dados }: { dados: DadosDoMes }) {
  const loc = dados.local;
  const base = `/novo/equipes/locais/${loc.id}/mes?m=`;
  return (
    <div data-tela-pronta="equipe-mes">
      <Migalhas itens={[[`Equipe · ${loc.nome}`, dados.links.equipe], ['Mês', null]]} />
      <RecadosDoEnvio />
      <h1 className="fc-titulo">Escala e presença · {dados.mes}</h1>
      <p className="fc-sub">{loc.nome}. Cada linha é uma escala; cada coluna, um dia. O ponto cinza é dia escalado ainda sem presença lançada.</p>
      <div className="d-flex flex-wrap gap-2 mb-3">
        <Ir className="btn btn-outline-secondary btn-sm" href={base + dados.anterior}><i className="bi bi-chevron-left"></i> Mês anterior</Ir>
        <Ir className="btn btn-outline-secondary btn-sm" href={base + dados.seguinte}>Mês seguinte <i className="bi bi-chevron-right"></i></Ir>
      </div>
      <div className="d-flex flex-wrap gap-2 mb-3">
        <div className="fc-cartao py-2 px-3"><div className="small text-muted">Dias escalados até hoje</div><div className="fs-4 fw-bold">{dados.totais.previstos}</div></div>
        <div className="fc-cartao py-2 px-3"><div className="small text-muted">Presença lançada</div><div className="fs-4 fw-bold">{dados.totais.lancados}</div></div>
        <div className="fc-cartao py-2 px-3"><div className="small text-muted">Faltas</div><div className="fs-4 fw-bold">{dados.totais.faltas}</div></div>
        <div className="fc-cartao py-2 px-3"><div className="small text-muted">Faltas cobertas</div><div className="fs-4 fw-bold">{dados.totais.cobertas}</div></div>
      </div>
      <p className="small"><span className="fc-pres fc-pres-veio">V</span> veio · <span className="fc-pres fc-pres-atrasou">A</span> atrasou · <span className="fc-pres fc-pres-faltou">F</span> faltou · <span className="fc-pres fc-pres-coberta">C</span> faltou e foi coberta · <span className="fc-pres fc-pres-pendente">·</span> sem lançamento</p>
      <div className="fc-cartao p-0 fc-mes-rolar">
        <table className="table table-sm mb-0 fc-mes">
          <caption className="visually-hidden">Escala e presença do mês</caption>
          <thead><tr><th scope="col">Funcionário · posto</th>{dados.dias.map((d) => <th scope="col" className="text-center" key={d}>{d}</th>)}</tr></thead>
          <tbody>
            {dados.linhas.length ? dados.linhas.map((linha, n) => (
              <tr key={n}>
                <th scope="row" className="text-nowrap small">{linha.funcionario}<br /><span className="text-muted">{linha.posto}</span></th>
                {linha.celulas.map((c, i) => <td className="text-center" key={i}><CelulaDoMes c={c} /></td>)}
              </tr>
            )) : <tr><td colSpan={dados.dias.length + 1} className="fc-vazio">Nenhuma escala neste mês.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
