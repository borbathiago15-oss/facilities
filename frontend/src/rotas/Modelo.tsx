// O checklist: o POP/FIT completo, o resumo, as perguntas e a publicação de
// uma versão nova (Fase 3b; a tela antiga é templates/rotas/modelo.html). O
// formulário é o mesmo: as fotos de referência vão no próprio envio, e a
// redução da foto no celular é a de sempre (static/js/foto-leve.js).
import { Migalhas, RecadosDoEnvio, useFormulario } from '../cadastros/comum';
import { API } from './comum';
import type { DadosDoModelo, ItemDoChecklist } from './tipos';

function Linha({ it, i, dados }: { it: ItemDoChecklist | null; i: number; dados: DadosDoModelo }) {
  return (
    <div className="border rounded p-2 mb-2">
      <div className="row g-2">
        <div className="col-3 col-md-1"><label className="form-label small" htmlFor={`o${i}`}>Ordem</label><input className="form-control" id={`o${i}`} name="ordem" inputMode="numeric" defaultValue={it ? String(i + 1) : ''} /></div>
        <div className="col-9 col-md-6"><label className="form-label small" htmlFor={`t${i}`}>Pergunta</label><input className="form-control" id={`t${i}`} name="texto" maxLength={300} defaultValue={it ? it.texto : ''} /></div>
        <div className="col-md-3"><label className="form-label small" htmlFor={`ti${i}`}>Tipo de resposta</label>
          <select className="form-select" id={`ti${i}`} name="tipo" defaultValue={it ? it.tipo : undefined}>{dados.tipos.map(([k, v]) => <option value={k} key={k}>{v}</option>)}</select></div>
        <div className="col-md-2 small"><span className="form-label d-block">Regras</span>
          <label className="d-block"><input type="checkbox" name="obrigatorio" value={i} defaultChecked={!!it && it.obrigatorio} /> Obrigatória</label>
          <label className="d-block"><input type="checkbox" name="exige_foto" value={i} defaultChecked={!!it && it.exige_foto} /> Pede foto</label></div>
        <div className="col-md-4"><label className="form-label small" htmlFor={`op${i}`}>Opções (escolha), separadas por ;</label><input className="form-control" id={`op${i}`} name="opcoes" defaultValue={it ? it.opcoes : ''} /></div>
        <div className="col-6 col-md-2"><label className="form-label small" htmlFor={`mn${i}`}>Mínimo (número)</label><input className="form-control" id={`mn${i}`} name="minimo" defaultValue={it ? it.minimo : ''} /></div>
        <div className="col-6 col-md-2"><label className="form-label small" htmlFor={`mx${i}`}>Máximo (número)</label><input className="form-control" id={`mx${i}`} name="maximo" defaultValue={it ? it.maximo : ''} /></div>
        <div className="col-md-2"><label className="form-label small" htmlFor={`ps${i}`}>Sim/não: é problema se</label>
          <select className="form-select" id={`ps${i}`} name="problema_se" defaultValue={it ? it.problema_se : ''}><option value="">nenhum</option><option value="nao">não</option><option value="sim">sim</option></select></div>
        <div className="col-md-2"><label className="form-label small" htmlFor={`ms${i}`}>Só aparece se</label><input className="form-control" id={`ms${i}`} name="mostrar_se" defaultValue={it ? it.mostrar_se : ''} /></div>
        <div className="col-md-8"><label className="form-label small" htmlFor={`cf${i}`}>Como fazer <span className="text-muted">(aparece embaixo da pergunta, no celular)</span></label>
          <textarea className="form-control" id={`cf${i}`} name="como_fazer" rows={2} maxLength={400} placeholder="Ex.: Repor 2 rolos no suporte e conferir o papel-toalha." defaultValue={it ? it.como_fazer : ''}></textarea></div>
        <div className="col-md-4"><label className="form-label small" htmlFor={`fr${i}`}>Foto de referência <span className="text-muted">(como deve ficar)</span></label>
          {it && it.referencia && (
            <div className="d-flex align-items-center gap-2 mb-1"><img className="fc-miniatura fc-miniatura-p" src={it.referencia} alt={`Referência de ${it.texto}`} />
              <label className="small"><input type="checkbox" name="tirar_foto_ref" value={i} /> Tirar</label></div>
          )}
          <input className="form-control form-control-sm" type="file" id={`fr${i}`} name={`foto_ref_${i}`} accept="image/*" data-foto-leve /></div>
        <input type="hidden" name="foto_ref" value={it ? it.foto_ref || '' : ''} />
        <input type="hidden" name="codigo" value={it ? it.codigo : ''} />
      </div>
      {it && it.codigo && <div className="small text-muted mt-1">Código: <code>{it.codigo}</code></div>}
    </div>
  );
}

export function Modelo({ dados }: { dados: DadosDoModelo }) {
  const { submeter, enviarFormulario, ocupado, aviso } = useFormulario();
  const m = dados.modelo;
  const v = dados.versao;
  const pode = dados.pode_montar;
  const tipos = Object.fromEntries(dados.tipos);
  // A foto ainda sendo reduzida (foto-leve.js) segura o envio e o refaz
  // quando terminar; aqui só se envia o que ele deixou passar.
  const publicar = (ev: React.FormEvent<HTMLFormElement>) => {
    const adiado = ev.nativeEvent.defaultPrevented;
    ev.preventDefault();
    if (!adiado) enviarFormulario(`${API}/modelos/${m.id}`, ev.currentTarget);
  };
  const anexar = (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    enviarFormulario(`${API}/modelos/${m.id}/documentos`, ev.currentTarget);
  };
  const linhas: (ItemDoChecklist | null)[] = [...dados.itens, ...Array(dados.linhas_em_branco).fill(null)];
  return (
    <div data-tela-pronta="rotas-modelo">
      <Migalhas itens={[['Rotas', '/novo/rotas/'],
        m.local ? [m.local.nome, `/novo/rotas/locais/${m.local.id}`] : ['Biblioteca', '/novo/rotas/biblioteca'],
        [m.nome, null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">{m.nome}</h1>
      <p className="fc-sub">{v ? `Versão publicada: ${v.numero}, em ${v.publicada_em}.` : 'Ainda não publicado.'} {m.local ? `Checklist do local ${m.local.nome}.` : 'Modelo da biblioteca da Trino.'}</p>

      <section className="fc-cartao mb-3" aria-labelledby="tit-docs">
        <h2 className="h6 fw-bold" id="tit-docs">POP / FIT completo</h2>
        {dados.documentos.length ? (
          <ul className="list-unstyled mb-2">
            {dados.documentos.map((d) => (
              <li className="d-flex flex-wrap align-items-center gap-2 border-bottom py-2" key={d.id}>
                <i className="bi bi-file-earmark-text" aria-hidden="true"></i>
                <a className="fw-semibold" href={d.url}>{d.nome}</a>
                <span className="small text-muted">{d.enviado_em}</span>
                {m.local && <span className={`badge ${d.visivel_cliente ? 'text-bg-info' : 'text-bg-light'}`}>{d.visivel_cliente ? 'O cliente vê' : 'Só a equipe'}</span>}
                {pode && (
                  <span className="ms-auto d-flex gap-2">
                    {m.local && (
                      <form method="post" onSubmit={submeter(`${API}/documentos/${d.id}/${d.visivel_cliente ? 'interno' : 'cliente'}`)}>
                        <button className="btn btn-sm btn-outline-secondary" type="submit" disabled={ocupado}>{d.visivel_cliente ? 'Tirar do portal do cliente' : 'Mostrar ao cliente'}</button></form>
                    )}
                    <form method="post" onSubmit={submeter(`${API}/documentos/${d.id}/retirar`)}>
                      <button className="btn btn-sm btn-outline-danger" type="submit" disabled={ocupado}>Retirar</button></form>
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : <p className="small text-muted">Nenhum documento guardado ainda.</p>}
        {pode && dados.documentos.length < dados.limite_docs && (
          <>
            <form method="post" encType="multipart/form-data" className="d-flex flex-wrap gap-2 align-items-end" onSubmit={anexar}>
              <div><label className="form-label small" htmlFor="docarq">Arquivo do POP ou da FIT (PDF, Excel, Word ou imagem)</label>
                <input className="form-control" type="file" id="docarq" name="arquivo" required accept=".pdf,.xlsx,.xls,.docx,.doc,.jpg,.jpeg,.png,.webp" /></div>
              <button className="btn btn-outline-primary fw-bold" type="submit" disabled={ocupado}><i className="bi bi-paperclip" aria-hidden="true"></i> Guardar documento</button>
            </form>
            <p className="small text-muted mt-2 mb-0">{m.local ? 'O documento é só da equipe. O cliente só vê se você clicar em "Mostrar ao cliente".' : 'Quem copiar este checklist para um local leva o documento junto.'}</p>
          </>
        )}
      </section>
      {pode ? (
        <form method="post" encType="multipart/form-data" onSubmit={publicar}>
          <div className="fc-cartao mb-3">
            <label className="form-label small fw-semibold" htmlFor="mdesc">Resumo do procedimento (POP/FIT)</label>
            <p className="small text-muted mb-1" id="mdesc-ajuda">Escreva em poucas linhas, com palavras simples, o que o POP ou a FIT pede. É o que aparece no celular de quem faz o checklist. O documento completo você guarda logo abaixo.</p>
            <textarea className="form-control mb-2" id="mdesc" name="descricao" rows={4} aria-describedby="mdesc-ajuda" placeholder="Ex.: Use luva e placa de piso molhado. Limpe de dentro para fora: pia, vaso, piso. Produto azul para vidro, verde para piso." defaultValue={m.descricao}></textarea>
            <div className="row g-2 mb-2">
              <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor="mmat">Materiais usados</label>
                <textarea className="form-control" id="mmat" name="materiais" rows={2} maxLength={2000} placeholder="Ex.: vassoura, pá, mop úmido, sanitizante, detergente" defaultValue={v ? v.materiais : ''}></textarea></div>
              <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor="mepi">EPI</label>
                <textarea className="form-control" id="mepi" name="epi" rows={2} maxLength={2000} placeholder="Ex.: luva nitrílica, bota, óculos" defaultValue={v ? v.epi : ''}></textarea></div>
            </div>
            <div className="form-check"><input className="form-check-input" type="checkbox" id="fantes" name="exige_foto_antes" value="1" defaultChecked={m.exige_foto_antes} /><label className="form-check-label" htmlFor="fantes">Exigir foto de ANTES</label></div>
            <div className="form-check"><input className="form-check-input" type="checkbox" id="fdepois" name="exige_foto_depois" value="1" defaultChecked={m.exige_foto_depois} /><label className="form-check-label" htmlFor="fdepois">Exigir foto de DEPOIS</label></div>
          </div>
          <div className="fc-cartao mb-3">
            <h2 className="h6 fw-bold">Perguntas</h2>
            <p className="small text-muted">Deixe o texto vazio para tirar a pergunta. A ordem segue o número da coluna "Ordem". Pergunta condicional: em "Só aparece se", escreva <code>código=valor</code> de uma pergunta anterior (ex.: <code>vazamento=sim</code>).</p>
            {linhas.map((it, i) => <Linha it={it} i={i} dados={dados} key={i} />)}
          </div>
          <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Publicar {v ? 'nova versão' : 'a primeira versão'}</button>
          <span className="small text-muted ms-2">Precisa de mais linhas? Publique e as linhas em branco voltam.</span>
        </form>
      ) : (
        <div className="fc-cartao">
          {m.descricao && <p>{m.descricao}</p>}
          {v && v.materiais && <p className="small"><strong>Materiais usados:</strong> {v.materiais}</p>}
          {v && v.epi && <p className="small"><strong>EPI:</strong> {v.epi}</p>}
          <ol className="mb-0">{dados.itens.map((it) => (
            <li className="mb-2" key={it.codigo}>{it.texto} <span className="small text-muted">({tipos[it.tipo]}{it.obrigatorio && ', obrigatória'}{it.exige_foto && ', com foto'})</span>
              {it.como_fazer && <div className="small fc-como-fazer">{it.como_fazer}</div>}
              {it.referencia && <img className="fc-miniatura fc-miniatura-p mt-1" src={it.referencia} alt={`Como deve ficar: ${it.texto}`} loading="lazy" />}
            </li>))}</ol>
        </div>
      )}
    </div>
  );
}
