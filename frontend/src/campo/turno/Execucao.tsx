// A execução: foto do antes → um check por item → foto do depois → Pronto.
// Item de marcar: toca → verde ("Feito"); com foto exigida, o check só fica
// verde com a foto. Número, texto, escolha e data continuam como campo
// (exceção). "Não deu" abre a folha dos motivos.
import { useRef, useState } from 'react';
import { FolhaNaoDeu, type Material } from './Folhas';
import { ehDeMarcar, faltantes, fraseDoQueFalta, respostaFeito, visivel } from './regras';
import type { DadosDoTurno, ItemDoChecklist, MotivoNaoDeu, Preventiva, Tarefa, Troca, Versao } from './tipos';

export type Envio = {
  respostas: Record<string, string>;
  motivos: Record<string, { motivo: string; texto: string | null; material_id: number | null }>;
  fotos: { campo: string; arquivo: File }[];
  observacao: string;
};

type Props = {
  dados: DadosDoTurno;
  tarefa: Tarefa | null;
  versao: Versao;
  prev: Preventiva | null;
  troca: Troca | null;
  nome: string;                    // o nome do ponto
  semSelo: boolean;                // aberto sem ler o QR com a câmera
  outras: number;                  // preventivas e avisos neste ponto
  catalogo: () => Promise<Material[]>;
  voltar: () => void;
  /** O "Pronto": ``liberar`` devolve o botão quando o envio não foi. */
  pronto: (envio: Envio, liberar: () => void) => void;
};

/** O botão grande de foto: um toque abre a câmera. */
function BlocoFoto({ chave, rotulo, foto, mudou }: {
  chave: string; rotulo: string; foto: File | null | undefined; mudou: (f: File | null) => void;
}) {
  const id = 'f_' + chave.replace(/[^a-z0-9]/gi, '_');
  return (
    <div className="fc-foto mb-3">
      <input type="file" accept="image/*" capture="environment" id={id} className="fc-foto-input" data-foto={chave}
        onChange={(e) => mudou(e.target.files && e.target.files.length ? e.target.files[0] : null)} />
      <label className={'btn btn-lg w-100 fc-app-acao fc-foto-botao ' + (foto ? 'btn-success' : 'btn-outline-primary')}
        htmlFor={id}>
        <i className={foto ? 'bi bi-check-circle-fill' : 'bi bi-camera'}></i>{' ' + (foto ? 'Foto pronta · trocar' : rotulo)}
      </label>
    </div>
  );
}

function LinhaDoItem({ it, dados, resposta, motivo, foto, oculto, responder, desmarcar, tirarMotivo, fotografar, naoDeu }: {
  it: ItemDoChecklist; dados: DadosDoTurno; resposta: string | undefined; motivo: MotivoNaoDeu | undefined;
  foto: File | null | undefined; oculto: boolean;
  /** A resposta do item (null: apagada) — tira o motivo do "Não deu". */
  responder: (r: string | null) => void;
  /** Desmarca o check: some a resposta e a foto do item. */
  desmarcar: () => void;
  tirarMotivo: () => void;
  fotografar: (f: File | null, marcar: boolean) => void;
  naoDeu: (limpar: () => void) => void;
}) {
  const [ajuda, setAjuda] = useState(false);
  const fotoEntrada = useRef<HTMLInputElement>(null);
  const campo = useRef<HTMLInputElement & HTMLSelectElement>(null);
  const marcar = ehDeMarcar(it);
  let classe = '';
  let marcado = '';
  if (resposta === 'nao_feito') {
    classe = ' fc-item-naodeu';
    const m = motivo || ({} as MotivoNaoDeu);
    marcado = 'Não deu: ' + (m.rotulo || dados.motivos_nao_feito[m.motivo] || '') +
              (m.texto && m.motivo === 'outro' ? ' — ' + m.texto : '') +
              (m.material_nome ? ' — ' + m.material_nome : '');
  } else if (resposta) {
    if (!it.exige_foto || foto) {
      classe = ' fc-item-feito';
      marcado = marcar ? 'Feito' : '';
    } else {
      marcado = 'Falta a foto';
    }
  }
  const feito = classe === ' fc-item-feito';
  const limparEntradas = () => {
    if (fotoEntrada.current) fotoEntrada.current.value = '';
    if (campo.current) campo.current.value = '';
  };
  const arquivo = (e: React.ChangeEvent<HTMLInputElement>) =>
    e.target.files && e.target.files.length ? e.target.files[0] : null;

  const topo = (
    <div className="fc-item-topo">
      {marcar && (
        <button type="button" className={'fc-check' + (feito ? ' fc-check-feito' : '')} aria-pressed={feito ? 'true' : 'false'}
          aria-label={'Feito: ' + it.texto} onClick={() => {
            if (feito) {
              if (fotoEntrada.current) fotoEntrada.current.value = '';
              desmarcar();
              return;
            }
            tirarMotivo();
            // O check só fica verde com a foto: um toque abre a câmera.
            if (it.exige_foto) { fotoEntrada.current?.click(); return; }
            responder(respostaFeito(it));
          }}>
          <i className={feito ? 'bi bi-check-lg' : 'bi bi-circle'} aria-hidden="true"></i>
        </button>
      )}
      <div className="fc-item-texto">
        <span>{it.texto}</span>
        <span className="fc-item-estado" aria-live="polite">{marcado}</span>
      </div>
      {(it.como_fazer || it.foto_ref_url) && (
        <button type="button" className="fc-item-info" aria-label={'Como fazer: ' + it.texto}
          aria-expanded={ajuda ? 'true' : 'false'} onClick={() => setAjuda(!ajuda)}>
          <i className="bi bi-info-circle" aria-hidden="true"></i>
        </button>
      )}
      <button type="button" className="btn btn-sm btn-outline-secondary fc-naodeu"
        onClick={() => naoDeu(limparEntradas)}>Não deu</button>
    </div>
  );

  let corpo = null;
  if (!marcar) {
    const nome = 'r_' + it.codigo;
    const digitou = (v: string) => responder(v.trim() ? v.trim() : null);
    let entrada;
    if (it.tipo === 'numero') {
      const faixa = (it.minimo !== null && it.minimo !== undefined ? 'de ' + it.minimo : '') +
                    (it.maximo !== null && it.maximo !== undefined ? ' até ' + it.maximo : '');
      entrada = <input className="form-control form-control-lg" name={nome} inputMode="decimal" aria-label={it.texto}
        placeholder={faixa ? 'Aceitável: ' + faixa.trim() : ''} ref={campo} onChange={(e) => digitou(e.target.value)} />;
    } else if (it.tipo === 'escolha') {
      entrada = (
        <select className="form-select form-select-lg" name={nome} aria-label={it.texto} ref={campo}
          defaultValue="" onChange={(e) => digitou(e.target.value)}>
          <option value="">Escolha</option>
          {(it.opcoes || []).map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      );
    } else if (it.tipo === 'data_hora') {
      entrada = <input type="datetime-local" className="form-control form-control-lg" name={nome} aria-label={it.texto}
        ref={campo} onChange={(e) => digitou(e.target.value)} />;
    } else {
      entrada = <input className="form-control form-control-lg" name={nome} maxLength={300} aria-label={it.texto}
        ref={campo} onChange={(e) => digitou(e.target.value)} />;
    }
    corpo = (
      <div className="fc-item-campo">
        {entrada}
        {it.exige_foto && (
          <>
            <input type="file" accept="image/*" capture="environment" className="fc-foto-input"
              data-foto={'item:' + it.codigo} id={'f_item_' + it.codigo} ref={fotoEntrada}
              onChange={(e) => fotografar(arquivo(e), false)} />
            <label className={'btn fc-app-acao w-100 mt-2 ' + (foto ? 'btn-success' : 'btn-outline-primary')}
              htmlFor={'f_item_' + it.codigo}>
              <i className="bi bi-camera"></i> Foto deste item
            </label>
          </>
        )}
      </div>
    );
  }

  return (
    <div className={'fc-item' + classe} data-codigo={it.codigo} hidden={oculto}>
      {marcar && it.exige_foto && (
        <input type="file" accept="image/*" capture="environment" className="fc-foto-input"
          data-foto={'item:' + it.codigo} id={'f_item_' + it.codigo} aria-label={'Foto: ' + it.texto}
          ref={fotoEntrada} onChange={(e) => fotografar(arquivo(e), true)} />
      )}
      {topo}
      {(it.como_fazer || it.foto_ref_url) && (
        <div className="fc-item-ajuda" hidden={!ajuda}>
          {it.como_fazer && <div className="small fc-como-fazer">{it.como_fazer}</div>}
          {it.foto_ref_url && <img className="fc-ref" src={it.foto_ref_url} loading="lazy" alt={'Como deve ficar: ' + it.texto} />}
        </div>
      )}
      {corpo}
    </div>
  );
}

export function Execucao(props: Props) {
  const { dados, tarefa, versao, prev, troca } = props;
  const [respostas, setRespostas] = useState<Record<string, string>>({});
  const [motivos, setMotivos] = useState<Record<string, MotivoNaoDeu>>({});
  const [fotos, setFotos] = useState<Record<string, File | null>>({});
  const [enviando, setEnviando] = useState(false);
  const [folha, setFolha] = useState<{ it: ItemDoChecklist; limpar: () => void } | null>(null);
  const obs = useRef<HTMLTextAreaElement>(null);

  const faltam = faltantes(versao, { respostas, fotos });
  let passo = 0;
  const titulo = (texto: string) => { passo += 1; return <h2 className="fc-exec-passo">{passo + '. ' + texto}</h2>; };

  const sem = <T,>(o: Record<string, T>, k: string) => { const n = { ...o }; delete n[k]; return n; };
  const responder = (codigo: string, r: string | null) => {
    if (r === null) { setRespostas((x) => sem(x, codigo)); return; }
    setRespostas((x) => ({ ...x, [codigo]: r }));
    setMotivos((m) => sem(m, codigo));
  };

  const enviar = (ev: React.FormEvent) => {
    ev.preventDefault();
    if (faltam.length) return;
    setEnviando(true);
    const r: Envio['respostas'] = {};
    const m: Envio['motivos'] = {};
    versao.itens.forEach((it) => {
      if (!visivel(it, respostas)) return;      // a condição não se cumpriu: não vai
      const v = respostas[it.codigo];
      if (v === undefined || v === null || v === '') return;
      r[it.codigo] = v;
      if (v === 'nao_feito') {
        const x = motivos[it.codigo] || ({} as MotivoNaoDeu);
        m[it.codigo] = { motivo: x.motivo, texto: x.texto || null, material_id: x.material_id || null };
      }
    });
    const lista = Object.keys(fotos).filter((k) => fotos[k]).map((k) => ({ campo: k, arquivo: fotos[k] as File }));
    props.pronto({ respostas: r, motivos: m, fotos: lista, observacao: obs.current?.value || '' },
                 () => setEnviando(false));
  };

  const docs = versao.documentos || [];
  return (
    <>
      <h1 className="fc-titulo">{props.nome}</h1>
      <p className="fc-sub fc-exec-sub">
        {versao.modelo + (tarefa ? ' das ' + tarefa.hora : prev ? ' · preventiva ' + prev.numero : ' · fora da rota') +
          (troca ? ' · ' + (tarefa ? 'adiantada' : 'motivo') + ': ' + troca.rotulo : '') +
          (tarefa && tarefa.tempo_previsto_min ? ' · Previsto: ' + tarefa.tempo_previsto_min + ' min' : '')}
      </p>
      {props.semSelo && (
        <p className="small text-muted fc-exec-sem-selo">Aberto sem ler o QR com a câmera: fica com a hora do celular.</p>
      )}
      <form noValidate className="fc-exec" onSubmit={enviar}>
        {versao.foto_antes && titulo('Foto do antes')}
        {versao.foto_antes && (
          <BlocoFoto chave="antes" rotulo="Tirar a foto do antes" foto={fotos.antes}
            mudou={(f) => setFotos((x) => ({ ...x, antes: f }))} />
        )}
        {titulo(versao.foto_antes || versao.foto_depois ? 'O que fazer' : 'Checklist')}
        <div className="fc-itens">
          {versao.itens.map((it) => (
            <LinhaDoItem key={it.codigo} it={it} dados={dados} resposta={respostas[it.codigo]}
              motivo={motivos[it.codigo]} foto={fotos['item:' + it.codigo]} oculto={!visivel(it, respostas)}
              responder={(r) => responder(it.codigo, r)}
              desmarcar={() => {
                setRespostas((x) => sem(x, it.codigo));
                setFotos((f) => sem(f, 'item:' + it.codigo));
              }}
              tirarMotivo={() => setMotivos((m) => sem(m, it.codigo))}
              fotografar={(f, marcar) => {
                setFotos((x) => ({ ...x, ['item:' + it.codigo]: f }));
                if (marcar && f) setRespostas((x) => ({ ...x, [it.codigo]: respostaFeito(it) }));
              }}
              naoDeu={(limpar) => setFolha({ it, limpar })} />
          ))}
        </div>
        {versao.foto_depois && titulo('Foto do depois')}
        {versao.foto_depois && (
          <BlocoFoto chave="depois" rotulo="Tirar a foto do depois" foto={fotos.depois}
            mudou={(f) => setFotos((x) => ({ ...x, depois: f }))} />
        )}
        <details className="fc-exec-obs mb-3">
          <summary className="small fw-semibold">Quer anotar algo? (opcional)</summary>
          <textarea className="form-control" id="obs" name="observacao" rows={2} aria-label="Observação" ref={obs}></textarea>
        </details>
        {(versao.procedimento || docs.length > 0) && (
          <details className="fc-exec-obs mb-3 fc-procedimento">
            <summary className="small fw-semibold">Ver o procedimento (POP)</summary>
            {versao.procedimento && <div className="mt-2 fc-texto-livre small">{versao.procedimento}</div>}
            {docs.length > 0 && (
              <div className="mt-2 d-flex flex-wrap gap-2">
                {docs.map((d) => (
                  <a key={d.url} className="btn btn-sm btn-outline-primary" href={d.url} target="_blank" rel="noopener">
                    {'Ver o POP completo: ' + d.nome}
                  </a>
                ))}
              </div>
            )}
          </details>
        )}
        <button type="submit" className="btn btn-success btn-lg w-100 fc-app-acao fc-pronto"
          disabled={enviando || faltam.length > 0}>
          <i className="bi bi-check-circle"></i> Pronto
        </button>
        <p className="small text-muted text-center mt-2 fc-faltam" role="status">{fraseDoQueFalta(faltam)}</p>
        <button type="button" className="btn btn-link w-100 mt-1" onClick={props.voltar}>
          {props.outras ? 'Outras coisas neste ponto (' + props.outras + ')' : 'Voltar'}
        </button>
      </form>
      {folha && (
        <FolhaNaoDeu it={folha.it} dados={dados} catalogo={props.catalogo} devolver={(motivo) => {
          const { it, limpar } = folha;
          setFolha(null);
          if (!motivo) return;
          setMotivos((m) => ({ ...m, [it.codigo]: motivo }));
          setRespostas((x) => ({ ...x, [it.codigo]: 'nao_feito' }));
          setFotos((f) => sem(f, 'item:' + it.codigo));
          limpar();
        }} />
      )}
    </>
  );
}
