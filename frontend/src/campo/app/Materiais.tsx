// O material no aplicativo de campo (Fase 1d; a tela antiga é
// templates/materiais/app.html, com os mesmos textos, campos e classes):
// "Usei material" e "Está faltando material". Os envios vão a
// /api/v1/campo/materiais/... e chamam a mesma ação da antiga
// (materiais.telas.acao_app_consumo e acao_app_pedido); a foto do pedido vai
// no próprio formulário. Quem consome não vê preço.
import { useEnvioDoCampo } from './comum';
import type { DadosDosMateriais } from './tipos';

const API = '/api/v1/campo/materiais';

export function Materiais({ dados }: { dados: DadosDosMateriais }) {
  const { mandar, ocupado, aviso } = useEnvioDoCampo();
  const submeter = (url: string) => (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    mandar(url, new FormData(ev.currentTarget));
  };
  return (
    <div data-tela-pronta="campo-materiais">
      {aviso}
      <h1 className="fc-titulo">Material</h1>
      <p className="fc-sub">Lance o que usou e avise o gestor do que está faltando.</p>
      {!dados.locais.length ? <div className="fc-cartao fc-vazio">Você ainda não tem local liberado.</div> : (
        <>
          <section className="fc-cartao mb-3" aria-labelledby="tit-usei">
            <h2 className="h6 fw-bold" id="tit-usei"><i className="bi bi-droplet-half" aria-hidden="true"></i> Usei material</h2>
            {!dados.materiais.length ? <p className="small text-muted mb-0">O catálogo de materiais ainda está vazio. Avise a gestão.</p> : (
              <form method="post" onSubmit={submeter(`${API}/consumo`)}>
                <label className="form-label small fw-semibold" htmlFor="cl">Local</label>
                <select className="form-select form-select-lg mb-2" id="cl" name="client_id" required>{dados.locais.map((l) => <option value={l.id} key={l.id}>{l.nome}</option>)}</select>
                <label className="form-label small fw-semibold" htmlFor="cm">Material</label>
                <select className="form-select form-select-lg mb-2" id="cm" name="material_id" required>{dados.materiais.map((m) => <option value={m.id} key={m.id}>{m.nome} ({m.unidade})</option>)}</select>
                <label className="form-label small fw-semibold" htmlFor="cq">Quantidade</label>
                <input className="form-control form-control-lg mb-2" id="cq" name="quantidade" required inputMode="decimal" placeholder="Ex.: 1,5" />
                <label className="form-label small fw-semibold" htmlFor="cc">Numa ordem de serviço (opcional)</label>
                <select className="form-select mb-2" id="cc" name="chamado_id"><option value="">—</option>{dados.chamados.map((c) => <option value={c.id} key={c.id}>{c.rotulo}</option>)}</select>
                <label className="form-label small fw-semibold" htmlFor="cr">Na rotina (opcional)</label>
                <select className="form-select mb-3" id="cr" name="rota_id"><option value="">—</option>{dados.rotas.map((r) => <option value={r.id} key={r.id}>{r.rotulo}</option>)}</select>
                <button className="btn btn-primary btn-lg w-100 fc-app-acao" type="submit" disabled={ocupado}><i className="bi bi-check-circle" aria-hidden="true"></i> Registrar consumo</button>
              </form>
            )}
          </section>
          <section className="fc-cartao mb-3" aria-labelledby="tit-falta">
            <h2 className="h6 fw-bold" id="tit-falta"><i className="bi bi-cart" aria-hidden="true"></i> Está faltando material</h2>
            <form method="post" encType="multipart/form-data" onSubmit={submeter(`${API}/pedido`)}>
              <label className="form-label small fw-semibold" htmlFor="pl">Local</label>
              <select className="form-select form-select-lg mb-2" id="pl" name="client_id" required>{dados.locais.map((l) => <option value={l.id} key={l.id}>{l.nome}</option>)}</select>
              <label className="form-label small fw-semibold" htmlFor="pm">Material (se estiver na lista)</label>
              <select className="form-select mb-2" id="pm" name="material_id"><option value="">Não está na lista</option>{dados.materiais.map((m) => <option value={m.id} key={m.id}>{m.nome} ({m.unidade})</option>)}</select>
              <label className="form-label small fw-semibold" htmlFor="pq">Quantidade (opcional)</label>
              <input className="form-control mb-2" id="pq" name="quantidade" inputMode="decimal" />
              <label className="form-label small fw-semibold" htmlFor="pt">O que precisa</label>
              <input className="form-control mb-2" id="pt" name="texto" maxLength={300} placeholder="Ex.: saco de lixo 100 L acabou" />
              <label className="form-label small fw-semibold" htmlFor="pf">Foto (opcional)</label>
              <input className="form-control mb-3" id="pf" name="foto" type="file" accept="image/*" capture="environment" />
              <button className="btn btn-outline-primary btn-lg w-100 fc-app-acao" type="submit" disabled={ocupado}><i className="bi bi-send" aria-hidden="true"></i> Avisar o gestor</button>
            </form>
            {dados.meus.length > 0 && (
              <>
                <h3 className="h6 fw-bold mt-3">Meus últimos pedidos</h3>
                {dados.meus.map((p) => <div className="fc-app-item" key={p.id}><span className="fw-semibold">{p.resumo}</span><span className="small text-muted">{p.detalhe}</span></div>)}
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
