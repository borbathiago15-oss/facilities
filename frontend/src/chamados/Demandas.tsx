// O painel de demandas (Fase 4a; a tela antiga é templates/demandas/painel.html,
// com os mesmos textos e classes): tudo que espera alguém, numa fila só. Os
// itens levam à tela de cada um — a nova onde já existe (chamados, o dia do
// local), a de sempre nas outras (visitas, insumos, cobranças).
import { useNavigate } from 'react-router';
import { Ir, RecadosDoEnvio } from '../cadastros/comum';
import { buscaDoFormulario } from './Chamados';
import type { DadosDasDemandas } from './tipos';

/** O ``url_for('demandas.painel', situacao=k, local=cid, tipo=tipo)`` da
 * antiga: o local fica de fora quando não há; o tipo vai mesmo vazio. */
export function urlDaSituacao(situacao: string, local: number | null, tipo: string): string {
  const partes = [`situacao=${encodeURIComponent(situacao)}`];
  if (local !== null && local !== undefined) partes.push(`local=${local}`);
  partes.push(`tipo=${encodeURIComponent(tipo)}`);
  return '/novo/demandas/?' + partes.join('&');
}

export function Demandas({ dados }: { dados: DadosDasDemandas }) {
  const navegar = useNavigate();
  const rotuloSituacao = Object.fromEntries(dados.situacoes);
  return (
    <div data-tela-pronta="demandas">
      <RecadosDoEnvio />
      <h1 className="fc-titulo">Demandas</h1>
      <p className="fc-sub">Tudo que espera alguém, numa fila só: chamados, preventivas, avisos do público pelo QR, visitas, pedidos de insumo e cobranças do cliente. O atrasado vem primeiro.</p>
      <p className="small"><a href={dados.links.cobrancas}><i className="bi bi-megaphone" aria-hidden="true"></i> Todas as cobranças do cliente, inclusive as respondidas e encerradas</a></p>
      <div className="d-flex flex-wrap gap-2 mb-3">
        {dados.situacoes.map(([k, v]) => (
          <Ir className={`fc-cartao py-2 px-3 text-reset text-decoration-none${dados.situacao === k ? ' border-primary' : ''}`}
            href={urlDaSituacao(k, dados.local, dados.tipo)} key={k}>
            <div className="small text-muted">{v}</div><div className="fs-4 fw-bold">{dados.contagem[k]}</div></Ir>
        ))}
      </div>
      <form className="d-flex flex-wrap gap-2 mb-3" method="get"
        onSubmit={(ev) => { ev.preventDefault(); navegar('/demandas/?' + buscaDoFormulario(ev.currentTarget)); }}>
        <label className="visually-hidden" htmlFor="flocal">Local</label>
        <select className="form-select w-auto" id="flocal" name="local" defaultValue={dados.local ?? ''}>
          <option value="">Todos os locais</option>
          {dados.locais.map((l) => <option value={l.id} key={l.id}>{l.nome}</option>)}
        </select>
        <label className="visually-hidden" htmlFor="ftipo">Tipo</label>
        <select className="form-select w-auto" id="ftipo" name="tipo" defaultValue={dados.tipo}>
          <option value="">Todos os tipos</option>
          {dados.tipos.map(([k, v]) => <option value={k} key={k}>{v}</option>)}
        </select>
        <label className="visually-hidden" htmlFor="fsit">Situação</label>
        <select className="form-select w-auto" id="fsit" name="situacao" defaultValue={dados.situacao}>
          <option value="">Todas as situações</option>
          {dados.situacoes.map(([k, v]) => <option value={k} key={k}>{v}</option>)}
        </select>
        <button className="btn btn-outline-primary" type="submit">Filtrar</button>
      </form>
      <div className="fc-cartao p-0">
        {dados.itens.length ? dados.itens.map((i, n) => (
          <Ir className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2 text-reset text-decoration-none" href={i.link} key={n}>
            <span className={`badge fc-dem fc-dem-${i.situacao}`}>{rotuloSituacao[i.situacao]}</span>
            <span className="badge text-bg-light">{i.tipo_rotulo}</span>
            {i.numero && <span className="small fw-semibold">{i.numero}</span>}
            <span className="fw-semibold">{i.titulo}</span>
            <span className="small text-muted">{i.local} · {i.estado}{i.responsavel && ` · ${i.responsavel}`}</span>
            <span className="small ms-auto">{i.prazo && `prazo ${i.prazo}`}</span>
          </Ir>
        )) : <div className="fc-vazio">Nenhuma demanda esperando. Tudo em dia.</div>}
      </div>
    </div>
  );
}
