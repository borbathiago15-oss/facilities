// Os chamados (Fase 4a): a lista, abrir e o chamado. As telas antigas são
// templates/chamados/index.html, novo.html, ver.html e _selo.html, com os
// mesmos textos, campos e classes (app.css). Os envios levam o próprio
// formulário (FormData, com as fotos) para o MESMO caminho da antiga abaixo
// de /api/v1, que chama a MESMA ação (chamados.rotas.acao_*).
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Ir, Migalhas, RecadosDoEnvio, useFormulario } from '../cadastros/comum';
import type { DadosDaLista, DadosDoChamado, DadosDoNovo, ResumoDoChamado, SeloDoPrazo } from './tipos';

export const API = '/api/v1/chamados';

/** O endereço da lista com os parâmetros na ordem do ``url_for`` da antiga
 * (o vazio e o ``None`` ficam de fora). */
export function urlDaLista(params: [string, string | number | null | undefined][]): string {
  const q = params.filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&');
  return '/novo/chamados/' + (q ? '?' + q : '');
}

/** O formulário como a busca de um GET (todos os campos, os vazios também). */
export function buscaDoFormulario(form: HTMLFormElement): string {
  const q = new URLSearchParams();
  new FormData(form).forEach((v, k) => q.append(k, typeof v === 'string' ? v : ''));
  return q.toString();
}

// ── Os selos (templates/chamados/_selo.html) ──────────────────────────────

export function SeloPrioridade({ ch }: { ch: ResumoDoChamado }) {
  return <span className={`ch-pri ch-pri-${ch.prioridade}`}>{ch.prioridade_rotulo}</span>;
}

export function SeloStatus({ ch }: { ch: ResumoDoChamado }) {
  return <span className={`ch-st ch-st-${ch.status}`}>{ch.status_rotulo}</span>;
}

export function SeloPrazo({ selo }: { selo: SeloDoPrazo }) {
  if (!selo) return null;
  if (selo.tipo === 'ok') return <span className="ch-prazo ok">{selo.texto}</span>;
  if (selo.tipo === 'atrasado') {
    return <span className="ch-prazo atrasado"><i className="bi bi-exclamation-triangle"></i> {selo.texto}</span>;
  }
  return <span className={selo.perto ? 'ch-prazo perto' : 'ch-prazo'}>{selo.texto}</span>;
}

// ── A lista ───────────────────────────────────────────────────────────────

export function Lista({ dados }: { dados: DadosDaLista }) {
  const navegar = useNavigate();
  const { client_id: cid, visao, prioridade, categoria, numeros: n } = dados;
  const filtrar = (ev: React.ChangeEvent<HTMLSelectElement>) => {
    navegar('/chamados/?' + buscaDoFormulario(ev.currentTarget.form!));
  };
  const vazio = visao === 'atrasados' ? 'Nenhum chamado atrasado. '
    : visao === 'confirmar' ? 'Nada aguardando confirmação. ' : 'Nenhum chamado aqui. ';
  return (
    <div data-tela-pronta="chamados">
      <RecadosDoEnvio />
      <div className="d-flex align-items-start justify-content-between flex-wrap gap-2">
        <div>
          <h1 className="fc-titulo">Chamados</h1>
          <p className="fc-sub">Ordens de serviço de manutenção: quem pediu, quem atende e o prazo.</p>
        </div>
        {dados.pode_abrir && (
          <Ir className="btn btn-primary fw-bold" href={'/novo/chamados/novo' + (cid ? `?client_id=${cid}` : '')}><i className="bi bi-plus-lg"></i> Abrir chamado</Ir>
        )}
      </div>

      <div className="ch-numeros">
        <Ir className="ch-num" href={urlDaLista([['client_id', cid], ['visao', 'abertos']])}><b>{n.em_aberto}</b><span>em aberto</span></Ir>
        <Ir className={n.atrasados ? 'ch-num alerta' : 'ch-num'} href={urlDaLista([['client_id', cid], ['visao', 'atrasados']])}><b>{n.atrasados}</b><span>{n.atrasados === 1 ? 'atrasado' : 'atrasados'}</span></Ir>
        <Ir className="ch-num" href={urlDaLista([['client_id', cid], ['visao', 'confirmar']])}><b>{n.aguardando_confirmacao}</b><span>aguardando confirmação</span></Ir>
        <div className="ch-num"><b>{n.pct_no_prazo}</b><span>resolvidos no prazo ({n.dias} dias)</span></div>
        <div className="ch-num"><b>{n.tempo_medio}</b><span>tempo médio até resolver</span></div>
      </div>

      <form className="ch-filtros" method="get" onSubmit={(ev) => ev.preventDefault()}>
        <select className="form-select form-select-sm" name="client_id" aria-label="Contrato" defaultValue={cid ?? ''} onChange={filtrar}>
          <option value="">Todos os meus contratos</option>
          {dados.contratos.map((c) => <option value={c.id} key={c.id}>{c.nome}</option>)}
        </select>
        <select className="form-select form-select-sm" name="prioridade" aria-label="Prioridade" defaultValue={prioridade} onChange={filtrar}>
          <option value="">Toda prioridade</option>
          {dados.prioridades.map(([k, v]) => <option value={k} key={k}>{v}</option>)}
        </select>
        <select className="form-select form-select-sm" name="categoria" aria-label="Categoria" defaultValue={categoria} onChange={filtrar}>
          <option value="">Toda categoria</option>
          {dados.categorias.map(([k, v]) => <option value={k} key={k}>{v}</option>)}
        </select>
        <input type="hidden" name="visao" value={visao} />
      </form>

      <nav className="ch-abas" aria-label="Visões">
        {dados.visoes.map(([k, v]) => (
          <Ir className={k === visao ? 'ativo' : undefined} key={k}
            href={urlDaLista([['client_id', cid], ['visao', k], ['prioridade', prioridade], ['categoria', categoria]])}>{v}</Ir>
        ))}
      </nav>

      {dados.cortada && (
        <p className="small text-muted mb-2">Mostrando os {dados.por_pagina} chamados mais recentes. Para achar um mais antigo, escolha o contrato, a prioridade ou a categoria acima.</p>
      )}
      <div className="ch-lista">
        {dados.chamados.length ? dados.chamados.map((ch) => (
          <Ir className={ch.atrasado ? 'ch-item atrasado' : 'ch-item'} href={`/novo/chamados/${ch.id}`} key={ch.id}>
            <div className="ch-item-topo">
              <span className="ch-num-os">{ch.numero}</span>
              <SeloPrioridade ch={ch} /> <SeloStatus ch={ch} />
              <span className="ms-auto"><SeloPrazo selo={ch.prazo_selo} /></span>
            </div>
            <div className="ch-item-tit">{ch.titulo}</div>
            <div className="ch-item-meta">
              {ch.contrato}{ch.area && ` · ${ch.area}`}{ch.local && ` · ${ch.local}`}
              {' · '}{ch.categoria_rotulo}
              {' · '}{ch.responsavel ? `com ${ch.responsavel}` : <em>sem responsável</em>}
            </div>
          </Ir>
        )) : <div className="fc-cartao fc-vazio">{vazio}</div>}
      </div>
    </div>
  );
}

// ── Abrir ─────────────────────────────────────────────────────────────────

export function Novo({ dados }: { dados: DadosDoNovo }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const um = dados.contratos.length === 1;
  const inicial = um ? String(dados.contratos[0].id)
    : (dados.contratos.some((c) => c.id === dados.client_id) ? String(dados.client_id) : '');
  const [contrato, setContrato] = useState(inicial);
  const areas = dados.areas[contrato] || [];
  return (
    <div data-tela-pronta="chamados-novo">
      <Migalhas itens={[['Chamados', '/novo/chamados/'], ['Abrir', null]]} />
      <RecadosDoEnvio />{aviso}
      <div className="fc-cartao" style={{ maxWidth: '720px' }}>
        <h1 className="fc-titulo">Abrir chamado</h1>
        <p className="fc-sub">Diga o que está errado e onde. A gestão e a supervisão do local são avisadas e escolhem quem vai atender.</p>
        <form method="post" encType="multipart/form-data" onSubmit={submeter(`${API}/`)}>
          <div className="row g-3">
            <div className="col-md-6">
              <label className="form-label small fw-semibold" htmlFor="client_id">Contrato</label>
              <select className="form-select" id="client_id" name="client_id" required value={contrato} onChange={(ev) => setContrato(ev.target.value)}>
                {!um && <option value="">Escolha…</option>}
                {dados.contratos.map((c) => <option value={c.id} key={c.id}>{c.nome}</option>)}
              </select>
            </div>
            <div className="col-md-6">
              <label className="form-label small fw-semibold" htmlFor="area_id">Área / serviço <span className="text-muted fw-normal">(opcional)</span></label>
              <select className="form-select" id="area_id" name="area_id" key={contrato} defaultValue="" disabled={!areas.length}>
                <option value="">—</option>
                {areas.map((a) => <option value={a.id} key={a.id}>{a.nome}</option>)}
              </select>
            </div>
            <div className="col-12">
              <label className="form-label small fw-semibold" htmlFor="titulo">O que está errado?</label>
              <input className="form-control" id="titulo" name="titulo" required maxLength={200} placeholder="Ex.: Torneira do banheiro masculino vazando" />
            </div>
            <div className="col-md-6">
              <label className="form-label small fw-semibold" htmlFor="local">Onde?</label>
              <input className="form-control" id="local" name="local" maxLength={200} placeholder="Ex.: Bloco B, 2º andar" />
            </div>
            <div className="col-md-3">
              <label className="form-label small fw-semibold" htmlFor="categoria">Categoria</label>
              <select className="form-select" id="categoria" name="categoria" defaultValue="outro">
                {dados.categorias.map(([k, v]) => <option value={k} key={k}>{v}</option>)}
              </select>
            </div>
            <div className="col-md-3">
              <label className="form-label small fw-semibold" htmlFor="prioridade">Prioridade</label>
              <select className="form-select" id="prioridade" name="prioridade" defaultValue="media">
                {dados.prioridades.map(([k, v]) => <option value={k} key={k}>{v}</option>)}
              </select>
            </div>
            <div className="col-12">
              <p className="small text-muted mb-0" id="regua-prazo">Prazo para resolver: urgente 4h · alta 24h · média 3 dias · baixa 7 dias.</p>
            </div>
            <div className="col-12">
              <label className="form-label small fw-semibold" htmlFor="descricao">Detalhes <span className="text-muted fw-normal">(opcional)</span></label>
              <textarea className="form-control" id="descricao" name="descricao" rows={3}></textarea>
            </div>
            <div className="col-12">
              <label className="form-label small fw-semibold" htmlFor="arquivo">Fotos <span className="text-muted fw-normal">(opcional, até 6)</span></label>
              <input className="form-control" id="arquivo" name="arquivo" type="file" accept="image/*,application/pdf" multiple />
            </div>
          </div>
          <button className="btn btn-primary fw-bold mt-3" type="submit" disabled={ocupado}>Abrir chamado</button>
        </form>
      </div>
    </div>
  );
}

// ── O chamado ─────────────────────────────────────────────────────────────

function Acao({ nome, url, enviar, children, ...resto }: {
  nome: string; url: string; enviar: (url: string) => (ev: React.FormEvent<HTMLFormElement>) => void;
  children: React.ReactNode;
} & Omit<React.FormHTMLAttributes<HTMLFormElement>, 'onSubmit'>) {
  return (
    <form method="post" onSubmit={enviar(url)} {...resto}>
      <input type="hidden" name="acao" value={nome} />
      {children}
    </form>
  );
}

export function Ver({ dados }: { dados: DadosDoChamado }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const { chamado: ch, acoes } = dados;
  const url = `${API}/${ch.id}/acao`;
  const tem = (a: string) => acoes.includes(a);
  const antes = dados.anexos.filter((a) => a.momento === 'antes');
  const depois = dados.anexos.filter((a) => a.momento === 'depois');
  return (
    <div data-tela-pronta="chamado">
      <Migalhas itens={[['Chamados', `/novo/chamados/?client_id=${ch.client_id}`], [ch.numero, null]]} />
      <RecadosDoEnvio />{aviso}
      <div className={ch.atrasado ? 'ch-cab atrasado' : 'ch-cab'}>
        <div className="d-flex flex-wrap gap-2 align-items-center">
          <span className="ch-num-os">{ch.numero}</span>
          <SeloPrioridade ch={ch} /> <SeloStatus ch={ch} /> <SeloPrazo selo={ch.prazo_selo} />
        </div>
        <h1 className="fc-titulo mt-2">{ch.titulo}</h1>
        <dl className="ch-dados">
          <div><dt>Contrato</dt><dd>{ch.contrato}{ch.area && ` · ${ch.area}`}</dd></div>
          {ch.local && <div><dt>Onde</dt><dd>{ch.local}</dd></div>}
          <div><dt>Categoria</dt><dd>{ch.categoria_rotulo}</dd></div>
          <div><dt>Pedido por</dt><dd>{ch.solicitante} · {ch.aberto_em}</dd></div>
          <div><dt>Responsável</dt><dd>{ch.responsavel || '—'}</dd></div>
          <div><dt>Prazo</dt><dd>{ch.prazo}</dd></div>
          {ch.origem === 'ocorrencia' && <div><dt>Origem</dt><dd>Ocorrência da passagem de turno</dd></div>}
          {ch.origem === 'preventiva' && <div><dt>Origem</dt><dd>Manutenção preventiva programada</dd></div>}
          {ch.origem === 'visita' && ch.visita && <div><dt>Origem</dt><dd><a href={ch.visita}>Visita de supervisão</a></dd></div>}
          {ch.pausa && <div><dt>Tempo parado</dt><dd>{ch.pausa}</dd></div>}
        </dl>
        {ch.descricao && <p className="ch-desc">{ch.descricao}</p>}
        {ch.origem === 'preventiva' && ['aberto', 'em_atendimento'].includes(ch.status) && (
          <div className="alert alert-info py-2 small">Para fazer esta preventiva: no aplicativo, abra <b>Meu turno</b>, leia o QR do ponto e toque em <b>Fazer a preventiva</b>. Ao terminar o checklist, a ordem fica resolvida.</div>
        )}
        {ch.status === 'aguardando' && ch.motivo_espera && <div className="alert alert-warning py-2 small mb-0"><b>Aguardando:</b> {ch.motivo_espera}</div>}
        {ch.solucao && ['resolvido', 'fechado'].includes(ch.status) && <div className="alert alert-success py-2 small mb-0"><b>O que foi feito:</b> {ch.solucao}</div>}
      </div>

      {acoes.length > 0 && (
        <div className="fc-cartao mt-3">
          <h2 className="h6 fw-bold mb-3">O que fazer agora</h2>
          <div className="ch-acoes">
            {tem('iniciar') && (
              <Acao nome="iniciar" url={url} enviar={submeter}>
                <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}><i className="bi bi-play-fill"></i> Iniciar atendimento</button>
              </Acao>
            )}
            {tem('retomar') && (
              <Acao nome="retomar" url={url} enviar={submeter}>
                <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}><i className="bi bi-play-fill"></i> Retomar atendimento</button>
              </Acao>
            )}
            {tem('confirmar') && (
              <Acao nome="confirmar" url={url} enviar={submeter}>
                <button className="btn btn-success fw-bold" type="submit" disabled={ocupado}><i className="bi bi-check2-circle"></i> Ficou bom — fechar</button>
              </Acao>
            )}
          </div>

          {tem('resolver') && (
            <details className="ch-acao" open>
              <summary>Resolver</summary>
              <Acao nome="resolver" url={url} enviar={submeter} encType="multipart/form-data">
                <textarea className="form-control mb-2" name="texto" rows={2} required placeholder="O que foi feito (ex.: troquei o reparo da torneira)" aria-label="O que foi feito"></textarea>
                <label className="form-label small" htmlFor="arq-resolver">Foto do serviço feito <span className="text-muted">(opcional)</span></label>
                <input className="form-control mb-2" id="arq-resolver" name="arquivo" type="file" accept="image/*,application/pdf" multiple />
                <button className="btn btn-success fw-bold" type="submit" disabled={ocupado}>Marcar como resolvido</button>
              </Acao>
            </details>
          )}
          {tem('aguardar') && (
            <details className="ch-acao">
              <summary>Pôr em espera</summary>
              <Acao nome="aguardar" url={url} enviar={submeter}>
                <input className="form-control mb-2" name="texto" required maxLength={300} placeholder="O que está faltando (peça, terceiro, acesso…)" aria-label="O que está faltando" />
                <button className="btn btn-outline-secondary" type="submit" disabled={ocupado}>Aguardar</button>
              </Acao>
            </details>
          )}
          {tem('reabrir') && (
            <details className="ch-acao">
              <summary>Não ficou bom — reabrir</summary>
              <Acao nome="reabrir" url={url} enviar={submeter}>
                <textarea className="form-control mb-2" name="texto" rows={2} required placeholder="O que ainda não está bom" aria-label="O que ainda não está bom"></textarea>
                <button className="btn btn-outline-danger" type="submit" disabled={ocupado}>Reabrir</button>
              </Acao>
            </details>
          )}
          {tem('atribuir') && (
            <details className="ch-acao" open={!ch.responsavel_id}>
              <summary>{ch.responsavel_id ? 'Trocar responsável' : 'Atribuir a um técnico'}</summary>
              <Acao nome="atribuir" url={url} enviar={submeter} className="d-flex flex-wrap gap-2">
                <select className="form-select" name="responsavel_id" required style={{ maxWidth: '320px' }} defaultValue={ch.responsavel_id ?? ''} aria-label="Responsável">
                  <option value="">Escolha…</option>
                  {dados.tecnicos.map((t) => <option value={t.id} key={t.id}>{t.nome} — {t.perfil}</option>)}
                </select>
                <button className="btn btn-primary" type="submit" disabled={ocupado}>Atribuir</button>
              </Acao>
              {!dados.tecnicos.length && <p className="small text-muted mt-2 mb-0">Nenhum técnico ou gestor vinculado a este contrato. Vincule no cadastro de pessoas.</p>}
            </details>
          )}
          {tem('prioridade') && (
            <details className="ch-acao">
              <summary>Mudar prioridade</summary>
              <Acao nome="prioridade" url={url} enviar={submeter} className="d-flex flex-wrap gap-2">
                <select className="form-select" name="prioridade" style={{ maxWidth: '200px' }} defaultValue={ch.prioridade} aria-label="Prioridade">
                  {dados.prioridades.map(([k, v]) => <option value={k} key={k}>{v}</option>)}
                </select>
                <input className="form-control" name="texto" maxLength={200} placeholder="Motivo (opcional)" style={{ maxWidth: '320px' }} aria-label="Motivo" />
                <button className="btn btn-outline-secondary" type="submit" disabled={ocupado}>Salvar</button>
              </Acao>
              <p className="small text-muted mt-2 mb-0">O prazo é recalculado a partir da abertura.</p>
            </details>
          )}
          {tem('comentar') && (
            <details className="ch-acao">
              <summary>Comentar</summary>
              <Acao nome="comentar" url={url} enviar={submeter}>
                <textarea className="form-control mb-2" name="texto" rows={2} required aria-label="Comentário"></textarea>
                <button className="btn btn-outline-secondary" type="submit" disabled={ocupado}>Comentar</button>
              </Acao>
            </details>
          )}
          {tem('cancelar') && (
            <details className="ch-acao">
              <summary className="text-danger">Cancelar chamado</summary>
              <Acao nome="cancelar" url={url} enviar={submeter}>
                <input className="form-control mb-2" name="texto" required maxLength={300} placeholder="Por que está sendo cancelado (duplicado, aberto por engano…)" aria-label="Por que está sendo cancelado" />
                <button className="btn btn-outline-danger" type="submit" disabled={ocupado}>Cancelar chamado</button>
              </Acao>
            </details>
          )}
        </div>
      )}

      <div className="row g-3 mt-0">
        <div className="col-lg-7">
          <div className="fc-cartao">
            <h2 className="h6 fw-bold mb-3">Histórico</h2>
            <ol className="ch-trilha">
              {dados.eventos.map((e, i) => (
                <li className={`ev-${e.tipo}`} key={i}>
                  <div><b>{e.autor}</b> {e.rotulo} <time>{e.quando}</time></div>
                  {e.texto && <p>{e.texto}</p>}
                </li>
              ))}
            </ol>
          </div>
        </div>
        <div className="col-lg-5">
          <div className="fc-cartao">
            <h2 className="h6 fw-bold mb-3">Fotos e arquivos</h2>
            {([['Antes', antes], ['Depois', depois]] as const).map(([titulo, lista]) => lista.length > 0 && (
              <div key={titulo}>
                <div className="small fw-semibold text-muted mb-1">{titulo}</div>
                <div className="ch-anexos mb-2">
                  {lista.map((a) => (
                    <a href={a.url} target="_blank" rel="noopener" key={a.id}>
                      {a.imagem ? <img src={a.url} alt={a.nome} loading="lazy" /> : <span className="ch-arq"><i className="bi bi-file-earmark"></i> {a.nome}</span>}
                    </a>
                  ))}
                </div>
              </div>
            ))}
            {!dados.anexos.length && <p className="small text-muted">Nenhum arquivo.</p>}
            {dados.pode_anexar && (
              <form method="post" encType="multipart/form-data" className="mt-2" onSubmit={submeter(`${API}/${ch.id}/anexos`)}>
                <input className="form-control form-control-sm mb-2" name="arquivo" type="file" accept="image/*,application/pdf" multiple required aria-label="Arquivos" />
                <div className="d-flex gap-2 align-items-center">
                  <select className="form-select form-select-sm" name="momento" style={{ maxWidth: '150px' }} aria-label="De quando">
                    <option value="antes">do problema</option><option value="depois">do serviço feito</option>
                  </select>
                  <button className="btn btn-sm btn-outline-secondary" type="submit" disabled={ocupado}>Anexar</button>
                </div>
              </form>
            )}
          </div>
          <div className="fc-cartao mt-3">
            <h2 className="h6 fw-bold mb-2">Material usado</h2>
            {dados.consumos.length ? dados.consumos.map((c, i) => (
              <div className="d-flex flex-wrap gap-2 border-top py-1 small" key={i}>
                <span className="fw-semibold">{c.quantidade} {c.unidade} · {c.material}</span>
                <span className="text-muted">{c.pessoa} · {c.quando}</span>
                {dados.ve_custo && <span className="ms-auto">{c.valor}</span>}
              </div>
            )) : <p className="small text-muted">Nenhum material lançado nesta OS.</p>}
            {dados.materiais.length > 0 && (
              <form method="post" className="mt-2" onSubmit={submeter(`/api/v1/materiais/locais/${ch.client_id}/consumo`)}>
                <input type="hidden" name="chamado_id" value={ch.id} />
                <input type="hidden" name="voltar" value="chamado" />
                <label className="visually-hidden" htmlFor="chm">Material</label>
                <select className="form-select form-select-sm mb-2" id="chm" name="material_id" required>{dados.materiais.map((m) => <option value={m.id} key={m.id}>{m.nome} ({m.unidade})</option>)}</select>
                <div className="d-flex gap-2">
                  <label className="visually-hidden" htmlFor="chq">Quantidade</label>
                  <input className="form-control form-control-sm" id="chq" name="quantidade" required inputMode="decimal" placeholder="Quantidade" />
                  <button className="btn btn-sm btn-outline-secondary text-nowrap" type="submit" disabled={ocupado}>Lançar material</button>
                </div>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
