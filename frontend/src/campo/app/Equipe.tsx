// A equipe do dia no aplicativo de campo (Fase 1d; a tela antiga é
// templates/equipes/app_equipe.html, com os mesmos textos, campos e classes).
// Os envios vão a /api/v1/campo/equipe/... e chamam a mesma ação da antiga
// (equipes.telas.acao_app_presenca e acao_app_cobertura).
import { useEffect } from 'react';
import { useLocation } from 'react-router';
import { Destino } from '../CascaCampo';
import { useEnvioDoCampo } from './comum';
import type { DadosDaEquipe, LinhaDaEquipe } from './tipos';

const API = '/api/v1/campo/equipe';

function Linha({ l, dia, situacoes, cobridores, mandar, ocupado }: {
  l: LinhaDaEquipe; dia: string; situacoes: [string, string][];
  cobridores: { id: number; nome: string }[];
  mandar: (url: string, corpo: FormData) => void; ocupado: boolean;
}) {
  const p = l.presenca;
  const marcar = (situacao: string) => {
    const fd = new FormData();
    fd.append('escala_id', String(l.escala_id));
    fd.append('data', dia);
    fd.append('situacao', situacao);
    mandar(`${API}/presenca`, fd);
  };
  const cobrir = (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    if (p) mandar(`${API}/presencas/${p.id}/cobertura`, new FormData(ev.currentTarget));
  };
  return (
    <div className="fc-app-item" id={`escala-${l.escala_id}`}>
      <div className="d-flex flex-wrap align-items-center gap-2">
        <span className="fw-semibold">{l.funcionario}</span>
        {p && <span className={`badge fc-pres-badge fc-pres-${p.situacao}`}>{p.rotulo}</span>}
      </div>
      <span className="small text-muted">{l.detalhe}</span>
      <div className="d-flex gap-2 mt-2">
        {situacoes.map(([k, v]) => {
          const marcada = p?.situacao === k;
          return (
            <button className={`btn ${marcada ? 'btn-primary' : 'btn-outline-primary'} flex-fill fc-app-acao`}
              type="button" key={k} aria-pressed={marcada || undefined} disabled={ocupado}
              onClick={() => marcar(k)}>{v}</button>
          );
        })}
      </div>
      {p && p.situacao === 'faltou' && (p.cobertura ? (
        <p className="small mt-2 mb-0"><i className="bi bi-arrow-left-right" aria-hidden="true"></i> Coberto por <b>{p.cobertura.funcionario}</b> — {p.cobertura.motivo}</p>
      ) : (
        <details className="mt-2">
          <summary className="fw-semibold small">Alguém cobriu esta falta?</summary>
          <form method="post" className="mt-2" onSubmit={cobrir}>
            <label className="form-label small" htmlFor={`cq${p.id}`}>Quem cobriu</label>
            <select className="form-select mb-2" id={`cq${p.id}`} name="funcionario_id" required>
              {cobridores.filter((f) => f.id !== l.funcionario_id).map((f) => <option value={f.id} key={f.id}>{f.nome}</option>)}
            </select>
            <label className="form-label small" htmlFor={`cm${p.id}`}>Motivo</label>
            <input className="form-control mb-2" id={`cm${p.id}`} name="motivo" required minLength={3} maxLength={300} placeholder="Ex.: atestado médico, folga trocada" />
            <button className="btn btn-primary w-100 fc-app-acao" type="submit" disabled={ocupado}>Registrar cobertura</button>
          </form>
        </details>
      ))}
    </div>
  );
}

export function Equipe({ dados }: { dados: DadosDaEquipe }) {
  const { mandar, ocupado, aviso } = useEnvioDoCampo();
  const { hash } = useLocation();
  // Depois de marcar, volta à pessoa marcada (o ``#escala-<id>`` da antiga).
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView?.({ block: 'center' });
  }, [hash, dados]);
  return (
    <div data-tela-pronta="campo-equipe">
      {aviso}
      <h1 className="fc-titulo">Equipe · {dados.dia}</h1>
      <p className="fc-sub">Marque quem veio, quem faltou e quem atrasou. Se alguém cobriu a falta, registre quem foi e o motivo.</p>
      <div className="d-flex gap-2 mb-3">
        <Destino className="btn btn-outline-secondary flex-fill" href={dados.ontem}><i className="bi bi-chevron-left" aria-hidden="true"></i> Dia anterior</Destino>
        {dados.amanha && <Destino className="btn btn-outline-secondary flex-fill" href={dados.amanha}>Dia seguinte <i className="bi bi-chevron-right" aria-hidden="true"></i></Destino>}
      </div>
      {dados.locais.length ? dados.locais.map((loc) => (
        <section className="fc-cartao mb-3" aria-labelledby={`tit-l${loc.id}`} key={loc.id}>
          <h2 className="h6 fw-bold" id={`tit-l${loc.id}`}><i className="bi bi-geo-alt" aria-hidden="true"></i> {loc.nome}</h2>
          {loc.linhas.map((l) => (
            <Linha l={l} dia={dados.data} situacoes={dados.situacoes} cobridores={loc.cobridores}
              mandar={mandar} ocupado={ocupado} key={l.escala_id} />
          ))}
        </section>
      )) : (
        <div className="fc-cartao fc-vazio">Ninguém escalado neste dia nos seus locais. A escala é lançada no site, em Rotas › Equipe.</div>
      )}
    </div>
  );
}
