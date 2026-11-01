// O painel da Passagem de turno — a torre de controle da operação (Fase 2b
// da migração para React; a tela antiga é templates/diario_operacional/
// dashboard.html + static/js/diario_dashboard.js, com o mesmo comportamento,
// os mesmos textos e as mesmas classes).
//
// De cima para baixo: que recorte estou olhando → a operação cumpriu a
// rotina? → o que ficou pendente apodrecendo? → onde estão os desvios (tipo
// e turno)? → qual rotina é o gargalo? → o que eu faço agora (abrir chamado).
// Nada aqui faz conta: tudo vem de /api/v1/passagem/painel, o mesmo
// ``contexto_painel`` da tela antiga. As ações vão para as APIs de sempre.
import { type ReactNode, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { enviarBruto } from '../api';
import {
  decimal, faixaDoPainel, faltaNaTarefa, idade, pct, plural, prioridadeDoPainel, recorte, turnosDoModelo,
} from './gestao';
import { carregarChart, configDoBurndown, configDoPareto, configDosTurnos, padroes } from './graficos';
import { Recados } from './Recados';
import type { DadosDoPainel } from './tipos';
import './passagem.css';

/** ``{{ meta }}`` de um float no Jinja: "95.0", não "95". */
function metaComoNoPython(v: number) {
  return Number.isInteger(v) ? v.toFixed(1) : String(v);
}

type Resposta = { ok: boolean; x: { error?: string; url?: string } };

function json(r: Response): Promise<Resposta> {
  return r.json().then((x) => ({ ok: r.ok, x }), () => ({ ok: false, x: {} }));
}

/** A ajuda do ícone (?). A tela antiga usa o tooltip do Bootstrap; aqui o
 * toque (ou o Enter) mostra e esconde o texto logo abaixo, e o mouse vê o
 * ``title`` — no celular não há "passar o mouse". */
function Ajuda({ texto }: { texto: string }) {
  const [aberta, setAberta] = useState(false);
  return (
    <>
      <span className="dop-help text-muted" role="button" tabIndex={0} title={texto} aria-label={texto}
        aria-expanded={aberta} onClick={() => setAberta(!aberta)}
        onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); setAberta(!aberta); } }}>
        {' '}<i className="bi bi-question-circle"></i></span>
      {aberta && <span className="d-block small text-muted mt-1">{texto}</span>}
    </>
  );
}

/** Um gráfico do Chart.js, desenhado depois que a biblioteca carrega. */
function Grafico({ id, altura, config }: { id: string; altura: number; config: (el: HTMLCanvasElement) => unknown }) {
  const tela = useRef<HTMLCanvasElement>(null);
  const montar = useRef(config);
  useEffect(() => {
    let vivo = true;
    let grafico: { destroy(): void } | null = null;
    carregarChart().then(() => {
      if (!vivo || !window.Chart || !tela.current) return;
      padroes();
      grafico = new window.Chart(tela.current, montar.current(tela.current));
    });
    return () => { vivo = false; if (grafico) grafico.destroy(); };
  }, []);
  return <canvas id={id} height={altura} ref={tela}></canvas>;
}

/** O modal no desenho do Bootstrap (a casca não carrega o JS dele). */
function Janela({ id, titulo, centrado, fechar, rodape, children }: {
  id: string; titulo: string; centrado?: boolean; fechar: () => void; rodape: ReactNode; children: ReactNode;
}) {
  const caixa = useRef<HTMLDivElement>(null);
  useEffect(() => {
    document.body.classList.add('modal-open');
    caixa.current?.focus();
    const tecla = (ev: KeyboardEvent) => { if (ev.key === 'Escape') fechar(); };
    document.addEventListener('keydown', tecla);
    return () => {
      document.body.classList.remove('modal-open');
      document.removeEventListener('keydown', tecla);
    };
  }, [fechar]);
  return (
    <>
      <div className="modal fade show d-block" id={id} tabIndex={-1} role="dialog" aria-modal="true"
        aria-labelledby={id + '-titulo'} ref={caixa}
        onClick={(ev) => { if (ev.target === ev.currentTarget) fechar(); }}>
        <div className={'modal-dialog' + (centrado ? ' modal-dialog-centered' : '')}><div className="modal-content">
          <div className="modal-header">
            <h5 className="modal-title" id={id + '-titulo'}>{titulo}</h5>
            <button type="button" className="btn-close" aria-label="Fechar" onClick={fechar}></button>
          </div>
          <div className="modal-body">{children}</div>
          <div className="modal-footer">{rodape}</div>
        </div></div>
      </div>
      <div className="modal-backdrop fade show"></div>
    </>
  );
}

function ModalPendencia({ cliente, fechar }: { cliente: number; fechar: () => void }) {
  const [titulo, setTitulo] = useState('');
  const [descricao, setDescricao] = useState('');
  const [prioridade, setPrioridade] = useState('media');
  const salvar = () => {
    enviarBruto('/passagem-de-turno/api/pendencias', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: cliente, titulo, descricao, prioridade }),
    }).then(json).then((res) => {
      if (!res.ok) { window.alert(res.x.error || 'Não foi possível salvar.'); return; }
      window.location.reload();
    });
  };
  return (
    <Janela id="modalPendencia" titulo="Deixar pendência para a operação" fechar={fechar}
      rodape={<button className="btn btn-primary" type="button" data-acao="criarPendenciaGestor"
        onClick={salvar}>Salvar</button>}>
      <label className="form-label" htmlFor="gestor-p-title">Pendência</label>
      <input id="gestor-p-title" className="form-control mb-2" value={titulo}
        onChange={(ev) => setTitulo(ev.target.value)} />
      <label className="form-label" htmlFor="gestor-p-desc">Descrição</label>
      <textarea id="gestor-p-desc" className="form-control mb-2" value={descricao}
        onChange={(ev) => setDescricao(ev.target.value)}></textarea>
      <label className="form-label" htmlFor="gestor-p-priority">Prioridade</label>
      <select id="gestor-p-priority" className="form-select" value={prioridade}
        onChange={(ev) => setPrioridade(ev.target.value)}>
        <option value="baixa">Baixa</option>
        <option value="media">Média</option>
        <option value="alta">Alta</option>
      </select>
    </Janela>
  );
}

/** A tarefa para um turno: a EXCEÇÃO ("no 2º turno de quinta, confira a
 * câmara"), com dono (o turno) e data, que volta respondida. A forma de
 * resposta é escolhida por quem pede. */
function ModalTarefa({ dados, fechar }: { dados: DadosDoPainel; fechar: () => void }) {
  const [area, setArea] = useState(dados.modelos.length ? String(dados.modelos[0].id) : '');
  const turnos = turnosDoModelo(dados.modelos, area);
  const [turno, setTurno] = useState(turnos[0] || '');
  const [dia, setDia] = useState(dados.hoje);
  const [titulo, setTitulo] = useState('');
  const [descricao, setDescricao] = useState('');
  const [forma, setForma] = useState('sim_nao');
  const [ocupado, setOcupado] = useState(false);
  const trocarArea = (v: string) => { setArea(v); setTurno(turnosDoModelo(dados.modelos, v)[0] || ''); };
  const enviar = () => {
    const falta = faltaNaTarefa(area, turno, titulo);
    if (falta) { window.alert(falta); return; }
    setOcupado(true);
    enviarBruto('/passagem-de-turno/api/tarefas-turno', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: Number(dados.client_id || 0), configuracao_id: area, data_turno: dia, turno,
        titulo, descricao, forma_resposta: forma }),
    }).then((r) => r.json().then((x) => ({ ok: r.ok, x })))
      .then((res) => {
        if (!res.ok) { window.alert(res.x.error || 'Não foi possível atribuir.'); setOcupado(false); return; }
        window.location.reload();
      }).catch(() => { window.alert('Falha de rede.'); setOcupado(false); });
  };
  return (
    <Janela id="modalTarefaTurno" titulo="Tarefa para um turno" centrado fechar={fechar} rodape={<>
      <button className="btn btn-light" type="button" onClick={fechar}>Cancelar</button>
      <button className="btn btn-primary" type="button" id="tt-enviar" data-acao="ttCriarTarefa" disabled={ocupado}
        onClick={enviar}>Atribuir ao turno</button>
    </>}>
      <p className="text-muted small">
        Ela aparece na passagem daquele turno, e volta respondida — ou vira
        pendência, se não for possível fazer.
      </p>
      <div className="row g-2">
        <div className="col-12 tsel">
          <label htmlFor="tt-area">Área</label>
          <select className="form-select" id="tt-area" value={area} onChange={(ev) => trocarArea(ev.target.value)}>
            {dados.modelos.length
              ? dados.modelos.map((m) => <option value={m.id} key={m.id}>{m.nome}</option>)
              : <option value="">Nenhum modelo ativo neste contrato</option>}
          </select>
        </div>
        <div className="col-6 tsel">
          <label htmlFor="tt-data">Dia</label>
          <input type="date" className="form-control" id="tt-data" value={dia} onChange={(ev) => setDia(ev.target.value)} />
        </div>
        <div className="col-6 tsel">
          <label htmlFor="tt-turno">Turno</label>
          <select className="form-select" id="tt-turno" value={turno} onChange={(ev) => setTurno(ev.target.value)}>
            {/* Modelo sem turno cadastrado: em vez de um select vazio, que não
                explica nada, a tela diz onde se resolve isso. */}
            {turnos.length
              ? turnos.map((t) => <option value={t} key={t}>{t}</option>)
              : <option value="">— nenhum turno no modelo —</option>}
          </select>
        </div>
      </div>
      <div className="tsel mt-2">
        <label htmlFor="tt-titulo">O que precisa ser feito</label>
        <input type="text" className="form-control" id="tt-titulo" maxLength={300} value={titulo}
          placeholder="Ex.: Conferir a bomba da caixa d’água depois do reparo"
          onChange={(ev) => setTitulo(ev.target.value)} />
      </div>
      <div className="tsel mt-2">
        <label htmlFor="tt-desc">Detalhe <span className="fw-normal text-muted">(opcional)</span></label>
        <textarea className="form-control" id="tt-desc" rows={2} value={descricao}
          onChange={(ev) => setDescricao(ev.target.value)}></textarea>
      </div>
      <div className="tsel mt-2">
        <label htmlFor="tt-forma">Como o turno deve responder</label>
        <select className="form-select" id="tt-forma" value={forma} onChange={(ev) => setForma(ev.target.value)}>
          <option value="sim_nao">Sim ou não</option>
          <option value="numero">Um número</option>
          <option value="texto">Uma descrição</option>
        </select>
        <div className="tsel-ajuda">
          Escolha "um número" quando o valor for o ponto — "ok" não entra em
          série, "-18,4" entra.
        </div>
      </div>
    </Janela>
  );
}

/** O recorte no topo: cliente, período, área e turno. Recolhido, e o resumo
 * mostra o recorte FECHADO. Trocar um seletor já aplica (como a antiga,
 * que envia o formulário); o par De/Até só com "Aplicar". */
function Filtros({ dados }: { dados: DadosDoPainel }) {
  const navegar = useNavigate();
  const [periodo, setPeriodo] = useState(dados.periodo);
  const [de, setDe] = useState(dados.de);
  const [ate, setAte] = useState(dados.ate);
  const d = dados.dados;
  const comArea = !!(d && d.areas_disponiveis.length);
  const escondido = periodo !== 'custom';
  const valores = {
    client_id: String(dados.client_id ?? ''), periodo, de, ate,
    area_id: String(dados.area_sel), turno: dados.turno_sel,
  };
  // Os mesmos campos, na mesma ordem, que o formulário antigo envia.
  const aplicar = (troca: Partial<typeof valores>) => {
    const v = { ...valores, ...troca };
    const q = new URLSearchParams();
    if (dados.clients.length) q.set('client_id', v.client_id);
    q.set('periodo', v.periodo);
    q.set('de', v.de);
    q.set('ate', v.ate);
    if (comArea) q.set('area_id', v.area_id);
    q.set('turno', v.turno);
    navegar({ search: '?' + q.toString() });
  };
  return (
    <details className="pg-filtros">
      <summary>
        <i className="bi bi-funnel"></i> Filtros
        <span className="pg-recorte"> {recorte(dados)}</span>
      </summary>
      <form className="pg-filtros-corpo" method="get" id="dopFiltros"
        onSubmit={(ev) => { ev.preventDefault(); aplicar({}); }}>
        <div className="tsel">
          <label htmlFor="dopCliente">Cliente</label>
          <select className="form-select" id="dopCliente" name="client_id" value={valores.client_id}
            onChange={(ev) => aplicar({ client_id: ev.target.value })}>
            {dados.clients.map((c) => <option value={c.id} key={c.id}>{c.nome}</option>)}
          </select>
        </div>
        <div className="tsel">
          <label htmlFor="dopPeriodo">Período</label>
          {/* O par de datas só aparece em "Personalizado" — e o formulário não
              pode se aplicar enquanto a pessoa ainda escolhe De/Até. */}
          <select className="form-select" name="periodo" id="dopPeriodo" value={periodo}
            onChange={(ev) => {
              setPeriodo(ev.target.value);
              if (ev.target.value !== 'custom') aplicar({ periodo: ev.target.value });
            }}>
            {dados.periodos.map(([k, r]) => <option value={k} key={k}>{r}</option>)}
          </select>
        </div>
        <div className="tsel dop-custom" hidden={escondido}>
          <label htmlFor="dopDe">De</label>
          <input type="date" className="form-control" id="dopDe" name="de" value={de}
            onChange={(ev) => setDe(ev.target.value)} />
        </div>
        <div className="tsel dop-custom" hidden={escondido}>
          <label htmlFor="dopAte">Até</label>
          <input type="date" className="form-control" id="dopAte" name="ate" value={ate}
            onChange={(ev) => setAte(ev.target.value)} />
        </div>
        {/* A área só vira filtro quando o contrato tem área cadastrada. */}
        {comArea && (
          <div className="tsel">
            <label htmlFor="dopArea">Área</label>
            <select className="form-select" id="dopArea" name="area_id" value={valores.area_id}
              onChange={(ev) => aplicar({ area_id: ev.target.value })}>
              <option value={dados.todas_as_areas}>Todas</option>
              {d!.areas_disponiveis.map((a) => <option value={a.id} key={a.id}>{a.nome}</option>)}
            </select>
          </div>
        )}
        <div className="tsel">
          <label htmlFor="dopTurno">Turno</label>
          <select className="form-select" id="dopTurno" name="turno" value={valores.turno}
            onChange={(ev) => aplicar({ turno: ev.target.value })}>
            <option value="todos">Todos</option>
            {(d ? d.turnos_disponiveis : []).map((n) => <option value={n} key={n}>{n}</option>)}
          </select>
        </div>
        <div className="dop-custom d-flex align-items-end" hidden={escondido}>
          <button className="btn btn-outline-primary w-100" type="submit">Aplicar</button>
        </div>
      </form>
    </details>
  );
}

export function Painel({ dados }: { dados: DadosDoPainel }) {
  const [modal, setModal] = useState<'pendencia' | 'tarefa' | null>(null);
  const fechar = useRef(() => setModal(null)).current;
  const d = dados.dados;

  // A nota é obrigatória aqui também: o gestor que baixa a pendência pelo
  // painel deve a mesma frase que se pede ao encarregado.
  const resolver = (id: number) => {
    let texto = window.prompt('O que foi feito para resolver?');
    if (texto === null) return;
    texto = texto.trim();
    if (!texto) { window.alert('Diga em uma linha o que foi feito.'); return; }
    enviarBruto('/passagem-de-turno/api/pendencias/' + id + '/resolver', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ resolucao: texto }),
    }).then(json).then((res) => {
      if (!res.ok) { window.alert(res.x.error || 'Não foi possível resolver.'); return; }
      window.location.reload();
    });
  };

  // Ocorrência → chamado de manutenção. O botão é desabilitado no clique; a
  // resposta que não é JSON (sem sinal, sessão vencida) devolve o botão e diz
  // o que houve.
  const abrirChamado = (id: number, botao: HTMLButtonElement) => {
    botao.disabled = true;
    const falhou = (msg: string) => { botao.disabled = false; window.alert(msg); };
    enviarBruto('/passagem-de-turno/api/ocorrencias/' + id + '/chamado', { method: 'POST' })
      .then(json).then((res) => {
        if (!res.ok) {
          falhou(res.x.error || 'Não foi possível abrir o chamado. Recarregue a página e tente de novo.');
          return;
        }
        window.location.assign(res.x.url || '/chamados/');
      }, () => falhou('Sem conexão: o chamado não foi aberto. Tente de novo quando o sinal voltar.'));
  };

  const comAcao = dados.pode_chamado || (dados.pode_ver_chamado && !!d && d.ocorrencias.some((o) => o.chamado));
  const nDias = d ? d.burndown.labels.length : 0;

  return (
    <>
      <nav aria-label="breadcrumb"><ol className="breadcrumb">
        <li className="breadcrumb-item active">Passagem de Turno</li>
      </ol></nav>
      <Recados />
      <div className="container-fluid py-3 diario-page" data-tela-pronta="painel">

        <div className="pg-topo">
          <div>
            <div className="pg-olho">{dados.nome_do_sistema.toUpperCase()}</div>
            <h1 className="pg-titulo">Passagem de Turno</h1>
            <div className="pg-sub">O turno, as pendências e as ocorrências num histórico só.</div>
          </div>
          {/* Só para quem GRAVA na Passagem: a diretoria (só leitura) lê o painel. */}
          {dados.pode_gravar && (
            <a className="btn btn-primary px-3" href={dados.links.nova_passagem}>
              <i className="bi bi-plus-lg"></i> Nova passagem</a>
          )}
        </div>

        <div className="pg-acoes">
          {dados.client_id && dados.links.relatorio && (
            <a className="btn btn-outline-secondary btn-sm" href={dados.links.relatorio}>
              <i className="bi bi-file-earmark-pdf"></i> Relatório mensal</a>
          )}
          {dados.e_gestao && (
            <>
              <button className="btn btn-outline-primary btn-sm" type="button" onClick={() => setModal('pendencia')}>
                <i className="bi bi-flag"></i> Deixar pendência</button>
              <button className="btn btn-outline-primary btn-sm" type="button" onClick={() => setModal('tarefa')}>
                <i className="bi bi-clipboard-plus"></i> Tarefa para um turno</button>
            </>
          )}
          {/* O botão pergunta pela PERMISSÃO, e não pelo perfil. */}
          {dados.pode_configurar && (
            <a className="btn btn-light btn-sm so-computador" href={dados.links.configurar}>
              <i className="bi bi-sliders"></i> Configurar</a>
          )}
        </div>

        <Filtros dados={dados} />

        {!dados.client_id || !d ? (
          <div className="card shadow-sm border-0"><div className="dop-vazio">
            Você ainda não tem nenhum contrato liberado. Peça ao administrador para
            vincular os seus contratos ao seu cadastro.</div></div>
        ) : (
          <>
            <div className="dop-gov mb-3">
              <i className="bi bi-calendar3"></i>
              <span><strong>{d.periodo_label}</strong> ({d.inicio} a {d.fim})
                {d.turno !== 'todos' && <> · turno <strong>{d.turno}</strong></>}
                {' '}· <strong>{d.n_turnos}</strong> {d.n_turnos === 1 ? 'turno encerrado' : 'turnos encerrados'} no recorte</span>
              <span className="text-muted">Turno em aberto não entra nos indicadores — ainda é rascunho do encarregado.</span>
            </div>

            {/* ── Os quatro indicadores mestres ── */}
            <div className="row g-3 mb-3" id="dopHero">
              <div className="col-xl-3 col-md-6">
                <div className="dop-hero">
                  <div className="dop-hero-label">Aderência às rotinas obrigatórias</div>
                  <div className="dop-hero-value">
                    {pct(d.aderencia.pct)}
                    {' '}<span className={`dop-tag ${d.aderencia.faixa} align-middle ms-1`}>{faixaDoPainel(d.aderencia.faixa)}</span>
                  </div>
                  <div className="dop-track">
                    <div className={`dop-fill ${d.aderencia.faixa}`} style={{ width: (d.aderencia.pct || 0) + '%' }}></div>
                  </div>
                  <div className="dop-meta">
                    <span className="dop-meta-mark" style={{ left: d.aderencia.meta + '%' }}
                      title={`Meta ${metaComoNoPython(d.aderencia.meta)}%`}></span>
                  </div>
                  <div className="dop-hero-sub">
                    {d.aderencia.cumpridas} de {plural(d.aderencia.exigidas, 'atividade', 'atividades')} ·
                    meta {Math.trunc(d.aderencia.meta)}%</div>
                </div>
              </div>

              <div className="col-xl-3 col-md-6">
                <div className="dop-hero">
                  <div className="dop-hero-label">Taxa de resolução de pendências</div>
                  <div className="dop-hero-value">{pct(d.resolucao.pct)}</div>
                  <div className="dop-track">
                    <div className={`dop-fill ${d.resolucao.faixa}`} style={{ width: (d.resolucao.pct || 0) + '%' }}></div>
                  </div>
                  <div className="dop-hero-sub">
                    {plural(d.resolucao.abertas, 'aberta', 'abertas')} | {plural(d.resolucao.resolvidas, 'resolvida', 'resolvidas')}
                    <Ajuda texto="Da safra do período: das pendências abertas nesta janela, quantas já foram baixadas. Mutirão de backlog antigo não infla este número." />
                  </div>
                </div>
              </div>

              <div className="col-xl-3 col-md-6">
                <div className="dop-hero">
                  <div className="dop-hero-label">Pendências críticas e vencidas</div>
                  <div className={'dop-hero-value' + (d.n_criticas ? ' critico' : '')}>{d.n_criticas}</div>
                  <div className="dop-hero-sub">
                    Prioridade alta ou paradas há mais de 24h, em aberto agora
                    <Ajuda texto="Este cartão ignora o filtro de período de propósito: pendência velha em aberto é problema de hoje, e esconder por ter nascido fora da janela seria o erro que ele existe para evitar." />
                  </div>
                </div>
              </div>

              <div className="col-xl-3 col-md-6">
                <div className="dop-hero">
                  <div className="dop-hero-label">Índice de ocorrências por turno</div>
                  <div className="dop-hero-value">
                    {d.indice_ocorrencias.valor === null ? '—' : decimal(d.indice_ocorrencias.valor, 2)}
                    {' '}<span className="fs-6 fw-normal text-muted">ocorrências/turno</span>
                  </div>
                  <div className="dop-hero-sub">
                    {plural(d.indice_ocorrencias.ocorrencias, 'ocorrência', 'ocorrências')} ÷{' '}
                    {plural(d.indice_ocorrencias.turnos, 'turno', 'turnos')}
                    {d.indice_ocorrencias.delta !== null && (d.indice_ocorrencias.delta > 0
                      ? <> <span className="dop-tag critico ms-1">▲ {decimal(d.indice_ocorrencias.delta, 2)} vs. janela anterior</span></>
                      : d.indice_ocorrencias.delta < 0
                        ? <> <span className="dop-tag ok ms-1">▼ {decimal(-d.indice_ocorrencias.delta, 2)} vs. janela anterior</span></>
                        : <> <span className="dop-tag neutro ms-1">estável</span></>)}
                  </div>
                </div>
              </div>
            </div>

            {/* ── Gráficos: onde dói, em que turno, e se a fila anda ── */}
            <div className="row g-3 mb-3">
              <div className="col-xl-6">
                <div className="card shadow-sm border-0 h-100">
                  <div className="card-header bg-white fw-bold d-flex justify-content-between align-items-center">
                    <span>Pareto de ocorrências por categoria</span>
                    <span className="small text-muted fw-normal">vermelho = 80% do volume</span>
                  </div>
                  <div className="card-body">
                    {d.pareto.length
                      ? <Grafico id="dopPareto" altura={60 + d.pareto.length * 34}
                        config={(el) => configDoPareto(d.pareto, () => el.clientWidth)} />
                      : <div className="dop-vazio">Nenhuma ocorrência no período.</div>}
                  </div>
                </div>
              </div>
              <div className="col-xl-6">
                <div className="card shadow-sm border-0 h-100">
                  <div className="card-header bg-white fw-bold">Eficiência entre turnos</div>
                  <div className="card-body">
                    {d.turnos_comparativo.length
                      ? <Grafico id="dopTurnos" altura={240} config={() => configDosTurnos(d.turnos_comparativo)} />
                      : <div className="dop-vazio">Nenhum turno encerrado no período.</div>}
                  </div>
                </div>
              </div>
            </div>

            <div className="row g-3 mb-3">
              <div className="col-xl-7">
                <div className="card shadow-sm border-0 h-100">
                  <div className="card-header bg-white fw-bold d-flex justify-content-between align-items-center">
                    <span>Evolução diária de pendências</span>
                    <span className="small text-muted fw-normal">
                      {nDias === 1 ? 'último dia' : `últimos ${nDias} dias`}</span>
                  </div>
                  <div className="card-body"><Grafico id="dopBurndown" altura={190} config={() => configDoBurndown(d.burndown)} /></div>
                </div>
              </div>
              <div className="col-xl-5">
                <div className="card shadow-sm border-0 h-100">
                  <div className="card-header bg-white fw-bold d-flex justify-content-between align-items-center">
                    <span>Raio-X do checklist</span>
                    <span className="small text-muted fw-normal">pior primeiro</span>
                  </div>
                  <div className="card-body">
                    {d.rotinas.length ? d.rotinas.map((r) => (
                      <div className="dop-rot" key={r.codigo}>
                        <div>
                          <div className="dop-rot-nome">{r.nome}</div>
                          <div className="dop-track mt-1">
                            <div className={`dop-fill ${r.faixa}`} style={{ width: (r.pct || 0) + '%' }}></div>
                          </div>
                        </div>
                        <div className="small text-muted">{r.cumprida}/{r.exigida}</div>
                        {/* Uma casa decimal, como os cartões de cima. */}
                        <div className="dop-rot-pct">
                          {pct(r.pct)}
                          {r.faixa === 'critico' && <i className="bi bi-exclamation-triangle-fill text-danger ms-1"
                            title="Gargalo de rotina"></i>}
                        </div>
                      </div>
                    )) : <div className="dop-vazio">Nenhuma atividade obrigatória exigida no período.</div>}
                  </div>
                </div>
              </div>
            </div>

            {/* ── O que fazer agora ── */}
            <div className="row g-3">
              <div className="col-xl-7">
                <div className="card shadow-sm border-0 h-100">
                  <div className="card-header bg-white fw-bold">Ocorrências do período</div>
                  <div className="table-responsive">
                    <table className="table align-middle mb-0 tab-cartao">
                      <thead><tr><th>Quando</th><th>Tipo</th><th>Referência</th>
                        <th>Descrição</th>{comAcao && <th className="text-end">Ação</th>}</tr></thead>
                      <tbody>
                        {d.ocorrencias.length ? d.ocorrencias.map((o) => (
                          <tr key={o.id}>
                            <td className="text-nowrap small" data-rot="Quando">
                              {o.quando.dia || '—'}{o.quando.turno && ` · ${o.quando.turno}`}</td>
                            <td data-rot="Tipo">
                              <span className={'badge ' + (o.gravidade === 'critica' ? 'text-bg-warning' : 'text-bg-light border')}
                                title={o.gravidade === 'critica' ? 'Ponto de atenção' : undefined}>{o.tipo}</span></td>
                            <td className="small text-muted" data-rot="Referência">{o.referencia || '—'}</td>
                            <td className="small" data-rot="Descrição">{o.descricao}</td>
                            {comAcao && (
                              <td className="text-end" data-rot="">
                                {/* Ocorrência que já virou chamado mostra a OS e a situação dela. */}
                                {o.chamado ? (
                                  <a className="btn btn-sm btn-outline-secondary text-nowrap dop-os" href={o.chamado.url}>
                                    <i className="bi bi-box-arrow-up-right"></i> Ver {o.chamado.numero}
                                    {' '}<span className="small text-muted">({o.chamado.status_rotulo})</span></a>
                                ) : dados.pode_chamado && (
                                  <button className="btn btn-sm btn-outline-primary text-nowrap" type="button"
                                    data-acao="dopAbrirChamado" onClick={(ev) => abrirChamado(o.id, ev.currentTarget)}>
                                    <i className="bi bi-tools"></i> Abrir chamado</button>
                                )}
                              </td>
                            )}
                          </tr>
                        )) : (
                          <tr><td colSpan={comAcao ? 5 : 4} className="dop-vazio">Nenhuma ocorrência no período.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              <div className="col-xl-5">
                <div className="card shadow-sm border-0 mb-3">
                  <div className="card-header bg-white fw-bold">Pendências críticas e vencidas</div>
                  <div className="list-group list-group-flush">
                    {d.criticas.length ? d.criticas.map((c) => (
                      <div className={'list-group-item dop-crit' + (c.alta && !c.vencida ? ' so-alta' : '')} key={c.id}>
                        <div className="d-flex justify-content-between align-items-start gap-2">
                          <strong className="small">{c.titulo}</strong>
                          <span className={'dop-tag ' + (c.vencida ? 'critico' : 'alerta')}>{idade(c.dias, c.horas)}</span>
                        </div>
                        <div className="small text-muted">{c.descricao || 'Sem descrição'}</div>
                        <div className="small">
                          <span className={'dop-tag ' + (c.alta ? 'critico' : 'neutro')}>{prioridadeDoPainel(c.prioridade)}</span>
                          {/* Só para quem pode GRAVAR na Passagem. */}
                          {dados.pode_gravar && (
                            <button className="btn btn-sm btn-link p-0 ms-2" type="button" data-acao="resolverPendenciaDop"
                              onClick={() => resolver(c.id)}>marcar resolvida</button>
                          )}
                        </div>
                      </div>
                    )) : <div className="dop-vazio">Nenhuma pendência crítica ou vencida. Fila limpa.</div>}
                  </div>
                </div>

                <div className="card shadow-sm border-0">
                  <div className="card-header bg-white fw-bold">Últimos turnos do período</div>
                  <div className="table-responsive">
                    <table className="table table-sm align-middle mb-0 tab-cartao">
                      <thead><tr><th>Data</th><th>Área</th><th>Turno</th><th>Status</th><th></th></tr></thead>
                      <tbody>
                        {dados.turnos.length ? dados.turnos.map((t) => (
                          <tr key={t.id}>
                            <td className="small" data-rot="Data">{t.data}</td>
                            <td className="small" data-rot="Área">{t.area || '—'}</td>
                            <td className="small" data-rot="Turno">{t.turno}</td>
                            <td data-rot="Status"><span className={'badge text-bg-' + (t.status === 'encerrado' ? 'success' : 'warning')}>
                              {t.status}</span></td>
                            <td className="text-end" data-rot="">
                              <a className="btn btn-sm btn-link p-0" href={dados.links.ver_turno + t.id}>abrir</a>
                            </td>
                          </tr>
                        )) : <tr><td colSpan={5} className="dop-vazio">Nenhum turno registrado no período.</td></tr>}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {dados.e_gestao && modal === 'pendencia' && <ModalPendencia cliente={Number(dados.client_id || 0)} fechar={fechar} />}
      {dados.e_gestao && modal === 'tarefa' && <ModalTarefa dados={dados} fechar={fechar} />}
    </>
  );
}
