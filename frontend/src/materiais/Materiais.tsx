// As telas dos materiais na gestão (Fase 4b; as antigas são
// templates/materiais/catalogo.html, local.html, mes.html, custo.html e
// pedidos.html, com os mesmos textos, campos e classes). Os envios vão ao
// mesmo caminho da antiga abaixo de /api/v1 e chamam a mesma ação
// (materiais.telas.acao_*). A foto do pedido continua no servidor; o
// aplicativo de quem usa o material é o do campo (/novo/app/materiais, Fase 1d).
import { useNavigate } from 'react-router';
import { Ir, Migalhas, RecadosDoEnvio, useFormulario } from '../cadastros/comum';
import type { DadosDoCatalogo, DadosDoConsumoDoMes, DadosDoCusto, DadosDoEstoque, DadosDosPedidos, Pedido } from './tipos';

const API = '/api/v1/materiais';

/** A busca de um formulário GET (o ``?de=&ate=`` do custo). */
export function buscaDoFormulario(form: HTMLFormElement): string {
  const q = new URLSearchParams();
  new FormData(form).forEach((v, k) => q.append(k, typeof v === 'string' ? v : ''));
  return q.toString();
}

// ── Catálogo ──────────────────────────────────────────────────────────────

export function Catalogo({ dados }: { dados: DadosDoCatalogo }) {
  const { submeter, ocupado, aviso } = useFormulario();
  return (
    <div data-tela-pronta="materiais">
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Materiais e insumos</h1>
      <p className="fc-sub">O catálogo do grupo. O preço é opcional: material sem preço entra no estoque, mas fica fora do custo.</p>
      <div className="d-flex flex-wrap gap-2 mb-3">
        <Ir className="btn btn-primary btn-sm" href={dados.links.custo}><i className="bi bi-cash-coin"></i> Custo operacional</Ir>
        <Ir className="btn btn-outline-secondary btn-sm" href={dados.links.pedidos}><i className="bi bi-cart"></i> Pedidos de insumo</Ir>
      </div>
      <section className="fc-cartao mb-3" aria-labelledby="tit-est">
        <h2 className="h6 fw-bold" id="tit-est"><i className="bi bi-box-seam"></i> Estoque por local</h2>
        {dados.locais.length ? dados.locais.map((l) => (
          <Ir className="d-flex border-top py-2 text-reset text-decoration-none" href={l.url} key={l.id}><span className="fw-semibold">{l.nome}</span><i className="bi bi-chevron-right ms-auto"></i></Ir>
        )) : <p className="small text-muted">Nenhum local na sua carteira.</p>}
      </section>
      <section className="fc-cartao" aria-labelledby="tit-cat">
        <h2 className="h6 fw-bold" id="tit-cat"><i className="bi bi-list-ul"></i> Catálogo</h2>
        {dados.materiais.length ? dados.materiais.map((m) => (
          <div className="border-top py-2" key={m.id}>
            <div className="d-flex flex-wrap gap-2 align-items-center">
              <span className="fw-semibold">{m.nome}</span><span className="small text-muted">{m.unidade}</span>
              <span className="small ms-auto">{m.preco !== null ? `${m.preco} / ${m.unidade}` : <span className="text-muted">sem preço</span>}</span>
              {!m.ativo && <span className="badge text-bg-secondary">desativado</span>}
            </div>
            {dados.pode_montar && (
              <details className="mt-1"><summary className="small fw-semibold">Editar</summary>
                <form method="post" className="row g-2 mt-1" onSubmit={submeter(`${API}/${m.id}`)}>
                  <div className="col-md-5"><label className="form-label small" htmlFor={`mn${m.id}`}>Nome</label><input className="form-control" id={`mn${m.id}`} name="nome" required maxLength={120} defaultValue={m.nome} /></div>
                  <div className="col-6 col-md-3"><label className="form-label small" htmlFor={`mu${m.id}`}>Unidade</label><input className="form-control" id={`mu${m.id}`} name="unidade" required maxLength={20} defaultValue={m.unidade} /></div>
                  <div className="col-6 col-md-4"><label className="form-label small" htmlFor={`mp${m.id}`}>Preço por unidade (R$, opcional)</label><input className="form-control" id={`mp${m.id}`} name="preco_unitario" inputMode="decimal" defaultValue={m.preco_campo} /></div>
                  <div className="col-12"><button className="btn btn-primary btn-sm fw-bold" type="submit" disabled={ocupado}>Salvar</button></div>
                </form>
                <form method="post" className="mt-2" onSubmit={submeter(`${API}/${m.id}`)}>
                  <input type="hidden" name="ativo" value={m.ativo ? '0' : '1'} />
                  <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={ocupado}>{m.ativo ? 'Desativar' : 'Reativar'}</button>
                </form>
              </details>
            )}
          </div>
        )) : <p className="small text-muted">Nenhum material ainda.</p>}
        {dados.pode_montar && (
          <details className="mt-2" open={!dados.materiais.length}><summary className="fw-semibold">Cadastrar material</summary>
            <form method="post" className="row g-2 mt-1" onSubmit={submeter(`${API}/`)}>
              <div className="col-md-5"><label className="form-label small" htmlFor="nmn">Nome</label><input className="form-control" id="nmn" name="nome" required maxLength={120} placeholder="Ex.: Detergente neutro 5 L" /></div>
              <div className="col-6 col-md-3"><label className="form-label small" htmlFor="nmu">Unidade</label><input className="form-control" id="nmu" name="unidade" required maxLength={20} placeholder="Ex.: un, L, kg" /></div>
              <div className="col-6 col-md-4"><label className="form-label small" htmlFor="nmp">Preço por unidade (R$, opcional)</label><input className="form-control" id="nmp" name="preco_unitario" inputMode="decimal" placeholder="Ex.: 12,90" /></div>
              <div className="col-12"><button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Cadastrar</button></div>
            </form>
          </details>
        )}
      </section>
    </div>
  );
}

// ── Estoque do local ──────────────────────────────────────────────────────

export function Estoque({ dados }: { dados: DadosDoEstoque }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const loc = dados.local;
  const opcoesDeMaterial = dados.materiais.map((m) => <option value={m.id} key={m.id}>{m.nome} ({m.unidade})</option>);
  return (
    <div data-tela-pronta="materiais-local">
      <Migalhas itens={[['Materiais', dados.links.catalogo], [loc.nome, null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Estoque · {loc.nome}</h1>
      <p className="fc-sub">O saldo é a soma de tudo que entrou e saiu. O consumo do dia a dia é lançado no aplicativo, por quem usou.</p>
      <div className="d-flex flex-wrap gap-2 mb-3">
        <Ir className="btn btn-primary btn-sm" href={dados.links.mes}><i className="bi bi-calendar3"></i> Consumo do mês</Ir>
      </div>
      <section className="fc-cartao mb-3" aria-labelledby="tit-saldo">
        <h2 className="h6 fw-bold" id="tit-saldo"><i className="bi bi-box-seam"></i> Saldo</h2>
        {dados.com_saldo.length ? dados.com_saldo.map((m) => (
          <div className="d-flex border-top py-2 gap-2" key={m.id}><span className="fw-semibold">{m.nome}</span>
            <span className={`ms-auto fw-bold${m.negativo ? ' text-danger' : ''}`}>{m.saldo} {m.unidade}</span></div>
        )) : <p className="small text-muted">Nenhum material lançado neste local ainda.</p>}
      </section>
      {dados.pode_montar && dados.materiais.length > 0 && (
        <section className="fc-cartao mb-3" aria-labelledby="tit-mov">
          <h2 className="h6 fw-bold" id="tit-mov"><i className="bi bi-arrow-left-right"></i> Lançar entrada, saída ou ajuste</h2>
          <form method="post" className="row g-2" onSubmit={submeter(`${API}/locais/${loc.id}/movimento`)}>
            <div className="col-md-3"><label className="form-label small" htmlFor="mvt">Tipo</label>
              <select className="form-select" id="mvt" name="tipo">{dados.tipos.map(([k, v]) => <option value={k} key={k}>{v}</option>)}</select></div>
            <div className="col-md-4"><label className="form-label small" htmlFor="mvm">Material</label>
              <select className="form-select" id="mvm" name="material_id" required>{opcoesDeMaterial}</select></div>
            <div className="col-md-2"><label className="form-label small" htmlFor="mvq">Quantidade</label><input className="form-control" id="mvq" name="quantidade" required inputMode="decimal" placeholder="Ex.: 10" /></div>
            <div className="col-md-3"><label className="form-label small" htmlFor="mvmo">Motivo</label><input className="form-control" id="mvmo" name="motivo" maxLength={300} placeholder="Obrigatório em saída e ajuste" /></div>
            <div className="col-12"><p className="form-text mt-0">No ajuste de inventário, use número negativo para tirar (ex.: -2).</p>
              {dados.gestor_do_contrato && <label className="d-flex gap-2 small"><input type="checkbox" name="autorizar_negativo" value="1" /> Autorizo o saldo ficar negativo (gestor do contrato; escreva a justificativa no motivo)</label>}
              <button className="btn btn-primary fw-bold mt-2" type="submit" disabled={ocupado}>Lançar</button></div>
          </form>
        </section>
      )}
      {dados.materiais.length > 0 && (
        <section className="fc-cartao mb-3" aria-labelledby="tit-cons">
          <h2 className="h6 fw-bold" id="tit-cons"><i className="bi bi-droplet-half"></i> Lançar consumo</h2>
          <form method="post" className="row g-2" onSubmit={submeter(`${API}/locais/${loc.id}/consumo`)}>
            <div className="col-md-4"><label className="form-label small" htmlFor="csm">Material</label>
              <select className="form-select" id="csm" name="material_id" required>{opcoesDeMaterial}</select></div>
            <div className="col-md-2"><label className="form-label small" htmlFor="csq">Quantidade</label><input className="form-control" id="csq" name="quantidade" required inputMode="decimal" /></div>
            <div className="col-md-3"><label className="form-label small" htmlFor="csr">Na rotina (opcional)</label>
              <select className="form-select" id="csr" name="rota_id"><option value="">—</option>{dados.rotas.map((r) => <option value={r.id} key={r.id}>{r.nome}</option>)}</select></div>
            <div className="col-md-3"><label className="form-label small" htmlFor="csmo">Observação</label><input className="form-control" id="csmo" name="motivo" maxLength={300} /></div>
            {dados.gestor_do_contrato && <div className="col-12"><label className="d-flex gap-2 small"><input type="checkbox" name="autorizar_negativo" value="1" /> Autorizo o saldo ficar negativo (escreva a justificativa na observação)</label></div>}
            <div className="col-12"><button className="btn btn-outline-primary fw-bold" type="submit" disabled={ocupado}>Lançar consumo</button></div>
          </form>
        </section>
      )}
      <section className="fc-cartao p-0" aria-labelledby="tit-hist">
        <h2 className="h6 fw-bold px-3 pt-3" id="tit-hist"><i className="bi bi-clock-history"></i> Últimos lançamentos</h2>
        <div className="fc-mes-rolar">
          <table className="table table-sm mb-0">
            <thead><tr><th scope="col">Dia</th><th scope="col">Tipo</th><th scope="col">Material</th><th scope="col" className="text-end">Qtd.</th><th scope="col" className="text-end">Valor</th><th scope="col">Quem · motivo</th></tr></thead>
            <tbody>
              {dados.movimentos.length ? dados.movimentos.map((mv, n) => (
                <tr key={n}><td className="text-nowrap">{mv.dia}</td><td>{mv.tipo_rotulo}</td><td>{mv.material}</td>
                  <td className="text-end text-nowrap">{mv.quantidade}</td>
                  <td className="text-end text-nowrap">{mv.valor}</td>
                  <td className="small">{mv.pessoa}{mv.motivo && ` · ${mv.motivo}`}{mv.autorizou && <> · <b>saldo negativo autorizado por {mv.autorizou}</b></>}</td></tr>
              )) : <tr><td colSpan={6} className="fc-vazio">Nenhum lançamento ainda.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

// ── Consumo do mês ────────────────────────────────────────────────────────

export function ConsumoDoMes({ dados }: { dados: DadosDoConsumoDoMes }) {
  const loc = dados.local;
  const base = `/novo/materiais/locais/${loc.id}/mes?m=`;
  return (
    <div data-tela-pronta="materiais-mes">
      <Migalhas itens={[[`Estoque · ${loc.nome}`, dados.links.local], ['Mês', null]]} />
      <RecadosDoEnvio />
      <h1 className="fc-titulo">Consumo · {dados.mes}</h1>
      <p className="fc-sub">{loc.nome}. Custo operacional do local — não substitui nem alimenta o DRE.</p>
      <div className="d-flex flex-wrap gap-2 mb-3">
        <Ir className="btn btn-outline-secondary btn-sm" href={base + dados.anterior}><i className="bi bi-chevron-left"></i> Mês anterior</Ir>
        <Ir className="btn btn-outline-secondary btn-sm" href={base + dados.seguinte}>Mês seguinte <i className="bi bi-chevron-right"></i></Ir>
      </div>
      <div className="fc-cartao py-2 px-3 mb-3 d-inline-block"><div className="small text-muted">Custo do mês</div><div className="fs-4 fw-bold">{dados.total}</div></div>
      {dados.sem_preco.length > 0 && <div className="alert alert-warning small">Fora do custo (material sem preço): {dados.sem_preco.join(', ')}.</div>}
      <div className="fc-cartao p-0"><div className="fc-mes-rolar">
        <table className="table table-sm mb-0">
          <thead><tr><th scope="col">Material</th><th scope="col" className="text-end">Consumido</th><th scope="col" className="text-end">Lançamentos</th><th scope="col" className="text-end">Valor</th></tr></thead>
          <tbody>
            {dados.linhas.length ? dados.linhas.map((x, n) => (
              <tr key={n}><td>{x.material}</td><td className="text-end text-nowrap">{x.quantidade}</td><td className="text-end">{x.vezes}</td><td className="text-end text-nowrap">{x.valor}</td></tr>
            )) : <tr><td colSpan={4} className="fc-vazio">Nenhum consumo neste mês.</td></tr>}
          </tbody>
        </table>
      </div></div>
    </div>
  );
}

// ── Custo operacional ─────────────────────────────────────────────────────

function Somas({ titulo, id, linhas }: { titulo: string; id: string; linhas: [string, string][] }) {
  return (
    <section className="fc-cartao" aria-labelledby={id}><h2 className="h6 fw-bold" id={id}>{titulo}</h2>
      {linhas.length ? linhas.map(([k, v]) => (
        <div className="d-flex border-top py-1" key={k}><span>{k}</span><span className="ms-auto fw-semibold">{v}</span></div>
      )) : <p className="small text-muted">Nada no período.</p>}</section>
  );
}

export function Custo({ dados }: { dados: DadosDoCusto }) {
  const navegar = useNavigate();
  return (
    <div data-tela-pronta="materiais-custo">
      <Migalhas itens={[['Materiais', dados.links.catalogo], ['Custo operacional', null]]} />
      <RecadosDoEnvio />
      <h1 className="fc-titulo">Custo operacional de materiais</h1>
      <p className="fc-sub">O que foi consumido no período, pelo preço do dia de cada lançamento. É controle da operação: não substitui nem alimenta o DRE.</p>
      <form className="d-flex flex-wrap gap-2 mb-3" method="get"
        onSubmit={(ev) => { ev.preventDefault(); navegar('/materiais/custo?' + buscaDoFormulario(ev.currentTarget)); }}>
        <label className="visually-hidden" htmlFor="cde">De</label><input className="form-control w-auto" type="date" id="cde" name="de" defaultValue={dados.de} />
        <label className="visually-hidden" htmlFor="cate">Até</label><input className="form-control w-auto" type="date" id="cate" name="ate" defaultValue={dados.ate} />
        <button className="btn btn-outline-primary" type="submit">Ver</button>
      </form>
      <div className="fc-cartao py-2 px-3 mb-3 d-inline-block"><div className="small text-muted">Total de {dados.de_br} a {dados.ate_br}</div><div className="fs-4 fw-bold">{dados.total}</div></div>
      {dados.sem_preco > 0 && <div className="alert alert-warning small">{dados.sem_preco} consumo(s) de material sem preço ficaram fora do total.</div>}
      <div className="row g-3">
        <div className="col-lg-6"><Somas titulo="Por cliente" id="tit-cli" linhas={dados.clientes} /></div>
        <div className="col-lg-6"><Somas titulo="Por estado" id="tit-uf" linhas={dados.estados} /></div>
        <div className="col-12"><section className="fc-cartao" aria-labelledby="tit-loc"><h2 className="h6 fw-bold" id="tit-loc">Por local</h2>
          {dados.locais.length ? dados.locais.map((x) => (
            <Ir className="d-flex flex-wrap gap-2 border-top py-1 text-reset text-decoration-none" href={x.url} key={x.url}>
              <span>{x.nome}</span>
              <span className="small text-muted">{x.cliente} · {x.estado} · {x.consumos} lançamento(s){x.sem_preco > 0 && `, ${x.sem_preco} sem preço`}</span>
              <span className="ms-auto fw-semibold">{x.valor}</span></Ir>
          )) : <p className="small text-muted">Nada no período.</p>}</section></div>
      </div>
    </div>
  );
}

// ── Pedidos de insumo ─────────────────────────────────────────────────────

export function classeDoPedido(p: Pedido): string {
  return p.selo === 'visto' ? 'text-bg-light' : `fc-dem fc-dem-${p.selo}`;
}

export function Pedidos({ dados }: { dados: DadosDosPedidos }) {
  const { submeter, ocupado, aviso } = useFormulario();
  return (
    <div data-tela-pronta="materiais-pedidos">
      <Migalhas itens={[['Materiais', dados.links.catalogo], ['Pedidos de insumo', null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Pedidos de insumo</h1>
      <p className="fc-sub">O que o posto avisou que está faltando. A compra é feita no sistema de compras; aqui o gestor do contrato marca que viu.</p>
      <div className="fc-cartao">
        {dados.pedidos.length ? dados.pedidos.map((p) => (
          <div className="border-top py-2" key={p.id}>
            <div className="d-flex flex-wrap gap-2 align-items-center">
              <span className="fw-semibold">{p.resumo}</span>
              <span className={`badge ${classeDoPedido(p)}`}>{p.situacao_rotulo}{p.atrasado && ' · atrasado'}</span>
            </div>
            <div className="small text-muted">{p.local} · {p.pessoa} · {p.criado_em}{p.prazo && ` · prazo ${p.prazo}`}{p.quem_viu && ` · visto por ${p.quem_viu} em ${p.visto_em}`}</div>
            {p.foto && <a className="small" href={p.foto}>Ver foto</a>}
            {p.pode_marcar && (
              <form method="post" className="mt-1" onSubmit={submeter(`${API}/pedidos/${p.id}/visto`)}>
                <button className="btn btn-primary btn-sm" type="submit" disabled={ocupado}><i className="bi bi-check2"></i> Marcar como visto</button>
              </form>
            )}
          </div>
        )) : <div className="fc-vazio">Nenhum pedido de insumo.</div>}
      </div>
    </div>
  );
}
