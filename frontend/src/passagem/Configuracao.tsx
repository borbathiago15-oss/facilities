// O cadastro do modelo de passagem, contrato a contrato (Fase 2b da migração
// para React; a tela antiga é templates/diario_operacional/configuracao.html
// + static/js/diario_config.js, com o mesmo comportamento, os mesmos textos
// e as mesmas classes). A mesma ideia da régua do SLA Contratual: cada
// cliente cobra o que foi combinado com ele. A lista manda, e o editor à
// direita mostra sempre o modelo que está selecionado.
//
// As ações vão para as APIs de sempre (/passagem-de-turno/api/areas e
// /api/configuracoes) e o "Criar modelos" para o formulário de sempre
// (/passagem-de-turno/modelos-prontos), cujo recado chega pela API.
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { enviarBruto } from '../api';
import {
  avisoDeUso, avisoDoModeloSalvo, type LinhaDePergunta, linhaDaPergunta, mover, nModelos, opcoesDoTipo,
  perguntasParaSalvar,
} from './gestao';
import { Recados } from './Recados';
import type { AreaDoContrato, DadosDaConfiguracao, Modelo } from './tipos';
import './passagem.css';

type Linha = { n: number; nome: string };

function nomeDe(x: { nome?: string } | string): string {
  return (typeof x === 'object' && x && x.nome) || String(x);
}

function Remover({ onClick }: { onClick: () => void }) {
  return (
    <div className="col-2"><button type="button" className="btn btn-outline-danger w-100"
      aria-label="Remover este item" title="Remover este item" data-remover=".config-row" onClick={onClick}>×</button></div>
  );
}

function Areas({ areas, cliente }: { areas: AreaDoContrato[]; cliente: number }) {
  const chamarArea = (url: string, metodo: string, corpo: unknown) => {
    enviarBruto(url, { method: metodo, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo) })
      .then((r) => r.json().then((x) => ({ ok: r.ok, x })))
      .then((res) => {
        if (!res.ok) { window.alert(res.x.error || 'Não foi possível salvar a área.'); return; }
        window.location.reload();
      }).catch(() => window.alert('Falha de rede.'));
  };
  const novaArea = () => {
    let nome = window.prompt('Nome da área (ex.: Limpeza, Portaria, Manutenção predial):');
    if (nome === null) return;
    nome = nome.trim();
    if (!nome) return;
    chamarArea('/passagem-de-turno/api/areas', 'POST', { client_id: cliente, nome });
  };
  const renomear = (a: AreaDoContrato) => {
    let nome = window.prompt('Novo nome da área:', a.nome);
    if (nome === null) return;
    nome = nome.trim();
    if (!nome || nome === a.nome) return;
    chamarArea('/passagem-de-turno/api/areas/' + a.id, 'PUT', { nome });
  };
  // Desativar NÃO apaga: a área some dos seletores e continua amparando as
  // passagens já lançadas por ela.
  const alternar = (a: AreaDoContrato) => {
    if (a.ativo && a.modelos &&
        !window.confirm('A área "' + a.nome + '" ampara ' + nModelos(a.modelos) +
          '. Desativar esconde a área de quem lança; o que ' +
          'já foi lançado continua no histórico. Continuar?')) {
      return;
    }
    chamarArea('/passagem-de-turno/api/areas/' + a.id, 'PUT', { ativo: !a.ativo });
  };
  return (
    <div className="card shadow-sm border-0 mb-3" id="cfg-areas-card">
      <div className="card-header bg-white fw-bold d-flex justify-content-between align-items-center">
        <span>Áreas deste contrato</span>
        <button className="btn btn-sm btn-outline-primary" type="button" data-acao="novaArea" onClick={novaArea}>
          <i className="bi bi-plus"></i> Nova área</button>
      </div>
      <div className="card-body">
        <div className="ar-lista" id="cfg-areas">
          {areas.length ? areas.map((a) => (
            <div className={'ar-item' + (a.ativo ? '' : ' off')} key={a.id}>
              <span className="ar-nome">{a.nome}</span>
              <span className="ar-meta">{nModelos(a.modelos)}</span>
              <span className="ar-acoes">
                <button type="button" className="btn btn-sm btn-link p-0" data-acao="renomearArea"
                  onClick={() => renomear(a)}>renomear</button>
                <button type="button" className="btn btn-sm btn-link p-0" data-acao="alternarArea"
                  onClick={() => alternar(a)}>{a.ativo ? 'desativar' : 'reativar'}</button>
              </span>
            </div>
          )) : <div className="text-muted small">Nenhuma área cadastrada. Sem área, o contrato tem uma passagem só.</div>}
        </div>
        <div className="small text-muted mt-2">
          Cada área tem o seu modelo de passagem. O encarregado é do contrato e
          escolhe a área ao lançar.
        </div>
      </div>
    </div>
  );
}

/** Modelos prontos de facilities: ponto de partida para o contrato novo não
 * começar com o modelo em branco. Rodar de novo não duplica. O formulário é
 * o de sempre (ele redireciona); a tela se refaz e mostra o recado dele. */
function Prontos({ dados }: { dados: DadosDaConfiguracao }) {
  const [ocupado, setOcupado] = useState(false);
  const enviar = (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    setOcupado(true);
    enviarBruto(dados.links.modelos_prontos, { method: 'POST', body: new FormData(ev.currentTarget), redirect: 'manual' })
      .then((r) => {
        if (r.type === 'opaqueredirect' || r.ok) { window.location.reload(); return; }
        return r.json().catch(() => ({})).then((x: { error?: string }) => {
          setOcupado(false);
          window.alert(x.error || 'Não foi possível criar os modelos. Recarregue a página e tente de novo.');
        });
      }, () => { setOcupado(false); window.alert('Falha de rede.'); });
  };
  return (
    <details className="card shadow-sm border-0 mb-3" id="cfg-prontos" open={!dados.configs.length}>
      <summary className="card-header bg-white fw-bold">Começar com um modelo pronto</summary>
      <form className="card-body" method="post" action={dados.links.modelos_prontos} onSubmit={enviar}>
        <input type="hidden" name="client_id" value={dados.client_id ?? ''} />
        <p className="small text-muted mb-2">Cria a área e um modelo com turnos, rotina e tipos de ocorrência típicos. Depois é só ajustar aqui mesmo.</p>
        <div className="d-flex flex-wrap gap-3 mb-2">
          {dados.modelos_prontos.map((m) => (
            <label className="form-check" key={m.chave}><input className="form-check-input" type="checkbox" name="servico"
              value={m.chave} /> {m.area}
              <span className="small text-muted d-block">{m.turnos.join(' · ')}</span></label>
          ))}
        </div>
        <button className="btn btn-outline-primary btn-sm" type="submit" disabled={ocupado}>Criar modelos</button>
      </form>
    </details>
  );
}

function Editor({ dados }: { dados: DadosDaConfiguracao }) {
  const seq = useRef(0);
  const nomeRef = useRef<HTMLInputElement>(null);
  const cliente = Number(dados.client_id || 0);
  const ativas = dados.areas.filter((a) => a.ativo);
  const usos = (m: Modelo) => Number(dados.usos[String(m.id)] || 0);

  // Abre o modelo pedido pela URL (volta do salvar), ou o primeiro da lista.
  const inicial = (dados.editar && dados.configs.find((m) => m.id === dados.editar)) || dados.configs[0] || null;
  const [editando, setEditando] = useState<Modelo | null>(inicial);
  const formulario = (m: Modelo | null, areaAtual: string) => ({
    nome: m ? m.nome || '' : '',
    descricao: m ? m.descricao || '' : '',
    ativo: m ? String(m.ativo !== false) : 'true',
    // Área inativa não está na lista: o seletor fica em "Sem área", como o antigo.
    area: m ? (ativas.some((a) => String(a.id) === String(m.area_id || '')) ? String(m.area_id) : '') : areaAtual,
    turnos: m ? (m.turnos || []).map((x) => ({ n: ++seq.current, nome: nomeDe(x) })) : [],
    perguntas: m ? (m.perguntas || []).map((p) => linhaDaPergunta(++seq.current, p)) : [],
    ocorrencias: m ? (m.tipos_ocorrencia || []).map((x) => ({ n: ++seq.current, nome: nomeDe(x) })) : [],
  });
  const [f, setF] = useState(() => formulario(inicial, ''));
  const mudar = <K extends keyof typeof f>(campo: K, v: (typeof f)[K]) => setF((x) => ({ ...x, [campo]: v }));

  const abrirModelo = (m: Modelo) => { setEditando(m); setF(formulario(m, f.area)); };
  const novoModelo = () => {
    setEditando(null);
    setF(formulario(null, f.area));
    setTimeout(() => nomeRef.current?.focus(), 0);
  };

  const mudarLinha = (campo: 'turnos' | 'ocorrencias', n: number, nome: string) =>
    mudar(campo, f[campo].map((l: Linha) => (l.n === n ? { ...l, nome } : l)));
  const tirarLinha = (campo: 'turnos' | 'ocorrencias', n: number) => mudar(campo, f[campo].filter((l: Linha) => l.n !== n));
  const mudarPergunta = (n: number, troca: Partial<LinhaDePergunta>) =>
    mudar('perguntas', f.perguntas.map((l) => (l.n === n ? { ...l, ...troca } : l)));

  const salvar = () => {
    const nome = f.nome.trim();
    if (!nome) { window.alert('Informe o nome do modelo.'); return; }
    const turnos = f.turnos.map((v) => ({ nome: v.nome.trim() })).filter((x) => x.nome);
    const { perguntas, erro } = perguntasParaSalvar(f.perguntas);
    if (erro) { window.alert(erro); return; }
    const ocorrencias = f.ocorrencias.map((v) => ({ nome: v.nome.trim() })).filter((x) => x.nome);
    const corpo = {
      client_id: cliente, nome,
      area_id: Number(f.area || 0) || null,
      descricao: f.descricao,
      ativo: f.ativo === 'true',
      turnos, perguntas, tipos_ocorrencia: ocorrencias,
    };
    const url = editando ? '/passagem-de-turno/api/configuracoes/' + editando.id : '/passagem-de-turno/api/configuracoes';
    enviarBruto(url, {
      method: editando ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo),
    }).then((r) => r.json().then((x) => ({ ok: r.ok, x }), () => ({ ok: false, x: {} as { error?: string; id?: number; nome?: string } })))
      .then((res) => {
        if (!res.ok) {
          window.alert(res.x.error || 'O modelo não foi salvo. Recarregue a página e tente de novo.');
          return;
        }
        // A tela recarrega no topo: o recado fica para a próxima página.
        try {
          sessionStorage.setItem('fc-aviso', JSON.stringify({ texto: avisoDoModeloSalvo(res.x.nome || nome), tipo: 'success' }));
        } catch { /* sem sessionStorage (aba privada): salva sem o recado */ }
        window.location.assign(dados.links.aqui + '?client_id=' + cliente + '&editar=' + res.x.id);
      }, () => window.alert('Sem conexão: o modelo não foi salvo. Tente de novo quando o sinal voltar.'));
  };

  return (
    <div className="row g-3">
      <div className="col-lg-4">
        <div className="card shadow-sm border-0 h-100">
          <div className="card-header bg-white fw-bold d-flex justify-content-between align-items-center">
            <span>Modelos deste contrato</span>
            <button className="btn btn-sm btn-outline-primary" type="button" data-acao="novoModelo" onClick={novoModelo}>
              <i className="bi bi-plus"></i> Novo</button>
          </div>
          <div className="card-body cf-lista" id="cfg-lista">
            {dados.configs.length ? dados.configs.map((c) => {
              const nPerg = (c.perguntas || []).length;
              const nTurnos = (c.turnos || []).length;
              const nUsos = usos(c);
              return (
                <button type="button" className={'cf-item' + (editando && editando.id === c.id ? ' ativo-sel' : '')}
                  data-id={c.id} data-usos={nUsos} data-acao="abrirModelo" key={c.id} onClick={() => abrirModelo(c)}>
                  <div className="d-flex justify-content-between align-items-start gap-2">
                    <span className="cf-nome">{c.nome}</span>
                    <span className={'cf-tag ' + (c.ativo ? 'on' : 'off')}>{c.ativo ? 'Ativo' : 'Inativo'}</span>
                  </div>
                  <div className="cf-meta">
                    {nPerg} {nPerg === 1 ? 'pergunta' : 'perguntas'} ·{' '}
                    {nTurnos} {nTurnos === 1 ? 'turno' : 'turnos'} ·{' '}
                    {nUsos} {nUsos === 1 ? 'turno lançado' : 'turnos lançados'}
                  </div>
                </button>
              );
            }) : (
              <div className="text-muted small py-3 text-center">
                Nenhum modelo cadastrado. Clique em <strong>Novo</strong>.
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="col-lg-8">
        <div className="card shadow-sm border-0 mb-3">
          <div className="card-body">
            <div className="row g-3">
              <div className="col-md-7">
                <label className="form-label" htmlFor="cfg-name">Nome do modelo</label>
                <input id="cfg-name" className="form-control" placeholder="Ex.: Limpeza — rotina do turno" ref={nomeRef}
                  value={f.nome} onChange={(ev) => mudar('nome', ev.target.value)} />
              </div>
              <div className="col-md-5">
                <label className="form-label" htmlFor="cfg-ativo">Situação</label>
                <select id="cfg-ativo" className="form-select" value={f.ativo} onChange={(ev) => mudar('ativo', ev.target.value)}>
                  <option value="true">Ativo — aparece para o encarregado</option>
                  <option value="false">Inativo — some da tela de passagem</option>
                </select>
              </div>
              {/* A área se SELECIONA entre as cadastradas acima. */}
              <div className="col-md-7">
                <label className="form-label" htmlFor="cfg-area">Área</label>
                <select id="cfg-area" className="form-select" value={f.area} onChange={(ev) => mudar('area', ev.target.value)}>
                  <option value="">Sem área — contrato não dividido</option>
                  {ativas.map((a) => <option value={a.id} key={a.id}>{a.nome}</option>)}
                </select>
              </div>
              <div className="col-12">
                <label className="form-label" htmlFor="cfg-description">Descrição</label>
                <input id="cfg-description" className="form-control" placeholder="Como este modelo será usado"
                  value={f.descricao} onChange={(ev) => mudar('descricao', ev.target.value)} />
              </div>
            </div>
            <div className="cf-aviso mt-2" id="cfg-aviso-uso">{editando ? avisoDeUso(usos(editando)) : ''}</div>
          </div>
        </div>

        <div className="card shadow-sm border-0">
          <div className="card-header bg-white fw-bold">Turnos</div>
          <div className="card-body">
            <div id="cfg-shifts">
              {f.turnos.map((l) => (
                <div className="row g-2 mb-2 config-row" key={l.n}>
                  <div className="col-10"><input className="form-control cfg-shift" placeholder="Ex.: Diurno" value={l.nome}
                    aria-label="Turno" onChange={(ev) => mudarLinha('turnos', l.n, ev.target.value)} /></div>
                  <Remover onClick={() => tirarLinha('turnos', l.n)} />
                </div>
              ))}
            </div>
            <button className="btn btn-sm btn-outline-primary" type="button" data-acao="addCfgShift"
              onClick={() => mudar('turnos', [...f.turnos, { n: ++seq.current, nome: '' }])}>
              Adicionar turno</button>
          </div>
        </div>

        {/* UMA lista, na ordem em que a pergunta aparece na tela do encarregado. */}
        <div className="card shadow-sm border-0 mt-3">
          <div className="card-header bg-white fw-bold d-flex justify-content-between align-items-center">
            <span>Perguntas do turno</span>
            <span className="small text-muted fw-normal">na ordem em que aparecem para o encarregado</span>
          </div>
          <div className="card-body">
            <div id="cfg-perguntas">
              {f.perguntas.map((l) => (
                <div className="row g-2 mb-2 config-row" key={l.n} data-codigo={l.codigo}>
                  <div className="col-5"><input className="form-control cfg-p-nome" aria-label="Pergunta"
                    placeholder="Ex.: Sanitários limpos e abastecidos?" value={l.nome}
                    onChange={(ev) => mudarPergunta(l.n, { nome: ev.target.value })} /></div>
                  <div className="col-3"><select className="form-select cfg-p-tipo" aria-label="Tipo da resposta" value={l.tipo}
                    onChange={(ev) => mudarPergunta(l.n, { tipo: ev.target.value })}>
                    {opcoesDoTipo(l.tipo).map(([v, r]) => <option value={v} key={v}>{r}</option>)}
                  </select></div>
                  <div className="col-2"><select className="form-select cfg-p-obrig" aria-label="Obrigatória ou opcional"
                    value={String(l.obrigatorio)} onChange={(ev) => mudarPergunta(l.n, { obrigatorio: ev.target.value === 'true' })}>
                    <option value="true">Obrigatória</option>
                    <option value="false">Opcional</option>
                  </select></div>
                  <div className="col-2 d-flex gap-1">
                    <button type="button" className="btn btn-outline-secondary flex-fill" title="Subir" aria-label="Subir"
                      data-acao="moverPergunta" onClick={() => mudar('perguntas', mover(f.perguntas, l.n, -1))}>↑</button>
                    <button type="button" className="btn btn-outline-secondary flex-fill" title="Descer" aria-label="Descer"
                      data-acao="moverPergunta" onClick={() => mudar('perguntas', mover(f.perguntas, l.n, 1))}>↓</button>
                    <button type="button" className="btn btn-outline-danger flex-fill" data-remover=".config-row"
                      aria-label="Remover este item" onClick={() => mudar('perguntas', f.perguntas.filter((x) => x.n !== l.n))}>×</button>
                  </div>
                  <div className="col-12 cfg-p-opcoes-caixa" hidden={l.tipo !== 'escolha'}>
                    <textarea className="form-control cfg-p-opcoes" rows={3} aria-label="Opções da escolha" value={l.opcoes}
                      placeholder={'Uma opção por linha. Ex.:\n🟢 Normal\n🟡 Atenção\n🔴 Crítico'}
                      onChange={(ev) => mudarPergunta(l.n, { opcoes: ev.target.value })}></textarea>
                    <div className="form-text">As opções que o encarregado vai tocar, uma por linha.</div>
                  </div>
                </div>
              ))}
            </div>
            <button className="btn btn-sm btn-outline-primary" type="button" data-acao="addCfgPergunta"
              onClick={() => mudar('perguntas', [...f.perguntas, linhaDaPergunta(++seq.current)])}>
              Adicionar pergunta</button>
            <div className="cf-aviso mt-2">
              Só a pergunta <strong>Sim/Não</strong> marcada como obrigatória entra na
              aderência às rotinas. Número, texto e escolha são registro, não cobrança.
              Na <strong>Escolha</strong>, escreva as opções que o encarregado vai
              tocar, uma por linha (ex.: 🟢 Normal, 🟡 Atenção, 🔴 Crítico).
            </div>
          </div>
        </div>

        <div className="card shadow-sm border-0 mt-3">
          <div className="card-header bg-white fw-bold">Tipos de ocorrência</div>
          <div className="card-body">
            <div id="cfg-occurrences">
              {f.ocorrencias.map((l) => (
                <div className="row g-2 mb-2 config-row" key={l.n}>
                  <div className="col-10"><input className="form-control cfg-occ" placeholder="Ex.: Vazamento" value={l.nome}
                    aria-label="Tipo de ocorrência" onChange={(ev) => mudarLinha('ocorrencias', l.n, ev.target.value)} /></div>
                  <Remover onClick={() => tirarLinha('ocorrencias', l.n)} />
                </div>
              ))}
            </div>
            <button className="btn btn-sm btn-outline-primary" type="button" data-acao="addCfgOccurrence"
              onClick={() => mudar('ocorrencias', [...f.ocorrencias, { n: ++seq.current, nome: '' }])}>
              Adicionar tipo</button>
          </div>
        </div>

        <div className="mt-3 d-flex justify-content-between align-items-center">
          <span className="cf-aviso" id="cfg-editando">
            {editando ? 'Editando: ' + (editando.nome || '') : 'Novo modelo — ainda não salvo.'}</span>
          <button className="btn btn-primary px-4" type="button" data-acao="saveConfig" onClick={salvar}>Salvar modelo</button>
        </div>
      </div>
    </div>
  );
}

export function Configuracao({ dados }: { dados: DadosDaConfiguracao }) {
  const navegar = useNavigate();
  return (
    <>
      <nav aria-label="breadcrumb"><ol className="breadcrumb">
        <li className="breadcrumb-item"><a href={dados.links.painel}>Passagem de Turno</a></li>
        <li className="breadcrumb-item active">Modelo de passagem</li>
      </ol></nav>
      <Recados servidor={dados.recados} />
      <div className="container-fluid py-3 diario-page" id="diario-config-app" data-tela-pronta="configuracao">

        <div className="d-flex justify-content-between align-items-start mb-3 gap-2 flex-wrap">
          <div>
            <div className="text-uppercase small text-muted fw-semibold">ADMINISTRAÇÃO</div>
            <h2 className="mb-0">Modelo de passagem de turno</h2>
            <div className="text-muted">Cada contrato define o que o encarregado registra no fim do turno.</div>
          </div>
          <a className="btn btn-light" href={dados.links.painel}>Voltar</a>
        </div>

        {/* A troca de contrato é uma navegação (o editor nunca salva os dados
            de um contrato no outro). */}
        <form className="row g-2 align-items-end mb-3" method="get" onSubmit={(ev) => ev.preventDefault()}>
          <div className="col-lg-5 col-md-7">
            <label className="form-label small text-muted mb-1" htmlFor="cfg-contrato">Contrato</label>
            <select className="form-select" name="client_id" id="cfg-contrato" value={dados.client_id ?? ''}
              onChange={(ev) => navegar({ search: '?client_id=' + encodeURIComponent(ev.target.value) })}>
              {dados.clients.map((c) => <option value={c.id} key={c.id}>{c.nome}</option>)}
            </select>
          </div>
        </form>

        {!dados.client_id ? (
          <div className="card shadow-sm border-0"><div className="p-4 text-center text-muted">
            Nenhum contrato disponível.</div></div>
        ) : (
          <>
            <Prontos dados={dados} />
            <Areas areas={dados.areas} cliente={dados.client_id} />
            <Editor dados={dados} />
          </>
        )}
      </div>
    </>
  );
}
