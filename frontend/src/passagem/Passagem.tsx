// A nova passagem de turno — a tela que o encarregado preenche no fim do
// expediente (Fase 2a da migração para React; a tela antiga é
// templates/diario_operacional/turno.html + static/js/diario_operacional.js,
// com o mesmo comportamento, os mesmos textos e as mesmas classes).
//
// As duas abas: o que eu RECEBI (o turno anterior e as pendências em aberto)
// e o que eu ENTREGO (as perguntas do modelo, a observação, as ocorrências e
// as pendências para o próximo turno). A área e o turno decidem o modelo; o
// modelo decide as perguntas.
//
// As ações vão para as APIs de sempre (/passagem-de-turno/api/...). Sem
// sinal, o turno e as fotos vão para a fila do aparelho (window.TrinoFila, a
// mesma da tela antiga) e sobem sozinhos quando a conexão voltar.
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import { enviarBruto } from '../api';
import {
  avisoDoEnvio, chaveDaArea, chaveDe, coletar, confirmacaoDasTarefas, type Escolha,
  escolherTurno, idadeDaPendencia, jaEncerrado, modeloEmUso, perguntasDe, type Resposta, rotuloDoTurno,
  tarefasSemResposta, textoDosEscolhidos, turnosDaArea,
} from './regras';
import type { Anterior, DadosDaPassagem, Modelo, Pendencia, Pergunta, TarefaDaGestao } from './tipos';
import './passagem.css';

const SEM_MODELO_NA_AREA = 'Esta área ainda não tem um modelo de passagem cadastrado. ' +
  'Peça ao gestor do contrato ou ao administrador para cadastrar o modelo.';

// ── Os anexos: a foto (câmera direto) e o arquivo (galeria ou PDF) ──────
//
// O arquivo mora no próprio <input> (é o navegador que o guarda); aqui fica,
// por campo, a redução da foto em andamento e o resumo dela.
type Marca = { preparo?: Promise<unknown>; resumo: string };
const marcas = new WeakMap<HTMLInputElement, Marca>();

const SELETOR_DE_ARQUIVOS = '.diario-activity-file, #diario-observacao-file';

function marcaDe(e: HTMLInputElement): Marca {
  let m = marcas.get(e);
  if (!m) { m = { resumo: '' }; marcas.set(e, m); }
  return m;
}

function CaixaDeAnexos({ chave, daObservacao }: { chave: string; daObservacao?: boolean }) {
  const caixa = useRef<HTMLDivElement>(null);
  const [texto, setTexto] = useState('');
  const atualizar = () => {
    const entradas = Array.from(caixa.current?.querySelectorAll<HTMLInputElement>(SELETOR_DE_ARQUIVOS) || []);
    const arquivos = entradas.reduce((n, e) => n + (e.files ? e.files.length : 0), 0);
    setTexto(textoDosEscolhidos(arquivos, entradas.map((e) => marcaDe(e).resumo).filter(Boolean)));
  };
  // A foto é reduzida na escolha (static/js/foto-leve.js): sobe em segundos
  // com 4G fraco e ocupa pouco na fila sem internet.
  const escolheu = (ev: React.ChangeEvent<HTMLInputElement>) => {
    const alvo = ev.currentTarget;
    const m = marcaDe(alvo);
    m.resumo = '';
    atualizar();
    if (!window.TrinoFoto || !alvo.files || !alvo.files.length) return;
    setTexto('Preparando a foto…');
    m.preparo = window.TrinoFoto.prepararEntrada(alvo).then((t) => { m.resumo = t; atualizar(); },
      () => atualizar());
  };
  return (
    <div className="dt-anexos mt-2" ref={caixa}>
      <label className="dt-anexo">
        <i className="bi bi-camera"></i> Tirar foto
        <input type="file" className="diario-activity-file" data-key={chave}
          accept="image/*" capture="environment" hidden onChange={escolheu} />
      </label>{' '}
      <label className="dt-anexo">
        <i className="bi bi-paperclip"></i> Anexar arquivo
        {daObservacao
          ? <input type="file" id="diario-observacao-file" data-key=""
              accept="image/*,application/pdf" multiple hidden onChange={escolheu} />
          : <input type="file" className="diario-activity-file" data-key={chave}
              accept="image/*,application/pdf" multiple hidden onChange={escolheu} />}
      </label>
      <div className="dt-escolhidos small text-muted mt-1">{texto}</div>
    </div>
  );
}

// ── As perguntas do modelo ────────────────────────────────────────────────

function CartaoPergunta({ p, i, valor, mudar }: {
  p: Pergunta; i: number; valor: Record<string, Resposta>; mudar: (k: string, v: Resposta) => void;
}) {
  const chave = chaveDe(p);
  const tipo = p.tipo || 'sim_nao';
  let corpo;
  if (tipo === 'sim_nao') {
    const k = 'atividade:' + chave;
    const r = (valor[k] && typeof valor[k] === 'object' ? valor[k] : { concluido: false, observacao: '' }) as
      { concluido: boolean; observacao: string };
    corpo = (
      <>
        <div className="form-check form-switch dt-switch">
          <input className="form-check-input diario-activity" type="checkbox" id={'p-' + i} data-key={chave}
            checked={r.concluido} onChange={(e) => mudar(k, { ...r, concluido: e.target.checked })} />
          <label className="form-check-label" htmlFor={'p-' + i}>Concluído</label>
        </div>
        <textarea className="form-control mt-2 diario-activity-note" data-key={chave} rows={2}
          placeholder="Observação (o que houve, se não foi feito)" value={r.observacao}
          onChange={(e) => mudar(k, { ...r, observacao: e.target.value })}></textarea>
      </>
    );
  } else {
    const v = typeof valor[chave] === 'string' ? (valor[chave] as string) : '';
    const set = (x: string) => mudar(chave, x);
    if (tipo === 'numero') {
      corpo = <input type="number" inputMode="numeric" className="form-control diario-field" data-key={chave}
        value={v} onChange={(e) => set(e.target.value)} />;
    } else if (tipo === 'texto_longo') {
      corpo = <textarea className="form-control diario-field" rows={3} data-key={chave} value={v}
        onChange={(e) => set(e.target.value)}></textarea>;
    } else if (tipo === 'escolha') {
      // Botões, não lista suspensa: um toque escolhe, e a resposta fica visível.
      corpo = (
        <div className="dt-opcoes" data-key={chave}>
          {(p.opcoes || []).map((o, n) => (
            <button type="button" className={'dt-opcao' + (v === o ? ' sel' : '')} data-valor={o} key={n}
              onClick={() => set(o)}>{o}</button>
          ))}
          <input type="hidden" className="diario-field" data-key={chave} value={v} />
        </div>
      );
    } else {
      corpo = <input type="text" className="form-control diario-field" data-key={chave} value={v}
        onChange={(e) => set(e.target.value)} />;
    }
  }
  return (
    <div className="dt-p dt-atividade">
      <span className="dt-p-nome">{p.nome}{p.obrigatorio && <> <span className="obrig">*</span></>}</span>
      {corpo}
      <CaixaDeAnexos chave={chave} />
    </div>
  );
}

// ── O que o turno anterior deixou (um bloco por área) ────────────────────

function BlocoAnterior({ a, visivel }: { a: Anterior; visivel: boolean }) {
  if (!a.turno) {
    return (
      <div className="dt-anterior mb-3" data-area={a.chave} hidden={!visivel}>
        <div className="d-flex align-items-center gap-2 flex-wrap px-3 py-2" style={{ minHeight: '48px' }}>
          <span className="dt-ant-tit">O turno anterior deixou</span>
          <span className="dt-ant-meta">Nenhuma passagem encerrada nesta área ainda.</span>
        </div>
      </div>
    );
  }
  return (
    <details className="dt-anterior mb-3" data-area={a.chave} hidden={!visivel} open={a.tem_o_que_ler}>
      <summary>
        <span className="dt-ant-tit">O turno anterior deixou</span>
        <span className="dt-ant-meta">
          {a.area ? a.area + ' · ' : ''}{a.turno.turno} · {a.turno.data}{a.autor ? ' · ' + a.autor : ''}
        </span>
      </summary>
      <div className="dt-ant-corpo">
        {a.turno.observacao && (
          <div className="dt-ant-bloco">
            <div className="dt-ant-rot">Observações</div>
            <div className="dt-ant-txt">{a.turno.observacao}</div>
          </div>
        )}
        {a.ocorrencias.length > 0 && (
          <div className="dt-ant-bloco">
            <div className="dt-ant-rot">Ocorrências ({a.ocorrencias.length})</div>
            {a.ocorrencias.map((o, n) => (
              <div className="dt-ant-oco" key={n}>
                <strong>{o.tipo}</strong>{o.referencia ? ' · ' + o.referencia : ''}
                {o.gravidade === 'critica' && (
                  <> <span className="badge text-bg-warning">
                    <i className="bi bi-exclamation-triangle"></i> ponto de atenção</span></>
                )}
                <div className="dt-ant-txt">{o.descricao}</div>
              </div>
            ))}
          </div>
        )}
        {a.anexos.length > 0 && (
          <div className="dt-ant-bloco">
            <div className="dt-ant-rot">Provas anexadas ({a.anexos.length})</div>
            <div className="dt-ant-fotos">
              {a.anexos.map((x) => (
                <a href={x.url} target="_blank" rel="noopener" className="dt-ant-foto" title={x.nome} key={x.id}>
                  {x.mime && x.mime.startsWith('image/')
                    ? <img src={x.url} alt={x.nome} loading="lazy" />
                    : <span className="dt-ant-pdf"><i className="bi bi-file-earmark-pdf"></i></span>}
                </a>
              ))}
            </div>
          </div>
        )}
        {!a.tem_o_que_ler && <div className="dt-vazio">Sem ocorrências, observação ou anexo nesse turno.</div>}
      </div>
    </details>
  );
}

// ── Uma pendência em aberto: Resolver / Continua ─────────────────────────

function CartaoPendencia({ p, resolver, anotar }: {
  p: Pendencia; resolver: () => void; anotar: () => void;
}) {
  return (
    <div className={'diario-pending dt-pend' + (p.vencida ? ' vencida' : '')} id={'pendencia-' + p.id}
      data-id={p.id}>
      <div className="dt-pend-topo">
        <strong>{p.titulo}</strong>
        {p.referencia && <span className="dt-pend-ref">{p.referencia}</span>}
      </div>
      {p.descricao && <div className="dt-pend-desc">{p.descricao}</div>}
      <div className="dt-pend-meta">
        {p.origem_turno ? <span>{p.origem_turno} · {p.origem_data}</span> : <span>Aberta pela gestão</span>}
        <span className={'dt-pend-idade' + (p.vencida ? ' ruim' : '')}>{idadeDaPendencia(p)}</span>
        {p.passagens > 0 && <span>passou por {p.passagens} turno{p.passagens > 1 ? 's' : ''}</span>}
        {p.alta && <span className="dt-pend-alta">prioridade alta</span>}
      </div>
      {p.ultima_tentativa && (
        <div className="dt-pend-tent">
          <span className="dt-pend-tent-rot">Já se tentou</span> {p.ultima_tentativa.texto}{' '}
          <span className="dt-pend-tent-quem">— {p.ultima_tentativa.quem
            ? p.ultima_tentativa.quem + ', ' : ''}{p.ultima_tentativa.quando}</span>
        </div>
      )}
      <div className="dt-pend-acoes">
        <button type="button" className="btn btn-sm btn-outline-success" onClick={resolver}>Resolver</button>
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={anotar}>Continua</button>
      </div>
    </div>
  );
}

// ── O que a gestão pediu para ESTE turno ─────────────────────────────────

const FORMA_AJUDA: Record<string, string> = {
  sim_nao: 'responda sim ou não', numero: 'responda com o número', texto: 'descreva',
};

function CartaoTarefa({ t, respondida }: { t: TarefaDaGestao; respondida: () => void }) {
  const [resp, setResp] = useState('');
  const [ocupado, setOcupado] = useState<string | null>(null);
  if (t.status !== 'pendente') {
    const feita = t.status === 'feita';
    return (
      <div className="card shadow-sm border-0 mb-2"><div className="card-body py-2">
        <span className={'badge ' + (feita ? 'text-bg-success' : 'text-bg-warning')}>
          {feita ? 'feita' : 'virou pendência'}</span>{' '}
        <strong>{t.titulo}</strong>
        <div className="small text-muted mt-1">{t.resposta}</div>
      </div></div>
    );
  }
  const responder = (virou: boolean) => {
    let texto = resp.trim();
    if (virou) {
      texto = (window.prompt('Por que não foi possível fazer?') || '').trim();
      if (!texto) return;
    } else if (!texto) {
      window.alert('Responda antes de marcar como feita.');
      return;
    }
    const botao = virou ? 'pend' : 'fiz';
    setOcupado(botao);
    enviarBruto('/passagem-de-turno/api/tarefas-turno/' + t.id + '/responder', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resposta: texto, virou_pendencia: virou }),
    }).then((r) => r.json().then((x) => ({ ok: r.ok, x })))
      .then((res) => {
        if (!res.ok) { window.alert(res.x.error || 'Não foi possível responder.'); setOcupado(null); return; }
        respondida();
      }).catch(() => { window.alert('Falha de rede.'); setOcupado(null); });
  };
  return (
    <div className="card shadow-sm border-0 mb-2" data-tarefa={t.id}>
      <div className="card-body py-2">
        <div className="fw-semibold">{t.titulo}</div>
        {t.descricao && <div className="small text-muted">{t.descricao}</div>}
        <div className="mt-2">
          {t.forma_resposta === 'sim_nao'
            ? (
              <select className="form-select form-select-sm dt-tg-resp" value={resp}
                onChange={(e) => setResp(e.target.value)}>
                <option value="">—</option><option value="Sim">Sim</option><option value="Não">Não</option>
              </select>
            )
            : <input className="form-control form-control-sm dt-tg-resp"
                inputMode={t.forma_resposta === 'numero' ? 'decimal' : undefined}
                placeholder={FORMA_AJUDA[t.forma_resposta] || ''} value={resp}
                onChange={(e) => setResp(e.target.value)} />}
        </div>
        <div className="d-flex gap-2 mt-2">
          <button type="button" className="btn btn-sm btn-outline-success dt-tg-fiz dt-tg-botao"
            disabled={ocupado === 'fiz'} onClick={() => responder(false)}>Fiz</button>
          {/* A segunda saída: sem ela, quem não conseguiu fazer só teria a
              opção de mentir ou deixar em branco. */}
          <button type="button" className="btn btn-sm btn-outline-warning dt-tg-pend dt-tg-botao"
            disabled={ocupado === 'pend'} onClick={() => responder(true)}>Não deu — vira pendência</button>
        </div>
      </div>
    </div>
  );
}

// ── As linhas de pendência e de ocorrência do formulário ─────────────────

type LinhaPend = { n: number; titulo: string; referencia: string; descricao: string; prioridade: string };
type LinhaOco = { n: number; tipos: string[]; tipo: string; referencia: string; descricao: string; gravidade: string };

/** O "×" no computador; no celular, o link "Remover" (app.css). */
function BotaoRemover({ classeDaLinha, remover }: { classeDaLinha: string; remover: () => void }) {
  return (
    <div className="col-md-1 dt-linha-remover">
      <button type="button" className="btn btn-outline-danger w-100" title="Remover esta linha"
        aria-label="Remover esta linha" data-remover={'.' + classeDaLinha} onClick={remover}>
        <span className="dt-x" aria-hidden="true">×</span>
        <span className="dt-remover-txt">Remover</span>
      </button>
    </div>
  );
}

// ── A fila do aparelho ───────────────────────────────────────────────────

type Grupo = { envio: string; atividade: string; arquivos: File[]; feito: boolean };
type Envio = { ok: boolean; conexao?: boolean; grupo: Grupo; x: { error?: string } };
type RespostaDoEnvio = { conexao?: boolean; ok?: boolean; x?: Record<string, any> };
type Guardado = { turnoId: number | null; filaId: string | null;
  enviado?: { estado?: string; mensagem?: string; turno_id?: number | null } };

const filaDisponivel = () => !!(window.TrinoFila && window.TrinoFila.guardar);

function novoEnvio() {
  return filaDisponivel() ? window.TrinoFila!.novoId()
    : String(Date.now()) + '-' + Math.random().toString(16).slice(2, 10);
}

function falhaDeConexao(r: Response) {
  return filaDisponivel() && window.TrinoFila!.ehFalhaDeConexao(r);
}

export function Passagem({ dados }: { dados: DadosDaPassagem }) {
  const raiz = useRef<HTMLDivElement>(null);
  const { configs, areas, encerrados } = dados;
  const clientId = dados.client_id ?? (dados.clients[0] ? dados.clients[0].id : null);

  // ── Área, data e turno: o modelo é consequência dos três ──
  const [area, setArea] = useState(areas.length ? String(areas[0].id) : '');
  const [dia, setDia] = useState(dados.hoje);
  const turnoAMao = useRef(false);
  const escolha = (a: string, d: string): Escolha => ({ configs, area: a, dia: d, encerrados });
  const [turno, setTurno] = useState(() => escolherTurno(escolha(area, dia), '', true, false));
  const e = escolha(area, dia);
  const disponiveis = turnosDaArea(configs, area);
  const cfg = modeloEmUso(e, turno);
  const chaveAnterior = chaveDaArea(cfg);
  const desenho = disponiveis.length ? 'cfg-' + (cfg ? cfg.id : '') : 'sem-modelo';
  const perguntas = useMemo(() => (cfg ? perguntasDe(cfg) : []), [cfg]);

  const trocarArea = (v: string) => {
    setArea(v);
    setTurno(escolherTurno(escolha(v, dia), turno, true, turnoAMao.current));
  };
  const trocarDia = (v: string) => {
    setDia(v);
    setTurno(escolherTurno(escolha(area, v), turno, true, turnoAMao.current));
  };
  const trocarTurno = (v: string) => {
    turnoAMao.current = true;
    setTurno(escolherTurno(e, v, false, true));
  };

  // As respostas valem para o modelo desenhado: trocar de modelo redesenha
  // as perguntas (e apaga o que foi respondido), como na tela antiga.
  const [respostas, setRespostas] = useState<{ de: string; v: Record<string, Resposta> }>({ de: desenho, v: {} });
  const valores = respostas.de === desenho ? respostas.v : {};
  const mudar = (k: string, v: Resposta) => setRespostas({ de: desenho, v: { ...valores, [k]: v } });

  const [observacao, setObservacao] = useState('');
  const seq = useRef(0);
  const [pendRows, setPendRows] = useState<LinhaPend[]>([]);
  const [ocoRows, setOcoRows] = useState<LinhaOco[]>([]);

  // ── O que a gestão pediu: busca a cada troca de contrato, modelo, dia ou turno ──
  const [tarefas, setTarefas] = useState<TarefaDaGestao[] | null>(null);
  const [recarga, setRecarga] = useState(0);
  const cfgId = cfg ? cfg.id : null;
  useEffect(() => {
    if (cfgId === null || !clientId) return;
    if (!dia || !turno) { setTarefas(null); return; }
    let vale = true;
    fetch('/passagem-de-turno/api/tarefas-turno?client_id=' + clientId + '&configuracao_id=' + cfgId +
          '&data_turno=' + encodeURIComponent(dia) + '&turno=' + encodeURIComponent(turno),
    { credentials: 'same-origin' })
      .then((r) => r.json())
      .then((x) => { if (vale) setTarefas(((x && x.tarefas) || []).length ? x.tarefas : null); })
      .catch(() => { if (vale) setTarefas(null); });
    return () => { vale = false; };
  }, [clientId, cfgId, dia, turno, recarga]);

  // ── As pendências recebidas ──
  const tinhaPendencias = dados.pendencias.length > 0;
  const [pendencias, setPendencias] = useState<Pendencia[]>(dados.pendencias);
  const [painel, setPainel] = useState<'pendencias' | 'passagem'>(tinhaPendencias ? 'pendencias' : 'passagem');
  const mostrarPainel = (nome: 'pendencias' | 'passagem') => {
    setPainel(nome);
    // Voltar ao topo: quem troca de aba no meio da lista cai no meio do formulário.
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  const vencidas = pendencias.filter((p) => p.vencida).length;

  // O aviso "pendência parada" leva a /...#pendencia-<id>: a tela antiga
  // chega desenhada e o navegador rola sozinho; aqui, depois de desenhar.
  useEffect(() => {
    const m = /^#pendencia-\d+$/.test(window.location.hash) ? window.location.hash.slice(1) : null;
    if (m) document.getElementById(m)?.scrollIntoView();
  }, []);

  const enviarNaPendencia = (id: number, caminho: string, corpo: Record<string, unknown>,
    erroPadrao: string, aoDarCerto: () => void) => {
    corpo.data_turno = dia;
    corpo.turno = turno;
    corpo.configuracao_id = cfg ? cfg.id : null;
    return enviarBruto('/passagem-de-turno/api/pendencias/' + id + '/' + caminho, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo),
    }).then((r) => r.json().then((x) => ({ ok: r.ok, x })))
      .then((res) => {
        if (!res.ok) { window.alert(res.x.error || erroPadrao); return; }
        aoDarCerto();
      }).catch(() => { window.alert('Falha de rede.'); });
  };

  const resolverPendencia = (id: number) => {
    let texto = window.prompt('O que foi feito para resolver?');
    if (texto === null) return;
    texto = texto.trim();
    if (!texto) { window.alert('Diga em uma linha o que foi feito.'); return; }
    enviarNaPendencia(id, 'resolver', { resolucao: texto }, 'Não foi possível resolver.', () => {
      const resta = pendencias.filter((p) => p.id !== id);
      setPendencias(resta);
      // Resolveu a última: o que resta do turno é entregar.
      if (!resta.length) mostrarPainel('passagem');
    });
  };

  const anotarPendencia = (id: number) => {
    let texto = window.prompt('O que você tentou? (fica para o próximo turno)');
    if (texto === null) return;
    texto = texto.trim();
    if (!texto) return;
    enviarNaPendencia(id, 'nota', { texto }, 'Não foi possível anotar.', () => {
      const quem = (dados.usuario.nome || '').trim();
      setPendencias((lista) => lista.map((p) => (p.id === id
        ? { ...p, ultima_tentativa: { texto: texto as string, quem, quando: 'agora' } } : p)));
    });
  };

  // ── Salvar ──
  const [ocupado, setOcupado] = useState(false);
  const [guardado, setGuardado] = useState<Guardado | null>(null);
  const guardadoAqui = useRef<string | null>(null);

  // A fila avisa quando um item sobe: se é o que ESTA tela guardou, a caixa
  // troca o "guardado" por "enviado".
  useEffect(() => {
    const ouvir = (ev: Event) => {
      const d = ((ev as CustomEvent).detail || {}) as { id?: string; estado?: string; mensagem?: string;
        turno_id?: number | null };
      if (!guardadoAqui.current || d.id !== guardadoAqui.current) return;
      setGuardado((g) => (g ? { ...g, enviado: d } : g));
      guardadoAqui.current = null;
    };
    window.addEventListener('trino-fila:enviado', ouvir);
    return () => window.removeEventListener('trino-fila:enviado', ouvir);
  }, []);

  const entradasDeArquivo = () =>
    Array.from(raiz.current?.querySelectorAll<HTMLInputElement>(SELETOR_DE_ARQUIVOS) || []);

  // Os arquivos sobem DEPOIS que o turno existe — é o id dele que ancora o
  // anexo. Cada grupo leva uma marca de envio (não duplica no reenvio).
  const gruposDeAnexos = (): Grupo[] => entradasDeArquivo()
    .filter((i) => i.files && i.files.length)
    .map((i) => ({ envio: novoEnvio(), atividade: i.dataset.key || '', arquivos: Array.from(i.files!), feito: false }));

  const fotosProntas = () => Promise.all(entradasDeArquivo().map((i) => marcaDe(i).preparo || null))
    .catch(() => null);

  const enviarAnexos = (turnoId: number, grupos: Grupo[]): Promise<Envio[]> => {
    if (!grupos.length) return Promise.resolve([]);
    return Promise.all(grupos.map((g) => {
      const corpo = new FormData();
      corpo.append('atividade', g.atividade);
      corpo.append('envio', g.envio);
      g.arquivos.forEach((f) => corpo.append('arquivo', f));
      return enviarBruto('/passagem-de-turno/api/turnos/' + turnoId + '/anexos', { method: 'POST', body: corpo })
        .then((r): Promise<Envio> | Envio => {
          if (falhaDeConexao(r)) return { ok: false, conexao: true, grupo: g, x: {} };
          return r.json().then((x) => ({ ok: r.ok, x, grupo: g }), () => ({ ok: false, x: {}, grupo: g }));
        }, () => ({ ok: false, conexao: true, grupo: g, x: {} }));
    }));
  };

  type Corpo = { client_id: number; configuracao_id: number; data_turno: string; turno: string;
    finalizar: boolean; [k: string]: unknown };

  const guardarNoAparelho = (corpo: Corpo, grupos: Grupo[], turnoId?: number) => {
    const rotulo = rotuloDoTurno(cfg ? cfg.nome : null, corpo);
    const item = { tipo: 'turno', rotulo: turnoId ? 'Fotos — ' + rotulo : rotulo, corpo: turnoId ? null : corpo,
      turno_id: turnoId || null, anexos: grupos } as { tipo: string; rotulo: string; corpo: unknown; id?: string;
      turno_id: number | null; anexos: Grupo[] };
    return window.TrinoFila!.guardar(item).then((g) => {
      guardadoAqui.current = ((g as { id?: string } | null)?.id) || item.id || null;
      setGuardado({ turnoId: turnoId || null, filaId: guardadoAqui.current });
    });
  };

  const salvarTurno = (finalizar: boolean) => {
    if (!cfg) {
      window.alert('Este contrato ainda não tem um modelo de passagem cadastrado. ' +
        'Peça ao gestor do contrato ou ao administrador para cadastrar o modelo.');
      return;
    }
    // A hora do TOQUE em "Encerrar", pelo relógio do aparelho.
    const tocadoEm = new Date().toISOString();
    if (finalizar) {
      // Só conta o que a lista MOSTRA: sem sinal ela não carregou, e nada bloqueia.
      const semResposta = tarefas ? tarefasSemResposta(tarefas) : 0;
      if (semResposta && !window.confirm(confirmacaoDasTarefas(semResposta))) return;
    }
    setOcupado(true);
    fotosProntas().then(() => continuarSalvar(cfg, finalizar, tocadoEm));
  };

  const continuarSalvar = (modelo: Modelo, finalizar: boolean, tocadoEm: string) => {
    const corpo: Corpo = {
      client_id: Number(clientId),
      configuracao_id: modelo.id,
      data_turno: dia,
      turno,
      dados: coletar(perguntas, valores),
      observacao,
      pendencias: pendRows.map((r) => ({ titulo: r.titulo, referencia: r.referencia, descricao: r.descricao,
        prioridade: r.prioridade })),
      ocorrencias: ocoRows.map((r) => ({ tipo: r.tipo, referencia: r.referencia, descricao: r.descricao,
        gravidade: r.gravidade })),
      finalizar: !!finalizar,
      // Uma marca por clique: o reenvio é reconhecido como o mesmo.
      envio_id: novoEnvio(),
    };
    // Vai DENTRO do corpo: se cair na fila, sobe com a hora do toque.
    if (finalizar) corpo.encerrado_no_aparelho = tocadoEm;
    const grupos = gruposDeAnexos();
    const liberar = () => setOcupado(false);

    const semConexao = () => {
      if (!filaDisponivel()) { liberar(); window.alert('Falha de rede ao salvar o turno.'); return; }
      guardarNoAparelho(corpo, grupos).catch(() => {
        liberar();
        window.alert('Sem conexão, e não foi possível guardar neste aparelho. ' +
          'Não feche a tela: tente de novo quando o sinal voltar.');
      });
    };

    if (navigator.onLine === false && filaDisponivel()) { semConexao(); return; }

    enviarBruto('/passagem-de-turno/api/turnos', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo),
    }).then((r): Promise<RespostaDoEnvio> | RespostaDoEnvio => {
      if (falhaDeConexao(r)) return { conexao: true };
      return r.json().then((x) => ({ ok: r.ok, x }), () => ({ conexao: true }));
    }, (): RespostaDoEnvio => ({ conexao: true }))
      .then((res: RespostaDoEnvio) => {
        if (res.conexao) { semConexao(); return null; }
        if (!res.ok) { liberar(); window.alert((res.x && res.x.error) || 'Não foi possível salvar.'); return null; }
        const x = res.x || {};
        return enviarAnexos(x.id, grupos).then((envios) => {
          const semRede = envios.filter((v) => v.conexao);
          const recusados = envios.filter((v) => !v.ok && !v.conexao);
          if (recusados.length) {
            // O turno JÁ está salvo: avisar e seguir é honesto.
            window.alert('O turno foi salvo, mas ' + (recusados.length === 1
              ? '1 anexo não subiu: ' : recusados.length + ' anexos não subiram: ') +
              (recusados[0].x.error || 'tente anexar de novo pela tela do turno.'));
          }
          if (semRede.length && filaDisponivel()) {
            return guardarNoAparelho(corpo, semRede.map((v) => v.grupo), x.id);
          }
          try {
            sessionStorage.setItem('fc-aviso', JSON.stringify({ texto: avisoDoEnvio(corpo, x), tipo: 'success' }));
          } catch { /* sem sessionStorage (aba privada): segue sem o recado */ }
          // O painel novo (Fase 2b), que mostra o recado como o antigo.
          window.location.assign('/novo/passagem-de-turno/?client_id=' + corpo.client_id);
          return null;
        });
      });
  };

  const novaPendencia = () => setPendRows((l) => [...l, { n: ++seq.current, titulo: '', referencia: '',
    descricao: '', prioridade: 'media' }]);
  const novaOcorrencia = () => {
    const tipos = ((cfg && cfg.tipos_ocorrencia) || []).map((x) => (typeof x === 'object' && x && x.nome) || String(x));
    setOcoRows((l) => [...l, { n: ++seq.current, tipos, tipo: tipos[0] || 'Outros', referencia: '', descricao: '',
      gravidade: 'normal' }]);
  };
  const mudarPend = (n: number, campo: keyof LinhaPend, v: string) =>
    setPendRows((l) => l.map((r) => (r.n === n ? { ...r, [campo]: v } : r)));
  const mudarOco = (n: number, campo: keyof LinhaOco, v: string) =>
    setOcoRows((l) => l.map((r) => (r.n === n ? { ...r, [campo]: v } : r)));

  const unicoCliente = dados.clients.length === 1;

  return (
    <>
      <nav aria-label="breadcrumb"><ol className="breadcrumb">
        <li className="breadcrumb-item"><a href={dados.links.painel}>Passagem de Turno</a></li>
        <li className="breadcrumb-item active">Nova passagem</li>
      </ol></nav>
      <div className="container-fluid py-3 diario-page dt-pagina" id="diario-turno-app" ref={raiz}
        data-tela-pronta="passagem">

        <div className="d-flex justify-content-between align-items-start mb-3 gap-2 flex-wrap">
          <div>
            <div className="text-uppercase small text-muted fw-semibold">PASSAGEM DE TURNO</div>
            <h2 className="mb-0">Nova passagem de turno</h2>
          </div>
          <a href={dados.links.painel} className="btn btn-light px-3">Voltar</a>
        </div>

        {/* Já preenchido: quem lança e onde */}
        <div className="dt-cab">
          <div className="dt-cab-grid">
            <div>
              <div className="dt-cab-rot">{dados.usuario.perfil}</div>
              <div className="dt-cab-val">{dados.usuario.nome}</div>
            </div>
            <div>
              <div className="dt-cab-rot">Operação</div>
              {unicoCliente
                ? <>
                    <div className="dt-cab-val">{dados.clients[0].nome}</div>
                    <input type="hidden" id="diario-client" value={dados.clients[0].id} />
                  </>
                : <select id="diario-client" className="form-select form-select-sm mt-1"
                    value={String(clientId ?? '')}
                    onChange={(ev) => window.location.assign(dados.links.trocar_contrato +
                      encodeURIComponent(ev.target.value))}>
                    {dados.clients.map((c) => <option value={c.id} key={c.id}>{c.nome}</option>)}
                  </select>}
            </div>
            <div>
              <div className="dt-cab-rot">Centro de custo</div>
              <div className="dt-cab-val">{dados.centro_custo || '—'}</div>
            </div>
          </div>
        </div>

        {/* A única escolha do cabeçalho */}
        <div className="card shadow-sm border-0 mb-3">
          <div className="card-body">
            <div className="dt-escolhas">
              {areas.length > 1 && (
                <div>
                  <label className="form-label small text-muted mb-1" htmlFor="diario-area">Área</label>
                  <select id="diario-area" className="form-select" value={area}
                    onChange={(ev) => trocarArea(ev.target.value)}>
                    {areas.map((a) => <option value={String(a.id)} key={String(a.id)}>{a.nome}</option>)}
                  </select>
                </div>
              )}
              {areas.length === 1 && (
                <div>
                  <div className="dt-cab-rot text-muted">Área</div>
                  <div className="fw-semibold">{areas[0].nome}</div>
                  <input type="hidden" id="diario-area" value={String(areas[0].id)} />
                </div>
              )}
              <div>
                <label className="form-label small text-muted mb-1" htmlFor="diario-date">Data</label>
                <input id="diario-date" type="date" className="form-control" value={dia}
                  onChange={(ev) => trocarDia(ev.target.value)} />
              </div>
              <div>
                <label className="form-label small text-muted mb-1" htmlFor="diario-shift">Turno</label>
                <select id="diario-shift" className="form-select" value={turno}
                  onChange={(ev) => trocarTurno(ev.target.value)}>
                  {disponiveis.map((n) => (
                    <option value={n} key={n}>{n + (jaEncerrado(e, n) ? ' — já encerrado' : '')}</option>
                  ))}
                </select>
              </div>
              {/* O modelo é consequência de área + turno: o campo oculto é o
                  que o servidor recebe (configuracao_id). */}
              <div hidden>
                <label className="form-label small text-muted mb-1" htmlFor="diario-config">Modelo de passagem</label>
                <select id="diario-config" className="form-select" value={cfg ? cfg.id : ''} onChange={() => {}}>
                  {configs.map((c) => <option value={c.id} key={c.id}>{c.nome}</option>)}
                </select>
              </div>
            </div>
          </div>
        </div>

        {/* As duas abas: o que eu RECEBI e o que eu ENTREGO */}
        <div className="dt-abas" role="tablist">
          <button type="button" className={'dt-aba' + (painel === 'pendencias' ? ' ativa' : '')}
            data-painel="pendencias" role="tab" aria-selected={painel === 'pendencias'}
            onClick={() => mostrarPainel('pendencias')}>
            <i className="bi bi-inbox"></i> Pendências
            {pendencias.length > 0 && (
              <span className={'dt-aba-n' + (vencidas ? ' ruim' : '')}>{pendencias.length}</span>
            )}
          </button>
          <button type="button" className={'dt-aba' + (painel === 'passagem' ? ' ativa' : '')}
            data-painel="passagem" role="tab" aria-selected={painel === 'passagem'}
            onClick={() => mostrarPainel('passagem')}>
            <i className="bi bi-pencil-square"></i> Passagem de turno
          </button>
        </div>

        {/* Painel 1: o que eu RECEBI */}
        <div className="dt-painel" data-painel="pendencias" hidden={painel !== 'pendencias'}>
          {dados.anteriores.map((a) => <BlocoAnterior a={a} visivel={a.chave === chaveAnterior} key={a.chave} />)}

          {tinhaPendencias && (
            <div className="card shadow-sm border-0 mb-3">
              <div className="card-header bg-white fw-bold d-flex justify-content-between">
                <span>Pendências em aberto</span>
                <span className="text-muted fw-normal small">{pendencias.length}</span>
              </div>
              <div className="card-body">
                {pendencias.map((p) => (
                  <CartaoPendencia p={p} key={p.id} resolver={() => resolverPendencia(p.id)}
                    anotar={() => anotarPendencia(p.id)} />
                ))}
                {!pendencias.length && <div className="dt-vazio">Todas as pendências recebidas foram baixadas.</div>}
              </div>
            </div>
          )}

          {!tinhaPendencias && (
            <div className="dt-sem-pend">
              <i className="bi bi-check2-circle fs-3 d-block mb-2 text-success"></i>
              Nenhuma pendência aberta neste contrato.<br />
              <span className="small">O turno anterior não deixou nada em aberto para você.</span>
            </div>
          )}
        </div>

        {/* Painel 2: o que eu ENTREGO */}
        <div className="dt-painel" data-painel="passagem" hidden={painel !== 'passagem'}>
          <form id="diario-form" onSubmit={(ev) => ev.preventDefault()}>

            {/* O que a gestão pediu PARA ESTE TURNO: antes das perguntas (a exceção do dia). */}
            <div id="dt-tarefas-gestao" hidden={!tarefas}>
              <div className="dt-secao">
                <i className="bi bi-clipboard-check"></i> A gestão pediu para este turno
              </div>
              <div id="dt-tarefas-lista">
                {(tarefas || []).map((t) => (
                  <CartaoTarefa t={t} key={t.id + ':' + t.status} respondida={() => setRecarga((n) => n + 1)} />
                ))}
              </div>
            </div>

            <div className="dt-secao">Perguntas deste contrato</div>
            <div id="diario-fields" key={desenho}>
              {!disponiveis.length
                ? <div className="alert alert-warning">{SEM_MODELO_NA_AREA}</div>
                : perguntas.length
                  ? perguntas.map((p, i) => <CartaoPergunta p={p} i={i} key={chaveDe(p) + ':' + i}
                      valor={valores} mudar={mudar} />)
                  : <div className="dt-vazio">Este turno ainda não tem perguntas cadastradas.</div>}
            </div>

            <div className="dt-secao">Observações do turno</div>
            <div className="card shadow-sm border-0 mb-3">
              <div className="card-body">
                <textarea id="diario-observacao" className="form-control" rows={4} value={observacao}
                  onChange={(ev) => setObservacao(ev.target.value)}
                  placeholder="Fatos relevantes da operação, desvios e contexto do turno."></textarea>
                <CaixaDeAnexos chave="" daObservacao />
              </div>
            </div>

            <div className="dt-secao">Ocorrências</div>
            <div className="card shadow-sm border-0 mb-3">
              <div className="card-body">
                <div id="occurrence-list">
                  {ocoRows.map((r) => (
                    <div className="row g-2 mb-2 occurrence-row" key={r.n}>
                      <div className="col-md-3">
                        <select className="form-select o-type" value={r.tipo}
                          onChange={(ev) => mudarOco(r.n, 'tipo', ev.target.value)}>
                          {r.tipos.length
                            ? r.tipos.map((t) => <option value={t} key={t}>{t}</option>)
                            : <option value="Outros">Outros</option>}
                        </select>
                      </div>
                      <div className="col-md-2">
                        <input className="form-control o-ref" placeholder="Número / referência" value={r.referencia}
                          onChange={(ev) => mudarOco(r.n, 'referencia', ev.target.value)} />
                      </div>
                      <div className="col-md-4">
                        <input className="form-control o-desc" placeholder="Descrição da ocorrência" value={r.descricao}
                          onChange={(ev) => mudarOco(r.n, 'descricao', ev.target.value)} />
                      </div>
                      <div className="col-md-2">
                        <select className="form-select o-grav" value={r.gravidade}
                          title={'Marque "Atenção" para o fato aparecer em destaque no painel do gestor ' +
                            'como ponto de atenção do contrato'}
                          onChange={(ev) => mudarOco(r.n, 'gravidade', ev.target.value)}>
                          <option value="normal">Normal</option>
                          <option value="critica">⚠ Atenção</option>
                        </select>
                      </div>
                      <BotaoRemover classeDaLinha="occurrence-row"
                        remover={() => setOcoRows((l) => l.filter((x) => x.n !== r.n))} />
                    </div>
                  ))}
                </div>
                <button type="button" className="btn btn-outline-danger" onClick={novaOcorrencia}>
                  <i className="bi bi-plus-lg"></i> Nova ocorrência</button>
              </div>
            </div>

            <div className="dt-secao">Pendências para o próximo turno</div>
            <div className="card shadow-sm border-0 mb-3">
              <div className="card-body">
                <div id="pending-list">
                  {pendRows.map((r) => (
                    <div className="row g-2 mb-2 pending-row" key={r.n}>
                      <div className="col-md-4">
                        <input className="form-control p-title" placeholder="Pendência" value={r.titulo}
                          onChange={(ev) => mudarPend(r.n, 'titulo', ev.target.value)} />
                      </div>
                      <div className="col-md-2">
                        <input className="form-control p-ref" placeholder="Nº / referência" value={r.referencia}
                          onChange={(ev) => mudarPend(r.n, 'referencia', ev.target.value)} />
                      </div>
                      <div className="col-md-3">
                        <input className="form-control p-desc" placeholder="Descrição" value={r.descricao}
                          onChange={(ev) => mudarPend(r.n, 'descricao', ev.target.value)} />
                      </div>
                      <div className="col-md-2">
                        <select className="form-select p-priority" value={r.prioridade}
                          onChange={(ev) => mudarPend(r.n, 'prioridade', ev.target.value)}>
                          <option value="baixa">Baixa</option>
                          <option value="media">Média</option>
                          <option value="alta">Alta</option>
                        </select>
                      </div>
                      <BotaoRemover classeDaLinha="pending-row"
                        remover={() => setPendRows((l) => l.filter((x) => x.n !== r.n))} />
                    </div>
                  ))}
                </div>
                <button type="button" className="btn btn-outline-primary" onClick={novaPendencia}>
                  <i className="bi bi-plus-lg"></i> Nova pendência</button>
              </div>
            </div>

            <div className="d-flex justify-content-end gap-2 dt-acoes" id="diario-salvar"
              style={guardado ? { position: 'static' } : undefined}>
              {guardado ? <CaixaGuardado g={guardado} verTurno={dados.links.ver_turno} /> : (
                <>
                  <button className="btn btn-outline-secondary" type="button" disabled={ocupado}
                    onClick={() => salvarTurno(false)}>Salvar rascunho</button>
                  <button className="btn btn-primary px-4" type="button" disabled={ocupado}
                    onClick={() => salvarTurno(true)}>Encerrar turno</button>
                </>
              )}
            </div>
          </form>
        </div>
      </div>
    </>
  );
}

/** "Guardado neste aparelho" — e, quando a fila sobe, "Enviado". */
function CaixaGuardado({ g, verTurno }: { g: Guardado; verTurno: string }) {
  const recarregar = (
    <div className="mt-2">
      <button type="button" className="btn btn-sm btn-outline-secondary" data-recarregar
        onClick={() => window.location.reload()}>Nova passagem</button>
    </div>
  );
  if (g.enviado) {
    const d = g.enviado;
    const link = d.turno_id ? verTurno + Number(d.turno_id) : null;
    return (
      <div className="dt-guardado dt-enviado" role="status" aria-live="polite">
        <strong><i className="bi bi-cloud-check"></i> Enviado.</strong>{' '}
        {d.estado === 'aviso'
          ? (d.mensagem || 'A passagem subiu, mas com um aviso — veja no alto da tela.')
          : 'A passagem que estava guardada neste aparelho já está no sistema.'}
        {link && <>{' '}<Link to={link.replace(/^\/novo/, '')}>Ver a passagem</Link></>}
        {recarregar}
      </div>
    );
  }
  return (
    <div className="dt-guardado" role="status" aria-live="polite">
      <strong><i className="bi bi-cloud-arrow-up"></i> Guardado neste aparelho.</strong>{' '}
      {g.turnoId ? 'A passagem foi enviada; as fotos ainda não subiram. '
        : <>Ainda <u>não foi enviado</u>: está sem conexão agora. </>}
      Vai subir sozinho quando houver sinal, com o sistema aberto neste aparelho. Enquanto isso, o aviso no
      alto da tela mostra o que está guardado.
      {recarregar}
    </div>
  );
}

