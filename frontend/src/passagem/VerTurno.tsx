// A passagem já lançada, para leitura (Fase 2a da migração para React; a
// tela antiga é templates/diario_operacional/ver_turno.html +
// static/js/diario_ver_turno.js, com os mesmos textos e as mesmas classes).
// É aqui que o supervisor confere o que foi feito e com que evidência; o
// autor corrige, enquanto o turno seguinte não fechou.
import { useCallback, useEffect, useRef, useState } from 'react';
import { enviarBruto } from '../api';
import type { Anexo, DadosDaLeitura } from './tipos';
import './passagem.css';

/** A foto que NÃO foi o autor quem prendeu diz de quem é. */
function Prova({ a }: { a: Anexo }) {
  return (
    <a className="vt-prova text-decoration-none" target="_blank" rel="noopener" href={a.url} title={a.nome}>
      {(a.mime || '').startsWith('image/')
        ? <img src={a.url} alt={a.nome} loading="lazy" />
        : <div className="vt-pdf"><i className="bi bi-file-earmark-pdf"></i></div>}
      <div className="vt-nome-arq">{a.nome}</div>
      {a.anexado_por && <div className="vt-quem-anexou">anexado por {a.anexado_por}</div>}
    </a>
  );
}

function Provas({ lista }: { lista: Anexo[] }) {
  return <div className="vt-provas">{lista.map((a) => <Prova a={a} key={a.id} />)}</div>;
}

function Corrigir({ dados, fechar }: { dados: DadosDaLeitura; fechar: () => void }) {
  const t = dados.turno;
  const [data, setData] = useState(t.data_iso);
  const [turno, setTurno] = useState(t.turno);
  const [obs, setObs] = useState(t.observacao);
  const [motivo, setMotivo] = useState('');
  const [ocupado, setOcupado] = useState(false);
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

  const enviar = () => {
    if (!motivo.trim()) { window.alert('Diga em uma linha o que estava errado.'); return; }
    setOcupado(true);
    enviarBruto(dados.links.corrigir, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ data_turno: data, turno, observacao: obs, motivo }),
    }).then((r) => r.json().then((x) => ({ ok: r.ok, x })))
      .then((res) => {
        if (!res.ok) { window.alert(res.x.error || 'Não foi possível corrigir.'); setOcupado(false); return; }
        window.location.reload();
      }).catch(() => { window.alert('Falha de rede.'); setOcupado(false); });
  };

  return (
    <>
      <div className="modal fade show d-block" id="vt-modal-corrigir" tabIndex={-1} role="dialog" aria-modal="true"
        aria-labelledby="vt-c-titulo" ref={caixa} onClick={(ev) => { if (ev.target === ev.currentTarget) fechar(); }}>
        <div className="modal-dialog modal-dialog-centered">
          <div className="modal-content">
            <div className="modal-header">
              <h5 className="modal-title" id="vt-c-titulo">Corrigir esta passagem</h5>
              <button type="button" className="btn-close" aria-label="Fechar" onClick={fechar}></button>
            </div>
            <div className="modal-body">
              <p className="text-muted small mb-3">
                A correção fica registrada: o valor antigo é guardado e quem abrir a
                passagem vê o que mudou e por quê. Pendências e ocorrências já
                lançadas não são tocadas — elas se resolvem no módulo.
              </p>
              <div className="row g-2">
                <div className="col-6 tsel">
                  <label htmlFor="vt-c-data">Data do turno</label>
                  <input type="date" className="form-control" id="vt-c-data" value={data}
                    onChange={(ev) => setData(ev.target.value)} />
                </div>
                <div className="col-6 tsel">
                  <label htmlFor="vt-c-turno">Turno</label>
                  <input type="text" className="form-control" id="vt-c-turno" value={turno} maxLength={50}
                    onChange={(ev) => setTurno(ev.target.value)} />
                </div>
              </div>
              <div className="tsel mt-2">
                <label htmlFor="vt-c-obs">Observação do turno</label>
                <textarea className="form-control" id="vt-c-obs" rows={3} value={obs}
                  onChange={(ev) => setObs(ev.target.value)}></textarea>
              </div>
              <div className="tsel mt-2">
                <label htmlFor="vt-c-motivo">O que estava errado <span className="text-danger">*</span></label>
                <input type="text" className="form-control" id="vt-c-motivo" maxLength={300} value={motivo}
                  placeholder="Ex.: lancei no 1º turno e era o 2º" onChange={(ev) => setMotivo(ev.target.value)} />
                <div className="tsel-ajuda">
                  Obrigatório. É o que permite a alguém entender a troca meses depois.
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-light" onClick={fechar}>Cancelar</button>
              <button type="button" className="btn btn-primary" id="vt-c-enviar" disabled={ocupado}
                onClick={enviar}>Registrar a correção</button>
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop fade show"></div>
    </>
  );
}

export function VerTurno({ dados }: { dados: DadosDaLeitura }) {
  const t = dados.turno;
  const [corrigindo, setCorrigindo] = useState(false);
  const fechar = useCallback(() => setCorrigindo(false), []);
  const encerrado = t.status === 'encerrado';
  const ap = dados.no_aparelho;
  return (
    <>
      <nav aria-label="breadcrumb"><ol className="breadcrumb">
        <li className="breadcrumb-item"><a href={dados.links.painel}>Passagem de Turno</a></li>
        <li className="breadcrumb-item active">Passagem de turno</li>
      </ol></nav>
      <div className="container-fluid py-3 diario-page vt-doc" data-tela-pronta="ver-turno">

        <div className="pg-topo">
          <div>
            <div className="pg-olho">PASSAGEM DE TURNO</div>
            <h1 className="pg-titulo">{t.turno} · {t.data}</h1>
          </div>
          <div className="d-flex gap-2">
            {/* Só para quem lançou, e só enquanto o turno seguinte não fechou. */}
            {dados.pode_corrigir && (
              <button type="button" className="btn btn-outline-primary" onClick={() => setCorrigindo(true)}>
                <i className="bi bi-pencil"></i> Corrigir</button>
            )}
            <a className="btn btn-light" href={dados.links.painel}>Voltar</a>
          </div>
        </div>

        {dados.correcoes.length > 0 && (
          <div className="pg-item" style={{ borderLeft: '3px solid var(--amber-600)' }}>
            <i className="bi bi-pencil-square" style={{ color: 'var(--amber-600)' }}></i>
            <div className="flex-grow-1">
              <div className="pg-item-tit" style={{ fontSize: '13px' }}>
                Esta passagem foi corrigida {dados.correcoes.length}×</div>
              {dados.correcoes.map((c, n) => (
                <div key={n}>
                  <div className="pg-item-meta">{c.quem} · {c.quando} · mudou {c.campos}</div>
                  <div className="pg-nota">{c.motivo}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="vt-cab">
          <h2>{t.turno} · {t.data_longa}{' '}
            <span className={'vt-tag ' + (encerrado ? 'ok' : 'neutro') + ' align-middle'}>
              {encerrado ? 'Encerrado' : 'Em aberto (rascunho)'}</span>
          </h2>
          <div className="vt-meta">
            {dados.cliente || '—'}
            {dados.configuracao && <> · modelo <strong>{dados.configuracao}</strong></>}
            {dados.autor && <> · lançado por {dados.autor}</>}
            {ap
              ? <> · encerrado no aparelho {ap.prep} {ap.aparelho} · chegou ao sistema {ap.prep} {ap.chegada}</>
              : t.encerrado_em && <> · encerrado em {t.encerrado_em}</>}
          </div>
          {!dados.congelada && encerrado && (
            <div className="vt-meta mt-1">
              <i className="bi bi-info-circle"></i>{' '}
              Turno lançado antes de o sistema passar a congelar a régua: as atividades
              abaixo são as do modelo de hoje, não necessariamente as exigidas naquele dia.
            </div>
          )}
        </div>

        {dados.campos.length > 0 && (
          <div className="card shadow-sm border-0 mb-3">
            <div className="card-header bg-white fw-bold">Dados do turno</div>
            <div className="card-body">
              <div className="row g-3">
                {dados.campos.map((c, n) => (
                  <div className="col-md-4" key={n}>
                    <div className="text-uppercase small text-muted fw-semibold">{c.nome}</div>
                    <div className="fs-5">{c.valor}</div>
                    {c.anexos.length > 0 && <Provas lista={c.anexos} />}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <h6 className="text-uppercase small text-muted fw-semibold mt-3">Checklist do turno</h6>
        {/* A rotina OPCIONAL aparece também, depois das obrigatórias: "não
            feita" não pinta de vermelho (não é falta). */}
        {dados.linhas.map((l) => (
          <div className={'vt-lin ' + (l.feito ? 'sim' : (l.opcional ? '' : 'nao'))} key={l.codigo}>
            <div className="d-flex justify-content-between align-items-start gap-2">
              <span className="vt-nome">{l.nome}
                {l.opcional && <> <span className="vt-tag neutro ms-1"
                  title="Rotina opcional: aparece na leitura, mas não conta na aderência do turno">opcional</span></>}
              </span>
              {l.opcional && !l.feito
                ? <span className="vt-tag neutro">Não feita</span>
                : <span className={'vt-tag ' + (l.feito ? 'ok' : 'bad')}>{l.feito ? 'Concluído' : 'Não concluído'}</span>}
            </div>
            {l.observacao && <div className="vt-obs">{l.observacao}</div>}
            {l.anexos.length > 0 && <Provas lista={l.anexos} />}
          </div>
        ))}
        {!dados.linhas.length && (
          <div className="card shadow-sm border-0"><div className="p-4 vt-vazio text-center">
            Este turno não tinha checklist configurado.</div></div>
        )}

        <div className="card shadow-sm border-0 mt-3">
          <div className="card-header bg-white fw-bold">Observação do turno</div>
          <div className="card-body">
            {t.observacao ? <div className="vt-obs">{t.observacao}</div> : <div className="vt-vazio">Sem observação.</div>}
            {dados.anexos_gerais.length > 0 && <Provas lista={dados.anexos_gerais} />}
          </div>
        </div>

        <div className="row g-3 mt-0">
          <div className="col-lg-6">
            <div className="card shadow-sm border-0 h-100">
              <div className="card-header bg-white fw-bold">Pendências deixadas</div>
              <div className="list-group list-group-flush">
                {dados.pendencias.map((p, n) => (
                  <div className="list-group-item" key={n}>
                    <div className="d-flex justify-content-between align-items-start gap-2">
                      <strong className="small">{p.titulo}{p.referencia && <>{' '}
                        <span className="vt-ref">{p.referencia}</span></>}</strong>
                      <span className={'vt-tag ' + (p.status === 'resolvida' ? 'ok' : 'neutro')}>
                        {p.status === 'resolvida' ? 'Resolvida' : 'Em aberto'}</span>
                    </div>
                    <div className="small text-muted">{p.descricao || 'Sem descrição'}</div>
                    {/* A trilha: quem carregou esta pendência e o que tentou. */}
                    {p.trilha.length > 0 && (
                      <ol className="vt-trilha">
                        {p.trilha.map((e, k) => (
                          <li className={'vt-ev vt-ev-' + e.tipo} key={k}>
                            <span className="vt-ev-quem">{e.quem}</span>
                            {e.turno && <> <span className="vt-ev-turno">{e.turno} · {e.data}</span></>}
                            {' '}<span className="vt-ev-quando">{e.quando}</span>
                            <div className="vt-ev-txt">
                              {e.texto ? e.texto : (e.tipo === 'recebida' ? 'recebeu e não resolveu' : '—')}
                            </div>
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>
                ))}
                {!dados.pendencias.length && <div className="p-4 vt-vazio text-center">Nenhuma pendência deixada.</div>}
              </div>
            </div>
          </div>
          <div className="col-lg-6">
            <div className="card shadow-sm border-0 h-100">
              <div className="card-header bg-white fw-bold">Ocorrências registradas</div>
              <div className="list-group list-group-flush">
                {dados.ocorrencias.map((o, n) => (
                  <div className="list-group-item" key={n}>
                    <div className="d-flex justify-content-between align-items-start gap-2">
                      <strong className="small">
                        {o.tipo}
                        {o.gravidade === 'critica' && <> <span className="badge text-bg-warning ms-1"
                          title="Ponto de atenção — aparece em destaque no painel">
                          <i className="bi bi-exclamation-triangle"></i> ponto de atenção</span></>}
                      </strong>
                      <span className="small text-muted">{o.referencia || ''}</span>
                    </div>
                    <div className="small text-muted">{o.descricao}</div>
                  </div>
                ))}
                {!dados.ocorrencias.length && (
                  <div className="p-4 vt-vazio text-center">Nenhuma ocorrência registrada.</div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
      {corrigindo && <Corrigir dados={dados} fechar={fechar} />}
    </>
  );
}
