// O painel por perfil (Fase 4c; a tela antiga é templates/paineis/painel.html,
// com os mesmos textos e classes): a nota de cada local da carteira, os
// indicadores, os elogios do público e o que está atrasado agora (que leva
// ao painel de demandas novo). Sem gráfico: a antiga é só tabela.
import { useNavigate } from 'react-router';
import { Ir, RecadosDoEnvio, buscaDoFormulario } from '../cadastros/comum';
import type { DadosDoPainel, LinhaDoPainel } from './tipos';

function Tabela({ linhas, indicadores }: { linhas: LinhaDoPainel[]; indicadores: string[] }) {
  return (
    <div className="fc-mes-rolar">
      <table className="table table-sm mb-0 align-middle">
        <thead><tr><th scope="col">Local</th><th scope="col" className="text-center">Nota</th>{indicadores.map((v) => <th scope="col" className="text-center small" key={v}>{v}</th>)}<th scope="col" className="text-center small">Elogios do público</th><th scope="col" className="text-center small">Atrasado agora</th></tr></thead>
        <tbody>{linhas.map((x) => (
          <tr key={x.local_id}>
            <th scope="row" className="small">{x.local}</th>
            <td className="text-center">{x.nota !== null ? <span className={`badge fc-nota fc-nota-${x.faixa}`}>{x.nota}</span> : <span className="small text-muted">sem dado</span>}</td>
            {x.indicadores.map((i, n) => (
              <td className="text-center small" key={n}>{i ? <>{i.pct}<br /><span className="text-muted">{i.base}</span></> : <span className="text-muted">—</span>}</td>
            ))}
            <td className="text-center small">{x.elogios ? <><span className="fc-nota-estrelas"><i className="bi bi-star-fill" aria-hidden="true"></i> {x.elogios.media}</span><br /><span className="text-muted">{x.elogios.total} avaliação(ões)</span></> : <span className="text-muted">—</span>}</td>
            <td className="text-center">{x.atrasadas ? <Ir className="badge fc-dem fc-dem-atrasada text-decoration-none" href={x.atrasadas_url}>{x.atrasadas}</Ir> : <span className="small text-muted">0</span>}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export function Painel({ dados }: { dados: DadosDoPainel }) {
  const navegar = useNavigate();
  const r = dados.resumo;
  return (
    <div data-tela-pronta="painel">
      <RecadosDoEnvio />
      <h1 className="fc-titulo">Painel</h1>
      <p className="fc-sub">A nota de cada local é a média, com pesos iguais, dos indicadores que tiveram movimento no período. Abaixo de {dados.faixa_critica}: crítica; de {dados.faixa_critica} a {dados.faixa_boa - 1}: atenção; {dados.faixa_boa} ou mais: boa.</p>
      <form className="d-flex flex-wrap gap-2 mb-3" method="get"
        onSubmit={(ev) => { ev.preventDefault(); navegar('/painel?' + buscaDoFormulario(ev.currentTarget)); }}>
        <label className="visually-hidden" htmlFor="pde">De</label><input className="form-control w-auto" type="date" id="pde" name="de" defaultValue={dados.de} />
        <label className="visually-hidden" htmlFor="pate">Até</label><input className="form-control w-auto" type="date" id="pate" name="ate" defaultValue={dados.ate} />
        <button className="btn btn-outline-primary" type="submit">Ver</button>
      </form>
      <div className="d-flex flex-wrap gap-2 mb-3">
        <div className="fc-cartao py-2 px-3"><div className="small text-muted">Nota média</div><div className="fs-4 fw-bold">{r.media}</div></div>
        {r.faixas.map(([rotulo, n]) => <div className="fc-cartao py-2 px-3" key={rotulo}><div className="small text-muted">{rotulo}</div><div className="fs-4 fw-bold">{n}</div></div>)}
        {r.sem_dado > 0 && <div className="fc-cartao py-2 px-3"><div className="small text-muted">Sem dado</div><div className="fs-4 fw-bold">{r.sem_dado}</div></div>}
      </div>
      {!dados.linhas.length ? <div className="fc-cartao fc-vazio">Nenhum local na sua carteira.</div>
        : dados.grupos ? dados.grupos.map((g, n) => (
          <section className="fc-cartao p-0 mb-3" aria-labelledby={`tit-g${n + 1}`} key={g.cliente}>
            <h2 className="h6 fw-bold px-3 pt-3" id={`tit-g${n + 1}`}>{g.cliente} <span className="small text-muted fw-normal">· nota média {g.media}</span></h2>
            <Tabela linhas={g.linhas} indicadores={dados.indicadores} />
          </section>
        )) : <section className="fc-cartao p-0"><Tabela linhas={dados.linhas} indicadores={dados.indicadores} /></section>}
      <p className="small text-muted mt-2">O período vai de {dados.de_br} a {dados.ate_br}. Os mesmos números saem pela integração com o Trino Intelligence. Os elogios do público (1 a 5 estrelas, pelo QR dos pontos) não entram na nota.</p>
    </div>
  );
}
