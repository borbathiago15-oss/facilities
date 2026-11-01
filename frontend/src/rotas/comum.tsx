// O que as telas da rotina dos locais têm em comum (Fase 3b): os campos do
// turno de uma rota (templates/rotas/_campos_rota.html) e de uma rota pronta
// (_campos_rota_pronta.html), os dias da semana e o selo do GPS. Os nomes
// dos campos são os das telas antigas: o envio é o mesmo formulário.
import type { Dias, Gps, Rota, RotaModelo } from './tipos';

export const API = '/api/v1/rotas';

/** "seg, ter, qua" — os dias de um código "123" (a ordem do código). */
export function nomesDosDias(codigo: string, dias: Dias): string {
  const mapa = Object.fromEntries(dias);
  return codigo.split('').filter((d) => d in mapa).map((d) => mapa[d]).join(', ');
}

/** O selo do GPS (o ``selo_gps`` da tela do dia). */
export function SeloGps({ gps }: { gps: Gps }) {
  if (gps.situacao === 'fora') {
    return <span className="badge text-bg-danger" title={`Precisão do celular: ${gps.precisao || '?'} m`}>{gps.texto}</span>;
  }
  if (gps.situacao === 'sem_gps') return <span className="badge text-bg-warning">Sem GPS</span>;
  return null;
}

/** Os campos de uma rota (criar do zero e alterar). */
export function CamposRota({ r, dias }: { r?: Rota; dias: Dias }) {
  return (
    <>
      <div className="row g-2">
        <div className="col-md-5"><label className="form-label small fw-semibold" htmlFor="rnome">Nome da rota</label>
          <input className="form-control" id="rnome" name="nome" required maxLength={150} defaultValue={r ? r.nome : ''} placeholder="Ex.: Limpeza 2º andar — turno 1" /></div>
        <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor="rturno">Turno</label>
          <input className="form-control" id="rturno" name="turno" required maxLength={50} defaultValue={r ? r.turno : ''} placeholder="Ex.: 1º Turno" /></div>
        <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="rini">Início</label>
          <input className="form-control" id="rini" name="hora_inicio" type="time" required defaultValue={r ? r.inicio : '07:00'} /></div>
        <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="rfim">Fim</label>
          <input className="form-control" id="rfim" name="hora_fim" type="time" required defaultValue={r ? r.fim : '15:00'} /></div>
        <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor="rtol">Tolerância (minutos)</label>
          <input className="form-control" id="rtol" name="tolerancia_min" type="number" min={0} max={240} defaultValue={r ? r.tolerancia_min : 15} /></div>
        <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="rpres">Presença por turno</label>
          <input className="form-control" id="rpres" name="presencas_por_turno" type="number" min={0} max={6} defaultValue={r ? r.presencas_por_turno : 0} /></div>
        <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="rpprazo">Minutos para confirmar</label>
          <input className="form-control" id="rpprazo" name="presenca_prazo_min" type="number" min={5} max={60} defaultValue={r ? r.presenca_prazo_min : 10} /></div>
        <fieldset className="col-md-5"><legend className="form-label small fw-semibold mb-1">Dias da semana</legend>
          <div className="d-flex flex-wrap gap-2">
            {dias.map(([k, v]) => (
              <label className="border rounded px-2 py-1 small" key={k}><input type="checkbox" name="dias_semana" value={k} defaultChecked={!r || r.dias_semana.includes(k)} /> {v}</label>
            ))}
          </div></fieldset>
        <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="rint1">Intervalo: início</label>
          <input className="form-control" id="rint1" name="intervalo_inicio" type="time" defaultValue={r ? r.intervalo_inicio : ''} /></div>
        <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="rint2">Intervalo: fim</label>
          <input className="form-control" id="rint2" name="intervalo_fim" type="time" defaultValue={r ? r.intervalo_fim : ''} /></div>
        <div className="col-12">
          <input type="hidden" name="feriado_no_form" value="1" />
          <div className="form-check">
            <input className="form-check-input" type="checkbox" id="rferiado" name="funciona_em_feriado" value="1" defaultChecked={!r || r.funciona_em_feriado} />
            <label className="form-check-label" htmlFor="rferiado">Funciona em feriado <span className="text-muted small">(desmarque para escritório e loja que fecham: nos feriados nacionais e nos do local, a rota não gera tarefa)</span></label>
          </div></div>
        <div className="col-12"><label className="form-label small fw-semibold" htmlFor="robs">Observações do plano (opcional)</label>
          <textarea className="form-control" id="robs" name="observacoes" rows={2} maxLength={4000} defaultValue={r ? r.observacoes : ''} placeholder="Ex.: manter as gaiolas de recicláveis conforme a identificação da câmara."></textarea></div>
      </div>
      <p className="form-text mb-0">Turno que passa da meia-noite: ponha o fim menor que o início (ex.: 22:00 às 06:00). Intervalo (almoço, ceia): nenhuma tarefa cai dentro dele; deixe vazio se não houver. Presença: o aplicativo pede a confirmação em horários sorteados do turno a quem está escalado; 0 desliga.</p>
    </>
  );
}

/** Os campos do turno de uma rota pronta (ou da rota criada ao aplicar). */
export function CamposRotaPronta({ m, editavel, dias }: { m: RotaModelo | null; editavel: boolean; dias: Dias }) {
  const ro = !editavel;
  return (
    <>
      <div className="row g-2">
        <div className="col-md-5"><label className="form-label small fw-semibold" htmlFor="rpnome">Nome</label>
          <input className="form-control" id="rpnome" name="nome" required maxLength={150} defaultValue={m ? m.nome : ''} readOnly={ro} /></div>
        <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor="rpturno">Turno</label>
          <input className="form-control" id="rpturno" name="turno" required maxLength={50} defaultValue={m ? m.turno : ''} readOnly={ro} /></div>
        <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="rpini">Início</label>
          <input className="form-control" id="rpini" name="hora_inicio" type="time" required defaultValue={m ? m.inicio : '07:00'} readOnly={ro} /></div>
        <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="rpfim">Fim</label>
          <input className="form-control" id="rpfim" name="hora_fim" type="time" required defaultValue={m ? m.fim : '15:00'} readOnly={ro} /></div>
        <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor="rptol">Tolerância (minutos)</label>
          <input className="form-control" id="rptol" name="tolerancia_min" type="number" min={0} max={240} defaultValue={m ? m.tolerancia_min : 30} readOnly={ro} /></div>
        <fieldset className="col-md-9"><legend className="form-label small fw-semibold mb-1">Dias da semana</legend>
          <div className="d-flex flex-wrap gap-2">
            {dias.map(([k, v]) => (
              <label className="border rounded px-2 py-1 small" key={k}><input type="checkbox" name="dias_semana" value={k}
                defaultChecked={m ? m.dias_semana.includes(k) : '12345'.includes(k)} disabled={ro} /> {v}</label>
            ))}
          </div></fieldset>
        {editavel && (
          <>
            <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="rpint1">Intervalo: início</label>
              <input className="form-control" id="rpint1" name="intervalo_inicio" type="time" defaultValue="" /></div>
            <div className="col-6 col-md-2"><label className="form-label small fw-semibold" htmlFor="rpint2">Intervalo: fim</label>
              <input className="form-control" id="rpint2" name="intervalo_fim" type="time" defaultValue="" /></div>
            <div className="col-12"><label className="form-label small fw-semibold" htmlFor="rpobs">Observações da rota (opcional)</label>
              <textarea className="form-control" id="rpobs" name="observacoes" rows={2} maxLength={4000}></textarea></div>
          </>
        )}
      </div>
      {editavel && <p className="form-text mb-0">Intervalo (almoço, ceia): nenhuma tarefa cai dentro dele; deixe vazio se não houver.</p>}
    </>
  );
}
