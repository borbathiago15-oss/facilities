// O relatório executivo mensal da Passagem de turno (Fase 2b da migração
// para React; a tela antiga é templates/diario_operacional/
// relatorio_mensal.html, com os mesmos textos e as mesmas classes).
//
// O fechamento da competência, no padrão que vai para a Diretoria e para o
// cliente: o número, a rotina, a pendência, o desvio e o fato relevante. A
// tela e o PDF saem do MESMO ``fechamento_mensal``; o PDF continua no
// servidor (o link "Baixar PDF" é o da rota de sempre, com a área da tela).
import { useNavigate } from 'react-router';
import { faixaDoRelatorio, parada, pct, plural, prioridadeDoRelatorio } from './gestao';
import type { DadosDoRelatorio } from './tipos';
import './passagem.css';

export function Relatorio({ dados }: { dados: DadosDoRelatorio }) {
  const navegar = useNavigate();
  const { rel, cliente } = dados;
  const pend = rel.pendencias;
  const oc = rel.ocorrencias;
  // Trocar mês, ano ou área já aplica (a antiga envia o formulário sozinha),
  // com os mesmos campos na mesma ordem.
  const aplicar = (troca: { area_id?: string; mes?: string; ano?: string }) => {
    const q = new URLSearchParams();
    q.set('client_id', String(cliente.id));
    if (dados.areas.length) q.set('area_id', troca.area_id ?? String(dados.area_sel));
    q.set('mes', troca.mes ?? String(dados.mes));
    q.set('ano', troca.ano ?? String(dados.ano));
    navegar({ search: '?' + q.toString() });
  };

  return (
    <>
      <nav aria-label="breadcrumb"><ol className="breadcrumb">
        <li className="breadcrumb-item"><a href={dados.links.painel}>Passagem de Turno</a></li>
        <li className="breadcrumb-item active">Relatório mensal</li>
      </ol></nav>
      <div className="container-fluid py-3 diario-page rm-doc" data-tela-pronta="relatorio">

        <div className="rm-noprint d-flex justify-content-between align-items-end mb-3 gap-2 flex-wrap">
          <form className="row g-2 align-items-end" method="get" onSubmit={(ev) => { ev.preventDefault(); aplicar({}); }}>
            {/* O relatório da Expedição e o do Almoxarifado são documentos
                diferentes. O seletor só aparece quando o contrato tem área. */}
            {dados.areas.length > 0 && (
              <div className="col-auto">
                <label className="form-label small text-muted mb-1" htmlFor="rm-area">Área</label>
                <select className="form-select" name="area_id" id="rm-area" value={dados.area_sel}
                  onChange={(ev) => aplicar({ area_id: ev.target.value })}>
                  <option value={dados.todas_as_areas}>Todas as áreas</option>
                  {dados.areas.map((a) => <option value={a.id} key={a.id}>{a.nome}</option>)}
                </select>
              </div>
            )}
            <div className="col-auto">
              <label className="form-label small text-muted mb-1" htmlFor="rm-mes">Mês</label>
              <select className="form-select" name="mes" id="rm-mes" value={dados.mes}
                onChange={(ev) => aplicar({ mes: ev.target.value })}>
                {dados.meses.map(([n, nome]) => <option value={n} key={n}>{nome}</option>)}
              </select>
            </div>
            <div className="col-auto">
              <label className="form-label small text-muted mb-1" htmlFor="rm-ano">Ano</label>
              <select className="form-select" name="ano" id="rm-ano" value={dados.ano}
                onChange={(ev) => aplicar({ ano: ev.target.value })}>
                {dados.anos.map((a) => <option value={a} key={a}>{a}</option>)}
              </select>
            </div>
          </form>
          <div className="d-flex gap-2">
            <a className="btn btn-outline-secondary" href={dados.links.painel}>Voltar</a>
            {/* O PDF leva a ÁREA que está na tela. */}
            <a className="btn btn-primary" href={dados.links.pdf}>
              <i className="bi bi-file-earmark-pdf"></i> Baixar PDF</a>
          </div>
        </div>

        {/* ── Cabeçalho institucional ── */}
        <div className="rm-cabeca">
          <div>
            <div className="rm-marca">Grupo Trino · Facilities</div>
            <h1>Passagem de Turno — Relatório Executivo Mensal</h1>
            <div className="rm-sub">{cliente.nome}{rel.area && ` · ${rel.area}`} ·
              Competência {rel.competencia}</div>
          </div>
          <div className="rm-sub text-end">
            Emitido em {rel.emitido_em}<br />
            por {rel.emitido_por}<br />
            {/* No mês em curso o período vai até hoje. */}
            {rel.fim_apurado
              ? <>Período apurado: {rel.inicio} a {rel.fim_apurado}{rel.em_andamento && ' (competência em andamento)'}</>
              : 'Competência ainda não iniciada'}
          </div>
        </div>

        {/* ── Bloco 1: scorecard consolidado ── */}
        <div className="rm-bloco">
          <h2>1. Scorecard consolidado do mês</h2>
          <div className="row g-3">
            <div className="col-lg-3 col-md-6">
              <div className="rm-big">
                <div className="rm-big-label">Turnos concluídos</div>
                <div className="rm-big-value">{rel.turnos.total}</div>
                <div className="rm-big-sub">
                  {rel.turnos.por_turno.length
                    ? rel.turnos.por_turno.map(([nome, qtd]) => `${nome}: ${qtd}`).join(' | ')
                    : 'Nenhum turno encerrado na competência'}
                </div>
              </div>
            </div>
            <div className="col-lg-3 col-md-6">
              <div className="rm-big">
                <div className="rm-big-label">Aderência global às rotinas</div>
                <div className="rm-big-value">{pct(rel.aderencia.pct)}
                  {' '}<span className={`rm-tag ${rel.aderencia.faixa} align-middle`}>{faixaDoRelatorio(rel.aderencia.faixa)}</span>
                </div>
                <div className="rm-big-sub">{rel.aderencia.cumpridas} de {rel.aderencia.exigidas}
                  {' '}atividades obrigatórias · meta {Math.trunc(rel.aderencia.meta)}%</div>
              </div>
            </div>
            <div className="col-lg-3 col-md-6">
              <div className="rm-big">
                <div className="rm-big-label">Eficácia na resolução de pendências</div>
                <div className="rm-big-value">{pct(pend.pct)}</div>
                <div className="rm-big-sub">{pend.resolvidas} resolvidas de
                  {' '}{pend.abertas} abertas no mês</div>
              </div>
            </div>
            <div className="col-lg-3 col-md-6">
              <div className="rm-big">
                <div className="rm-big-label">Ocorrências e desvios</div>
                <div className="rm-big-value">{oc.total}</div>
                <div className="rm-big-sub">
                  {oc.mais_frequente
                    ? `Mais frequente: ${oc.mais_frequente.tipo} (${oc.mais_frequente.qtd})`
                    : 'Nenhum desvio registrado'}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Bloco 2: mapa de aderência ── */}
        <div className="rm-bloco">
          <h2>2. Mapa de aderência às rotinas obrigatórias</h2>
          <div className="card shadow-sm border-0">
            <div className="table-responsive">
              <table className="table align-middle mb-0 tab-cartao">
                <thead><tr>
                  <th>Atividade</th><th className="text-end">Exigida no mês</th>
                  <th className="text-end">Cumprida no mês</th><th className="text-end">% Aderência</th>
                  <th className="text-end">Status</th>
                </tr></thead>
                <tbody>
                  {rel.rotinas.length ? rel.rotinas.map((r) => (
                    <tr key={r.codigo}>
                      <td data-rot="Atividade">{r.nome}</td>
                      <td className="text-end" data-rot="Exigida">{r.exigida}</td>
                      <td className="text-end" data-rot="Cumprida">{r.cumprida}</td>
                      <td className="text-end fw-bold" data-rot="Aderência">{pct(r.pct)}</td>
                      <td className="text-end" data-rot="Status"><span className={`rm-tag ${r.faixa}`}>{faixaDoRelatorio(r.faixa)}</span></td>
                    </tr>
                  )) : (
                    <tr><td colSpan={5} className="rm-vazio">
                      Nenhuma atividade obrigatória exigida na competência.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* ── Bloco 3: gestão de pendências ── */}
        <div className="rm-bloco">
          <h2>3. Gestão de pendências da operação</h2>
          <div className="row g-3">
            <div className="col-lg-6">
              <div className="card shadow-sm border-0 h-100">
                <div className="card-header bg-white fw-bold">
                  Resolvidas <span className="rm-tag ok">{pend.resolvidas}</span></div>
                <div className="table-responsive">
                  <table className="table table-sm align-middle mb-0 tab-cartao">
                    <thead><tr><th>Pendência</th><th>Prior.</th><th>Turno</th><th>Encerrada</th><th>Responsável</th></tr></thead>
                    <tbody>
                      {pend.lista_resolvidas.length ? pend.lista_resolvidas.map((l, n) => (
                        <tr key={n}>
                          <td className="small cel-pilha" data-rot="Pendência">{l.titulo}
                            {l.referencia && <> <span className="rm-ref">{l.referencia}</span></>}
                            {/* O que foi feito: sumir da fila não é ter sido resolvida. */}
                            {l.resolucao && <div className="rm-resol">{l.resolucao}</div>}
                          </td>
                          <td data-rot="Prioridade"><span className="rm-tag neutro">{prioridadeDoRelatorio(l.prioridade)}</span></td>
                          <td className="small cel-pilha" data-rot="Turno">{l.turno}
                            {l.passagens > 0 && <div className="text-muted">passou por {plural(l.passagens, 'turno', 'turnos')}</div>}
                          </td>
                          <td className="small text-nowrap" data-rot="Encerrada">{l.encerrada}</td>
                          <td className="small" data-rot="Resolvida por">{l.resolvida_por}</td>
                        </tr>
                      )) : <tr><td colSpan={5} className="rm-vazio">Nenhuma pendência resolvida no mês.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <div className="col-lg-6">
              <div className="card shadow-sm border-0 h-100">
                <div className="card-header bg-white fw-bold">
                  Críticas / em aberto
                  {' '}<span className={'rm-tag ' + (pend.lista_em_aberto.length ? 'critico' : 'ok')}>
                    {pend.lista_em_aberto.length}</span></div>
                <div className="table-responsive">
                  <table className="table table-sm align-middle mb-0 tab-cartao">
                    <thead><tr><th>Pendência</th><th>Prior.</th><th>Turno</th><th className="text-end">Parada</th></tr></thead>
                    <tbody>
                      {pend.lista_em_aberto.length ? pend.lista_em_aberto.map((l, n) => (
                        <tr key={n}>
                          <td className="small cel-pilha" data-rot="Pendência">{l.titulo}
                            {l.referencia && <> <span className="rm-ref">{l.referencia}</span></>}
                            {l.anterior && <> <span className="rm-tag alerta">de competência anterior</span></>}
                            {l.descricao && <div className="text-muted">{l.descricao}</div>}
                            {/* "O que já se tentou?" */}
                            {l.ultima_tentativa && <div className="rm-tentativa">Última tentativa: {l.ultima_tentativa}</div>}
                          </td>
                          <td data-rot="Prioridade"><span className={'rm-tag ' + (l.prioridade === 'alta' ? 'critico' : 'neutro')}>
                            {prioridadeDoRelatorio(l.prioridade)}</span></td>
                          <td className="small cel-pilha" data-rot="Turno">{l.turno}
                            {l.passagens > 0 && <div className="text-muted">passou por {plural(l.passagens, 'turno', 'turnos')}</div>}
                          </td>
                          <td className="small text-end text-nowrap" data-rot="Parada">{parada(l.dias)}</td>
                        </tr>
                      )) : <tr><td colSpan={4} className="rm-vazio">Nenhuma pendência em aberto. Fila limpa.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Bloco 4: matriz de ocorrências ── */}
        <div className="rm-bloco">
          <h2>4. Matriz de ocorrências e não conformidades</h2>

          {/* Os pontos de atenção primeiro, e em destaque: o Pareto conta TIPOS e nivela. */}
          {oc.atencao.length > 0 && (
            <div className="card shadow-sm border-0 mb-3 rm-atencao">
              <div className="card-body">
                <div className="fw-bold mb-2 rm-atencao-tit">
                  Pontos de atenção da competência ({oc.atencao.length})
                </div>
                {oc.atencao.map((l, n) => (
                  <div className="small py-1 rm-atencao-item" key={n}>
                    {/* O dia é o do TURNO, não o da digitação. */}
                    <span className="text-muted">{l.dia || '—'} · {l.turno} ·</span>
                    {' '}<span className="fw-semibold">{l.tipo}</span>
                    {l.referencia && <> <span className="text-muted">· {l.referencia}</span></>}
                    <div>{l.descricao}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="card shadow-sm border-0">
            <div className="table-responsive">
              <table className="table table-sm align-middle mb-0 tab-cartao">
                <thead><tr>
                  <th>Data / Turno</th><th>Tipo</th><th>Referência</th><th>Descrição</th>
                </tr></thead>
                <tbody>
                  {oc.lista.length ? oc.lista.map((l, n) => (
                    <tr key={n}>
                      <td className="small text-nowrap" data-rot="Data / Turno">{l.data || '—'} · {l.turno}</td>
                      <td data-rot="Tipo">
                        <span className={'badge ' + (l.gravidade === 'critica' ? 'text-bg-warning' : 'text-bg-light border')}>{l.tipo}</span></td>
                      <td className="small text-muted" data-rot="Referência">{l.referencia || '—'}</td>
                      <td className="small" data-rot="Descrição">{l.descricao}</td>
                    </tr>
                  )) : <tr><td colSpan={4} className="rm-vazio">Nenhuma ocorrência registrada na competência.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* ── Bloco 5: diário de bordo ── */}
        <div className="rm-bloco">
          <h2>5. Diário de bordo — fatos relevantes dos turnos</h2>
          {rel.bordo.length ? (
            <div className="rm-timeline">
              {rel.bordo.map((f, n) => (
                <div className="rm-item" key={n}>
                  <div className="rm-item-quando">{f.data} · {f.turno}</div>
                  <div className="rm-item-texto">{f.texto}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="card shadow-sm border-0"><div className="rm-vazio">
              Nenhum fato relevante registrado pelos encarregados nesta competência.
              Turnos que anotaram apenas "sem observações" não entram nesta linha do tempo.
            </div></div>
          )}
        </div>

        <div className="text-center text-muted small pt-2 border-top">
          Grupo Trino · {dados.nome_do_sistema} — documento confidencial de uso interno e do cliente.
        </div>
      </div>
    </>
  );
}
