// As rotas prontas da biblioteca: a edição (só o administrador) e o
// "Aplicar rota pronta" num local (Fase 3b; as telas antigas são
// templates/rotas/rota_pronta.html e aplicar_rota_pronta.html).
import { useNavigate } from 'react-router';
import { Migalhas, RecadosDoEnvio, useFormulario } from '../cadastros/comum';
import { API, CamposRotaPronta } from './comum';
import type { DadosDaRotaPronta, DadosDeAplicar } from './tipos';

export function RotaPronta({ dados }: { dados: DadosDaRotaPronta }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const m = dados.modelo;
  const editavel = dados.pode_montar;
  const titulo = m ? m.nome : 'Nova rota pronta';
  const ro = !editavel;
  return (
    <div data-tela-pronta="rotas-rota-pronta">
      <Migalhas itens={[['Biblioteca', '/novo/rotas/biblioteca'], [titulo, null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">{titulo}</h1>
      <p className="fc-sub">Uma rota pronta é um pacote para um tipo de local: os ambientes, o checklist de cada um e os horários. A gestão aplica num local e ajusta antes de gravar. Mudar aqui não muda os locais que já aplicaram.</p>
      <form method="post" onSubmit={submeter(`${API}/biblioteca/rotas/${m ? m.id : 'nova'}`)}>
        <section className="fc-cartao mb-3" aria-labelledby="tit-turno">
          <h2 className="h6 fw-bold" id="tit-turno">Turno</h2>
          <CamposRotaPronta m={m} editavel={editavel} dias={dados.dias} />
          <div className="row g-2 mt-1">
            <div className="col-md-5"><label className="form-label small fw-semibold" htmlFor="rpseg">Tipo de local</label>
              <input className="form-control" id="rpseg" name="segmento" maxLength={60} defaultValue={m ? m.segmento : ''} placeholder="Ex.: Escritório / corporativo" readOnly={ro} /></div>
            <div className="col-md-7"><label className="form-label small fw-semibold" htmlFor="rpdesc">Por que estes horários</label>
              <textarea className="form-control" id="rpdesc" name="descricao" rows={2} defaultValue={m ? m.descricao : ''} readOnly={ro}></textarea></div>
          </div>
        </section>
        <section className="fc-cartao mb-3" aria-labelledby="tit-amb">
          <h2 className="h6 fw-bold" id="tit-amb">Ambientes</h2>
          <p className="small text-muted">Uma linha por tipo de ambiente. "Quantidade 2" cria dois ambientes iguais (ex.: Banheiro da operação 1 e 2). Horários separados por vírgula. Deixe o ambiente vazio para tirar a linha.</p>
          <div className="table-responsive">
            <table className="table table-sm align-middle mb-0">
              <thead><tr><th scope="col">Setor</th><th scope="col">Ambiente</th><th scope="col">Checklist da biblioteca</th><th scope="col">Horários</th><th scope="col">Qtd.</th></tr></thead>
              <tbody>
                {dados.linhas.map((ln, i) => (
                  <tr key={i}>
                    <td><label className="visually-hidden" htmlFor={`s${i}`}>Setor</label><input className="form-control form-control-sm" id={`s${i}`} name="setor" maxLength={120} defaultValue={ln.setor} readOnly={ro} /></td>
                    <td><label className="visually-hidden" htmlFor={`a${i}`}>Ambiente</label><input className="form-control form-control-sm" id={`a${i}`} name="ambiente" maxLength={120} defaultValue={ln.ambiente} readOnly={ro} /></td>
                    <td><label className="visually-hidden" htmlFor={`c${i}`}>Checklist</label>
                      <select className="form-select form-select-sm" id={`c${i}`} name="checklist_id" disabled={ro} defaultValue={ln.checklist_id !== null ? String(ln.checklist_id) : ''}>
                        <option value="">—</option>
                        {dados.checklists.map((c) => <option value={c.id} key={c.id}>{c.nome}</option>)}
                      </select></td>
                    <td><label className="visually-hidden" htmlFor={`h${i}`}>Horários</label><input className="form-control form-control-sm" id={`h${i}`} name="horarios" maxLength={300} defaultValue={ln.horarios} placeholder="08:00, 12:00" readOnly={ro} /></td>
                    <td><label className="visually-hidden" htmlFor={`q${i}`}>Quantidade</label><input className="form-control form-control-sm" id={`q${i}`} name="quantidade" type="number" min={1} max={10} defaultValue={ln.quantidade} readOnly={ro} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        {editavel && (
          <>
            <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Salvar rota pronta</button>
            <span className="small text-muted ms-2">Precisa de mais linhas? Salve e as linhas em branco voltam.</span>
          </>
        )}
      </form>
      {editavel && m && (
        <form method="post" className="mt-3" onSubmit={submeter(`${API}/biblioteca/rotas/${m.id}/ativo`)}>
          <button className="btn btn-outline-secondary" type="submit" disabled={ocupado}>{m.ativa ? 'Desativar esta rota pronta' : 'Reativar esta rota pronta'}</button>
        </form>
      )}
    </div>
  );
}

export function Aplicar({ dados }: { dados: DadosDeAplicar }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const navegar = useNavigate();
  const loc = dados.local;
  const m = dados.modelo;
  // O formulário de escolha é um GET, como na antiga: a prévia é o endereço.
  const verPrevia = (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    const escolha = new FormData(ev.currentTarget).get('modelo') || '';
    navegar(`/rotas/locais/${loc.id}/rota-pronta?modelo=${encodeURIComponent(String(escolha))}`);
  };
  return (
    <div data-tela-pronta="rotas-aplicar">
      <Migalhas itens={[['Rotas', '/novo/rotas/'], [loc.nome, `/novo/rotas/locais/${loc.id}`], ['Aplicar rota pronta', null]]} />
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Aplicar rota pronta</h1>
      <p className="fc-sub">{loc.nome} · escolha o modelo, confira a lista e tire o que este local não tem. O sistema cria o que faltar: setores, ambientes, pontos com QR, os checklists e a rota com os horários.</p>

      <form method="get" className="fc-cartao mb-3 d-flex flex-wrap gap-2 align-items-end" onSubmit={verPrevia}>
        <div className="flex-grow-1"><label className="form-label small fw-semibold" htmlFor="escolha">Rota pronta</label>
          <select className="form-select" id="escolha" name="modelo" defaultValue={m ? String(m.id) : ''}>
            <option value="">Escolha…</option>
            {dados.opcoes.map((o) => <option value={o.id} key={o.id}>{o.segmento} · {o.nome}</option>)}
          </select></div>
        <button className="btn btn-outline-primary fw-bold" type="submit">Ver a prévia</button>
      </form>
      {!dados.opcoes.length && <div className="fc-vazio">Ainda não há rotas prontas. O administrador instala na Biblioteca ("Instalar na biblioteca").</div>}

      {m && (
        <form method="post" onSubmit={submeter(`${API}/locais/${loc.id}/rota-pronta/${m.id}`)}>
          {m.descricao && <div className="alert alert-light border small">{m.descricao}</div>}
          <section className="fc-cartao mb-3" aria-labelledby="tit-turno">
            <h2 className="h6 fw-bold" id="tit-turno">A rota que será criada</h2>
            <CamposRotaPronta m={m} editavel dias={dados.dias} />
            <p className="form-text mb-0">A confirmação de presença começa desligada (0 por turno). Ligue na rota depois da validação de RH e jurídico.</p>
          </section>
          <section className="fc-cartao mb-3" aria-labelledby="tit-amb">
            <h2 className="h6 fw-bold" id="tit-amb">Ambientes ({dados.linhas.length})</h2>
            <p className="small text-muted">Desmarque o que este local não tem. Pode mudar o nome do ambiente (ex.: "Banheiro masculino 2º andar") e os horários. Ambiente com o mesmo nome no mesmo setor é reaproveitado, sem duplicar.</p>
            <div className="table-responsive">
              <table className="table table-sm align-middle mb-0">
                <thead><tr><th scope="col">Incluir</th><th scope="col">Setor</th><th scope="col">Ambiente</th><th scope="col">Checklist</th><th scope="col">Horários</th></tr></thead>
                <tbody>
                  {dados.linhas.map((ln, i) => (
                    <tr key={i}>
                      <td><label className="visually-hidden" htmlFor={`inc${i}`}>Incluir {ln.ambiente}</label><input className="form-check-input" type="checkbox" id={`inc${i}`} name="incluir" value={i} defaultChecked /></td>
                      <td><label className="visually-hidden" htmlFor={`s${i}`}>Setor</label><input className="form-control form-control-sm" id={`s${i}`} name="setor" maxLength={120} defaultValue={ln.setor} /></td>
                      <td><label className="visually-hidden" htmlFor={`a${i}`}>Ambiente</label><input className="form-control form-control-sm" id={`a${i}`} name="ambiente" maxLength={120} defaultValue={ln.ambiente} /></td>
                      <td className="small">{ln.checklist}<input type="hidden" name="checklist_id" value={ln.checklist_id} /></td>
                      <td><label className="visually-hidden" htmlFor={`h${i}`}>Horários</label><input className="form-control form-control-sm" id={`h${i}`} name="horarios" maxLength={300} defaultValue={ln.horarios} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}><i className="bi bi-magic" aria-hidden="true"></i> Criar a rota neste local</button>
        </form>
      )}
    </div>
  );
}
