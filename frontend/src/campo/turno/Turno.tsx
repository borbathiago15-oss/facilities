// "Meu turno" — o aplicativo de campo executando a rota (Fase 1b da migração
// para React; a tela antiga é static/js/rotas-turno.js, com o mesmo
// comportamento e as mesmas chaves no aparelho).
//
//   /novo/app/turno              → um cartão por local ("ler o QR da entrada" /
//                                  "Você está no X — Ver o turno")
//   /novo/app/turno?local=<id>   → o turno de hoje DAQUELE local
//   /novo/app/turno?ponto=<QR>   → QR da ENTRADA: registra a chegada e abre o
//                                  turno do local; QR comum: abre DIRETO no que
//                                  é para fazer agora ali (foto do antes → um
//                                  check por item → foto do depois → Pronto)
//
// Com sinal, a hora da leitura é a do SERVIDOR (o selo de /app/api/leitura).
// Sem sinal, vale a hora do celular, e a execução vai marcada "feito sem
// sinal"; o envio fica na fila do aparelho (window.TrinoFila, a mesma das
// telas antigas) e sobe sozinho quando o sinal volta. O mesmo envio nunca
// vira duas execuções (envio_id). O servidor é a verdade: quando ele já
// registrou a tarefa, a marca local ("guardada"/"enviada") some.
import { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useNavigationType } from 'react-router';
import { enviarBruto } from '../../api';
import { Execucao, type Envio } from './Execucao';
import { FolhaTroca, type Material } from './Folhas';
import {
  apagarMarcasVencidas, chaveFeitas, chegadaDe, desdeQuando, exigeChegada, feitasNoAparelho, gravarJson,
  guardarTroca, hora, lerTroca, limparTroca, localDe, marcarChegadaLocal, marcarFeita, regrasDoTurno,
  type RegrasDoTurno, versoesDe,
} from './regras';
import type {
  DadosDoTurno, LocalDaCarteira, OcorrenciaDoPonto, Ponto, Preventiva, Tarefa, Troca, Versao,
} from './tipos';

const LER_QR = '/app/ler-qr';

type Gps = { lat?: number; lng?: number; precisao?: number; erro?: string };
type Leitura = {
  ponto: string; selo: string | null; lido_em: string; comCamera: boolean; gps: Gps | null;
  pronta: Promise<string | null>; gpsPronta: Promise<Gps>;
};
type Resposta = { conexao?: boolean; ok?: boolean; x?: Record<string, any> };
type PontoMinimo = Pick<Ponto, 'nome'> & Partial<Ponto>;
type AoConcluir = {
  respostas?: unknown; status?: string; situacao?: string; nao_conformes?: number;
  pedidos_insumo?: unknown[]; motivo_atraso?: string; duracao_min?: number;
};

type Tela =
  | { tipo: 'locais' }
  | { tipo: 'turno'; localId: string; mensagem?: string }
  | { tipo: 'chegada'; nome: string; entrada_nome?: string | null }
  | { tipo: 'registrando' }
  | { tipo: 'ponto_desconhecido' }
  | { tipo: 'ponto'; codigo: string }
  | { tipo: 'execucao' }
  | { tipo: 'atraso'; extra: { duracao_min?: number; previsto_min?: number };
      devolver: (motivo: string, texto: string | null) => void; cancelar: () => void }
  | { tipo: 'depois'; nome: string; h: string; guardada: boolean; resposta: AoConcluir | null;
      tarefa: Tarefa | null; prox: Tarefa | null; proxPode: boolean; localId: number | null }
  | { tipo: 'nao_realizada'; t: Tarefa };

type Aberta = {
  chave: number; tarefa: Tarefa | null; versao: Versao; prev: Preventiva | null; troca: Troca | null;
  codigo: string; inicio: string; p: PontoMinimo; semSelo: boolean; outras: number;
};

const NA_LISTA = ['locais', 'turno'];
const NA_EXECUCAO = ['execucao', 'nao_realizada'];

// GPS na leitura do QR (27/10/2026): a posição do celular SÓ neste instante,
// para mostrar que a leitura foi no local. Nunca trava: sem resposta em 10 s,
// sem permissão ou sem GPS, a leitura segue "sem GPS".
function obterGps(): Promise<Gps> {
  if (!navigator.geolocation) return Promise.resolve({ erro: 'indisponivel' });
  return new Promise((ok) => {
    let feito = false;
    const limite = setTimeout(() => { if (!feito) { feito = true; ok({ erro: 'sem_resposta' }); } }, 10000);
    navigator.geolocation.getCurrentPosition((pos) => {
      if (feito) return;
      feito = true; clearTimeout(limite);
      ok({ lat: pos.coords.latitude, lng: pos.coords.longitude, precisao: Math.round(pos.coords.accuracy || 0) });
    }, (e) => {
      if (feito) return;
      feito = true; clearTimeout(limite);
      ok({ erro: e && e.code === 1 ? 'negado' : 'indisponivel' });
    }, { enableHighAccuracy: true, timeout: 9000, maximumAge: 60000 });
  });
}

function novoId() {
  if (window.TrinoFila && window.TrinoFila.novoId) return window.TrinoFila.novoId();
  return 'e' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
}

const semSinal = () => navigator.onLine === false;

function BotaoLerQr({ classe }: { classe?: string }) {
  return (
    <Link className={classe || 'btn btn-primary btn-lg w-100 fc-app-acao'} to={LER_QR}>
      <i className="bi bi-qr-code-scan"></i> Ler o QR
    </Link>
  );
}

/** Um cartão de tarefa. ``n``: o número no roteiro do dia (1, 2, 3…);
 * ``proxima``: a que a pessoa deve fazer agora — fica destacada. */
function CartaoTarefa({ t, n, proxima, dados, r, children }: {
  t: Tarefa; n?: number; proxima?: boolean; dados: DadosDoTurno; r: RegrasDoTurno; children?: React.ReactNode;
}) {
  const s = r.situacao(t);
  const v = dados.versoes[t.versao] || ({} as Versao);
  return (
    <div className={'fc-app-item' + (proxima ? ' fc-proxima' : '')} data-tarefa={t.id}>
      <div className="d-flex align-items-center gap-2 flex-wrap">
        {n ? <span className="fc-roteiro-n" aria-label={'Passo ' + n + ' do roteiro'}>{String(n)}</span> : null}
        <span className="fs-5 fw-bold">{t.hora}</span>
        {proxima && <span className="badge text-bg-danger">Próxima</span>}
        <span className={'badge fc-sit fc-sit-' + s.cod}>{s.rotulo}</span>
        {t.minha && <span className="badge text-bg-light">Sua</span>}
      </div>
      <span className="fw-semibold">{t.ambiente + ' · ' + t.ponto_nome}</span>
      <span className="small text-muted">
        {(v.modelo || t.rota) + (t.tempo_previsto_min ? ' · ' + t.tempo_previsto_min + ' min' : '') +
          (t.escalado && !t.minha ? ' · escala: ' + t.escalado : '')}
      </span>
      {children}
    </div>
  );
}

/** Um aviso do público no ponto: "Vou atender" e "Resolvido". */
function LinhaDaOcorrencia({ o, agir }: {
  o: OcorrenciaDoPonto; agir: (acao: string) => Promise<{ ok: boolean; status?: string }>;
}) {
  // Como na tela antiga: o "Vou atender" é decidido quando o ponto abre.
  const [comAtender] = useState(o.status === 'aberta');
  const [botoes, setBotoes] = useState<Record<string, { ocupado: boolean; texto?: string }>>({});
  const tocar = (acao: string) => {
    setBotoes((b) => ({ ...b, [acao]: { ocupado: true } }));
    agir(acao).then((res) => {
      if (!res.ok) { setBotoes((b) => ({ ...b, [acao]: { ocupado: false } })); return; }
      if (res.status !== 'resolvida') setBotoes((b) => ({ ...b, [acao]: { ocupado: true, texto: 'Em atendimento' } }));
    });
  };
  return (
    <div className="fc-app-item">
      <span className="fw-semibold">{o.tipo + (o.atrasada ? ' · fora do prazo' : '')}</span>
      <span className="small text-muted">
        {'às ' + o.hora + (o.texto ? ' · "' + o.texto + '"' : '') + (o.prazo ? ' · prazo ' + o.prazo : '')}
      </span>
      <div className="d-flex gap-2 mt-2">
        {comAtender && (
          <button type="button" className="btn btn-outline-primary flex-fill fc-app-acao"
            disabled={!!botoes.atender?.ocupado} onClick={() => tocar('atender')}>
            {botoes.atender?.texto || 'Vou atender'}
          </button>
        )}
        <button type="button" className="btn btn-success flex-fill fc-app-acao"
          disabled={!!botoes.resolver?.ocupado} onClick={() => tocar('resolver')}>
          {botoes.resolver?.texto || 'Resolvido'}
        </button>
      </div>
    </div>
  );
}

/** Atividade extra (fora da rota): a lista dos checklists do local. */
function AtividadeExtra({ extras, fazer }: { extras: Versao[]; fazer: (v: Versao) => void }) {
  const [escolha, setEscolha] = useState(String(extras[0].id));
  return (
    <details className="fc-cartao mb-3">
      <summary className="fw-semibold">Atividade extra (fora da rota)</summary>
      <p className="small text-muted mt-2">Para registrar uma limpeza ou vistoria fora do horário da rota.</p>
      <select className="form-select form-select-lg" id="extra-modelo" aria-label="Checklist" value={escolha}
        onChange={(e) => setEscolha(e.target.value)}>
        {extras.map((v) => <option key={v.id} value={v.id}>{v.modelo}</option>)}
      </select>
      <button type="button" className="btn btn-outline-primary fc-app-acao w-100 mt-2"
        onClick={() => fazer(extras.find((v) => String(v.id) === escolha)!)}>Fazer atividade extra</button>
    </details>
  );
}

/** Levou mais que o previsto: o motivo do atraso, e o reenvio. */
function TelaAtraso({ dados, tela }: { dados: DadosDoTurno; tela: Extract<Tela, { tipo: 'atraso' }> }) {
  const [outro, setOutro] = useState(false);
  const [texto, setTexto] = useState('');
  const [erro, setErro] = useState(false);
  const campo = useRef<HTMLInputElement>(null);
  useEffect(() => { if (outro) campo.current?.focus(); }, [outro]);
  const vocab = dados.motivos_atraso;
  return (
    <>
      <h1 className="fc-titulo">
        {'Esta limpeza levou ' + tela.extra.duracao_min + ' min; o previsto era ' + tela.extra.previsto_min + '.'}
      </h1>
      <p className="fc-sub">O que aconteceu?</p>
      <div className="fc-cartao">
        {(dados.motivos_atraso_ordem || Object.keys(vocab)).map((k) => (
          <button type="button" key={k} className="btn btn-outline-dark btn-lg w-100 fc-app-acao mb-2 fc-motivo"
            data-motivo={k} onClick={() => {
              if (k !== 'outro') { tela.devolver(k, null); return; }
              setOutro(true);
              campo.current?.focus();
            }}>{vocab[k]}</button>
        ))}
        <input className="form-control form-control-lg mb-2" maxLength={300} hidden={!outro} ref={campo}
          aria-label="O que aconteceu" placeholder="Conte em poucas palavras" value={texto}
          onChange={(e) => setTexto(e.target.value)} />
        <p className="small text-danger" hidden={!erro}>Escreva o que aconteceu.</p>
        <button type="button" className="btn btn-primary btn-lg w-100 fc-app-acao mb-2" hidden={!outro}
          onClick={() => {
            if (!texto.trim()) { setErro(true); return; }
            tela.devolver('outro', texto.trim());
          }}>Confirmar</button>
        <button type="button" className="btn btn-link w-100" onClick={tela.cancelar}>Voltar</button>
      </div>
    </>
  );
}

/** "Não deu para fazer": a tarefa inteira não foi feita (avisa a gestão). */
function NaoRealizada({ t, dados, dizer, registrada, cancelar }: {
  t: Tarefa; dados: DadosDoTurno; dizer: (texto: string, tipo?: string) => void;
  registrada: (chamadoId: number | null) => void; cancelar: () => void;
}) {
  const [motivo, setMotivo] = useState('');
  const [texto, setTexto] = useState('');
  const [chamado, setChamado] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  return (
    <>
      <h1 className="fc-titulo">Não deu para fazer</h1>
      <p className="fc-sub">{t.hora + ' · ' + t.ponto_nome}</p>
      <form onSubmit={(ev) => {
        ev.preventDefault();
        if (!motivo) { dizer('Escolha o motivo.', 'warning'); return; }
        setOcupado(true);
        enviarBruto('/app/api/tarefas/' + t.id + '/nao-realizada', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ motivo, texto, abrir_chamado: chamado }),
        }).then((r) => r.json().then((x) => ({ ok: r.ok, x })))
          .then((res) => {
            if (!res.ok) { setOcupado(false); dizer(res.x.error || 'Não foi possível registrar.', 'danger'); return; }
            t.status = 'nao_realizada';
            registrada(res.x.chamado_id || null);
          }, () => {
            setOcupado(false);
            dizer('Sem sinal: "não realizada" precisa de sinal para avisar a gestão. Tente de novo quando voltar.', 'warning');
          });
      }}>
        <div className="fc-cartao mb-2" role="radiogroup" aria-label="Motivo">
          {Object.keys(dados.motivos).map((k) => (
            <label className="d-flex gap-2 py-2 fc-radio-linha" key={k}>
              <input type="radio" name="motivo" value={k} checked={motivo === k} onChange={() => setMotivo(k)} />
              <span>{dados.motivos[k]}</span>
            </label>
          ))}
        </div>
        <div className="fc-cartao mb-2">
          <label className="form-label small fw-semibold" htmlFor="nrtexto">O que aconteceu</label>
          <input className="form-control form-control-lg" id="nrtexto" name="texto" maxLength={300} value={texto}
            onChange={(e) => setTexto(e.target.value)} />
          <label className="d-flex gap-2 mt-2 fc-radio-linha">
            <input type="checkbox" name="chamado" checked={chamado} onChange={(e) => setChamado(e.target.checked)} />
            <span>Abrir chamado para resolver</span>
          </label>
        </div>
        <button type="submit" className="btn btn-primary btn-lg w-100 fc-app-acao" disabled={ocupado}>Registrar</button>
        <button type="button" className="btn btn-link w-100" onClick={cancelar}>Cancelar</button>
      </form>
    </>
  );
}

export function Turno({ dados: inicial }: { dados: DadosDoTurno }) {
  // Os dados da tela mudam com ela aberta (a tarefa feita, a chegada, o aviso
  // resolvido), como na tela antiga: ficam aqui, e ``redesenhar`` mostra.
  const dados = useRef(inicial).current;
  const r = useMemo(() => regrasDoTurno(dados), [dados]);
  const [, redesenhar] = useReducer((n: number) => n + 1, 0);
  const [tela, setTela] = useState<Tela | null>(null);
  const [aviso, setAviso] = useState<{ texto: string; tipo: string; n: number } | null>(null);
  const [folhaTroca, setFolhaTroca] = useState<{ titulo: string; devolver: (t: Troca | null) => void } | null>(null);
  const [aberta, setAberta] = useState<Aberta | null>(null);
  const [verColegas, setVerColegas] = useState(false);
  const leitura = useRef<Leitura | null>(null);
  const materiais = useRef<Record<string, Material[]>>({});
  const chaves = useRef(0);
  const caixaDoAviso = useRef<HTMLDivElement>(null);
  const navegar = useNavigate();
  const lugar = useLocation();
  const tipoDeNavegacao = useNavigationType();
  const usuario = dados.usuario;

  // ── Ajudantes ─────────────────────────────────────────────────────────
  const dizer = (texto: string, tipo?: string) =>
    setAviso((a) => (texto ? { texto, tipo: tipo || 'info', n: (a?.n || 0) + 1 } : null));
  useEffect(() => {
    if (aviso) caixaDoAviso.current?.scrollIntoView?.({ block: 'nearest' });
  }, [aviso]);
  const mostrar = (t: Tela) => {
    setTela(t);
    try { window.scrollTo(0, 0); } catch { /* sem janela (testes) */ }
  };
  const irPara = (url: string, substituir = false) => navegar(url, { replace: substituir });
  const pontoDe = (codigo: string | null | undefined) => (codigo ? dados.pontos[codigo] : undefined);

  // ── As telas ──────────────────────────────────────────────────────────
  const mostrarLocais = () => mostrar({ tipo: 'locais' });
  const telaConfirmeChegada = (local: { nome: string; entrada_nome?: string | null }) =>
    mostrar({ tipo: 'chegada', nome: local.nome, entrada_nome: local.entrada_nome });
  const telaPonto = (codigo: string) => mostrar({ tipo: 'ponto', codigo });

  function mostrarTurno(localId: number | string, mensagem?: string) {
    const l = localDe(dados, localId);
    if (l && exigeChegada(usuario, l)) { telaConfirmeChegada(l); return; }
    mostrar({ tipo: 'turno', localId: String(localId), mensagem });
    if (l) atualizarTurno(l.id);
  }

  // Com sinal, o servidor diz o que já foi feito (por esta pessoa ou outra)
  // e a chegada de hoje; a lista se atualiza no lugar.
  function atualizarTurno(localId: number) {
    if (semSinal()) return;
    enviarBruto('/app/api/turno?local=' + encodeURIComponent(localId))
      .then((resp) => (resp.ok ? resp.json() : null))
      .then((x) => {
        if (!x || !x.tarefas) return;
        const l = localDe(dados, localId);
        if (l && x.chegada) l.chegada = x.chegada;
        const porId: Record<string, Tarefa> = {};
        dados.tarefas.forEach((t) => { porId[t.id] = t; });
        let mudou = false;
        x.tarefas.forEach((nt: { id: number; status: string }) => {
          const t = porId[nt.id];
          if (t && t.status !== nt.status) { t.status = nt.status; mudou = true; }
        });
        if (!mudou) return;
        apagarMarcasVencidas(dados);
        redesenhar();
      })
      .catch(() => {});
  }

  // ── O ponto (depois de ler o QR) ──────────────────────────────────────
  // O selo (hora do servidor) é a prova de que a pessoa leu o QR no ponto: só
  // é pedido quando a CÂMERA leu agora (``lido=camera`` vindo do leitor). O
  // link de um aviso, o código digitado e a página recarregada abrem o ponto,
  // mas a execução fica com a hora do celular — marcada para a gestão.
  function lerNoServidor(codigo: string, comCamera = false) {
    if (leitura.current && leitura.current.ponto === codigo) return leitura.current.pronta;  // voltou ao mesmo ponto
    const esta = { ponto: codigo, selo: null, lido_em: new Date().toISOString(), comCamera: !!comCamera,
                   gps: null } as unknown as Leitura;
    leitura.current = esta;
    esta.gpsPronta = obterGps().then((g) => { esta.gps = g; return g; });
    if (!comCamera || semSinal()) {
      esta.pronta = Promise.resolve(null);
      return esta.pronta;
    }
    esta.pronta = enviarBruto('/app/api/leitura', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ponto: codigo }),
    }).then((resp) => (resp.ok ? resp.json() : null))
      .then((x) => { if (x && leitura.current === esta) esta.selo = x.selo; return esta.selo; })
      .catch(() => null);   // sem sinal: fica a hora do aparelho
    return esta.pronta;
  }

  function abrirPonto(codigo: string, comCamera: boolean) {
    const p = dados.pontos[codigo];
    if (!p) { mostrar({ tipo: 'ponto_desconhecido' }); return; }
    lerNoServidor(codigo, comCamera);
    const local = localDe(dados, p.local_id);
    if (p.entrada) { registrarChegada(p, codigo, local); return; }
    if (exigeChegada(usuario, local)) { telaConfirmeChegada(local!); return; }
    const agora = r.tarefaDaHora(codigo);
    const troca = lerTroca(usuario);
    if (agora) { limparTroca(usuario); abrirExecucao(agora, dados.versoes[agora.versao]); return; }
    if (troca) {
      // Veio de "Ir para outra área": a próxima tarefa desta área na rota é
      // adiantada; sem tarefa aqui, é a área fora da rota, com o escopo dela.
      const futura = r.tarefaParaAdiantar(codigo);
      if (futura) { abrirExecucao(futura, dados.versoes[futura.versao], null, troca); return; }
      const escopo = versoesDe(dados, p.escopo);
      if (escopo.length === 1) { abrirExecucao(null, escopo[0], null, troca); return; }
    }
    telaPonto(codigo);
  }

  // A pessoa leu o QR da ENTRADA: a chegada do dia fica registrada (com
  // sinal, na hora; sem sinal, guardada no aparelho e enviada depois).
  function registrarChegada(p: Ponto, codigo: string, local: LocalDaCarteira | null) {
    mostrar({ tipo: 'registrando' });
    const esta = leitura.current!;
    const nome = local ? local.nome : p.local;
    const chegou = (h: string, guardada: boolean) => {
      if (local) local.chegada = guardada ? null : { hora: h };
      if (guardada) marcarChegadaLocal(usuario, p.local_id, h);
      irPara('/app/turno?local=' + p.local_id, true);
      mostrarTurno(p.local_id, 'Você chegou ao ' + nome + ' às ' + h +
        (guardada ? '. Sem sinal: a chegada ficou guardada no aparelho.' : '.'));
    };
    const guardar = () => {
      if (!window.TrinoFila) {
        dizer('Sem sinal, e este aparelho não guarda envios. Tente de novo com sinal.', 'danger');
        telaConfirmeChegada(local || { nome: p.local });
        return;
      }
      const h = hora(esta.lido_em);
      window.TrinoFila.guardar({ tipo: 'chegada', rotulo: 'Chegada · ' + nome,
        corpo: { ponto: codigo, lido_em: esta.lido_em, com_camera: esta.comCamera, gps: esta.gps } })
        .then(() => chegou(h, true),
              () => dizer('Sem sinal, e não foi possível guardar. Tente de novo.', 'danger'));
    };
    Promise.all([esta.pronta, esta.gpsPronta]).then(([selo]) => {
      if (semSinal()) { guardar(); return; }
      return enviarBruto('/app/api/chegada', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ponto: codigo, selo_leitura: selo, com_camera: esta.comCamera, gps: esta.gps }),
      }).then((resp) => {
        if (window.TrinoFila && window.TrinoFila.ehFalhaDeConexao(resp)) { guardar(); return; }
        return resp.json().then((x) => {
          if (!resp.ok) {
            dizer(x.error || 'Não foi possível registrar a chegada.', 'danger');
            telaConfirmeChegada(local || { nome: p.local });
            return;
          }
          chegou(x.chegada.hora, false);
        }, guardar);
      }, guardar);
    });
  }

  function catalogo(localId: number | null | undefined): Promise<Material[]> {
    if (localId && materiais.current[localId]) return Promise.resolve(materiais.current[localId]);
    if (semSinal() || !localId) return Promise.resolve([]);
    return enviarBruto('/app/api/materiais?local=' + encodeURIComponent(localId))
      .then((resp) => (resp.ok ? resp.json() : []))
      .then((lista) => { materiais.current[localId] = lista; return lista; })
      .catch(() => []);
  }

  // ── A execução ────────────────────────────────────────────────────────
  function abrirExecucao(tarefa: Tarefa | null, versao: Versao | undefined, prev?: Preventiva | null,
                         troca?: Troca | null) {
    if (!versao) { dizer('Checklist não encontrado. Recarregue com sinal.', 'warning'); return; }
    const codigo = (tarefa ? tarefa.ponto : leitura.current && leitura.current.ponto) as string;
    if (!leitura.current || leitura.current.ponto !== codigo) lerNoServidor(codigo);
    const lt = leitura.current!;
    const p: PontoMinimo = dados.pontos[codigo] ||
      { nome: tarefa ? tarefa.ponto_nome : '', local_id: tarefa ? tarefa.local_id : undefined };
    dizer('');
    chaves.current += 1;
    setAberta({
      chave: chaves.current, tarefa, versao, prev: prev || null, troca: prev ? null : (troca || null),
      codigo, inicio: new Date().toISOString(), p,
      semSelo: !lt.comCamera && !lt.selo,
      outras: (dados.preventivas || []).filter((x) => x.ponto === codigo).length +
              (dados.ocorrencias || []).filter((o) => o.ponto === codigo).length,
    });
    mostrar({ tipo: 'execucao' });
  }

  function mandar(corpo: Record<string, unknown>, fotos: { campo: string; arquivo: File | Blob }[]): Promise<Resposta> {
    if (semSinal()) return Promise.resolve({ conexao: true });
    const fd = new FormData();
    fd.append('corpo', JSON.stringify(corpo));
    fotos.forEach((f) => fd.append(f.campo, f.arquivo, (f.arquivo as File).name || 'foto.jpg'));
    return enviarBruto('/app/api/execucoes', { method: 'POST', body: fd })
      .then((resp) => {
        if (window.TrinoFila && window.TrinoFila.ehFalhaDeConexao(resp)) return { conexao: true };
        return resp.json().then((x) => ({ ok: resp.ok, x }), () => ({ conexao: true }));
      }, () => ({ conexao: true }));
  }

  function enviar(a: Aberta, envio: Envio, liberar: () => void) {
    const { tarefa, versao, codigo, prev, troca } = a;
    const lt = leitura.current;
    const mesma = !!lt && lt.ponto === codigo;
    const corpo: Record<string, unknown> = {
      envio_id: novoId(), ponto: codigo, respostas: envio.respostas, motivos: envio.motivos,
      observacao: envio.observacao,
      selo_leitura: mesma ? lt!.selo : null,
      lido_em: mesma ? lt!.lido_em : a.inicio,
      concluida_em: new Date().toISOString(),
      sem_sinal: !(lt && lt.selo),
      gps: mesma ? lt!.gps : null,
    };
    if (tarefa) corpo.tarefa_id = tarefa.id; else corpo.versao_id = versao.id;
    if (prev) corpo.chamado_id = prev.id;
    if (troca) {
      corpo.motivo_troca = troca.motivo;
      corpo.motivo_troca_texto = troca.texto || null;
    }
    const reduzir = window.TrinoFoto ? window.TrinoFoto.reduzirTodos
      : (fs: File[]) => Promise.resolve(fs as (File | Blob)[]);
    reduzir(envio.fotos.map((f) => f.arquivo)).then((leves) => {
      const prontas = envio.fotos.map((f, i) => ({ campo: f.campo, arquivo: leves[i] || f.arquivo }));
      return mandar(corpo, prontas).then((res) => concluir(res, a, corpo, prontas, liberar));
    });
  }

  function concluir(res: Resposta, a: Aberta, corpo: Record<string, unknown>,
                    fotos: { campo: string; arquivo: File | Blob }[], liberar: () => void) {
    const { tarefa, codigo, prev } = a;
    const p: PontoMinimo = dados.pontos[codigo] ||
      { nome: tarefa ? tarefa.ponto_nome : '', local_id: tarefa ? tarefa.local_id : undefined };
    const tirarPreventiva = () => {
      if (prev) dados.preventivas = (dados.preventivas || []).filter((x) => x.id !== prev.id);
    };
    const reenviar = () => mandar(corpo, fotos).then((r2) => concluir(r2, a, corpo, fotos, liberar));
    if (res.conexao) {
      if (!window.TrinoFila) {
        liberar();
        dizer('Sem sinal, e este aparelho não guarda envios. Tente de novo com sinal.', 'danger');
        return;
      }
      // Sem sinal: a hora da conclusão é a do aparelho, e a execução vai
      // marcada assim.
      corpo.sem_sinal = true;
      window.TrinoFila.guardar({ tipo: 'execucao', rotulo: (tarefa ? tarefa.hora + ' · ' : '') + p.nome,
        tarefa_id: tarefa ? tarefa.id : null, corpo, fotos: fotos as { campo: string; arquivo: File }[] })
        .then(() => {
          if (tarefa) marcarFeita(usuario, tarefa.id, 'Guardada no aparelho');
          if (corpo.motivo_troca) limparTroca(usuario);
          tirarPreventiva();
          telaDepois(tarefa, p, null, true);
        }, () => {
          liberar();
          dizer('Sem sinal, e não foi possível guardar. Não feche a tela; tente de novo.', 'danger');
        });
      return;
    }
    if (!res.ok) {
      const x = res.x || {};
      if (x.motivo === 'motivo_atraso') {
        mostrar({ tipo: 'atraso', extra: x.extra || {},
          devolver: (motivo, texto) => {
            corpo.motivo_atraso = motivo;
            corpo.motivo_atraso_texto = texto || null;
            reenviar();
          },
          cancelar: () => { liberar(); setTela({ tipo: 'execucao' }); } });
        return;
      }
      if (x.motivo === 'motivo_troca') {
        setFolhaTroca({ titulo: x.error || 'Por que você foi a esta área agora?', devolver: (troca) => {
          if (!troca) { liberar(); return; }
          corpo.motivo_troca = troca.motivo;
          corpo.motivo_troca_texto = troca.texto || null;
          reenviar();
        } });
        return;
      }
      if (x.motivo === 'sem_chegada') {
        telaConfirmeChegada(localDe(dados, p.local_id) || { nome: p.local || '' });
        return;
      }
      liberar();
      dizer(x.error || 'Não foi possível registrar.', 'danger');
      return;
    }
    if (tarefa) tarefa.status = res.x!.status;
    if (corpo.motivo_troca) limparTroca(usuario);
    tirarPreventiva();
    telaDepois(tarefa, p, res.x as AoConcluir, false);
  }

  // Depois do "Pronto": a próxima tarefa.
  function telaDepois(tarefa: Tarefa | null, p: PontoMinimo, resposta: AoConcluir | null, guardada: boolean) {
    const localId = p.local_id || (tarefa ? tarefa.local_id : null);
    const prox = localId ? r.proximaTarefa(localId, tarefa) : null;
    mostrar({ tipo: 'depois', nome: p.nome, h: hora(), guardada, resposta, tarefa, prox,
              proxPode: !!prox && r.podeFazer(prox), localId: localId || null });
  }

  function agirNaOcorrencia(o: OcorrenciaDoPonto, acao: string) {
    return enviarBruto('/app/api/ocorrencias/' + o.id + '/' + acao, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    }).then((resp) => resp.json().then((x) => ({ ok: resp.ok, x })))
      .then((res) => {
        if (!res.ok) { dizer(res.x.error || 'Não foi possível.', 'danger'); return { ok: false }; }
        o.status = res.x.status;
        if (o.status === 'resolvida') {
          dados.ocorrencias = dados.ocorrencias.filter((x) => x.id !== o.id);
          dizer('Aviso resolvido. Quem avisou vê a resposta pelo QR.', 'success');
        }
        return { ok: true, status: o.status };
      }, () => { dizer('Sem sinal: tente de novo.', 'warning'); return { ok: false }; });
  }

  // ── Começo, e o "voltar" do celular ───────────────────────────────────
  const iniciado = useRef(false);
  useEffect(() => {
    if (iniciado.current) return;
    iniciado.current = true;
    apagarMarcasVencidas(dados);
    const params = new URLSearchParams(lugar.search);
    const ponto = params.get('ponto');
    const localParam = params.get('local');
    const comCamera = params.get('lido') === 'camera';
    if (comCamera) {
      // Recarregar a tela não vale como uma nova leitura do QR.
      params.delete('lido');
      irPara(lugar.pathname + '?' + params.toString(), true);
    }
    if (ponto) abrirPonto(ponto, comCamera);
    else if (localParam) mostrarTurno(localParam);
    else mostrarLocais();
  }, []);

  const ultimaChave = useRef(lugar.key);
  useEffect(() => {
    if (lugar.key === ultimaChave.current) return;
    ultimaChave.current = lugar.key;
    if (tipoDeNavegacao !== 'POP') return;
    const q = new URLSearchParams(lugar.search);
    if (q.get('ponto')) abrirPonto(q.get('ponto')!, false);
    else if (q.get('local')) mostrarTurno(q.get('local')!);
    else mostrarLocais();
  }, [lugar.key]);

  // A fila subiu uma execução guardada: só AQUELA tarefa deixa de ser
  // "guardada no aparelho" — as outras ainda estão na fila.
  useEffect(() => {
    const subiu = (ev: Event) => {
      const d = (ev as CustomEvent).detail;
      if (!d || d.tipo !== 'execucao') return;
      const f = feitasNoAparelho(usuario);
      if (d.tarefa_id) {
        if (!(d.tarefa_id in f)) return;
        f[d.tarefa_id] = 'Enviada';
      } else {
        // Item guardado por uma versão anterior do app, sem tarefa_id: não dá
        // para saber qual foi, então as guardadas viram "Enviada" como antes.
        Object.keys(f).forEach((k) => { if (f[k] === 'Guardada no aparelho') f[k] = 'Enviada'; });
      }
      gravarJson(chaveFeitas(usuario), f);
    };
    window.addEventListener('trino-fila:enviado', subiu);
    return () => window.removeEventListener('trino-fila:enviado', subiu);
  }, [usuario]);

  // ── Desenho ───────────────────────────────────────────────────────────
  function desenharLocais() {
    return (
      <>
        <h1 className="fc-titulo">Meu turno</h1>
        <p className="fc-sub">Escolha o local, ou leia o QR da entrada ao chegar.</p>
        <BotaoLerQr classe="btn btn-primary btn-lg w-100 fc-app-acao mb-3" />
        {!(dados.locais || []).length ? (
          <div className="fc-cartao fc-vazio">Você ainda não tem local liberado. Peça ao seu supervisor ou à gestão.</div>
        ) : dados.locais.map((l) => {
          const n = r.tarefasDoLocal(l.id);
          const abertas = n.filter(r.emAberto).length;
          const ch = chegadaDe(usuario, l);
          const plural = n.length > 1 ? ' tarefas' : ' tarefa';
          const sub = n.length ? abertas + ' de ' + n.length + plural + ' por fazer' : 'Nenhuma tarefa da rota hoje';
          if (l.entrada && !ch) {
            return (
              <Link key={l.id} className="fc-cartao fc-local-turno mb-2" to={LER_QR} data-local={l.id}
                data-situacao="sem_chegada">
                <span className="fc-local-turno-nome">{l.nome}</span>
                <span className="fc-local-turno-sub">
                  {(n.length ? n.length + plural + ' hoje · ' : '') + 'Ao chegar, leia o QR da entrada (' + l.entrada_nome + ')'}
                </span>
                <span className="fc-local-turno-acao"><i className="bi bi-qr-code-scan"></i> Ler o QR da entrada</span>
              </Link>
            );
          }
          return (
            <Link key={l.id} className={'fc-cartao fc-local-turno mb-2' + (ch ? ' fc-local-turno-aqui' : '')}
              to={'/app/turno?local=' + l.id} data-local={l.id} data-situacao={ch ? 'chegou' : 'sem_entrada'}
              onClick={(ev) => { ev.preventDefault(); irPara('/app/turno?local=' + l.id); mostrarTurno(l.id); }}>
              <span className="fc-local-turno-nome">{ch ? 'Você está no ' + l.nome : l.nome}</span>
              <span className="fc-local-turno-sub">{(ch ? 'Chegou às ' + ch.hora + ' · ' : '') + sub}</span>
              <span className="fc-local-turno-acao"><i className="bi bi-list-check"></i> Ver o turno</span>
            </Link>
          );
        })}
      </>
    );
  }

  // Avisos do público na lista do turno (27/10/2026): cada aviso é uma
  // tarefa "Checar aviso", a de quem cuida do ponto com o selo "Sua". Tocar
  // abre o ponto, onde se atende e resolve.
  function cartaoChecarAvisos(lista: OcorrenciaDoPonto[]) {
    return (
      <div className="fc-cartao mb-3 border-warning" id="turno-avisos">
        <h2 className="h6 fw-bold">{'Checar avisos do público (' + lista.length + ')'}</h2>
        {lista.slice().sort((a, b) => (b.minha ? 1 : 0) - (a.minha ? 1 : 0)).map((o) => {
          const url = '/app/turno?ponto=' + encodeURIComponent(o.ponto);
          return (
            <Link key={o.id} className="fc-app-item text-reset text-decoration-none" to={url} data-aviso={o.id}
              onClick={(ev) => { ev.preventDefault(); irPara(url); telaPonto(o.ponto); }}>
              <div className="d-flex align-items-center gap-2 flex-wrap">
                <span className="badge text-bg-warning">Checar aviso</span>
                {o.atrasada && <span className="badge fc-sit fc-sit-atrasada">Fora do prazo</span>}
                {o.status === 'em_atendimento' && <span className="badge fc-ocor-em_atendimento">Em atendimento</span>}
                {o.minha && <span className="badge text-bg-light">Sua</span>}
              </div>
              <span className="fw-semibold">{o.tipo}</span>
              <span className="small text-muted">
                {o.ambiente + ' · ' + o.ponto_nome + ' · às ' + o.hora + (o.texto ? ' · "' + o.texto + '"' : '') +
                  (o.responsavel && !o.minha ? ' · com ' + o.responsavel : '')}
              </span>
            </Link>
          );
        })}
      </div>
    );
  }

  function desenharTurno(t: Extract<Tela, { tipo: 'turno' }>) {
    const l = localDe(dados, t.localId);
    if (!l) {
      return (
        <>
          <div className="alert alert-warning">Este local não está entre os seus.</div>
          <button type="button" className="btn btn-outline-secondary w-100 fc-app-acao" onClick={mostrarLocais}>
            Ver meus locais
          </button>
        </>
      );
    }
    const ch = chegadaDe(usuario, l);
    const visiveis = r.tarefasVisiveis(l.id, verColegas);
    const proxima = r.proximaTarefa(l.id, null);
    const avisos = (dados.ocorrencias || []).filter((o) => (dados.pontos[o.ponto] || {}).local_id === l.id);
    const prevs = (dados.preventivas || []).filter((x) => (dados.pontos[x.ponto] || {}).local_id === l.id);
    return (
      <>
        {t.mensagem && <div className="alert alert-success" role="status">{t.mensagem}</div>}
        <h1 className="fc-titulo">{ch ? 'Você está no ' + l.nome : l.nome}</h1>
        <p className="fc-sub">
          {(ch ? 'Chegou às ' + ch.hora + (ch.guardada ? ' (chegada guardada no aparelho)' : '') + ' · ' : '') + 'Tarefas de hoje'}
        </p>
        <BotaoLerQr classe="btn btn-primary btn-lg w-100 fc-app-acao mb-2" />
        {/* Ir a outra área antes da ordem da rota: pergunta o motivo e manda
            ler o QR da área (adiantar uma da rota ou limpar uma fora da rota). */}
        <button type="button" className="btn btn-outline-primary w-100 fc-app-acao mb-3" data-trocar-area="1"
          onClick={() => setFolhaTroca({ titulo: 'Ir para outra área', devolver: (troca) => {
            if (!troca) return;
            troca.em = Date.now();
            guardarTroca(usuario, troca);
            irPara(LER_QR);
          } })}>
          <i className="bi bi-arrow-left-right"></i> Ir para outra área
        </button>
        {avisos.length > 0 && cartaoChecarAvisos(avisos)}
        {prevs.length > 0 && (
          <div className="alert alert-info">
            {prevs.length + ' preventiva(s) em aberto. Leia o QR do ponto para fazer o checklist.'}
          </div>
        )}
        {!visiveis.lista.length ? (
          <div className="fc-cartao fc-vazio">Nenhuma tarefa de rota para hoje aqui.</div>
        ) : (
          <>
            <div className="fc-cartao" id="turno-itens">
              {visiveis.lista.map((x, i) => (
                <CartaoTarefa key={x.id} t={x} n={i + 1} proxima={x === proxima} dados={dados} r={r} />
              ))}
            </div>
            {visiveis.minhas > 0 && visiveis.minhas < visiveis.todas && (
              <button type="button" className="btn btn-link w-100 mt-1" onClick={() => {
                setVerColegas(!verColegas);
                mostrarTurno(l.id);
              }}>
                {verColegas ? 'Ver só as minhas tarefas'
                  : 'Ver também as dos colegas (' + (visiveis.todas - visiveis.minhas) + ')'}
              </button>
            )}
            <p className="small text-muted mt-2">Para fazer uma tarefa, leia o QR do ponto: o checklist abre na hora.</p>
          </>
        )}
        <button type="button" className="btn btn-link w-100 mt-2"
          onClick={() => { irPara('/app/turno', true); mostrarLocais(); }}>Outro local</button>
      </>
    );
  }

  // O ponto sem tarefa para fazer agora: o que há ali hoje (horários,
  // preventivas, avisos do público, atividade extra).
  function desenharPonto(codigo: string) {
    const p = dados.pontos[codigo];
    const avisos = (dados.ocorrencias || []).filter((o) => o.ponto === codigo);
    const prevs = (dados.preventivas || []).filter((x) => x.ponto === codigo);
    const doPonto = dados.tarefas.filter((t) => t.ponto === codigo);
    const escopo = versoesDe(dados, p.escopo);
    const extras = versoesDe(dados, p.extras);
    return (
      <>
        <h1 className="fc-titulo">{p.nome}</h1>
        <p className="fc-sub">{p.ambiente + ' · ' + p.local}</p>
        {p.descricao && (
          <div className="fc-cartao mb-3">
            <div className="small fw-semibold text-muted">Sobre este ponto</div>
            <div>{p.descricao}</div>
          </div>
        )}
        {avisos.length > 0 && (
          <div className="fc-cartao mb-3 border-warning">
            <h2 className="h6 fw-bold">Avisos do público aqui</h2>
            {avisos.map((o) => (
              <LinhaDaOcorrencia key={o.id} o={o} agir={(acao) => agirNaOcorrencia(o, acao)} />
            ))}
          </div>
        )}
        {prevs.length > 0 && (
          <div className="fc-cartao mb-3 border-primary">
            <h2 className="h6 fw-bold">Preventiva a fazer aqui</h2>
            {prevs.map((x) => (
              <div className="fc-app-item" key={x.id}>
                <div className="d-flex align-items-center gap-2">
                  <span className="fw-semibold">{x.titulo}</span>
                  {x.atrasada && <span className="badge fc-sit fc-sit-atrasada">Atrasada</span>}
                  {x.minha && <span className="badge text-bg-light">Sua</span>}
                </div>
                <span className="small text-muted">
                  {x.numero + ' · vence ' + x.vence + ' · ' + (dados.versoes[x.versao] || ({} as Versao)).modelo}
                </span>
                <button type="button" className="btn btn-primary fc-app-acao w-100 mt-2"
                  onClick={() => abrirExecucao(null, dados.versoes[x.versao], x)}>
                  <i className="bi bi-tools"></i> Fazer a preventiva
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="fc-cartao mb-3">
          <h2 className="h6 fw-bold">Tarefas deste ponto hoje</h2>
          {!doPonto.length && <p className="small text-muted mb-0">Nenhuma tarefa de rota aqui hoje.</p>}
          {doPonto.map((t) => {
            const s = r.situacao(t).cod;
            const aberta = s === 'prevista' || s === 'no_horario' || s === 'atrasada';
            return (
              <CartaoTarefa key={t.id} t={t} dados={dados} r={r}>
                {aberta && (
                  <div className="d-flex gap-2 mt-2">
                    {r.podeFazer(t) ? (
                      <button type="button" className="btn btn-primary fc-app-acao flex-grow-1"
                        onClick={() => abrirExecucao(t, dados.versoes[t.versao])}>Fazer agora</button>
                    ) : s === 'prevista' && (t.minha || !t.escalado) ? (
                      // Adiantar (27/10/2026): pergunta o motivo e abre o checklist.
                      <button type="button" className="btn btn-outline-primary fc-app-acao flex-grow-1"
                        data-adiantar={t.id} onClick={() => setFolhaTroca({
                          titulo: 'Adiantar: ' + t.ambiente + ' das ' + t.hora,
                          devolver: (troca) => { if (troca) abrirExecucao(t, dados.versoes[t.versao], null, troca); },
                        })}>Adiantar esta área</button>
                    ) : (
                      <span className="small text-muted align-self-center flex-grow-1">
                        {'Pode ser feita a partir das ' + desdeQuando(t) + '.'}
                      </span>
                    )}
                    <button type="button" className="btn btn-outline-secondary fc-app-acao"
                      onClick={() => mostrar({ tipo: 'nao_realizada', t })}>Não realizada</button>
                  </div>
                )}
              </CartaoTarefa>
            );
          })}
        </div>
        {/* Área fora da rota (27/10/2026): o escopo da área (o checklist das
            rotas que passam por ela) abre direto, com o motivo da troca. */}
        {escopo.map((v) => (
          <button type="button" key={v.id} className="btn btn-outline-primary w-100 fc-app-acao mb-2"
            data-fora-da-rota={v.id} onClick={() => {
              const pendente = lerTroca(usuario);
              if (pendente) { abrirExecucao(null, v, null, pendente); return; }
              setFolhaTroca({ titulo: 'Limpar fora da rota: ' + p.nome,
                devolver: (troca) => { if (troca) abrirExecucao(null, v, null, troca); } });
            }}>
            <i className="bi bi-plus-circle"></i>
            {' Limpar esta área fora da rota' + (escopo.length > 1 ? ' (' + v.modelo + ')' : '')}
          </button>
        ))}
        {extras.length > 0 && (
          <AtividadeExtra extras={extras} fazer={(v) => abrirExecucao(null, v, null, lerTroca(usuario))} />
        )}
        <button type="button" className="btn btn-outline-secondary w-100 fc-app-acao"
          onClick={() => { irPara('/app/turno?local=' + p.local_id, true); mostrarTurno(p.local_id); }}>
          Ver o turno
        </button>
      </>
    );
  }

  function desenharDepois(t: Extract<Tela, { tipo: 'depois' }>) {
    const resposta = t.resposta;
    const prox = t.prox;
    return (
      <>
        <div className="fc-cartao fc-pronto-feito text-center mb-3">
          <i className="bi bi-check-circle-fill fc-pronto-icone" aria-hidden="true"></i>
          <h1 className="fc-titulo">{'Pronto. ' + t.nome + ' feito às ' + t.h + '.'}</h1>
          {t.guardada && <p className="small text-muted mb-0">Guardada no aparelho: sobe sozinha quando o sinal voltar.</p>}
          {!t.guardada && resposta && (
            <>
              {resposta.situacao && !t.tarefa && <p className="small text-muted mb-0">{resposta.situacao + '.'}</p>}
              {!!resposta.nao_conformes && (
                <p className="small text-muted mb-0">
                  {resposta.nao_conformes + (resposta.nao_conformes > 1 ? ' itens com problema' : ' item com problema') +
                    ': a gestão foi avisada' +
                    (resposta.pedidos_insumo && resposta.pedidos_insumo.length ? ' e o material foi pedido' : '') + '.'}
                </p>
              )}
              {resposta.motivo_atraso && (
                <p className="small text-muted mb-0">{'Levou ' + resposta.duracao_min + ' min; o motivo ficou registrado.'}</p>
              )}
            </>
          )}
        </div>
        {prox ? (
          <div className="fc-cartao fc-proxima-tarefa">
            <div className="small fw-semibold text-muted">Próxima tarefa</div>
            <div className="fs-4 fw-bold">{prox.ambiente + ' · ' + prox.ponto_nome}</div>
            <div className="fc-sub">
              {(dados.versoes[prox.versao] || ({} as Versao)).modelo + ' às ' + prox.hora +
                (t.proxPode ? '' : ' (a partir das ' + desdeQuando(prox) + ')')}
            </div>
            <BotaoLerQr />
          </div>
        ) : (
          <div className="fc-cartao">
            <div className="fs-5 fw-bold">Nenhuma outra tarefa da rota por agora.</div>
            <button type="button" className="btn btn-outline-primary btn-lg w-100 fc-app-acao mt-2" onClick={() => {
              irPara('/app/turno' + (t.localId ? '?local=' + t.localId : ''), true);
              if (t.localId) mostrarTurno(t.localId); else mostrarLocais();
            }}>Ver o turno</button>
          </div>
        )}
      </>
    );
  }

  function desenharNoPonto(t: Tela) {
    switch (t.tipo) {
      case 'chegada':
        return (
          <div className="fc-cartao fc-chegada text-center">
            <i className="bi bi-door-open fc-chegada-icone" aria-hidden="true"></i>
            <h1 className="fc-titulo">Confirme a chegada</h1>
            <p className="fc-sub">{'Leia o QR da entrada do ' + t.nome + (t.entrada_nome ? ' (' + t.entrada_nome + ')' : '') + '.'}</p>
            <BotaoLerQr />
          </div>
        );
      case 'registrando':
        return <p className="fc-sub" role="status">Registrando a chegada…</p>;
      case 'ponto_desconhecido':
        return (
          <>
            <div className="alert alert-warning">
              Este QR não é de um ponto dos seus locais (ou foi desativado). Confira a etiqueta ou avise a gestão.
            </div>
            <button type="button" className="btn btn-outline-secondary w-100 fc-app-acao" onClick={mostrarLocais}>
              Voltar ao meu turno
            </button>
          </>
        );
      case 'ponto':
        return desenharPonto(t.codigo);
      case 'atraso':
        return <TelaAtraso dados={dados} tela={t} />;
      case 'depois':
        return desenharDepois(t);
      default:
        return null;
    }
  }

  const voltarDoPonto = () => {
    const lt = leitura.current;
    if (lt && pontoDe(lt.ponto)) telaPonto(lt.ponto); else mostrarLocais();
  };
  const naExecucao = !!aberta && (tela?.tipo === 'execucao' || tela?.tipo === 'atraso');
  const naLista = !tela || NA_LISTA.includes(tela.tipo);
  return (
    <div id="turno-app" data-tela-pronta={tela ? 'turno' : undefined}>
      <div id="turno-aviso" role="status" ref={caixaDoAviso}>
        {aviso && <div className={'alert alert-' + aviso.tipo}>{aviso.texto}</div>}
      </div>
      <section id="turno-ponto" hidden={!tela || naLista || NA_EXECUCAO.includes(tela.tipo)}>
        {tela && desenharNoPonto(tela)}
      </section>
      <section id="turno-execucao" hidden={!tela || !NA_EXECUCAO.includes(tela.tipo)}>
        {naExecucao && (
          <Execucao key={aberta.chave} dados={dados} tarefa={aberta.tarefa} versao={aberta.versao} prev={aberta.prev}
            troca={aberta.troca} nome={aberta.p.nome} semSelo={aberta.semSelo} outras={aberta.outras}
            catalogo={() => catalogo(aberta.p.local_id)}
            voltar={() => (pontoDe(aberta.codigo) ? telaPonto(aberta.codigo) : mostrarLocais())}
            pronto={(envio, liberar) => enviar(aberta, envio, liberar)} />
        )}
        {tela?.tipo === 'nao_realizada' && (
          <NaoRealizada t={tela.t} dados={dados} dizer={dizer} cancelar={voltarDoPonto}
            registrada={(chamadoId) => {
              dizer('Registrado como não realizada.' + (chamadoId ? ' Chamado aberto.' : ''), 'success');
              voltarDoPonto();
            }} />
        )}
      </section>
      <section id="turno-lista" hidden={!naLista}>
        {!tela && (
          <>
            <h1 className="fc-titulo">Meu turno</h1>
            <p className="fc-sub">Carregando…</p>
          </>
        )}
        {tela?.tipo === 'locais' && desenharLocais()}
        {tela?.tipo === 'turno' && desenharTurno(tela)}
      </section>
      {folhaTroca && (
        <FolhaTroca titulo={folhaTroca.titulo} dados={dados} devolver={(troca) => {
          const { devolver } = folhaTroca;
          setFolhaTroca(null);
          devolver(troca);
        }} />
      )}
    </div>
  );
}
