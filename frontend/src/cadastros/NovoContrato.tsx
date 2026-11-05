// O assistente "Novo contrato" e os convites (Fase 3a da migração para
// React; as telas antigas são templates/cadastros/novo_contrato/*.html +
// static/js/novo-contrato.js, com os mesmos textos, campos e classes).
// Passos: 1. Cliente → 2. Local → 3. Estrutura e QR → 4. Equipe. Cada passo
// grava na hora: dá para parar e voltar depois pelo mesmo endereço.
import { useState } from 'react';
import { useParams } from 'react-router';
import { Recados } from '../passagem/Recados';
import { enviar, Ir, Pagina, RecadosDoEnvio, tresDigitos, useFormulario, useIr } from './comum';
import { camposDaFuncao, continuar, etapas, situacao } from './regras';
import type {
  ConviteCriado as DadosDoConviteCriado, DadosDaEquipe, DadosDaEstrutura, DadosDoNovoContrato, DadosDoNovoLocal,
  DadosDosConvites, Passos as DadosDosPassos,
} from './tipos';

const API = '/api/v1/cadastros';

/** Os quatro passos do assistente (``_passos.html``). */
export function Passos({ p }: { p: DadosDosPassos }) {
  const loc = p.local;
  const cli = p.cliente;
  return (
    <>
      <nav aria-label="Passos do novo contrato">
        <ol className="fc-passos">
          {etapas(p).map((e) => {
            const dentro = (
              <>
                <span className="n">{e.n < p.atual
                  ? <><i className="bi bi-check-lg" aria-hidden="true"></i><span className="visually-hidden">feito:</span></>
                  : e.n}</span>
                {' '}{e.rotulo}
              </>
            );
            return (
              <li className={e.classe || undefined} key={e.n}>
                {e.url ? <Ir href={e.url}>{dentro}</Ir> : <span aria-current={e.atual ? 'step' : undefined}>{dentro}</span>}
              </li>
            );
          })}
        </ol>
      </nav>
      {loc ? (
        <p className="small text-muted mb-3"><i className="bi bi-geo-alt" aria-hidden="true"></i> {cli ? cli.nome : ''}{cli && ' › '}<strong>{loc.nome}</strong></p>
      ) : cli ? (
        <p className="small text-muted mb-3"><i className="bi bi-briefcase" aria-hidden="true"></i> {cli.nome}</p>
      ) : null}
    </>
  );
}

// ── Passo 1: cliente ──────────────────────────────────────────────────────

export function NovoContrato({ dados }: { dados: DadosDoNovoContrato }) {
  const { submeter, ocupado, aviso } = useFormulario();
  return (
    <div data-tela-pronta="novo-contrato">
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Novo contrato</h1>
      <p className="fc-sub">Quatro passos: o cliente, o local, onde ficam os QR e quem trabalha lá. Cada passo fica salvo na hora: dá para parar e continuar depois por aqui.</p>
      <Passos p={dados.passos} />

      <div className="fc-cartao mb-3">
        <h2 className="h6 fw-bold">De qual cliente é o local?</h2>
        {dados.clientes.length ? (
          <div className="list-group list-group-flush">
            {dados.clientes.map((c) => (
              <div className="list-group-item px-0" key={c.id}>
                <div className="d-flex flex-wrap align-items-center gap-2">
                  {c.logo && <img className="fc-logo-cliente" src={c.logo} alt={`Logo de ${c.nome}`} />}
                  <strong>{c.nome}</strong>
                  {c.centro_custo && <span className="small text-muted">CC {c.centro_custo}</span>}
                  <Ir className="btn btn-primary btn-sm fw-bold ms-auto" href={`/novo/novo-contrato/cliente/${c.id}/local`}><i className="bi bi-plus-lg" aria-hidden="true"></i> Novo local deste cliente</Ir>
                </div>
                {c.locais.length > 0 && (
                  <ul className="list-unstyled small mt-2 mb-0">
                    {c.locais.map((l) => {
                      const a = l.andamento;
                      const seguir = continuar(l.id, a);
                      return (
                        <li className="d-flex flex-wrap gap-2 align-items-center py-1 border-top" key={l.id}>
                          <span>{l.nome}</span>
                          <span className="text-muted">{a.pontos} QR · {a.equipe} pessoa(s){a.convites > 0 && ` · ${a.convites} convite(s) aberto(s)`}</span>
                          <Ir className="ms-auto" href={seguir.url}>{seguir.rotulo}</Ir>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="fc-vazio">{dados.pode_criar
            ? 'Você ainda não tem cliente. Cadastre o primeiro logo abaixo.'
            : 'O seu gerente ainda não tem cliente cadastrado. Peça a ele para cadastrar o cliente; depois você monta os locais aqui.'}</div>
        )}
      </div>

      {dados.pode_criar && (
        <details className="fc-cartao" open={!dados.clientes.length}>
          <summary className="fw-bold">Cadastrar cliente novo</summary>
          {!dados.empresas.length ? (
            <div className="alert alert-warning small mt-3 mb-0">Ainda não há empresa do grupo cadastrada. Peça ao administrador para cadastrar em Cadastros › Empresas do grupo.</div>
          ) : (
            <form method="post" encType="multipart/form-data" className="mt-3" onSubmit={submeter(`${API}/novo-contrato/cliente`)}>
              <div className="row g-2">
                <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor="nome">Nome do cliente</label>
                  <input className="form-control" id="nome" name="nome" required maxLength={120} placeholder="Ex.: Trino Frio" /></div>
                <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor="centro_custo">Centro de custo</label>
                  <input className="form-control" id="centro_custo" name="centro_custo" maxLength={50} /></div>
                <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor="empresa_id">Empresa do grupo que atende</label>
                  <select className="form-select" id="empresa_id" name="empresa_id" required>
                    {dados.empresas.map((e) => <option value={e.id} key={e.id}>{e.nome}</option>)}
                  </select></div>
                <div className="col-12"><label className="form-label small fw-semibold" htmlFor="logo">Logo do cliente (opcional)</label>
                  <input className="form-control" id="logo" name="logo" type="file" accept="image/png,image/jpeg,image/webp" />
                  <div className="form-text">PNG ou JPG até 2 MB. Ela sai nas etiquetas de QR; sem logo, sai o nome do cliente.</div></div>
              </div>
              <button className="btn btn-primary fw-bold mt-3" type="submit" disabled={ocupado}>Cadastrar e seguir para o local</button>
            </form>
          )}
        </details>
      )}
    </div>
  );
}

export function PaginaNovoContrato() {
  return <Pagina<DadosDoNovoContrato> api="/cadastros/novo-contrato">{(d) => <NovoContrato dados={d} />}</Pagina>;
}

// ── Passo 2: local ────────────────────────────────────────────────────────

export function NovoLocal({ dados }: { dados: DadosDoNovoLocal }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const cli = dados.cliente;
  return (
    <div data-tela-pronta="novo-local">
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Novo local</h1>
      <p className="fc-sub">O armazém, a loja ou a sede onde a equipe trabalha.</p>
      <Passos p={dados.passos} />

      <div className="fc-cartao mb-3">
        <form method="post" onSubmit={submeter(`${API}/novo-contrato/cliente/${cli.id}/local`)}>
          <div className="row g-2">
            <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor="name">Nome do local</label>
              <input className="form-control" id="name" name="name" required maxLength={120} placeholder={`Ex.: ${cli.nome} — Armazém 1 (Simões Filho)`} /></div>
            <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor="cost_center">Centro de custo do local</label>
              <input className="form-control" id="cost_center" name="cost_center" maxLength={50} /></div>
            <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor="estado_id">Estado</label>
              <select className="form-select" id="estado_id" name="estado_id" required defaultValue="">
                <option value="">Escolha</option>
                {dados.estados.map((e) => <option value={e.id} key={e.id}>{e.nome}</option>)}
              </select>
              {!dados.estados.length && <div className="form-text text-danger">Nenhum estado em uso. Peça ao administrador para ativar em Cadastros › Estados em uso.</div>}</div>
            <div className="col-12"><label className="form-label small fw-semibold" htmlFor="endereco">Endereço</label>
              <input className="form-control" id="endereco" name="endereco" maxLength={255} /></div>
          </div>
          <button className="btn btn-primary fw-bold mt-3" type="submit" disabled={ocupado}>Cadastrar e seguir para a estrutura</button>
        </form>
      </div>

      {dados.pode_logo && (
        <details className="fc-cartao">
          <summary className="fw-bold">{cli.logo ? `Trocar a logo de ${cli.nome}` : `Enviar a logo de ${cli.nome}`}</summary>
          <form method="post" encType="multipart/form-data" className="mt-3" onSubmit={submeter(`${API}/novo-contrato/cliente/${cli.id}/logo`)}>
            {cli.logo && <img className="fc-logo-cliente mb-2" src={cli.logo} alt={`Logo atual de ${cli.nome}`} />}
            <label className="visually-hidden" htmlFor="logo">Arquivo da logo</label>
            <input className="form-control" id="logo" name="logo" type="file" accept="image/png,image/jpeg,image/webp" required />
            <div className="form-text">PNG ou JPG até 2 MB. Sai nas etiquetas de QR de todos os locais deste cliente.</div>
            <button className="btn btn-outline-secondary fw-bold mt-2" type="submit" disabled={ocupado}>Salvar logo</button>
          </form>
        </details>
      )}
    </div>
  );
}

export function PaginaNovoLocal() {
  const { id } = useParams();
  return <Pagina<DadosDoNovoLocal> api={`/cadastros/novo-contrato/cliente/${id}/local`}>{(d) => <NovoLocal dados={d} />}</Pagina>;
}

// ── Passo 3: estrutura e QR ───────────────────────────────────────────────

export function Estrutura({ dados }: { dados: DadosDaEstrutura }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const { local: loc, andamento: a } = dados;
  return (
    <div data-tela-pronta="estrutura">
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Estrutura e QR</h1>
      <p className="fc-sub">Onde a equipe trabalha: cada ponto ganha um QR para colar na parede. O primeiro a colar é o da <strong>entrada</strong>: a pessoa lê ao chegar e o turno começa.</p>
      <Passos p={dados.passos} />

      <div className="fc-modulos mb-3">
        <div className="fc-cartao">
          <h2 className="h6 fw-bold"><i className="bi bi-file-earmark-spreadsheet" aria-hidden="true"></i> Tem a planilha do plano de limpeza?</h2>
          <p className="small text-muted">O sistema lê a planilha e monta setores, QR, checklists e rotas de uma vez. Você confere antes de gravar.</p>
          <Ir className="btn btn-primary fw-bold" href={dados.links.importar}>Importar a planilha</Ir>
        </div>
        <div className="fc-cartao">
          <h2 className="h6 fw-bold"><i className="bi bi-printer" aria-hidden="true"></i> Etiquetas</h2>
          <p className="small text-muted">{a.pontos} QR neste local{!a.entrada && ', ainda sem o QR da entrada'}. A folha sai em A4, 8 etiquetas por página, com a logo do cliente.</p>
          {a.pontos
            ? <a className="btn btn-outline-secondary fw-bold" href={dados.links.etiquetas} target="_blank" rel="noopener">Imprimir etiquetas</a>
            : <p className="small mb-0">Cadastre os pontos primeiro.</p>}
        </div>
      </div>

      <div className="fc-cartao mb-3">
        <h2 className="h6 fw-bold">Cadastrar um ambiente com os seus QR</h2>
        <p className="small text-muted">Ex.: setor "Administrativo", ambiente "Banheiro masculino", pontos "Pias" e "Vasos". Sem pontos, o próprio ambiente vira o QR.</p>
        <form method="post" onSubmit={submeter(`${API}/novo-contrato/${loc.id}/estrutura`)}>
          <div className="row g-2">
            <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor="setor_id">Setor</label>
              <select className="form-select" id="setor_id" name="setor_id" defaultValue="">
                <option value="">Setor novo (escreva ao lado)</option>
                {dados.setores.map((s) => <option value={s.id} key={s.id}>{s.nome}</option>)}
              </select></div>
            <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor="setor_nome">Nome do setor novo</label>
              <input className="form-control" id="setor_nome" name="setor_nome" maxLength={120} placeholder="Ex.: Administrativo" /></div>
            <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor="ambiente_nome">Ambiente</label>
              <input className="form-control" id="ambiente_nome" name="ambiente_nome" required maxLength={120} placeholder="Ex.: Banheiro masculino" /></div>
            <div className="col-12"><label className="form-label small fw-semibold" htmlFor="pontos">Pontos com QR (um por linha, opcional)</label>
              <textarea className="form-control" id="pontos" name="pontos" rows={3} placeholder={'Pias\nVasos'}></textarea></div>
            {!a.entrada && (
              <div className="col-12"><div className="form-check">
                <input className="form-check-input" type="checkbox" id="entrada" name="entrada" value="1" />
                <label className="form-check-label" htmlFor="entrada">O primeiro ponto é a <strong>entrada do local</strong> (o QR que a equipe lê ao chegar)</label>
              </div></div>
            )}
          </div>
          <button className="btn btn-primary fw-bold mt-3" type="submit" disabled={ocupado}>Cadastrar</button>
        </form>
      </div>

      <div className="fc-cartao p-0 mb-3">
        <div className="px-3 pt-3 d-flex flex-wrap align-items-center gap-2">
          <h2 className="h6 fw-bold mb-0">O que já está cadastrado</h2>
          <Ir className="small ms-auto" href={`/novo/cadastros/locais/${loc.id}`}>Editar a estrutura completa</Ir>
        </div>
        {dados.setores.length ? dados.setores.map((s) => (
          <div className="border-top px-3 py-2" key={s.id}>
            <strong>{s.nome}</strong>
            <ul className="list-unstyled small mb-0">
              {s.ambientes.map((amb, n) => (
                <li className="mt-1" key={n}>{amb.nome}:{' '}
                  {amb.pontos.length ? amb.pontos.map((p, i) => (
                    <span key={i}><span className="badge text-bg-light">QR {tresDigitos(p.numero)} · {p.nome}{p.entrada && ' · entrada'}</span>{' '}</span>
                  )) : <span className="text-muted">sem QR</span>}
                </li>
              ))}
            </ul>
          </div>
        )) : <div className="fc-vazio">Nada cadastrado ainda. Importe a planilha ou cadastre o primeiro ambiente acima.</div>}
      </div>

      <div className="d-flex flex-wrap gap-2">
        <Ir className="btn btn-primary btn-lg fw-bold" href={`/novo/novo-contrato/${loc.id}/equipe`}>Seguir para a equipe <i className="bi bi-arrow-right" aria-hidden="true"></i></Ir>
        {a.rotas > 0 && <Ir className="btn btn-outline-secondary btn-lg" href={dados.links.rotas}>Ver as {a.rotas} rota(s) do local</Ir>}
      </div>
    </div>
  );
}

export function PaginaEstrutura() {
  const { id } = useParams();
  return <Pagina<DadosDaEstrutura> api={`/cadastros/novo-contrato/${id}/estrutura`}>{(d) => <Estrutura dados={d} />}</Pagina>;
}

// ── Passo 4: equipe e convites ────────────────────────────────────────────

function Situacao({ sit }: { sit: string }) {
  const s = situacao(sit);
  return <span className={`badge ${s.classe} ms-auto`}>{s.rotulo}</span>;
}

/** A página com o link do convite: a resposta do envio (sem endereço próprio:
 * o link não passa pelo histórico do navegador, como na tela antiga). */
export function ConviteCriado({ dados }: { dados: DadosDoConviteCriado }) {
  const { convite } = dados;
  return (
    <div data-tela-pronta="convite-criado">
      <h1 className="fc-titulo">Convite pronto</h1>
      {dados.passos && <Passos p={dados.passos} />}
      <div className="fc-cartao mb-3">
        <p className="mb-2"><strong>{convite.nome}</strong> · {dados.perfil}{dados.locais.length > 0 && ` · ${dados.locais.join(', ')}`}</p>
        {dados.enviado === true && (
          <div className="alert alert-success small"><i className="bi bi-envelope-check" aria-hidden="true"></i> O convite já foi enviado para {convite.email}. Se preferir, mande também pelo WhatsApp.</div>
        )}
        {dados.enviado === false && (
          <div className="alert alert-warning small">O e-mail não saiu agora. Mande pelo WhatsApp ou pelo botão de e-mail abaixo.</div>
        )}
        <p className="small text-muted mb-2">Mande o link para a pessoa. Ele vale 7 dias e funciona uma vez só. <strong>Este link não aparece de novo</strong>: se perder, gere um link novo em "Meus convites".</p>
        <div className="d-flex flex-wrap gap-2 mb-3">
          <a className="btn btn-success btn-lg fw-bold" href={dados.whatsapp} target="_blank" rel="noopener"><i className="bi bi-whatsapp" aria-hidden="true"></i> Enviar pelo WhatsApp</a>
          <a className="btn btn-outline-secondary btn-lg fw-bold" href={dados.email}><i className="bi bi-envelope" aria-hidden="true"></i> Enviar por e-mail</a>
        </div>
        <label className="form-label small fw-semibold" htmlFor="link">Ou copie o link</label>
        <input className="form-control fc-link-convite" id="link" value={dados.link} readOnly />
      </div>
      <div className="d-flex flex-wrap gap-2">
        {dados.local && <Ir className="btn btn-primary fw-bold" href={`/novo/novo-contrato/${dados.local.id}/equipe`}><i className="bi bi-person-plus" aria-hidden="true"></i> Convidar outra pessoa</Ir>}
        <Ir className="btn btn-outline-secondary" href="/novo/convites">Meus convites</Ir>
      </div>
    </div>
  );
}

export function Equipe({ dados }: { dados: DadosDaEquipe }) {
  const loc = dados.local;
  const valores = dados.perfis.map(([v]) => v);
  const [papel, setPapel] = useState(valores.includes('encarregado') ? 'encarregado' : (valores[0] || ''));
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [criado, setCriado] = useState<DadosDoConviteCriado | null>(null);
  const campos = camposDaFuncao(papel);
  const convidar = (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    if (ocupado) return;
    setOcupado(true);
    setErro(null);
    enviar(`${API}/novo-contrato/${loc.id}/equipe`, new FormData(ev.currentTarget)).then(({ ok, dados: r }) => {
      setOcupado(false);
      window.scrollTo(0, 0);
      if (ok) { setCriado(r as unknown as DadosDoConviteCriado); return; }
      setErro(r.error || 'Algo deu errado. Tente de novo.');
    });
  };
  if (criado) return <ConviteCriado dados={criado} />;
  return (
    <div data-tela-pronta="equipe">
      <RecadosDoEnvio />
      {erro && <Recados servidor={[{ tipo: 'danger', texto: erro }]} key={erro} />}
      <h1 className="fc-titulo">Equipe</h1>
      <p className="fc-sub">Convide quem vai trabalhar neste local. A pessoa recebe um link pelo WhatsApp ou por e-mail, cria a própria senha e já entra no lugar certo. O link vale 7 dias e funciona uma vez só.</p>
      <Passos p={dados.passos} />

      <div className="fc-cartao mb-3">
        <h2 className="h6 fw-bold">Convidar uma pessoa</h2>
        <form method="post" onSubmit={convidar}>
          <div className="row g-2">
            <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor="nome">Nome</label>
              <input className="form-control" id="nome" name="nome" required maxLength={100} /></div>
            <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor="email">E-mail (é com ele que a pessoa entra)</label>
              <input className="form-control" id="email" name="email" type="email" required maxLength={150} inputMode="email" /></div>
            <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor="telefone">Celular com DDD (para o WhatsApp)</label>
              <input className="form-control" id="telefone" name="telefone" inputMode="tel" maxLength={20} placeholder="71 99999-0000" /></div>
            <div className="col-md-4"><label className="form-label small fw-semibold" htmlFor="role">Função</label>
              <select className="form-select" id="role" name="role" required value={papel} onChange={(ev) => setPapel(ev.target.value)}>
                {dados.perfis.map(([valor, rotulo]) => <option value={valor} key={valor}>{rotulo}</option>)}
              </select></div>
            <div className="col-md-4" data-so-equipe hidden={!campos.equipe}><label className="form-label small fw-semibold" htmlFor="superior_id">Responde a</label>
              <select className="form-select" id="superior_id" name="superior_id" defaultValue="">
                <option value="">{dados.eu.e_admin ? 'Ninguém (fora da cadeia)' : `Você (${dados.eu.nome})`}</option>
                {dados.superiores.map((s) => <option value={s.id} key={s.id}>{s.nome} — {s.perfil}</option>)}
              </select></div>
            {valores.includes('cliente') && dados.clientes.length > 0 && (
              <div className="col-md-4" data-so-cliente hidden={!campos.cliente}><label className="form-label small fw-semibold" htmlFor="cliente_id">De qual cliente</label>
                <select className="form-select" id="cliente_id" name="cliente_id" defaultValue={loc.cliente_id ? String(loc.cliente_id) : undefined}>
                  {dados.clientes.map((c) => <option value={c.id} key={c.id}>{c.nome}</option>)}
                </select></div>
            )}
            <div className="col-12" data-so-equipe hidden={!campos.equipe}>
              <fieldset>
                <legend className="form-label small fw-semibold">Locais que a pessoa vai ver</legend>
                <div className="d-flex flex-wrap gap-3">
                  {dados.locais.map((l) => (
                    <div className="form-check" key={l.id}>
                      <input className="form-check-input" type="checkbox" name="locais" value={l.id} id={`loc${l.id}`} defaultChecked={l.id === loc.id} />
                      <label className="form-check-label" htmlFor={`loc${l.id}`}>{l.nome}</label>
                    </div>
                  ))}
                </div>
              </fieldset>
            </div>
          </div>
          <button className="btn btn-primary fw-bold mt-3" type="submit" disabled={ocupado}><i className="bi bi-send" aria-hidden="true"></i> Criar convite</button>
        </form>
      </div>

      <div className="row g-3">
        <div className="col-lg-6">
          <div className="fc-cartao p-0 h-100">
            <h2 className="h6 fw-bold px-3 pt-3">Quem já trabalha aqui</h2>
            {dados.equipe.length ? dados.equipe.map((u, n) => (
              <div className="border-top px-3 py-2 d-flex flex-wrap gap-2" key={n}><strong>{u.nome}</strong><span className="small text-muted">{u.perfil}</span></div>
            )) : <div className="fc-vazio">Ninguém ainda.</div>}
          </div>
        </div>
        <div className="col-lg-6">
          <div className="fc-cartao p-0 h-100">
            <div className="px-3 pt-3 d-flex align-items-center gap-2"><h2 className="h6 fw-bold mb-0">Convites deste local</h2>
              <Ir className="small ms-auto" href="/novo/convites">Todos os meus convites</Ir></div>
            {dados.convites.length ? dados.convites.map((c) => (
              <div className="border-top px-3 py-2 d-flex flex-wrap gap-2 align-items-center" key={c.id}>
                <strong>{c.nome}</strong><span className="small text-muted">{c.perfil}</span>
                <Situacao sit={c.situacao} />
              </div>
            )) : <div className="fc-vazio">Nenhum convite ainda.</div>}
          </div>
        </div>
      </div>

      <div className="d-flex flex-wrap gap-2 mt-3">
        <Ir className="btn btn-outline-secondary btn-lg" href={`/novo/novo-contrato/${loc.id}/estrutura`}><i className="bi bi-arrow-left" aria-hidden="true"></i> Estrutura e QR</Ir>
        <Ir className="btn btn-primary btn-lg fw-bold" href={dados.links.concluir}>Concluir: ver a rotina do local</Ir>
      </div>
    </div>
  );
}

export function PaginaEquipe() {
  const { id } = useParams();
  return <Pagina<DadosDaEquipe> api={`/cadastros/novo-contrato/${id}/equipe`}>{(d) => <Equipe dados={d} />}</Pagina>;
}

// ── Convites ──────────────────────────────────────────────────────────────

export function Convites({ dados }: { dados: DadosDosConvites }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const ir = useIr();
  const [criado, setCriado] = useState<DadosDoConviteCriado | null>(null);
  const [gerando, setGerando] = useState(false);
  const novoLink = (id: number) => (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    if (gerando) return;
    setGerando(true);
    enviar(`${API}/convites/${id}/novo-link`, new FormData(ev.currentTarget)).then(({ ok, dados: r }) => {
      setGerando(false);
      window.scrollTo(0, 0);
      if (ok) { setCriado(r as unknown as DadosDoConviteCriado); return; }
      ir(r.destino || '/novo/convites', [{ tipo: 'danger', texto: r.error || 'Algo deu errado. Tente de novo.' }]);
    });
  };
  if (criado) return <ConviteCriado dados={criado} />;
  return (
    <div data-tela-pronta="convites">
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Convites</h1>
      <p className="fc-sub">Quem você convidou e se já criou a conta. Link perdido ou vencido? Gere um link novo: o anterior deixa de valer.</p>
      <div className="fc-cartao p-0">
        {dados.convites.length ? dados.convites.map((c) => (
          <div className="border-top px-3 py-2" key={c.id}>
            <div className="d-flex flex-wrap gap-2 align-items-center">
              <strong>{c.nome}</strong>
              <span className="small text-muted">{c.email} · {c.perfil}</span>
              <Situacao sit={c.situacao} />
            </div>
            <div className="small text-muted">{c.onde} · convidado por {c.criado_por} em {c.criado_em}</div>
            {c.situacao !== 'aceito' && (
              <div className="d-flex flex-wrap gap-2 mt-2">
                <form method="post" className="m-0" onSubmit={novoLink(c.id)}>
                  <button className="btn btn-outline-secondary btn-sm fw-bold" type="submit" disabled={gerando || ocupado}><i className="bi bi-link-45deg" aria-hidden="true"></i> Gerar link novo</button>
                </form>
                {c.situacao === 'pendente' && (
                  <form method="post" className="m-0" onSubmit={submeter(`${API}/convites/${c.id}/cancelar`)}>
                    <button className="btn btn-outline-danger btn-sm" type="submit" disabled={gerando || ocupado}>Cancelar convite</button>
                  </form>
                )}
              </div>
            )}
          </div>
        )) : <div className="fc-vazio">Nenhum convite ainda. Os convites saem do passo "Equipe" do novo contrato.</div>}
      </div>

      <h2 className="h6 fw-bold mt-4" id="configurar-passagem">Quem pode configurar a passagem de turno</h2>
      <p className="fc-sub">Configurar a passagem é mudar as perguntas, os turnos, as áreas e os tipos de ocorrência do modelo. A gestão já pode. Um encarregado só pode se você autorizar, pessoa a pessoa. Aparecem aqui os encarregados dos seus locais.</p>
      <div className="fc-cartao p-0">
        {dados.encarregados.length ? dados.encarregados.map((u) => (
          <div className="border-top px-3 py-2 d-flex flex-wrap gap-2 align-items-center" key={u.id}>
            <div>
              <strong>{u.nome}</strong>
              <div className="small text-muted">{u.locais}</div>
            </div>
            <span className={`badge ${u.autorizado ? 'text-bg-success' : 'text-bg-secondary'} ms-auto`}>{u.autorizado ? 'pode configurar' : 'não configura'}</span>
            {u.autorizado ? (
              <form method="post" className="m-0" onSubmit={submeter(`${API}/convites/pessoas/${u.id}/retirar-passagem`)}>
                <button className="btn btn-outline-danger btn-sm" type="submit" disabled={gerando || ocupado}>Retirar a autorização</button>
              </form>
            ) : (
              <form method="post" className="m-0" onSubmit={submeter(`${API}/convites/pessoas/${u.id}/autorizar-passagem`)}>
                <button className="btn btn-outline-primary btn-sm fw-bold" type="submit" disabled={gerando || ocupado}>Autorizar a configurar</button>
              </form>
            )}
          </div>
        )) : <div className="fc-vazio">Nenhum encarregado nos seus locais ainda.</div>}
      </div>
    </div>
  );
}

export function PaginaConvites() {
  return <Pagina<DadosDosConvites> api="/cadastros/convites">{(d) => <Convites dados={d} />}</Pagina>;
}
