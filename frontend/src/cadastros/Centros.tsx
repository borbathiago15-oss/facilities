// O cadastro simplificado: Cliente › Centro de custo › Áreas › Rotas (Fase 3a
// da migração para React; as telas antigas são templates/cadastros/centros/
// clientes.html, cliente.html, centro.html e rota.html + static/js/
// posicao-local.js, com os mesmos textos, campos e classes). Por baixo são os
// mesmos locais, pontos e rotas da tela completa.
import { useRef, useState } from 'react';
import { useLocation, useParams } from 'react-router';
import { Ir, Migalhas, Pagina, RecadosDoEnvio, tresDigitos, useFormulario } from './comum';
import { erroDoGps } from './regras';
import type { DadosDaRota, DadosDoCentro, DadosDoCentrosCliente, DadosDosCentrosClientes } from './tipos';

const API = '/api/v1/cadastros/centros';

// ── Clientes, áreas e rotas ───────────────────────────────────────────────

export function CentrosClientes({ dados }: { dados: DadosDosCentrosClientes }) {
  return (
    <div data-tela-pronta="centros-clientes">
      <RecadosDoEnvio />
      <h1 className="fc-titulo">Clientes, áreas e rotas</h1>
      <p className="fc-sub">Escolha o cliente, depois o centro de custo. Lá dentro você cadastra as áreas (cada uma ganha um QR) e as rotas de limpeza.</p>
      {dados.pode_criar && <Ir className="btn btn-outline-primary mb-3" href="/novo/novo-contrato"><i className="bi bi-plus-lg" aria-hidden="true"></i> Novo cliente</Ir>}
      {dados.clientes.length ? dados.clientes.map((c) => (
        <section className="fc-cartao mb-3" aria-labelledby={`cli${c.id}`} key={c.id}>
          <div className="d-flex flex-wrap align-items-center gap-2 mb-2">
            <h2 className="h5 fw-bold mb-0" id={`cli${c.id}`}>{c.nome}</h2>
            <Ir className="btn btn-sm btn-primary ms-auto" href={`/novo/clientes/${c.id}`}>Abrir o cliente</Ir>
          </div>
          {c.centros.length ? c.centros.map((loc) => (
            <Ir className="fc-app-item text-reset text-decoration-none" href={`/novo/centros/${loc.id}`} key={loc.id}>
              <span className="fw-semibold">{loc.nome}</span>
              <span className="small text-muted">Centro de custo{loc.centro_custo && ` ${loc.centro_custo}`}</span>
            </Ir>
          )) : <p className="small text-muted mb-0">Nenhum centro de custo ainda. Abra o cliente para cadastrar o primeiro.</p>}
        </section>
      )) : (
        <div className="fc-cartao fc-vazio">Nenhum cliente na sua carteira.{dados.pode_criar && ' Comece por "Novo cliente".'}</div>
      )}
    </div>
  );
}

export function PaginaCentrosClientes() {
  return <Pagina<DadosDosCentrosClientes> api="/cadastros/centros/clientes">{(d) => <CentrosClientes dados={d} />}</Pagina>;
}

// ── O cliente: os centros de custo ────────────────────────────────────────

export function CentrosCliente({ dados }: { dados: DadosDoCentrosCliente }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const cli = dados.cliente;
  return (
    <div data-tela-pronta="centros-cliente">
      <Migalhas itens={[['Clientes', '/novo/clientes'], [cli.nome, null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">{cli.nome}</h1>
      <p className="fc-sub">Os centros de custo deste cliente. Em cada um você cadastra as áreas e as rotas.</p>
      <div className="fc-cartao p-0 mb-3">
        {dados.centros.length ? dados.centros.map((loc) => (
          <Ir className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2 text-reset text-decoration-none"
            href={`/novo/centros/${loc.id}`} key={loc.id}>
            <span className="fw-semibold">{loc.nome}</span>
            {loc.centro_custo && <span className="small text-muted">CC {loc.centro_custo}</span>}
            <span className="small ms-auto">{loc.areas} área(s) · {loc.rotas} rota(s)</span>
          </Ir>
        )) : <div className="fc-vazio">Nenhum centro de custo ainda. Cadastre o primeiro abaixo.</div>}
      </div>
      <details className="fc-cartao" open={!dados.centros.length}>
        <summary className="fw-bold"><i className="bi bi-plus-lg" aria-hidden="true"></i> Novo centro de custo</summary>
        <form method="post" className="mt-3" onSubmit={submeter(`${API}/clientes/${cli.id}/centros`)}>
          <div className="row g-2">
            <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor="name">Nome</label>
              <input className="form-control" id="name" name="name" required maxLength={120} placeholder={`Ex.: ${cli.nome} — Armazém 1`} /></div>
            <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor="cost_center">Código do centro de custo</label>
              <input className="form-control" id="cost_center" name="cost_center" maxLength={50} /></div>
            <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor="estado_id">Estado</label>
              <select className="form-select" id="estado_id" name="estado_id" required defaultValue="">
                <option value="">Escolha</option>
                {dados.estados.map((e) => <option value={e.id} key={e.id}>{e.nome}</option>)}
              </select></div>
            <div className="col-12"><label className="form-label small fw-semibold" htmlFor="endereco">Endereço (opcional)</label>
              <input className="form-control" id="endereco" name="endereco" maxLength={255} /></div>
          </div>
          <button className="btn btn-primary fw-bold mt-3" type="submit" disabled={ocupado}>Criar e cadastrar as áreas</button>
        </form>
      </details>
    </div>
  );
}

export function PaginaCentrosCliente() {
  const { id } = useParams();
  return <Pagina<DadosDoCentrosCliente> api={`/cadastros/centros/clientes/${id}`}>{(d) => <CentrosCliente dados={d} />}</Pagina>;
}

// ── O centro de custo: áreas e rotas ──────────────────────────────────────

const DIAS: [string, string][] = [['1', 'seg'], ['2', 'ter'], ['3', 'qua'], ['4', 'qui'], ['5', 'sex'], ['6', 'sáb'], ['7', 'dom']];

/** Posição do local (GPS na leitura do QR): a gestão, DENTRO do local, toca
 * no botão; o celular dá a posição e o formulário vai com ela. Sem
 * permissão ou sem GPS, diz o que fazer. */
function Posicao({ dados, enviar }: { dados: DadosDoCentro; enviar: (form: HTMLFormElement) => void }) {
  const form = useRef<HTMLFormElement>(null);
  const [estado, setEstado] = useState('');
  const [pegando, setPegando] = useState(false);
  const loc = dados.local;
  const marcar = () => {
    if (!navigator.geolocation) { setEstado('Este aparelho não informa a localização.'); return; }
    setPegando(true);
    setEstado('Pegando a posição do celular…');
    navigator.geolocation.getCurrentPosition((pos) => {
      const f = form.current!;
      const precisao = Math.round(pos.coords.accuracy || 0);
      f.querySelector<HTMLInputElement>('[name=lat]')!.value = String(pos.coords.latitude);
      f.querySelector<HTMLInputElement>('[name=lng]')!.value = String(pos.coords.longitude);
      f.querySelector<HTMLInputElement>('[name=precisao]')!.value = String(precisao);
      setEstado('Posição encontrada (precisão de ' + precisao + ' m). Salvando…');
      enviar(f);
    }, (e) => {
      setPegando(false);
      setEstado(erroDoGps(e && e.code));
    }, { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 });
  };
  return (
    <section className="fc-cartao mb-3" aria-labelledby="tit-posicao">
      <h2 className="h6 fw-bold" id="tit-posicao"><i className="bi bi-geo-alt" aria-hidden="true"></i> Posição do local (GPS)</h2>
      {loc.marcada
        ? <p className="small mb-2">Marcada em {loc.marcada_em}. Leitura de QR a mais de <strong>{dados.raio} m</strong> daqui fica marcada "fora do local" e avisa o supervisor.</p>
        : <p className="small mb-2">Ainda não marcada. Esteja <strong>dentro do local</strong>, com a localização do celular ligada, e toque no botão: as leituras de QR longe daqui passam a ficar marcadas "fora do local".</p>}
      <form method="post" className="d-flex flex-wrap gap-2 align-items-end m-0" data-form-posicao ref={form}
        onSubmit={(ev) => ev.preventDefault()}>
        <input type="hidden" name="lat" /><input type="hidden" name="lng" /><input type="hidden" name="precisao" />
        <div><label className="form-label small fw-semibold mb-1" htmlFor="raio">Raio (metros)</label>
          <input className="form-control" id="raio" name="raio" type="number" min={50} max={5000} step={10} defaultValue={dados.raio} /></div>
        <button className="btn btn-outline-primary" type="button" data-marcar-posicao disabled={pegando} onClick={marcar}>
          <i className="bi bi-crosshair" aria-hidden="true"></i> {loc.marcada ? 'Marcar de novo' : 'Marcar a posição deste local'}</button>
      </form>
      <p className="small text-muted mt-2 mb-0" data-posicao-estado role="status">{estado}</p>
    </section>
  );
}

export function Centro({ dados }: { dados: DadosDoCentro }) {
  const { submeter, enviarFormulario, ocupado, aviso } = useFormulario();
  const loc = dados.local;
  const rotasAtivas = dados.rotas.filter((r) => r.ativa).length;
  const naRota = dados.aba === 'rotas';
  const enviarPosicao = (f: HTMLFormElement) => enviarFormulario(`${API}/${loc.id}/posicao`, f);
  return (
    <div data-tela-pronta="centro">
      <Migalhas itens={[['Clientes', '/novo/clientes'],
        ...(loc.cliente ? [[loc.cliente.nome, `/novo/clientes/${loc.cliente.id}`] as [string, string]] : []),
        [loc.nome, null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">{loc.nome}</h1>
      <p className="fc-sub">Centro de custo{loc.centro_custo && ` ${loc.centro_custo}`}. Primeiro as áreas, depois as rotas.</p>
      <ul className="nav nav-tabs mb-3">
        <li className="nav-item"><Ir className={`nav-link${!naRota ? ' active' : ''}`} aria-current={!naRota ? 'page' : undefined}
          href={`/novo/centros/${loc.id}`}>1. Áreas ({dados.areas.length})</Ir></li>
        <li className="nav-item"><Ir className={`nav-link${naRota ? ' active' : ''}`} aria-current={naRota ? 'page' : undefined}
          href={`/novo/centros/${loc.id}?aba=rotas`}>2. Rotas ({rotasAtivas})</Ir></li>
      </ul>

      {!naRota ? (
        <>
          <Posicao dados={dados} enviar={enviarPosicao} />
          <div className="fc-cartao p-0 mb-3">
            {dados.areas.length ? dados.areas.map((p) => (
              <div className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2" key={p.id}>
                <span className="badge text-bg-light">QR {tresDigitos(p.numero)}</span>
                <span className="fw-semibold">{p.nome}</span>
                {p.entrada && <span className="badge text-bg-info">Entrada</span>}
                <form method="post" className="d-flex gap-1 ms-auto m-0" onSubmit={submeter(`${API}/${loc.id}/areas/${p.id}/checklist`)}>
                  <label className="visually-hidden" htmlFor={`ck${p.id}`}>Checklist de {p.nome}</label>
                  <select className="form-select form-select-sm" id={`ck${p.id}`} name="checklist_id" defaultValue={p.checklist_id ? String(p.checklist_id) : ''}>
                    {!p.checklist_id && <option value="">Sem checklist</option>}
                    {dados.checklists.map((m) => <option value={m.id} key={m.id}>{m.nome}</option>)}
                  </select>
                  <button className="btn btn-sm btn-outline-primary" type="submit" disabled={ocupado}>Trocar</button>
                </form>
              </div>
            )) : <div className="fc-vazio">Nenhuma área ainda. Escreva abaixo, uma por linha.</div>}
          </div>
          <section className="fc-cartao mb-3" aria-labelledby="tit-novas">
            <h2 className="h6 fw-bold" id="tit-novas">Novas áreas</h2>
            <form method="post" onSubmit={submeter(`${API}/${loc.id}/areas`)}>
              <label className="form-label small" htmlFor="areas">Uma área por linha. Cada uma ganha um QR e o checklist que combina com o nome (banheiro, copa, vestiário, recepção…), que você troca na lista acima.</label>
              <textarea className="form-control mb-2" id="areas" name="areas" rows={6} placeholder={'Banheiro 01\nBanheiro 02\nRecepção\nCopa'}></textarea>
              <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Cadastrar as áreas</button>
            </form>
          </section>
          <div className="d-flex flex-wrap gap-2">
            {dados.areas.length > 0 && <a className="btn btn-outline-secondary" href={dados.links.etiquetas}><i className="bi bi-printer" aria-hidden="true"></i> Imprimir as etiquetas QR</a>}
            {dados.areas.length > 0 && <Ir className="btn btn-primary" href={`/novo/centros/${loc.id}?aba=rotas`}>Seguir para as rotas <i className="bi bi-arrow-right" aria-hidden="true"></i></Ir>}
            <Ir className="btn btn-link" href={`/novo/cadastros/locais/${loc.id}`}>Modo avançado (setores, vários QRs por área)</Ir>
          </div>
        </>
      ) : (
        <>
          <div className="fc-cartao p-0 mb-3">
            {dados.rotas.length ? dados.rotas.map((r) => (
              <Ir className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2 text-reset text-decoration-none"
                href={`/novo/centros/${loc.id}/rotas/${r.id}`} key={r.id}>
                <span className="fw-semibold">{r.nome}</span>
                <span className="small text-muted">{r.turno} · {r.inicio} às {r.fim}</span>
                {!r.ativa && <span className="badge text-bg-secondary">Desativada</span>}
                <span className="small ms-auto">{r.areas} área(s)</span>
              </Ir>
            )) : <div className="fc-vazio">Nenhuma rota ainda. Crie a primeira abaixo.</div>}
          </div>
          {!dados.areas.length && <div className="alert alert-warning">Cadastre as áreas primeiro: a rota é feita de horários e áreas.</div>}
          <section className="fc-cartao" aria-labelledby="tit-rota">
            <h2 className="h6 fw-bold" id="tit-rota">Nova rota</h2>
            <form method="post" onSubmit={submeter(`${API}/${loc.id}/rotas`)}>
              <div className="row g-2">
                <div className="col-md-5"><label className="form-label small fw-semibold" htmlFor="rnome">Nome da rota</label>
                  <input className="form-control" id="rnome" name="nome" required maxLength={150} placeholder="Ex.: Banheiros — manhã" /></div>
                <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor="rturno">Turno</label>
                  <input className="form-control" id="rturno" name="turno" required maxLength={50} defaultValue="1º Turno" /></div>
                <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="rini">Começa</label>
                  <input className="form-control" id="rini" name="hora_inicio" type="time" required defaultValue="06:00" /></div>
                <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="rfim">Termina</label>
                  <input className="form-control" id="rfim" name="hora_fim" type="time" required defaultValue="14:00" /></div>
              </div>
              <fieldset className="mt-2"><legend className="form-label small fw-semibold">Dias</legend>
                <div className="d-flex flex-wrap gap-2">
                  {DIAS.map(([d, nome]) => (
                    <label className="form-check-label" key={d}><input className="form-check-input" type="checkbox" name="dias_semana" value={d}
                      defaultChecked={'12345'.includes(d)} /> {nome}</label>
                  ))}
                </div>
              </fieldset>
              <button className="btn btn-primary fw-bold mt-3" type="submit" disabled={!dados.areas.length || ocupado}>Criar e digitar os horários</button>
            </form>
          </section>
        </>
      )}
    </div>
  );
}

export function PaginaCentro() {
  const { id } = useParams();
  const { search } = useLocation();
  const aba = new URLSearchParams(search).get('aba');
  return (
    <Pagina<DadosDoCentro> api={`/cadastros/centros/${id}${aba ? '?aba=' + encodeURIComponent(aba) : ''}`}>
      {(d) => <Centro dados={d} />}
    </Pagina>
  );
}

// ── A rota: as linhas, quem faz ───────────────────────────────────────────

export function Rota({ dados }: { dados: DadosDaRota }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const { local: loc, rota } = dados;
  const base = `${API}/${loc.id}/rotas/${rota.id}`;
  return (
    <div data-tela-pronta="rota">
      <Migalhas itens={[['Clientes', '/novo/clientes'], [loc.nome, `/novo/centros/${loc.id}?aba=rotas`], [rota.nome, null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">{rota.nome}</h1>
      <p className="fc-sub">{rota.turno} · {rota.inicio} às {rota.fim} · {rota.dias.join(', ')}</p>

      <section className="fc-cartao p-0 mb-3" aria-labelledby="tit-linhas">
        <h2 className="h6 fw-bold px-3 pt-3" id="tit-linhas">O roteiro</h2>
        {dados.linhas.length ? dados.linhas.map((l) => (
          <div className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2" data-linha={l.hora} key={l.item_id + ' ' + l.hora}>
            <span className="fw-bold fs-5">{l.hora}</span>
            <span className="fw-semibold">{l.area}</span>
            <span className="small text-muted">{l.checklist}</span>
            <form method="post" className="ms-auto m-0" onSubmit={submeter(`${base}/linhas/${l.item_id}/remover`)}>
              <input type="hidden" name="hora" value={l.hora} />
              <button className="btn btn-sm btn-outline-danger" type="submit" aria-label={`Tirar ${l.hora} ${l.area} da rota`} disabled={ocupado}>Tirar</button>
            </form>
          </div>
        )) : <div className="fc-vazio">Nenhum horário ainda. Digite abaixo: horário e área.</div>}
      </section>

      <section className="fc-cartao mb-3" aria-labelledby="tit-incluir">
        <h2 className="h6 fw-bold" id="tit-incluir">Incluir horários</h2>
        <p className="small text-muted">Uma linha por passada: o horário e a área. O checklist vem da área. A mesma área pode aparecer em vários horários.</p>
        <form method="post" onSubmit={submeter(`${base}/linhas`)}>
          {Array.from({ length: dados.vazias }, (_, i) => (
            <div className="row g-2 mb-2" key={i}>
              <div className="col-4 col-md-2"><label className="visually-hidden" htmlFor={`h${i}`}>Horário da linha {i + 1}</label>
                <input className="form-control" id={`h${i}`} name="hora" type="time" /></div>
              <div className="col-8 col-md-6"><label className="visually-hidden" htmlFor={`a${i}`}>Área da linha {i + 1}</label>
                <select className="form-select" id={`a${i}`} name="area" defaultValue="">
                  <option value="">Área</option>
                  {dados.areas.map((p) => <option value={p.id} key={p.id}>{p.nome}</option>)}
                </select></div>
            </div>
          ))}
          <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Incluir na rota</button>
        </form>
      </section>

      <section className="fc-cartao mb-3" aria-labelledby="tit-quem">
        <h2 className="h6 fw-bold" id="tit-quem">Quem faz</h2>
        {dados.escalados.length ? dados.escalados.map((e, n) => (
          <p className="mb-1" key={n}><i className="bi bi-person" aria-hidden="true"></i> {e.nome} <span className="small text-muted">desde {e.desde}</span></p>
        )) : <p className="small text-muted">Ninguém escalado: as tarefas aparecem para todos do local.</p>}
        <form method="post" className="d-flex flex-wrap gap-2 mt-2" onSubmit={submeter(`${base}/escala`)}>
          <input type="hidden" name="data_inicio" value={dados.hoje} />
          <label className="visually-hidden" htmlFor="pessoa">Pessoa</label>
          <select className="form-select w-auto" id="pessoa" name="user_id" required defaultValue="">
            <option value="">Escolha a pessoa</option>
            {dados.pessoas.map((p) => <option value={p.id} key={p.id}>{p.nome}</option>)}
          </select>
          <button className="btn btn-outline-primary" type="submit" disabled={ocupado}>Escalar</button>
        </form>
        {!dados.pessoas.length && <p className="small text-muted mt-2 mb-0">Ninguém da equipe neste centro de custo ainda. <Ir href={`/novo/novo-contrato/${loc.id}/equipe`}>Convide a equipe</Ir>.</p>}
      </section>
      <Ir className="btn btn-link" href={dados.links.avancado}>Modo avançado (frequência, horários por dia, tolerância)</Ir>
    </div>
  );
}

export function PaginaRota() {
  const { id, rota } = useParams();
  return <Pagina<DadosDaRota> api={`/cadastros/centros/${id}/rotas/${rota}`}>{(d) => <Rota dados={d} />}</Pagina>;
}
