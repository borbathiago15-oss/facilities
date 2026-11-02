// As pessoas e os locais do administrador (Fase 6a; as telas antigas são
// templates/core/usuarios.html e contratos.html, com os mesmos textos,
// campos e classes). Só o administrador. Os envios vão ao mesmo caminho da
// antiga abaixo de /api/v1 e chamam a mesma ação (core.admin.acao_*).
//
// A senha temporária (cadastrar e "Gerar senha temporária") aparece uma vez,
// como a chave da integração: o texto vem só na resposta do envio que a cria
// e fica só na memória desta tela (o estado da página) — nunca no endereço,
// no histórico do navegador, na cópia dos dados (react-query), no
// armazenamento do aparelho nem no console. Sair da tela (ou qualquer
// navegação, como o "Salvar") a esquece.
import { useState } from 'react';
import { Ir, RecadosDoEnvio, enviar, useFormulario, useIr } from '../cadastros/comum';
import { Recados } from '../passagem/Recados';
import type { DadosDasPessoas, DadosDosLocais, Local, Pessoa, SenhaNova } from './tipos';

const API = '/api/v1/admin';

// ── Pessoas ──────────────────────────────────────────────────────────────

function CamposDaPessoa({ dados, u }: { dados: DadosDasPessoas; u: Pessoa | null }) {
  const sfx = u ? String(u.id) : 'novo';
  return (
    <div className="row g-2">
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`nome${sfx}`}>Nome</label>
        <input className="form-control" id={`nome${sfx}`} name="name" defaultValue={u ? u.nome : ''} required maxLength={100} /></div>
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`email${sfx}`}>E-mail (login)</label>
        <input className="form-control" id={`email${sfx}`} name="email" type="email" defaultValue={u ? u.email : ''} required maxLength={150} /></div>
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`perfil${sfx}`}>Perfil</label>
        <select className="form-select" id={`perfil${sfx}`} name="role" defaultValue={u ? u.perfil : 'encarregado'}>
          {dados.perfis.map(([chave, rotulo]) => <option value={chave} key={chave}>{rotulo}</option>)}
        </select></div>
      <div className="col-md-6 d-flex align-items-end">
        <div className="form-check">
          <input className="form-check-input" type="checkbox" name="all_clients" value="1" id={`todos${sfx}`} defaultChecked={!!u && u.todos_os_locais} />
          <label className="form-check-label small" htmlFor={`todos${sfx}`}>Todos os locais (inclusive os futuros)</label>
        </div>
      </div>
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`sup${sfx}`}>Superior direto</label>
        <select className="form-select" id={`sup${sfx}`} name="superior_id" defaultValue={u && u.superior_id !== null ? String(u.superior_id) : ''}>
          <option value="">Ninguém (topo da cadeia, ou fora dela)</option>
          {dados.superiores.filter((s) => !u || s.id !== u.id).map((s) => (
            <option value={s.id} key={s.id}>{s.nome} — {s.perfil}</option>
          ))}
        </select>
        <div className="form-text">Gerente › Coordenador › Supervisor › Encarregado/ASG e Técnico. Quem está acima vê os locais de quem está abaixo.</div></div>
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`cli${sfx}`}>Cliente (só para o perfil Cliente)</label>
        <select className="form-select" id={`cli${sfx}`} name="cliente_id" defaultValue={u && u.cliente_id !== null ? String(u.cliente_id) : ''}>
          <option value="">—</option>
          {dados.clientes.map((k) => <option value={k.id} key={k.id}>{k.nome}</option>)}
        </select></div>
      <div className="col-12"><span className="form-label small fw-semibold d-block">Locais</span>
        <div className="d-flex flex-wrap gap-2">
          {dados.locais.length ? dados.locais.map((c) => (
            <label className={`border rounded px-2 py-1 small${c.ativo ? '' : ' text-muted'}`} key={c.id}>
              <input type="checkbox" name="clients" value={c.id} defaultChecked={!!u && u.locais.includes(c.id)} /> {c.nome}{!c.ativo && ' (inativo)'}
            </label>
          )) : <span className="small text-muted">Cadastre os locais primeiro.</span>}
        </div></div>
      <div className="col-12"><span className="form-label small fw-semibold d-block">Permissões extras</span>
        {dados.permissoes.map(([chave, rotulo]) => (
          <div className="form-check" key={chave}>
            <input className="form-check-input" type="checkbox" name="permissoes" value={chave} id={`p${chave}${sfx}`} defaultChecked={!!u && u.permissoes.includes(chave)} />
            <label className="form-check-label small" htmlFor={`p${chave}${sfx}`}>{rotulo} <span className="text-muted">(o gestor já tem)</span></label>
          </div>
        ))}
      </div>
    </div>
  );
}

/** A senha temporária no recado, com a senha destacada para copiar. */
function RecadoDaSenha({ senha }: { senha: SenhaNova }) {
  const n = senha.texto.indexOf(senha.senha);
  const antes = n >= 0 ? senha.texto.slice(0, n) : senha.texto;
  const depois = n >= 0 ? senha.texto.slice(n + senha.senha.length) : '';
  return (
    <div className="alert alert-success" role="status">
      {antes}{n >= 0 && <code className="user-select-all">{senha.senha}</code>}{depois}
      <p className="small mb-0 mt-1">Esta senha não aparece de novo depois que você sair desta tela.</p>
    </div>
  );
}

export function Pessoas({ dados, senha, aoGerar }: {
  dados: DadosDasPessoas; senha: SenhaNova | null; aoGerar: (s: SenhaNova) => void;
}) {
  const { submeter, ocupado, aviso } = useFormulario();
  const ir = useIr();
  const [gerando, setGerando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  // Cadastrar e "Gerar senha temporária": a resposta traz a senha, que fica
  // nesta tela; a recusa volta à tela com o recado, como a antiga.
  const comSenha = (url: string, form: HTMLFormElement, depois?: () => void) => {
    if (gerando) return;
    setGerando(true);
    setErro(null);
    enviar(url, new FormData(form)).then(({ ok, dados: r }) => {
      setGerando(false);
      const s = (r as { senha?: SenhaNova }).senha;
      if (ok && s) {
        if (depois) depois();
        aoGerar({ texto: s.texto, senha: s.senha });
        window.scrollTo(0, 0);
        return;
      }
      if (r.destino) { ir(r.destino, r.recados); return; }
      setErro(r.error || 'Algo deu errado. Tente de novo.');
      window.scrollTo(0, 0);
    });
  };
  const cadastrar = (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    const form = ev.currentTarget;
    comSenha(`${API}/usuarios`, form, () => {
      form.reset();
      const detalhes = form.closest('details');
      if (detalhes) detalhes.open = false;
    });
  };
  const gerar = (u: Pessoa) => (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    if (!window.confirm(`Gerar uma senha temporária nova para ${u.nome}? A atual deixa de valer.`)) return;
    comSenha(`${API}/usuarios/${u.id}/nova-senha`, ev.currentTarget);
  };
  return (
    <div data-tela-pronta="pessoas">
      <RecadosDoEnvio />{aviso}
      {erro && <Recados servidor={[{ tipo: 'danger', texto: erro }]} key={erro} />}
      {senha && <RecadoDaSenha senha={senha} />}
      <h1 className="fc-titulo">Pessoas</h1>
      <p className="fc-sub">Quem entra no sistema, com que perfil, abaixo de quem e em quais locais. Ninguém é apagado: desative quem saiu, e o histórico continua com o nome certo.</p>

      <details className="fc-cartao mb-3">
        <summary className="fw-bold">Cadastrar pessoa</summary>
        <form method="post" className="mt-3" onSubmit={cadastrar} autoComplete="off">
          <CamposDaPessoa dados={dados} u={null} />
          <button className="btn btn-primary fw-bold mt-3" type="submit" disabled={gerando}>Cadastrar</button>
          <span className="small text-muted ms-2">O sistema gera uma senha temporária; no primeiro acesso a pessoa escolhe a dela.</span>
        </form>
      </details>

      <div className="fc-cartao p-0">
        {dados.pessoas.length ? dados.pessoas.map((u) => (
          <details className="border-bottom px-3 py-2" key={u.id}>
            <summary className="d-flex flex-wrap gap-2 align-items-center">
              <strong>{u.nome}</strong>
              <span className="badge text-bg-light">{u.perfil_rotulo}</span>
              {!u.ativo && <span className="badge text-bg-secondary">inativo</span>}
              <span className="small text-muted">{u.email}</span>
              {u.segunda_etapa && <span className="badge text-bg-success" title="Segunda etapa ativada"><i className="bi bi-shield-check"></i> 2 etapas</span>}
              <span className="small text-muted ms-auto">{u.alcance}</span>
            </summary>
            {u.cadeia.length > 0 && (
              <p className="small text-muted mt-2 mb-0">Cadeia: {u.cadeia.map((p) => `${p.nome} (${p.perfil}) › `).join('')}{u.nome}</p>
            )}
            <form method="post" className="mt-3" onSubmit={submeter(`${API}/usuarios/${u.id}`)} autoComplete="off">
              <CamposDaPessoa dados={dados} u={u} />
              <div className="form-check mt-2"><input className="form-check-input" type="checkbox" name="is_active" value="1" id={`ativo${u.id}`} defaultChecked={u.ativo} />
                <label className="form-check-label small" htmlFor={`ativo${u.id}`}>Ativo (desmarque para bloquear o acesso)</label></div>
              <button className="btn btn-primary btn-sm fw-bold mt-2" type="submit" disabled={ocupado}>Salvar</button>
            </form>
            <form method="post" className="mt-2 mb-2" onSubmit={gerar(u)}>
              <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={gerando}><i className="bi bi-key"></i> Gerar senha temporária</button>
            </form>
            {u.segunda_etapa && (
              <form method="post" className="mb-2" onSubmit={submeter(`${API}/usuarios/${u.id}/desligar-codigo`)}>
                <button className="btn btn-outline-secondary btn-sm" type="submit" disabled={ocupado}><i className="bi bi-shield-x"></i> Desligar a segunda etapa (perdeu o celular)</button>
              </form>
            )}
          </details>
        )) : <div className="fc-vazio">Nenhuma pessoa cadastrada.</div>}
      </div>
    </div>
  );
}

// ── Locais ───────────────────────────────────────────────────────────────

function CamposDoLocal({ dados, c }: { dados: DadosDosLocais; c: Local | null }) {
  const sfx = c ? String(c.id) : 'novo';
  return (
    <div className="row g-2">
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`lnome${sfx}`}>Nome do local</label>
        <input className="form-control" id={`lnome${sfx}`} name="name" defaultValue={c ? c.nome : ''} required maxLength={120} placeholder="Ex.: GL — Armazém 1 (Simões Filho)" /></div>
      <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor={`lcc${sfx}`}>Subcentro de custo</label>
        <input className="form-control" id={`lcc${sfx}`} name="cost_center" defaultValue={c ? c.centro_de_custo : ''} maxLength={50} /></div>
      <div className="col-md-3"><label className="form-label small fw-semibold" htmlFor={`lresp${sfx}`}>Gestor responsável</label>
        <select className="form-select" id={`lresp${sfx}`} name="responsible_user_id" defaultValue={c && c.responsavel_id !== null ? String(c.responsavel_id) : ''}>
          <option value="">—</option>
          {dados.gestores.map((g) => <option value={g.id} key={g.id}>{g.nome}</option>)}
        </select></div>
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`lcli${sfx}`}>Cliente</label>
        <select className="form-select" id={`lcli${sfx}`} name="contratante_id" defaultValue={c && c.cliente_id !== null ? String(c.cliente_id) : ''}>
          <option value="">Sem cliente ligado</option>
          {dados.clientes.filter((k) => k.ativo || (c && c.cliente_id === k.id)).map((k) => (
            <option value={k.id} key={k.id}>{k.nome}</option>
          ))}
        </select></div>
      <div className="col-md-6"><label className="form-label small fw-semibold" htmlFor={`lest${sfx}`}>Estado</label>
        <select className="form-select" id={`lest${sfx}`} name="estado_id" defaultValue={c && c.estado_id !== null ? String(c.estado_id) : ''}>
          <option value="">—</option>
          {dados.estados.filter((e) => e.ativo || (c && c.estado_id === e.id)).map((e) => (
            <option value={e.id} key={e.id}>{e.nome}</option>
          ))}
        </select></div>
      <div className="col-12"><label className="form-label small fw-semibold" htmlFor={`lend${sfx}`}>Endereço</label>
        <input className="form-control" id={`lend${sfx}`} name="endereco" defaultValue={c ? c.endereco : ''} maxLength={255} /></div>
    </div>
  );
}

export function Locais({ dados }: { dados: DadosDosLocais }) {
  const { submeter, ocupado, aviso } = useFormulario();
  return (
    <div data-tela-pronta="locais">
      <RecadosDoEnvio />{aviso}
      <h1 className="fc-titulo">Locais</h1>
      <p className="fc-sub">Cada local é um armazém, loja ou sede de um cliente, num estado, com o seu subcentro de custo. A estrutura (setores, ambientes e pontos com QR) fica em "Estrutura"; áreas e turnos, na Passagem de Turno.</p>
      {!dados.clientes.length && (
        <div className="alert alert-info small">Para ligar os locais a um cliente, cadastre antes a <Ir href={dados.links.empresas}>empresa</Ir> e o <Ir href={dados.links.clientes}>cliente</Ir>; e ative os <Ir href={dados.links.estados}>estados</Ir> em uso.</div>
      )}

      <details className="fc-cartao mb-3" open={!dados.locais.length || undefined}>
        <summary className="fw-bold">Cadastrar local</summary>
        <form method="post" className="mt-3" onSubmit={submeter(`${API}/contratos`)}>
          <CamposDoLocal dados={dados} c={null} />
          <button className="btn btn-primary fw-bold mt-3" type="submit" disabled={ocupado}>Cadastrar</button>
        </form>
      </details>

      <div className="fc-cartao p-0">
        {dados.locais.length ? dados.locais.map((c) => (
          <details className="border-bottom px-3 py-2" key={c.id}>
            <summary className="d-flex flex-wrap gap-2 align-items-center">
              <strong>{c.nome}</strong>
              {c.cliente && <span className="small">{c.cliente}</span>}
              {c.estado && <span className="badge text-bg-light">{c.estado}</span>}
              {c.centro_de_custo && <span className="small text-muted">CC {c.centro_de_custo}</span>}
              {!c.ativo && <span className="badge text-bg-secondary">inativo</span>}
              <span className="small text-muted ms-auto">{c.responsavel || 'sem gestor responsável'}</span>
            </summary>
            <form method="post" className="mt-3 mb-2" onSubmit={submeter(`${API}/contratos/${c.id}`)}>
              <CamposDoLocal dados={dados} c={c} />
              <div className="form-check mt-2"><input className="form-check-input" type="checkbox" name="is_active" value="1" id={`cativo${c.id}`} defaultChecked={c.ativo} />
                <label className="form-check-label small" htmlFor={`cativo${c.id}`}>Ativo</label></div>
              <div className="d-flex flex-wrap gap-2 mt-2">
                <button className="btn btn-primary btn-sm fw-bold" type="submit" disabled={ocupado}>Salvar</button>
                <Ir className="btn btn-outline-secondary btn-sm" href={c.links.estrutura}><i className="bi bi-diagram-3"></i> Estrutura (setores, ambientes, QR)</Ir>
                <Ir className="btn btn-outline-secondary btn-sm" href={c.links.passagem}><i className="bi bi-gear"></i> Configurar a passagem de turno</Ir>
              </div>
            </form>
          </details>
        )) : <div className="fc-vazio">Nenhum local ainda.</div>}
      </div>
    </div>
  );
}
