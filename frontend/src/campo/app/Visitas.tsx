// As visitas de supervisão no aplicativo de campo (Fase 1d; as telas antigas
// são templates/visitas/app_lista.html e app_visita.html, com os mesmos
// textos, campos e classes). O checklist envia os mesmos campos da antiga
// (r_<código>, f_antes, f_depois, f_item:<código>, f_livre e observacao) a
// /api/v1/campo/visitas/<id>, que chama a mesma ação (visitas.telas.acao_fazer).
// As fotos são reduzidas no aparelho ao escolher (static/js/foto-leve.js,
// carregado pela casca): a foto ainda sendo reduzida segura o envio e o refaz
// quando termina. A pergunta condicional mostra o mesmo "Responda só se...".
import { Destino } from '../CascaCampo';
import { useEnvioDoCampo } from './comum';
import type { DadosDaVisita, DadosDasVisitas, ItemDaVisita } from './tipos';

export function ListaDeVisitas({ dados }: { dados: DadosDasVisitas }) {
  return (
    <div data-tela-pronta="campo-visitas">
      <h1 className="fc-titulo">Visitas de supervisão</h1>
      <p className="fc-sub">As visitas programadas que estão esperando você. Toque para fazer o checklist.</p>
      <div className="fc-cartao">
        {dados.visitas.length ? dados.visitas.map((v) => (
          <Destino className="fc-app-item" href={v.url} key={v.id}>
            <div className="d-flex align-items-center gap-2">
              <span className="fw-semibold">{v.nome}</span>
              {v.selo === 'atrasada' && <span className="badge fc-sit fc-sit-atrasada">Atrasada</span>}
              {v.selo === 'hoje' && <span className="badge fc-sit fc-sit-no_horario">Hoje</span>}
            </div>
            <span className="small text-muted">{v.local} · até {v.ate}</span>
          </Destino>
        )) : <div className="fc-vazio">Nenhuma visita esperando você.</div>}
      </div>
    </div>
  );
}

function CampoFoto({ nome, rotulo, obrigatoria, varias = false }: { nome: string; rotulo: string; obrigatoria: boolean; varias?: boolean }) {
  return (
    <>
      <label className="form-label small fw-semibold" htmlFor={nome}><i className="bi bi-camera" aria-hidden="true"></i> {rotulo}{obrigatoria && ' *'}</label>
      <input className="form-control" type="file" id={nome} name={nome} accept="image/*"
        multiple={varias || undefined} capture={varias ? undefined : 'environment'} data-foto-leve required={obrigatoria} />
      <div className="form-text" data-resumo-de={nome}></div>
    </>
  );
}

function Condicao({ it }: { it: ItemDaVisita }) {
  if (!it.mostrar_se) return null;
  return <div className="form-text mt-0 mb-1">Responda só se "{it.mostrar_se.texto}" for "{it.mostrar_se.valor}".</div>;
}

/** O "Aceitável: de X até Y" do item de número (o texto da antiga). */
export function aceitavel(it: ItemDaVisita): string | null {
  if (it.minimo === null && it.maximo === null) return null;
  return `Aceitável: ${it.minimo !== null ? `de ${it.minimo}` : ''}${it.maximo !== null ? ` até ${it.maximo}` : ''}`;
}

function Pergunta({ it }: { it: ItemDaVisita }) {
  const nome = `r_${it.codigo}`;
  const marca = it.obrigatorio ? ' *' : '';
  if (it.tipo === 'sim_nao' || it.tipo === 'conforme') {
    const opcoes = it.tipo === 'sim_nao' ? [['sim', 'Sim'], ['nao', 'Não']] : [['conforme', 'Conforme'], ['nao_conforme', 'Não conforme']];
    return (
      <fieldset>
        <legend className="fw-semibold fs-6 mb-1">{it.texto}{marca}</legend>
        <Condicao it={it} />
        <div className="d-flex gap-2">
          {opcoes.map(([val, rot]) => (
            <label className="fc-opcao flex-fill" htmlFor={`${nome}_${val}`} key={val}>
              <input className="fc-opcao-radio" type="radio" id={`${nome}_${val}`} name={nome} value={val} /><span>{rot}</span>
            </label>
          ))}
        </div>
      </fieldset>
    );
  }
  const faixa = it.tipo === 'numero' ? aceitavel(it) : null;
  return (
    <>
      <label className="fw-semibold mb-1" htmlFor={nome}>{it.texto}{marca}</label>
      <Condicao it={it} />
      {it.tipo === 'numero' && <input className="form-control form-control-lg" id={nome} name={nome} inputMode="decimal" />}
      {faixa && <div className="form-text">{faixa}</div>}
      {it.tipo === 'escolha' && (
        <select className="form-select form-select-lg" id={nome} name={nome} defaultValue="">
          <option value="">Escolha</option>{it.opcoes.map((o) => <option value={o} key={o}>{o}</option>)}
        </select>
      )}
      {it.tipo === 'data_hora' && <input className="form-control form-control-lg" type="datetime-local" id={nome} name={nome} />}
      {!['numero', 'escolha', 'data_hora'].includes(it.tipo) && <input className="form-control form-control-lg" id={nome} name={nome} maxLength={300} />}
    </>
  );
}

export function Visita({ dados }: { dados: DadosDaVisita }) {
  const { mandar, ocupado, aviso } = useEnvioDoCampo();
  const v = dados.visita;
  const registrar = (ev: React.FormEvent<HTMLFormElement>) => {
    const adiado = ev.nativeEvent.defaultPrevented;      // foto-leve.js ainda reduzindo
    ev.preventDefault();
    if (!adiado) mandar(`/api/v1/campo/visitas/${v.id}`, new FormData(ev.currentTarget));
  };
  return (
    <div data-tela-pronta="campo-visita">
      {aviso}
      <h1 className="fc-titulo">{v.nome}</h1>
      <p className="fc-sub">{v.local} · {v.situacao_rotulo}{v.status === 'prevista' && ` · até ${v.ate}`}</p>
      {v.status === 'feita' ? (
        <>
          <div className="fc-cartao mb-3">
            <p className="mb-1"><b>Feita por</b> {v.quem_fez} · {v.feita_em}</p>
            {v.chamado
              ? <p className="mb-1"><b>Não conforme:</b> {v.n_nao_conformes} item(ns) · chamado <Destino href={v.chamado.url}>{v.chamado.numero}</Destino> ({v.chamado.status_rotulo})</p>
              : <p className="mb-1 text-success">Tudo conforme.</p>}
            {v.observacao && <p className="mb-0"><b>Observação:</b> {v.observacao}</p>}
          </div>
          {dados.fotos.length > 0 && (
            <div className="fc-cartao mb-3">
              <h2 className="h6 fw-bold">Fotos</h2>
              <div className="d-flex flex-wrap gap-2">
                {dados.fotos.map((f) => (
                  <figure className="m-0" key={f.id}>
                    <a href={f.url} target="_blank" rel="noopener"><img className="fc-miniatura" src={f.url} alt={f.alt} loading="lazy" /></a>
                    <figcaption className="small text-muted">{f.legenda}</figcaption>
                  </figure>
                ))}
              </div>
            </div>
          )}
          <div className="fc-cartao">
            <h2 className="h6 fw-bold">Respostas</h2>
            {dados.respostas.map((r) => (
              <div className="border-top py-2" key={r.codigo}><div className="small text-muted">{r.texto}</div><div className="fw-semibold">{r.valor}</div></div>
            ))}
          </div>
        </>
      ) : !dados.pode_fazer ? (
        <div className="alert alert-info">Esta visita é de {v.supervisor || 'um supervisor do local'}.</div>
      ) : (
        <form method="post" encType="multipart/form-data" onSubmit={registrar}>
          {dados.exige_foto_antes && <div className="fc-cartao mb-2"><CampoFoto nome="f_antes" rotulo="Foto de antes" obrigatoria /></div>}
          {dados.itens.map((it) => (
            <div className="fc-cartao mb-2" key={it.codigo}>
              <Pergunta it={it} />
              {it.exige_foto && <div className="mt-2"><CampoFoto nome={`f_item:${it.codigo}`} rotulo="Foto deste item" obrigatoria={!it.mostrar_se} /></div>}
            </div>
          ))}
          {dados.exige_foto_depois && <div className="fc-cartao mb-2"><CampoFoto nome="f_depois" rotulo="Foto de depois" obrigatoria /></div>}
          <div className="fc-cartao mb-2">
            <CampoFoto nome="f_livre" rotulo="Outras fotos da visita (opcional, até 5)" obrigatoria={false} varias />
          </div>
          <div className="fc-cartao mb-2">
            <label className="form-label small fw-semibold" htmlFor="obs">Observação (opcional)</label>
            <textarea className="form-control" id="obs" name="observacao" rows={3} maxLength={2000}></textarea>
          </div>
          <button className="btn btn-primary btn-lg w-100 fc-app-acao" type="submit" disabled={ocupado}><i className="bi bi-check-circle" aria-hidden="true"></i> Registrar a visita</button>
          <p className="small text-muted mt-2">O que estiver não conforme abre um chamado para a gestão do local. Esta tela precisa de sinal.</p>
        </form>
      )}
    </div>
  );
}
