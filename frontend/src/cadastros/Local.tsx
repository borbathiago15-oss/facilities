// A estrutura do local: setores, ambientes, equipamentos e pontos com QR
// (Fase 3a da migração para React; a tela antiga é
// templates/cadastros/local.html, com os mesmos textos, campos e classes).
// A gestão cadastra nos locais da carteira; a diretoria só consulta.
import { useLocation, useParams } from 'react-router';
import { Ir, Migalhas, Pagina, RecadosDoEnvio, useFormulario } from './comum';
import { Trilha } from './Cadastros';
import type { Ambiente, DadosDaTrilha, DadosDoLocal, Equipamento, Ponto, Setor } from './tipos';

type Ctx = {
  dados: DadosDoLocal;
  submeter: (url: string) => (ev: React.FormEvent<HTMLFormElement>) => void;
  ocupado: boolean;
};

const url = (d: DadosDoLocal, resto: string) => `/api/v1/cadastros/locais/${d.local.id}/${resto}`;

/** O que todo formulário da tela leva junto: com os desativados à mostra,
 * a volta continua mostrando (``?inativos=1``). */
function Volta({ d }: { d: DadosDoLocal }) {
  return d.com_inativos ? <input type="hidden" name="inativos" value="1" /> : null;
}

function BotaoAtivo({ c, entidade, obj }: { c: Ctx; entidade: string; obj: { id: number; ativo: boolean } }) {
  if (!c.dados.pode_alterar) return null;
  return (
    <form method="post" className="d-inline m-0" onSubmit={c.submeter(url(c.dados, `${entidade}/${obj.id}/ativo`))}>
      <Volta d={c.dados} /><input type="hidden" name="ativo" value={obj.ativo ? '0' : '1'} />
      <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={c.ocupado}>{obj.ativo ? 'Desativar' : 'Reativar'}</button>
    </form>
  );
}

function Inativo({ obj }: { obj: { ativo: boolean } }) {
  return obj.ativo ? null : <span className="badge text-bg-secondary">desativado</span>;
}

function FormAmbiente({ d, a, setor }: { d: DadosDoLocal; a: Ambiente | null; setor: Setor }) {
  const sfx = a ? String(a.id) : 'n' + setor.id;
  return (
    <div className="row g-2">
      <div className="col-md-5"><label className="form-label small fw-semibold" htmlFor={`anome${sfx}`}>Nome do ambiente</label>
        <input className="form-control" id={`anome${sfx}`} name="nome" defaultValue={a ? a.nome : ''} required maxLength={120} placeholder="Ex.: Banheiro masculino 2º andar" /></div>
      <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor={`adesc${sfx}`}>Descrição (opcional)</label>
        <input className="form-control" id={`adesc${sfx}`} name="descricao" defaultValue={a ? a.descricao : ''} maxLength={300} placeholder="Ex.: 2 mictórios, 3 vasos, 2 pias" /></div>
      <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor={`aset${sfx}`}>Setor</label>
        <select className="form-select" id={`aset${sfx}`} name="setor_id" defaultValue={String(setor.id)}>
          {d.todos_setores.map((s) => <option value={s.id} key={s.id}>{s.nome}</option>)}
        </select></div>
    </div>
  );
}

function FormEquipamento({ e, amb }: { e: Equipamento | null; amb: Ambiente }) {
  const sfx = e ? String(e.id) : 'n' + amb.id;
  return (
    <>
      <div className="row g-2">
        <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor={`enome${sfx}`}>Equipamento</label>
          <input className="form-control" id={`enome${sfx}`} name="nome" defaultValue={e ? e.nome : ''} required maxLength={120} placeholder="Ex.: Ar-condicionado split" /></div>
        <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor={`epat${sfx}`}>Patrimônio</label>
          <input className="form-control" id={`epat${sfx}`} name="patrimonio" defaultValue={e ? e.patrimonio : ''} maxLength={50} /></div>
        <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor={`efab${sfx}`}>Fabricante</label>
          <input className="form-control" id={`efab${sfx}`} name="fabricante" defaultValue={e ? e.fabricante : ''} maxLength={80} /></div>
        <div className="col-md-2"><label className="form-label small fw-semibold" htmlFor={`emod${sfx}`}>Modelo</label>
          <input className="form-control" id={`emod${sfx}`} name="modelo" defaultValue={e ? e.modelo : ''} maxLength={80} /></div>
      </div>
      {/* Só no cadastro: ao alterar, o seletor "Ambiente" manda o destino. */}
      {!e && <input type="hidden" name="ambiente_id" value={amb.id} />}
    </>
  );
}

function FormPonto({ p, amb }: { p: Ponto | null; amb: Ambiente }) {
  const sfx = p ? String(p.id) : 'n' + amb.id;
  return (
    <>
      <div className="row g-2">
        <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor={`pnome${sfx}`}>Ponto</label>
          <input className="form-control" id={`pnome${sfx}`} name="nome" defaultValue={p ? p.nome : ''} required maxLength={120} placeholder="Ex.: Porta do banheiro" /></div>
        <div className="col-md-5"><label className="form-label small fw-semibold" htmlFor={`pdesc${sfx}`}>Onde fica / o que conferir (opcional)</label>
          <input className="form-control" id={`pdesc${sfx}`} name="descricao" defaultValue={p ? p.descricao : ''} maxLength={300} /></div>
        <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor={`peq${sfx}`}>Equipamento (opcional)</label>
          <select className="form-select" id={`peq${sfx}`} name="equipamento_id" defaultValue={p && p.equipamento_id ? String(p.equipamento_id) : ''}>
            <option value="">Nenhum</option>
            {amb.equipamentos.filter((e) => e.ativo || (p && p.equipamento_id === e.id)).map((e) => (
              <option value={e.id} key={e.id}>{e.nome}</option>))}
          </select></div>
      </div>
      {!p && <input type="hidden" name="ambiente_id" value={amb.id} />}
    </>
  );
}

/** O seletor "Ambiente" de mudar o ponto ou o equipamento de lugar. */
function Mover({ d, id, atual }: { d: DadosDoLocal; id: string; atual: number }) {
  return (
    <select className="form-select" id={id} name="ambiente_id" defaultValue={String(atual)}>
      {d.todos_setores.map((s2) => s2.ambientes.map((a2) => (
        <option value={a2.id} key={a2.id}>{s2.nome} · {a2.nome}</option>)))}
    </select>
  );
}

function AmbienteDoSetor({ c, a, s }: { c: Ctx; a: Ambiente; s: Setor }) {
  const d = c.dados;
  const pontos = a.pontos.filter((p) => p.ativo || d.com_inativos);
  const equipamentos = a.equipamentos.filter((e) => e.ativo || d.com_inativos);
  return (
    <div className="border rounded p-2 mb-2">
      <div className="d-flex flex-wrap gap-2 align-items-center">
        <strong><i className="bi bi-door-open"></i> {a.nome}</strong><Inativo obj={a} />
        {a.descricao && <span className="small text-muted">{a.descricao}</span>}
        <span className="ms-auto"><BotaoAtivo c={c} entidade="ambiente" obj={a} /></span>
      </div>
      {d.pode_alterar && (
        <details className="mt-1"><summary className="small">Alterar ou mudar de setor</summary>
          <form method="post" className="mt-2" onSubmit={c.submeter(url(d, `ambiente/${a.id}`))}>
            <Volta d={d} /><FormAmbiente d={d} a={a} setor={s} />
            <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={c.ocupado}>Salvar</button>
          </form>
        </details>
      )}

      <div className="mt-2">
        <div className="small fw-semibold text-muted">Pontos com QR</div>
        {pontos.length ? pontos.map((p) => (
          <div className="d-flex flex-wrap gap-2 align-items-center border-top py-1" key={p.id}>
            <i className="bi bi-qr-code"></i> <span>{p.nome}</span><Inativo obj={p} />
            {p.equipamento && <span className="small text-muted">{p.equipamento}</span>}
            <span className="ms-auto d-flex flex-wrap gap-2">
              {p.ativo && <a className="btn btn-outline-primary btn-sm" href={`${d.links.etiquetas}?ponto=${p.id}`} target="_blank" rel="noopener">Etiqueta</a>}
              <BotaoAtivo c={c} entidade="ponto" obj={p} />
            </span>
            {d.pode_alterar && (
              <details className="w-100"><summary className="small">Alterar ou mudar de ambiente</summary>
                <form method="post" className="mt-2" onSubmit={c.submeter(url(d, `ponto/${p.id}`))}>
                  <Volta d={d} /><FormPonto p={p} amb={a} />
                  <label className="form-label small fw-semibold mt-2" htmlFor={`pmov${p.id}`}>Ambiente</label>
                  <Mover d={d} id={`pmov${p.id}`} atual={a.id} />
                  <p className="small text-muted mt-1 mb-0">O QR continua o mesmo: a etiqueta impressa segue valendo.</p>
                  <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={c.ocupado}>Salvar</button>
                </form>
              </details>
            )}
          </div>
        )) : <div className="small text-muted">Nenhum ponto ainda.</div>}
        {d.pode_alterar && a.ativo && (
          <details className="mt-1"><summary className="small fw-semibold">+ Cadastrar ponto</summary>
            <form method="post" className="mt-2" onSubmit={c.submeter(url(d, 'ponto'))}>
              <Volta d={d} /><FormPonto p={null} amb={a} />
              <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={c.ocupado}>Cadastrar ponto</button>
            </form>
          </details>
        )}
      </div>

      <div className="mt-2">
        <div className="small fw-semibold text-muted">Equipamentos</div>
        {equipamentos.length ? equipamentos.map((e) => (
          <div className="d-flex flex-wrap gap-2 align-items-center border-top py-1" key={e.id}>
            <i className="bi bi-gear"></i> <span>{e.nome}</span><Inativo obj={e} />
            {e.patrimonio && <span className="small text-muted">patrimônio {e.patrimonio}</span>}
            <span className="ms-auto"><BotaoAtivo c={c} entidade="equipamento" obj={e} /></span>
            {d.pode_alterar && (
              <details className="w-100"><summary className="small">Alterar ou mudar de ambiente</summary>
                <form method="post" className="mt-2" onSubmit={c.submeter(url(d, `equipamento/${e.id}`))}>
                  <Volta d={d} /><FormEquipamento e={e} amb={a} />
                  <label className="form-label small fw-semibold mt-2" htmlFor={`emov${e.id}`}>Ambiente</label>
                  <Mover d={d} id={`emov${e.id}`} atual={a.id} />
                  <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={c.ocupado}>Salvar</button>
                </form>
              </details>
            )}
          </div>
        )) : <div className="small text-muted">Nenhum equipamento.</div>}
        {d.pode_alterar && a.ativo && (
          <details className="mt-1"><summary className="small fw-semibold">+ Cadastrar equipamento</summary>
            <form method="post" className="mt-2" onSubmit={c.submeter(url(d, 'equipamento'))}>
              <Volta d={d} /><FormEquipamento e={null} amb={a} />
              <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={c.ocupado}>Cadastrar equipamento</button>
            </form>
          </details>
        )}
      </div>
    </div>
  );
}

export function Local({ dados: d }: { dados: DadosDoLocal }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const c: Ctx = { dados: d, submeter, ocupado };
  const loc = d.local;
  return (
    <div data-tela-pronta="local">
      <Migalhas itens={[['Cadastros', '/novo/cadastros/'], [loc.nome, null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">{loc.nome}</h1>
      <p className="fc-sub">
        {loc.cliente ? `Cliente ${loc.cliente}` : 'Sem cliente ligado'}
        {loc.estado && ` · ${loc.estado}`}
        {loc.subcentro && ` · subcentro ${loc.subcentro}`}
      </p>

      <div className="d-flex flex-wrap gap-2 mb-3">
        <a className="btn btn-outline-primary btn-sm" href={d.links.etiquetas} target="_blank" rel="noopener"><i className="bi bi-qr-code"></i> Imprimir as etiquetas de QR</a>
        <Ir className="btn btn-outline-secondary btn-sm" href={`/novo/cadastros/locais/${loc.id}/trilha`}><i className="bi bi-clock-history"></i> Histórico</Ir>
        {d.com_inativos
          ? <Ir className="btn btn-outline-secondary btn-sm" href={`/novo/cadastros/locais/${loc.id}`}>Esconder os desativados</Ir>
          : <Ir className="btn btn-outline-secondary btn-sm" href={`/novo/cadastros/locais/${loc.id}?inativos=1`}>Mostrar os desativados</Ir>}
      </div>

      {d.pode_alterar && (
        <details className="fc-cartao mb-3" open={!d.setores.length}>
          <summary className="fw-bold">Cadastrar setor</summary>
          <form method="post" className="mt-3 d-flex flex-wrap gap-2 align-items-end" onSubmit={submeter(url(d, 'setor'))}>
            <Volta d={d} />
            <div className="flex-grow-1"><label className="form-label small fw-semibold" htmlFor="snovo">Nome do setor</label>
              <input className="form-control" id="snovo" name="nome" required maxLength={120} placeholder="Ex.: Administrativo, Armazém 1, Área externa" /></div>
            <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Cadastrar</button>
          </form>
        </details>
      )}

      {d.setores.length ? d.setores.map((s) => {
        const ambientes = s.ambientes.filter((a) => a.ativo || d.com_inativos);
        return (
          <section className="fc-cartao mb-3" aria-labelledby={`setor${s.id}`} key={s.id}>
            <div className="d-flex flex-wrap gap-2 align-items-center mb-2">
              <h2 className="h5 fw-bold m-0" id={`setor${s.id}`}><i className="bi bi-diagram-3"></i> {s.nome}</h2><Inativo obj={s} />
              <span className="ms-auto d-flex gap-2"><BotaoAtivo c={c} entidade="setor" obj={s} /></span>
            </div>
            {d.pode_alterar && (
              <details className="mb-2"><summary className="small">Renomear o setor</summary>
                <form method="post" className="d-flex gap-2 mt-2" onSubmit={submeter(url(d, `setor/${s.id}`))}>
                  <Volta d={d} /><label className="visually-hidden" htmlFor={`sren${s.id}`}>Nome do setor</label>
                  <input className="form-control" id={`sren${s.id}`} name="nome" defaultValue={s.nome} required maxLength={120} />
                  <button className="btn btn-primary btn-sm fw-bold" type="submit" disabled={ocupado}>Salvar</button>
                </form>
              </details>
            )}

            {ambientes.length
              ? ambientes.map((a) => <AmbienteDoSetor c={c} a={a} s={s} key={a.id} />)
              : <p className="small text-muted mb-2">Nenhum ambiente neste setor ainda.</p>}

            {d.pode_alterar && s.ativo && (
              <details><summary className="small fw-semibold">+ Cadastrar ambiente neste setor</summary>
                <form method="post" className="mt-2" onSubmit={submeter(url(d, 'ambiente'))}>
                  <Volta d={d} /><FormAmbiente d={d} a={null} setor={s} />
                  <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={ocupado}>Cadastrar ambiente</button>
                </form>
              </details>
            )}
          </section>
        );
      }) : (
        <div className="fc-cartao fc-vazio">Nenhum setor ainda. {d.pode_alterar && 'Comece cadastrando os setores do local (ex.: Administrativo, Armazém 1).'}</div>
      )}
    </div>
  );
}

export function PaginaLocal() {
  const { id } = useParams();
  const { search } = useLocation();
  const inativos = new URLSearchParams(search).get('inativos') === '1' ? '?inativos=1' : '';
  return <Pagina<DadosDoLocal> api={`/cadastros/locais/${id}${inativos}`}>{(d) => <Local dados={d} />}</Pagina>;
}

export function PaginaTrilhaDoLocal() {
  const { id } = useParams();
  return <Pagina<DadosDaTrilha> api={`/cadastros/locais/${id}/trilha`}>{(d) => <Trilha dados={d} />}</Pagina>;
}
