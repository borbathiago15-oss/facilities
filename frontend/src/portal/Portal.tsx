// As telas do portal do cliente (Fase 5; as antigas são templates/portal/
// inicio.html, local.html, chamado.html, relatorios.html, relatorio.html,
// cobrancas.html, avisos_qr.html e cobranca.html, com os mesmos textos,
// campos e classes). Os envios vão ao mesmo caminho da antiga abaixo de
// /api/v1 e chamam a mesma ação (portal.telas.acao_*). As fotos, os POP/FIT,
// o PDF e o Excel continuam servidos pelo servidor (só links).
import { useLocation, useNavigate } from 'react-router';
import { Ir, Migalhas, RecadosDoEnvio, buscaDoFormulario, useFormulario } from '../cadastros/comum';
import { CorpoDoRelatorioDoMes } from '../relatorios/Relatorios';
import { AbasDasCobrancas, AvisosPeloQr, Filtros, Trilha } from './comum';
import type {
  CobrancaNaLista, DadosDaCobranca, DadosDasCobrancas, DadosDoChamado, DadosDoInicio, DadosDoLocal,
  DadosDoRelatorio, DadosDosAvisos, DadosDosRelatorios, Nota, Selo,
} from './tipos';

const API = '/api/v1/cliente';
const INICIO = '/novo/cliente/';

function NotaDoLocal({ nota }: { nota: Nota }) {
  return nota
    ? <span className={`badge fc-nota fc-nota-${nota.faixa}`}>{nota.texto}</span>
    : <span className="small text-muted">sem dado no período</span>;
}

function SeloDaCobranca({ s }: { s: Selo }) {
  return <span className={`badge ${s.classe}`}>{s.texto}</span>;
}

/** O ``?de=&ate=`` da tela (a macro ``periodo`` de ``_nota.html``). */
function Periodo({ de, ate }: { de: string; ate: string }) {
  const navegar = useNavigate();
  const { pathname } = useLocation();
  return (
    <form className="d-flex flex-wrap gap-2 mb-3" method="get"
      onSubmit={(ev) => { ev.preventDefault(); navegar(pathname + '?' + buscaDoFormulario(ev.currentTarget)); }}>
      <label className="visually-hidden" htmlFor="pde">De</label><input className="form-control w-auto" type="date" id="pde" name="de" defaultValue={de} />
      <label className="visually-hidden" htmlFor="pate">Até</label><input className="form-control w-auto" type="date" id="pate" name="ate" defaultValue={ate} />
      <button className="btn btn-outline-primary" type="submit">Ver o período</button>
    </form>
  );
}

function LinhaDaCobranca({ c, borda }: { c: CobrancaNaLista; borda: string }) {
  return (
    <Ir className={`d-flex flex-wrap gap-2 align-items-center ${borda} px-3 py-2 text-reset text-decoration-none`} href={c.url}>
      <SeloDaCobranca s={c.situacao} />
      <span className="small fw-semibold">{c.numero}</span>
      <span className="fw-semibold">{c.titulo}</span>
      <span className="small text-muted">{c.local}</span>
      <span className="small ms-auto">prazo {c.prazo}</span>
    </Ir>
  );
}

// ── Seus locais ───────────────────────────────────────────────────────────

export function InicioDoPortal({ dados }: { dados: DadosDoInicio }) {
  return (
    <div data-tela-pronta="portal-inicio">
      <RecadosDoEnvio />
      <h1 className="fc-titulo">Seus locais</h1>
      <p className="fc-sub">Como está o serviço em cada local: a nota do período, os chamados e as fotos dos checklists. Precisa de algo? Abra uma cobrança e escolha a data em que quer a resposta.</p>
      <Ir className="btn btn-primary fw-bold mb-3" href={dados.links.cobrancas}><i className="bi bi-megaphone"></i> Abrir uma cobrança</Ir>

      {dados.cobrancas.length > 0 && (
        <section className="fc-cartao p-0 mb-3" aria-labelledby="tit-cob">
          <h2 className="h6 fw-bold px-3 pt-3" id="tit-cob">Cobranças em andamento</h2>
          {dados.cobrancas.map((c) => <LinhaDaCobranca c={c} borda="border-top" key={c.id} />)}
        </section>
      )}

      <Periodo de={dados.de} ate={dados.ate} />
      {!dados.linhas.length ? (
        <div className="fc-cartao fc-vazio">Nenhum local ligado à sua conta ainda. Fale com o seu gerente na Trino.</div>
      ) : (
        <div className="fc-cartao p-0">
          {dados.linhas.map((x) => (
            <Ir className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-3 text-reset text-decoration-none" href={x.url} key={x.id}>
              <span className="fw-semibold">{x.nome}</span>
              <NotaDoLocal nota={x.nota} />
              <span className="small text-muted ms-auto">{x.abertos} chamado(s) em aberto</span>
              <i className="bi bi-chevron-right" aria-hidden="true"></i>
            </Ir>
          ))}
        </div>
      )}
      <p className="small text-muted mt-2">Período de {dados.de_br} a {dados.ate_br}. A nota é a média dos indicadores que tiveram movimento no período.</p>
    </div>
  );
}

// ── O local ───────────────────────────────────────────────────────────────

function SeloConforme({ n }: { n: number }) {
  return n
    ? <span className="badge fc-dem fc-dem-atrasada">{n} item(ns) não conforme(s)</span>
    : <span className="badge text-bg-light">Tudo conforme</span>;
}

function Miniaturas({ fotos }: { fotos: { id: number; url: string; alt: string }[] }) {
  if (!fotos.length) return null;
  return (
    <div className="d-flex flex-wrap gap-2 mt-2">
      {fotos.map((f) => <a href={f.url} target="_blank" rel="noopener" key={f.id}><img className="fc-miniatura" src={f.url} alt={f.alt} loading="lazy" /></a>)}
    </div>
  );
}

export function LocalDoPortal({ dados }: { dados: DadosDoLocal }) {
  return (
    <div data-tela-pronta="portal-local">
      <Migalhas itens={[['Seus locais', dados.links.inicio], [dados.local.nome, null]]} />
      <RecadosDoEnvio />
      <h1 className="fc-titulo">{dados.local.nome}</h1>
      <p className="fc-sub">Nota do período: <NotaDoLocal nota={dados.nota} /></p>
      <Ir className="btn btn-outline-primary fw-bold mb-3" href={dados.links.cobrar}><i className="bi bi-megaphone"></i> Cobrar algo deste local</Ir>
      <Periodo de={dados.de} ate={dados.ate} />

      <section className="mb-4" aria-labelledby="tit-ind">
        <h2 className="h5 fw-bold" id="tit-ind">Indicadores</h2>
        <div className="d-flex flex-wrap gap-2">
          {dados.indicadores.map((i) => (
            <div className="fc-cartao py-2 px-3" key={i.chave}><div className="small text-muted">{i.rotulo}</div>
              <div className="fs-4 fw-bold">{i.pct}</div>
              <div className="small text-muted">{i.base}</div></div>
          ))}
        </div>
      </section>

      <section className="mb-4" aria-labelledby="tit-ch">
        <h2 className="h5 fw-bold" id="tit-ch">Chamados</h2>
        <p className="small text-muted">Os em aberto e os abertos nos últimos 90 dias.</p>
        <div className="fc-cartao p-0">
          {dados.chamados.length ? dados.chamados.map((ch) => (
            <Ir className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2 text-reset text-decoration-none" href={ch.url} key={ch.id}>
              <span className="small fw-semibold">{ch.numero}</span>
              <span className="fw-semibold">{ch.titulo}</span>
              <span className={`badge ${ch.atrasado ? 'fc-dem fc-dem-atrasada' : 'text-bg-light'}`}>{ch.situacao}</span>
              {ch.fotos > 0 && <span className="small text-muted"><i className="bi bi-camera" aria-hidden="true"></i> {ch.fotos} foto(s)</span>}
              <span className="small ms-auto">{ch.quando}</span>
            </Ir>
          )) : <div className="fc-vazio">Nenhum chamado neste período.</div>}
        </div>
      </section>

      <section aria-labelledby="tit-ex">
        <h2 className="h5 fw-bold" id="tit-ex">Checklists dos últimos 30 dias</h2>
        <div className="fc-cartao p-0">
          {dados.execucoes.length ? dados.execucoes.map((ex) => (
            <div className="border-bottom px-3 py-2" key={ex.id}>
              <div className="d-flex flex-wrap gap-2 align-items-center">
                <span className="fw-semibold">{ex.onde}</span>
                <span className="small text-muted">{ex.detalhe}</span>
                <SeloConforme n={ex.nao_conformes} />
              </div>
              <Miniaturas fotos={ex.fotos} />
            </div>
          )) : <div className="fc-vazio">Nenhum checklist feito nos últimos 30 dias.</div>}
        </div>
      </section>

      <section className="mt-4" aria-labelledby="tit-vis">
        <h2 className="h5 fw-bold" id="tit-vis">Visitas de supervisão dos últimos 30 dias</h2>
        <div className="fc-cartao p-0">
          {dados.visitas.length ? dados.visitas.map((v) => (
            <div className="border-bottom px-3 py-2" key={v.id}>
              <div className="d-flex flex-wrap gap-2 align-items-center">
                <span className="fw-semibold">{v.nome}</span>
                <span className="small text-muted">{v.detalhe}</span>
                <SeloConforme n={v.nao_conformes} />
              </div>
              <Miniaturas fotos={v.fotos} />
            </div>
          )) : <div className="fc-vazio">Nenhuma visita de supervisão feita nos últimos 30 dias.</div>}
        </div>
      </section>
      {dados.documentos.length > 0 && (
        <section className="mt-4" aria-labelledby="tit-docs">
          <h2 className="h5 fw-bold" id="tit-docs">Procedimentos (POP/FIT)</h2>
          <div className="fc-cartao p-0">
            {dados.documentos.map((d) => (
              <a className="d-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2 text-reset text-decoration-none" href={d.url} key={d.id}>
                <i className="bi bi-file-earmark-text" aria-hidden="true"></i>
                <span className="fw-semibold">{d.modelo}</span>
                <span className="small text-muted">{d.nome}</span>
                <span className="small ms-auto">Baixar</span>
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ── O chamado ─────────────────────────────────────────────────────────────

export function ChamadoDoPortal({ dados }: { dados: DadosDoChamado }) {
  const linha = (rotulo: string, valor: React.ReactNode) => (
    <><dt className="col-sm-4">{rotulo}</dt><dd className="col-sm-8">{valor}</dd></>
  );
  return (
    <div data-tela-pronta="portal-chamado">
      <Migalhas itens={[['Seus locais', dados.links.inicio], [dados.local.nome, dados.links.local], [dados.numero, null]]} />
      <h1 className="fc-titulo">{dados.numero} · {dados.titulo}</h1>
      <div className="fc-cartao fc-estreito">
        <dl className="row mb-0">
          {linha('Situação', dados.situacao)}
          {linha('Tipo', dados.categoria)}
          {dados.onde && linha('Onde', dados.onde)}
          {linha('Aberto em', dados.aberto_em)}
          {linha('Prazo', <>{dados.prazo}{dados.aguardando && <> <span className="small text-muted">(parado enquanto aguarda peça ou terceiro)</span></>}</>)}
          {dados.resolvido_em && linha('Resolvido em', dados.resolvido_em)}
          {dados.solucao && linha('O que foi feito', dados.solucao)}
        </dl>
      </div>
      {dados.fotos.length > 0 && (
        <>
          <h2 className="h5 fw-bold mt-4">Fotos</h2>
          <div className="d-flex flex-wrap gap-2">
            {dados.fotos.map((a) => (
              <figure className="m-0" key={a.id}><a href={a.url} target="_blank" rel="noopener"><img className="fc-miniatura" src={a.url} alt={a.alt} loading="lazy" /></a>
                <figcaption className="small text-muted">{a.legenda}</figcaption></figure>
            ))}
          </div>
        </>
      )}
      <p className="mt-3"><Ir className="btn btn-outline-primary" href={dados.links.cobrar}><i className="bi bi-megaphone"></i> Cobrar este assunto</Ir></p>
    </div>
  );
}

// ── Os relatórios ─────────────────────────────────────────────────────────

export function RelatoriosDoPortal({ dados }: { dados: DadosDosRelatorios }) {
  return (
    <div data-tela-pronta="portal-relatorios">
      <h1 className="fc-titulo">Relatórios mensais</h1>
      <p className="fc-sub">O resumo de cada mês dos seus locais: a nota, as rotinas feitas, os chamados e as fotos. Abra na tela ou baixe em PDF.</p>
      <div className="fc-cartao p-0">
        {dados.relatorios.length ? dados.relatorios.map((r) => (
          <div className="fc-fila-item" key={r.id}>
            <span className="badge text-bg-light">{r.mes}</span>
            <span className="fc-fila-tit">{r.local}</span>
            <Ir className="btn btn-sm btn-outline-primary" href={r.url}>Abrir</Ir>
            <a className="btn btn-sm btn-primary" href={r.pdf}><i className="bi bi-file-earmark-pdf" aria-hidden="true"></i> PDF</a>
          </div>
        )) : <div className="fc-vazio">Nenhum relatório liberado ainda. Eles chegam no começo de cada mês.</div>}
      </div>
    </div>
  );
}

export function RelatorioDoPortal({ dados }: { dados: DadosDoRelatorio }) {
  return (
    <div data-tela-pronta="portal-relatorio">
      <Migalhas itens={[['Relatórios', dados.links.inicio], [dados.local.nome, null]]} />
      <div className="fc-ola"><div>
        <h1 className="fc-titulo">{dados.local.nome}</h1>
        <p className="fc-sub mb-0">{dados.nome_do_mes}</p>
      </div>
      <div className="d-flex flex-wrap gap-2">
        <a className="btn btn-primary" href={dados.links.pdf}><i className="bi bi-file-earmark-pdf" aria-hidden="true"></i> Baixar PDF</a>
        <a className="btn btn-outline-primary" href={dados.links.xlsx}><i className="bi bi-file-earmark-spreadsheet" aria-hidden="true"></i> Excel</a>
      </div></div>
      <CorpoDoRelatorioDoMes c={dados.corpo} recado={dados.recado} />
    </div>
  );
}

// ── As cobranças ──────────────────────────────────────────────────────────

export function CobrancasDoPortal({ dados }: { dados: DadosDasCobrancas | DadosDosAvisos }) {
  return dados.aba === 'qr' ? <AvisosDoPortal dados={dados} /> : <ListaDeCobrancas dados={dados} />;
}

function AvisosDoPortal({ dados }: { dados: DadosDosAvisos }) {
  return (
    <div data-tela-pronta="portal-avisos-qr">
      <Migalhas itens={[['Seus locais', INICIO], ['Avisos pelo QR', null]]} />
      <h1 className="fc-titulo">Cobranças</h1>
      <p className="fc-sub">O que as pessoas avisaram pelo QR dos seus locais e o que a equipe fez. Cada aviso vai direto para quem cuida do ponto no dia.</p>
      <AbasDasCobrancas abas={dados.abas} ativa="qr" />
      <Filtros filtros={dados.filtros} />
      <AvisosPeloQr avisos={dados.avisos} />
    </div>
  );
}

function ListaDeCobrancas({ dados }: { dados: DadosDasCobrancas }) {
  const { submeter, ocupado, aviso } = useFormulario();
  return (
    <div data-tela-pronta="portal-cobrancas">
      <Migalhas itens={[['Seus locais', INICIO], ['Cobranças', null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Cobranças</h1>
      <p className="fc-sub">Peça algo à coordenação do contrato e escolha até quando quer a resposta (no mínimo 24 horas). Quando ela responder, você confirma que ficou bom ou reabre.</p>
      <AbasDasCobrancas abas={dados.abas} ativa="cobrancas" />

      {dados.locais.length > 0 && (
        <details className="fc-cartao mb-3" open={dados.abrir_aberto}>
          <summary className="fw-bold">Abrir uma cobrança</summary>
          <form method="post" className="mt-3" onSubmit={submeter(`${API}/cobrancas`)}>
            <div className="row g-2">
              <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor="cloc">Local</label>
                <select className="form-select" id="cloc" name="client_id" required defaultValue={dados.local_escolhido != null && dados.locais.some((l) => l.id === dados.local_escolhido) ? String(dados.local_escolhido) : (dados.locais.length > 1 ? '' : String(dados.locais[0].id))}>
                  {dados.locais.length > 1 && <option value="">Escolha</option>}
                  {dados.locais.map((l) => <option value={l.id} key={l.id}>{l.nome}</option>)}
                </select></div>
              <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor="cprazo">Quero a resposta até</label>
                <input className="form-control" id="cprazo" name="prazo" type="date" min={dados.minimo} required />
                <div className="form-text">A partir de {dados.minimo_br}.</div></div>
              <div className="col-12"><label className="form-label small fw-semibold" htmlFor="ctit">Assunto</label>
                <input className="form-control" id="ctit" name="titulo" maxLength={200} required placeholder="Ex.: Limpeza do banheiro do 2º andar" /></div>
              <div className="col-12"><label className="form-label small fw-semibold" htmlFor="ctex">O que precisa ser feito</label>
                <textarea className="form-control" id="ctex" name="texto" rows={4} maxLength={4000} required></textarea></div>
            </div>
            <button className="btn btn-primary fw-bold mt-3" type="submit" disabled={ocupado}>Enviar à coordenação</button>
          </form>
        </details>
      )}

      <div className="fc-cartao p-0">
        {dados.cobrancas.length
          ? dados.cobrancas.map((c) => <LinhaDaCobranca c={c} borda="border-bottom" key={c.id} />)
          : <div className="fc-vazio">Nenhuma cobrança ainda.</div>}
      </div>
    </div>
  );
}

export function CobrancaDoPortal({ dados }: { dados: DadosDaCobranca }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const agir = (acao: string) => submeter(`${API}/cobrancas/${dados.id}/${acao}`);
  return (
    <div data-tela-pronta="portal-cobranca">
      <Migalhas itens={[['Cobranças', dados.links.cobrancas], [dados.numero, null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">{dados.numero} · {dados.titulo}</h1>
      <p className="fc-sub">{dados.local} · <SeloDaCobranca s={dados.situacao} /> · prazo {dados.prazo}</p>

      {dados.respondida ? (
        <div className="row g-3">
          <div className="col-md-6"><div className="fc-cartao h-100">
            <h2 className="h6 fw-bold">Ficou bom?</h2>
            <form method="post" onSubmit={agir('confirmar')}>
              <label className="form-label small" htmlFor="ctex">Comentário (opcional)</label>
              <textarea className="form-control mb-2" id="ctex" name="texto" rows={2} maxLength={4000}></textarea>
              <button className="btn btn-success fw-bold" type="submit" disabled={ocupado}>Confirmar e encerrar</button>
            </form>
          </div></div>
          <div className="col-md-6"><div className="fc-cartao h-100">
            <h2 className="h6 fw-bold">Ainda não ficou bom</h2>
            <form method="post" onSubmit={agir('reabrir')}>
              <label className="form-label small" htmlFor="rtex">O que falta</label>
              <textarea className="form-control mb-2" id="rtex" name="texto" rows={2} maxLength={4000} required></textarea>
              <label className="form-label small" htmlFor="rprazo">Novo prazo (a partir de {dados.minimo_br})</label>
              <input className="form-control mb-2" id="rprazo" name="prazo" type="date" min={dados.minimo} required />
              <button className="btn btn-outline-danger fw-bold" type="submit" disabled={ocupado}>Reabrir</button>
            </form>
          </div></div>
        </div>
      ) : dados.aberta ? (
        <div className="alert alert-info">A coordenação do contrato foi avisada e responde até {dados.prazo}.</div>
      ) : null}
      <Trilha eventos={dados.eventos} />
    </div>
  );
}
