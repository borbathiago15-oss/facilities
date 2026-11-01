// Os cadastros do grupo (Fase 3a da migração para React; as telas antigas
// são templates/cadastros/inicio.html, empresas.html, clientes.html,
// estados.html e trilha.html, com os mesmos textos, campos e classes).
// Empresas, clientes, estados e o histórico do grupo: só o administrador.
import { useLocation, useNavigate } from 'react-router';
import { Ir, Migalhas, Pagina, RecadosDoEnvio, useFormulario } from './comum';
import { mudanca } from './regras';
import type {
  Cliente, DadosDaTrilha, DadosDasEmpresas, DadosDoInicio, DadosDosClientes, DadosDosEstados, Empresa,
} from './tipos';

const API = '/api/v1/cadastros';

// ── Início ────────────────────────────────────────────────────────────────

export function Inicio({ dados }: { dados: DadosDoInicio }) {
  return (
    <div data-tela-pronta="cadastros">
      <RecadosDoEnvio />
      <h1 className="fc-titulo">Cadastros</h1>
      <p className="fc-sub">A estrutura de cada cliente: empresa do grupo, cliente, locais e, dentro de cada local, setores, ambientes, equipamentos e pontos com QR.</p>

      {dados.pode_novo_contrato && (
        <div className="fc-cartao mb-3 d-flex flex-wrap align-items-center gap-2">
          <div><strong>Vai começar um contrato novo?</strong><br /><span className="small text-muted">O assistente leva do cliente à equipe convidada, passo a passo.</span></div>
          <Ir className="btn btn-primary fw-bold ms-auto" href="/novo/novo-contrato"><i className="bi bi-magic" aria-hidden="true"></i> Novo contrato</Ir>
        </div>
      )}

      {dados.e_admin && (
        <div className="fc-modulos mb-3">
          <Ir className="fc-cartao fc-modulo" href="/novo/cadastros/empresas">
            <i className="bi bi-buildings"></i><h2>Empresas do grupo</h2>
            <p>{dados.n_empresas} cadastrada(s). A empresa do Grupo Trino que atende cada cliente.</p>
          </Ir>
          <Ir className="fc-cartao fc-modulo" href="/novo/cadastros/clientes">
            <i className="bi bi-briefcase"></i><h2>Clientes</h2>
            <p>{dados.n_clientes} cadastrado(s). Quem contrata, com o gerente responsável e o centro de custo.</p>
          </Ir>
          <a className="fc-cartao fc-modulo" href={dados.links.locais_admin}>
            <i className="bi bi-geo-alt"></i><h2>Locais</h2>
            <p>Cada armazém, loja ou sede do cliente, com o estado e o subcentro de custo.</p>
          </a>
          <Ir className="fc-cartao fc-modulo" href="/novo/cadastros/estados">
            <i className="bi bi-map"></i><h2>Estados</h2>
            <p>{dados.n_estados} em uso. Ative os estados onde há operação.</p>
          </Ir>
          <Ir className="fc-cartao fc-modulo" href="/novo/cadastros/trilha">
            <i className="bi bi-clock-history"></i><h2>Histórico de alterações</h2>
            <p>Quem cadastrou ou mudou o quê, e quando.</p>
          </Ir>
        </div>
      )}

      <div className="fc-cartao p-0">
        <div className="px-3 pt-3"><h2 className="h6 fw-bold">Estrutura dos locais</h2>
          <p className="small text-muted mb-2">Abra um local para cadastrar setores, ambientes, equipamentos e pontos, e imprimir as etiquetas de QR.</p></div>
        {dados.locais.length ? dados.locais.map((l) => (
          <Ir className="d-flex flex-wrap gap-2 align-items-center border-top px-3 py-2 text-reset text-decoration-none"
            href={`/novo/cadastros/locais/${l.id}`} key={l.id}>
            <strong>{l.nome}</strong>
            {l.cliente && <span className="small text-muted">{l.cliente}</span>}
            {l.estado && <span className="badge text-bg-light">{l.estado}</span>}
            <i className="bi bi-chevron-right ms-auto"></i>
          </Ir>
        )) : <div className="fc-vazio">Nenhum local na sua carteira.</div>}
      </div>
    </div>
  );
}

export function PaginaInicio() {
  return <Pagina<DadosDoInicio> api="/cadastros/inicio">{(d) => <Inicio dados={d} />}</Pagina>;
}

// ── Empresas ──────────────────────────────────────────────────────────────

function CamposDaEmpresa({ e }: { e: Empresa | null }) {
  const sfx = e ? e.id : '';
  return (
    <div className="row g-2">
      <div className="col-md-8"><label className="form-label small fw-semibold" htmlFor={`enome${sfx}`}>Nome da empresa</label>
        <input className="form-control" id={`enome${sfx}`} name="nome" defaultValue={e ? e.nome : ''} required maxLength={120} placeholder="Ex.: Trino Serviços Ltda." /></div>
      <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor={`ecnpj${sfx}`}>CNPJ (opcional)</label>
        <input className="form-control" id={`ecnpj${sfx}`} name="cnpj" defaultValue={e ? e.cnpj : ''} maxLength={18} inputMode="numeric" /></div>
    </div>
  );
}

export function Empresas({ dados }: { dados: DadosDasEmpresas }) {
  const { submeter, ocupado, aviso } = useFormulario();
  return (
    <div data-tela-pronta="empresas">
      <Migalhas itens={[['Cadastros', '/novo/cadastros/'], ['Empresas', null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Empresas do grupo</h1>
      <p className="fc-sub">As empresas do Grupo Trino. Cada cliente é atendido por uma delas.</p>

      <details className="fc-cartao mb-3" open={!dados.empresas.length}>
        <summary className="fw-bold">Cadastrar empresa</summary>
        <form method="post" className="mt-3" onSubmit={submeter(`${API}/empresas`)}>
          <CamposDaEmpresa e={null} />
          <button className="btn btn-primary fw-bold mt-3" type="submit" disabled={ocupado}>Cadastrar</button>
        </form>
      </details>

      <div className="fc-cartao p-0">
        {dados.empresas.length ? dados.empresas.map((e) => (
          <details className="border-bottom px-3 py-2" key={e.id}>
            <summary className="d-flex flex-wrap gap-2 align-items-center">
              <strong>{e.nome}</strong>
              {e.cnpj && <span className="small text-muted">CNPJ {e.cnpj}</span>}
              {!e.ativo && <span className="badge text-bg-secondary">desativada</span>}
            </summary>
            <form method="post" className="mt-3 mb-2" onSubmit={submeter(`${API}/empresas/${e.id}`)}>
              <CamposDaEmpresa e={e} />
              <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={ocupado}>Salvar</button>
            </form>
            <form method="post" className="mb-2" onSubmit={submeter(`${API}/empresas/${e.id}/ativo`)}>
              <input type="hidden" name="ativo" value={e.ativo ? '0' : '1'} />
              <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={ocupado}>{e.ativo ? 'Desativar' : 'Reativar'}</button>
            </form>
          </details>
        )) : <div className="fc-vazio">Nenhuma empresa ainda. Comece por aqui: o cliente precisa de uma empresa.</div>}
      </div>
    </div>
  );
}

export function PaginaEmpresas() {
  return <Pagina<DadosDasEmpresas> api="/cadastros/empresas">{(d) => <Empresas dados={d} />}</Pagina>;
}

// ── Estados ───────────────────────────────────────────────────────────────

export function Estados({ dados }: { dados: DadosDosEstados }) {
  const { submeter, ocupado, aviso } = useFormulario();
  return (
    <div data-tela-pronta="estados">
      <Migalhas itens={[['Cadastros', '/novo/cadastros/'], ['Estados', null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Estados</h1>
      <p className="fc-sub">Os 27 estados já vêm na lista. Ative os estados onde há operação: só eles aparecem no cadastro do local.</p>
      <div className="fc-cartao p-0">
        {dados.estados.map((e) => (
          <form method="post" className="d-flex align-items-center gap-2 border-bottom px-3 py-2 m-0" key={e.id}
            onSubmit={submeter(`${API}/estados/${e.id}/ativo`)}>
            <input type="hidden" name="ativo" value={e.ativo ? '0' : '1'} />
            <span className="fw-semibold">{e.nome}</span><span className="small text-muted">{e.sigla}</span>
            {e.ativo && <span className="badge text-bg-success">em uso</span>}
            <button className={`btn btn-sm ms-auto ${e.ativo ? 'btn-outline-secondary' : 'btn-outline-primary'}`} type="submit"
              disabled={ocupado}>{e.ativo ? 'Desativar' : 'Ativar'}</button>
          </form>
        ))}
      </div>
    </div>
  );
}

export function PaginaEstados() {
  return <Pagina<DadosDosEstados> api="/cadastros/estados">{(d) => <Estados dados={d} />}</Pagina>;
}

// ── Clientes ──────────────────────────────────────────────────────────────

function CamposDoCliente({ c, dados }: { c: Cliente | null; dados: DadosDosClientes }) {
  const sfx = c ? String(c.id) : 'novo';
  const regua = c ? c.regua : {};
  const prazos = c ? c.prazos : {};
  return (
    <div className="row g-2">
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`cnome${sfx}`}>Nome do cliente</label>
        <input className="form-control" id={`cnome${sfx}`} name="nome" defaultValue={c ? c.nome : ''} required maxLength={120} placeholder="Ex.: Grupo GL" /></div>
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`cemp${sfx}`}>Empresa do grupo que atende</label>
        <select className="form-select" id={`cemp${sfx}`} name="empresa_id" required defaultValue={c ? String(c.empresa_id) : ''}>
          <option value="">Escolha</option>
          {dados.empresas.filter((e) => e.ativo || (c && c.empresa_id === e.id)).map((e) => (
            <option value={e.id} key={e.id}>{e.nome}</option>))}
        </select></div>
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`ccc${sfx}`}>Centro de custo (pai)</label>
        <input className="form-control" id={`ccc${sfx}`} name="centro_custo" defaultValue={c ? c.centro_custo : ''} maxLength={50} placeholder="Ex.: GL" /></div>
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`cger${sfx}`}>Gerente responsável</label>
        <select className="form-select" id={`cger${sfx}`} name="gerente_id" defaultValue={c && c.gerente_id ? String(c.gerente_id) : ''}>
          <option value="">Sem gerente ainda</option>
          {dados.gerentes.map((g) => <option value={g.id} key={g.id}>{g.nome}</option>)}
        </select></div>
      <details className="col-12"><summary className="small fw-semibold">Prazo dos chamados deste cliente (horas)</summary>
        <p className="form-text">Vazio = a régua padrão. Vale para os chamados abertos daqui em diante; o prazo de quem já abriu não muda.</p>
        <div className="row g-2">
          {dados.prioridades.map(([k, v]) => (
            <div className="col-6 col-md-3" key={k}><label className="form-label small" htmlFor={`rg${sfx}${k}`}>{v} (padrão {dados.regua_padrao[k]} h)</label>
              <input className="form-control form-control-sm" id={`rg${sfx}${k}`} name={`regua_${k}`} type="number" min={1} max={2160}
                defaultValue={regua[k] ?? ''} /></div>
          ))}
        </div>
      </details>
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`ppi${sfx}`}>Prazo do pedido de insumo (horas)</label>
        <input className="form-control" id={`ppi${sfx}`} name="prazo_pedido_insumo_horas" type="number" min={1} max={720}
          defaultValue={c && c.prazo_pedido_insumo_horas ? c.prazo_pedido_insumo_horas : ''} placeholder="Vazio = 48 h" /></div>
      <div className="col-12"><div className="form-check">
        <input className="form-check-input" type="checkbox" id={`mne${sfx}`} name="mostrar_nome_executor" value="1"
          defaultChecked={!!(c && c.mostrar_nome_executor)} disabled={!dados.pode_mostrar_nome} />
        <label className="form-check-label small fw-semibold" htmlFor={`mne${sfx}`}>No portal do cliente, mostrar o nome de quem fez o checklist</label>
        <div className="form-text">Desligado, o cliente vê só a função (ex.: Encarregado / ASG). Só o administrador muda, e só depois do aval do jurídico.</div>
      </div></div>
      <details className="col-12"><summary className="small fw-semibold">Prazo de atendimento das ocorrências do QR público (minutos)</summary>
        <p className="form-text">Vazio = sem prazo. O prazo conta da hora em que a pessoa enviou o aviso.</p>
        <div className="row g-2">
          {dados.tipos_ocorrencia.map(([k, v]) => (
            <div className="col-6 col-md-3" key={k}><label className="form-label small" htmlFor={`pz${sfx}${k}`}>{v}</label>
              <input className="form-control form-control-sm" id={`pz${sfx}${k}`} name={`prazo_${k}`} type="number" min={5} max={10080}
                defaultValue={prazos[k] ?? ''} /></div>
          ))}
        </div>
      </details>
    </div>
  );
}

export function Clientes({ dados }: { dados: DadosDosClientes }) {
  const { submeter, ocupado, aviso } = useFormulario();
  return (
    <div data-tela-pronta="clientes">
      <Migalhas itens={[['Cadastros', '/novo/cadastros/'], ['Clientes', null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Clientes</h1>
      <p className="fc-sub">Quem contrata a Trino. Um cliente pode ter vários locais, em estados diferentes; cada local tem o seu subcentro de custo.</p>

      {!dados.empresas.length ? (
        <div className="alert alert-warning">Cadastre antes a <Ir href="/novo/cadastros/empresas">empresa do grupo</Ir> que atende o cliente.</div>
      ) : (
        <details className="fc-cartao mb-3" open={!dados.clientes.length}>
          <summary className="fw-bold">Cadastrar cliente</summary>
          <form method="post" className="mt-3" onSubmit={submeter(`${API}/clientes`)}>
            <CamposDoCliente c={null} dados={dados} />
            <button className="btn btn-primary fw-bold mt-3" type="submit" disabled={ocupado}>Cadastrar</button>
          </form>
        </details>
      )}

      <div className="fc-cartao p-0">
        {dados.clientes.length ? dados.clientes.map((c) => (
          <details className="border-bottom px-3 py-2" key={c.id}>
            <summary className="d-flex flex-wrap gap-2 align-items-center">
              <strong>{c.nome}</strong>
              {c.centro_custo && <span className="small text-muted">CC {c.centro_custo}</span>}
              <span className="small text-muted">{c.locais.length} local(is)</span>
              {!c.ativo && <span className="badge text-bg-secondary">desativado</span>}
              <span className="small text-muted ms-auto">{c.gerente || 'sem gerente'}</span>
            </summary>
            <form method="post" className="mt-3 mb-2" onSubmit={submeter(`${API}/clientes/${c.id}`)}>
              <CamposDoCliente c={c} dados={dados} />
              <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={ocupado}>Salvar</button>
            </form>
            {c.locais.length > 0 && (
              <p className="small mb-2">Locais: {c.locais.map((l, n) => (
                <span key={l.id}><Ir href={`/novo/cadastros/locais/${l.id}`}>{l.nome}</Ir>{l.estado && ` (${l.estado})`}{n < c.locais.length - 1 && ', '}</span>
              ))}</p>
            )}
            <form method="post" className="mb-2" onSubmit={submeter(`${API}/clientes/${c.id}/ativo`)}>
              <input type="hidden" name="ativo" value={c.ativo ? '0' : '1'} />
              <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={ocupado}>{c.ativo ? 'Desativar' : 'Reativar'}</button>
            </form>
          </details>
        )) : <div className="fc-vazio">Nenhum cliente ainda.</div>}
      </div>
    </div>
  );
}

export function PaginaClientes() {
  return <Pagina<DadosDosClientes> api="/cadastros/clientes">{(d) => <Clientes dados={d} />}</Pagina>;
}

// ── Histórico de alterações ───────────────────────────────────────────────

export function Trilha({ dados }: { dados: DadosDaTrilha }) {
  const navegar = useNavigate();
  const local = dados.local;
  const filtrar = (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    const v = new FormData(ev.currentTarget).get('entidade') || '';
    navegar({ search: '?entidade=' + encodeURIComponent(String(v)) });
  };
  return (
    <div data-tela-pronta="trilha">
      <Migalhas itens={[['Cadastros', '/novo/cadastros/'],
        ...(local ? [[local.nome, `/novo/cadastros/locais/${local.id}`] as [string, string]] : []),
        ['Histórico', null]]} />
      <RecadosDoEnvio />
      <h1 className="fc-titulo">Histórico de alterações{local && ` — ${local.nome}`}</h1>
      <p className="fc-sub">Cada cadastro, alteração, desativação e mudança de lugar, com quem fez e quando. Este histórico não se edita nem se apaga.</p>
      {!local && (
        <form method="get" className="d-flex gap-2 mb-3" onSubmit={filtrar}>
          <label className="visually-hidden" htmlFor="fent">Tipo de cadastro</label>
          <select className="form-select w-auto" id="fent" name="entidade" defaultValue={dados.entidade || ''}>
            <option value="">Todos os cadastros</option>
            {dados.entidades.map(([k, v]) => <option value={k} key={k}>{v}</option>)}
          </select>
          <button className="btn btn-outline-primary" type="submit">Filtrar</button>
        </form>
      )}
      <div className="fc-cartao p-0">
        {dados.eventos.length ? dados.eventos.map((ev) => (
          <div className="border-bottom px-3 py-2" key={ev.id}>
            <div className="d-flex flex-wrap gap-2 align-items-center">
              <span className="badge text-bg-light">{ev.entidade}</span>
              <strong>{ev.acao}</strong>
              <span className="small text-muted">#{ev.entidade_id}</span>
              <span className="small text-muted ms-auto">{ev.quando} · {ev.autor}</span>
            </div>
            {ev.mudancas.length > 0 && (
              <ul className="small mb-0 mt-1">
                {ev.mudancas.map(([campo, antes, depois], n) => (
                  <li key={n}><code>{campo}</code>: {mudanca(ev.com_antes, antes, depois)}</li>
                ))}
              </ul>
            )}
          </div>
        )) : <div className="fc-vazio">Nenhuma alteração registrada ainda.</div>}
      </div>
    </div>
  );
}

export function PaginaTrilha() {
  const { search } = useLocation();
  return <Pagina<DadosDaTrilha> api={'/cadastros/trilha' + search}>{(d) => <Trilha dados={d} />}</Pagina>;
}
