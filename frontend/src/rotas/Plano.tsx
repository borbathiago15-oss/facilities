// O plano de limpeza do cliente (a planilha): envia, mostra a prévia e cria
// (Fase 3b; a tela antiga é templates/rotas/importar_plano.html). Na antiga,
// a prévia é a página que responde ao envio da planilha; aqui, a resposta da
// API (os mesmos dados), desenhada na mesma tela. Nada é criado antes do
// "Criar".
import { useState } from 'react';
import { Migalhas, RecadosDoEnvio, enviar, useFormulario, useIr } from '../cadastros/comum';
import { Recados } from '../passagem/Recados';
import { API, nomesDosDias } from './comum';
import type { DadosDoPlano, Dias, Previa, RespostaDaPrevia } from './tipos';

function MostrarPrevia({ previa, dias }: { previa: Previa; dias: Dias }) {
  return (
    <>
      {previa.avisos.length > 0 && (
        <section className="alert alert-warning" aria-labelledby="tit-avisos">
          <h2 className="h6 fw-bold" id="tit-avisos">O que não entendi ou ajustei ({previa.avisos.length})</h2>
          <ul className="mb-0 small">{previa.avisos.map((a, n) => <li key={n}>{a}</li>)}</ul>
        </section>
      )}
      <section className="fc-cartao mb-3" aria-labelledby="tit-blocos">
        <h2 className="h6 fw-bold" id="tit-blocos"><i className="bi bi-geo-alt"></i> Blocos ({previa.blocos.length}) — um ponto com QR por bloco</h2>
        <div className="table-responsive"><table className="table table-sm align-middle mb-0">
          <thead><tr><th scope="col">Setor</th><th scope="col">Bloco</th><th scope="col">Atividades</th><th scope="col">Situação</th></tr></thead>
          <tbody>{previa.blocos.map((b, n) => <tr key={n}><td>{b.setor}</td><td>{b.nome}</td><td>{b.atividades}</td><td className="small text-muted">{b.existe ? 'já existe' : 'novo'}</td></tr>)}</tbody>
        </table></div>
      </section>
      <section className="fc-cartao mb-3" aria-labelledby="tit-cks">
        <h2 className="h6 fw-bold" id="tit-cks"><i className="bi bi-ui-checks"></i> Checklists ({previa.checklists.length}) — um por atividade distinta</h2>
        <div className="table-responsive"><table className="table table-sm align-middle mb-0">
          <thead><tr><th scope="col">Checklist</th><th scope="col">Perguntas</th><th scope="col">Materiais</th><th scope="col">EPI</th><th scope="col">Situação</th></tr></thead>
          <tbody>{previa.checklists.map((c, n) => (
            <tr key={n}>
              <td>{c.nome}</td>
              <td className="small">{c.itens.map((t) => `☐ ${t}`).join(' ')}</td>
              <td className="small text-muted">{c.materiais || '—'}</td>
              <td className="small text-muted">{c.epi || '—'}</td>
              <td className="small text-muted">{c.existe ? 'já existe' : 'novo'}</td>
            </tr>
          ))}</tbody>
        </table></div>
      </section>
      <section className="fc-cartao mb-3" aria-labelledby="tit-rotas">
        <h2 className="h6 fw-bold" id="tit-rotas"><i className="bi bi-signpost-split"></i> Rotas ({previa.rotas.length})</h2>
        {previa.rotas.map((r, n) => (
          <div className="border-top py-2" key={n}>
            <div className="fw-semibold">{r.nome}{r.existe && <> <span className="badge text-bg-warning">já existe</span></>}</div>
            <div className="small text-muted">{r.turno} · {r.hora_inicio} às {r.hora_fim}{r.intervalo_inicio && ` · intervalo ${r.intervalo_inicio} às ${r.intervalo_fim}`} · {nomesDosDias(r.dias_semana, dias)} · tolerância {r.tolerancia_min} min{r.responsavel && <> · <strong>Responsável: {r.responsavel}</strong> (escalar depois)</>}</div>
            <div className="table-responsive"><table className="table table-sm mb-1">
              <thead><tr><th scope="col">#</th><th scope="col">Hora</th><th scope="col">Tempo</th><th scope="col">Bloco</th><th scope="col">Checklist</th><th scope="col">Dias</th></tr></thead>
              <tbody>{r.itens.map((it, k) => (
                <tr key={k}>
                  <td>{it.ordem}</td><td>{it.horario}</td><td>{it.tempo_previsto_min || '—'} min</td>
                  <td>{it.bloco}</td><td className="small">{it.checklist}</td>
                  <td className="small text-muted">{it.dias_semana ? `só ${nomesDosDias(it.dias_semana, dias)}` : 'todos'}{it.horarios_por_dia.map(([d, h]) => ` · ${nomesDosDias(d, dias)} às ${h}`).join('')}</td>
                </tr>
              ))}</tbody>
            </table></div>
            {r.observacoes && <p className="small mb-0 fc-texto-livre"><strong>Observações:</strong> {r.observacoes}</p>}
          </div>
        ))}
      </section>
    </>
  );
}

export function ImportarPlano({ dados }: { dados: DadosDoPlano }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const ir = useIr();
  const [resposta, setResposta] = useState<RespostaDaPrevia | null>(null);
  const [lendo, setLendo] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const loc = dados.local;
  const verPrevia = (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    if (lendo) return;
    setLendo(true);
    setErro(null);
    enviar(`${API}/locais/${loc.id}/importar-plano`, new FormData(ev.currentTarget)).then(({ ok, dados: d }) => {
      setLendo(false);
      const previa = d as unknown as Partial<RespostaDaPrevia>;
      if (ok && previa.previa) { setResposta(previa as RespostaDaPrevia); return; }
      setResposta(null);
      if (d.destino) { ir(d.destino, d.recados); return; }
      setErro(d.error || 'Algo deu errado. Tente de novo.');
    });
  };
  return (
    <div data-tela-pronta="rotas-importar-plano">
      <Migalhas itens={[['Rotas', '/novo/rotas/'], [loc.nome, `/novo/rotas/locais/${loc.id}`], ['Importar plano', null]]} />
      <RecadosDoEnvio />{aviso}{erro && <Recados servidor={[{ tipo: 'danger', texto: erro }]} key={erro} />}
      <h1 className="fc-titulo">Importar plano de limpeza (planilha)</h1>
      <p className="fc-sub">{loc.nome} · envie a planilha "Plano de limpeza e conservação" do cliente (uma aba por rota). Primeiro você vê a prévia; nada é criado antes de clicar em "Criar".</p>

      <form method="post" encType="multipart/form-data" className="fc-cartao mb-3 d-flex flex-wrap gap-2 align-items-end" onSubmit={verPrevia}>
        <div className="flex-grow-1"><label className="form-label small fw-semibold" htmlFor="arquivo">Planilha do plano (.xlsx, até 5 MB)</label>
          <input className="form-control" type="file" id="arquivo" name="arquivo" accept=".xlsx" required /></div>
        <button className="btn btn-outline-primary fw-bold" type="submit" disabled={lendo}><i className="bi bi-eye" aria-hidden="true"></i> Ver a prévia</button>
      </form>

      {resposta && (
        <div data-previa key={resposta.chave}>
          <MostrarPrevia previa={resposta.previa} dias={dados.dias} />
          <form method="post" className="fc-cartao" onSubmit={submeter(`${API}/locais/${loc.id}/importar-plano/criar`)}>
            <input type="hidden" name="chave" value={resposta.chave} />
            {resposta.ja_existem.length > 0 && (
              <>
                <div className="alert alert-warning small">Já existe neste local: {resposta.ja_existem.join(', ')}. Marque abaixo para trocar pelo plano novo (a rota antiga é desativada e o histórico fica).</div>
                <div className="form-check mb-2"><input className="form-check-input" type="checkbox" id="subst" name="substituir" value="1" /><label className="form-check-label" htmlFor="subst">Substituir as rotas que já existem</label></div>
              </>
            )}
            <p className="small text-muted">A escala (quem faz cada rota) não vem da planilha: depois de criar, escale as pessoas em cada rota. A confirmação de presença começa desligada.</p>
            <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}><i className="bi bi-check2-circle" aria-hidden="true"></i> Criar blocos, checklists e rotas neste local</button>
          </form>
        </div>
      )}
    </div>
  );
}
