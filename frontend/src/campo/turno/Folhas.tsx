// As folhas que sobem de baixo (a mesma .fc-folha da tela antiga): por que
// foi a outra área (troca de área, 27/10/2026) e por que um item "Não deu"
// ("Faltou material" abre o catálogo do local; "Outro" pede o texto).
import { type ReactNode, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { DadosDoTurno, ItemDoChecklist, MotivoNaoDeu, Troca } from './tipos';

export type Material = { id: number; nome: string; unidade?: string };

function Folha({ rotulo, children, focar }: { rotulo: string; children: ReactNode; focar?: boolean }) {
  const caixa = useRef<HTMLDivElement>(null);
  useEffect(() => {
    document.body.classList.add('fc-folha-aberta');
    if (focar) caixa.current?.querySelector('button')?.focus();
    return () => document.body.classList.remove('fc-folha-aberta');
  }, [focar]);
  return createPortal(
    <div className="fc-folha" role="dialog" aria-modal="true" aria-label={rotulo}>
      <div className="fc-folha-caixa" ref={caixa}>{children}</div>
    </div>,
    document.body,
  );
}

function ordem(vocab: Record<string, string>, lista?: string[]) {
  return lista || Object.keys(vocab || {});
}

/** O texto livre do "Outro" (e do material que não está na lista). */
function TextoLivre({ titulo, rotulo, erroTexto, confirmar, voltar }: {
  titulo: string; rotulo: string; erroTexto: string;
  confirmar: (texto: string) => void; voltar: () => void;
}) {
  const [texto, setTexto] = useState('');
  const [erro, setErro] = useState(false);
  return (
    <>
      <h2 className="h5 fw-bold">{titulo}</h2>
      <input className="form-control form-control-lg mb-2" maxLength={300} aria-label={rotulo}
        placeholder="Conte em poucas palavras" autoFocus value={texto} onChange={(e) => setTexto(e.target.value)} />
      <p className="small text-danger" hidden={!erro}>{erroTexto}</p>
      <button type="button" className="btn btn-primary btn-lg w-100 fc-app-acao mb-2" onClick={() => {
        if (!texto.trim()) { setErro(true); return; }
        confirmar(texto.trim());
      }}>Confirmar</button>
      <button type="button" className="btn btn-link w-100" onClick={voltar}>Voltar</button>
    </>
  );
}

/** devolver({motivo, texto, rotulo}) ou devolver(null) ao cancelar. */
export function FolhaTroca({ titulo, dados, devolver }: {
  titulo: string; dados: DadosDoTurno; devolver: (t: Troca | null) => void;
}) {
  const [outro, setOutro] = useState(false);
  return (
    <Folha rotulo={titulo}>
      {outro ? (
        <TextoLivre titulo={titulo} rotulo="Por que vai a outra área" erroTexto="Escreva o motivo."
          confirmar={(t) => devolver({ motivo: 'outro', texto: t, rotulo: t })} voltar={() => setOutro(false)} />
      ) : (
        <>
          <h2 className="h5 fw-bold">{titulo}</h2>
          <p className="small text-muted">Por que você vai a outra área agora?</p>
          {ordem(dados.motivos_troca, dados.motivos_troca_ordem).map((k) => (
            <button type="button" key={k} className="btn btn-outline-dark btn-lg w-100 fc-app-acao mb-2 fc-motivo"
              data-motivo-troca={k} onClick={() => {
                if (k === 'outro') { setOutro(true); return; }
                devolver({ motivo: k, rotulo: dados.motivos_troca[k] });
              }}>{dados.motivos_troca[k]}</button>
          ))}
          <button type="button" className="btn btn-link w-100" onClick={() => devolver(null)}>Cancelar</button>
        </>
      )}
    </Folha>
  );
}

function EscolherMaterial({ catalogo, rotulo, confirmar, voltar }: {
  catalogo: Promise<Material[]>; rotulo: string;
  confirmar: (m: MotivoNaoDeu) => void; voltar: () => void;
}) {
  const [lista, setLista] = useState<Material[] | null>(null);   // null: carregando
  const [escolha, setEscolha] = useState('');
  const [livre, setLivre] = useState('');
  const [erro, setErro] = useState(false);
  const sel = useRef<HTMLSelectElement>(null);
  useEffect(() => {
    let vivo = true;
    catalogo.then((l) => {
      if (!vivo) return;
      setLista(l || []);
      // Sem catálogo: só o texto livre.
      if (!l || !l.length) setEscolha('livre');
    });
    return () => { vivo = false; };
  }, [catalogo]);
  const vazio = lista !== null && !lista.length;
  return (
    <>
      <h2 className="h5 fw-bold">Faltou qual material?</h2>
      <select className="form-select form-select-lg mb-2" aria-label="Material" ref={sel} value={escolha}
        onChange={(e) => setEscolha(e.target.value)}>
        {lista === null && <option value="">Carregando o catálogo…</option>}
        {vazio && <option value="livre">Escrever o que faltou</option>}
        {lista !== null && !vazio && (
          <>
            <option value="">Escolha o material</option>
            {lista.map((m) => (
              <option key={m.id} value={m.id}>{m.nome + (m.unidade ? ' (' + m.unidade + ')' : '')}</option>
            ))}
            <option value="livre">Não está na lista / não sei</option>
          </>
        )}
      </select>
      <input className="form-control form-control-lg mb-2" maxLength={300} aria-label="Qual material"
        placeholder="Ou escreva o que faltou" hidden={escolha !== 'livre'} value={livre}
        onChange={(e) => setLivre(e.target.value)} />
      <p className="small text-danger" hidden={!erro}>Escolha o material ou escreva o que faltou.</p>
      <button type="button" className="btn btn-primary btn-lg w-100 fc-app-acao mb-2" onClick={() => {
        const m: MotivoNaoDeu = { motivo: 'faltou_material', rotulo };
        if (escolha && escolha !== 'livre') {
          m.material_id = parseInt(escolha, 10);
          m.material_nome = sel.current?.selectedOptions[0]?.textContent || '';
        } else if (livre.trim()) {
          m.texto = livre.trim();
          m.material_nome = m.texto;
        } else { setErro(true); return; }
        confirmar(m);
      }}>Confirmar</button>
      <button type="button" className="btn btn-link w-100" onClick={voltar}>Voltar</button>
    </>
  );
}

export function FolhaNaoDeu({ it, dados, catalogo, devolver }: {
  it: ItemDoChecklist; dados: DadosDoTurno; catalogo: () => Promise<Material[]>;
  devolver: (m: MotivoNaoDeu | null) => void;
}) {
  const [passo, setPasso] = useState<'inicio' | 'outro' | 'material'>('inicio');
  const [lista, setLista] = useState<Promise<Material[]> | null>(null);
  const vocab = dados.motivos_nao_feito;
  const titulo = 'Não deu: ' + it.texto;
  return (
    <Folha rotulo={titulo} focar>
      {passo === 'outro' && (
        <TextoLivre titulo={titulo} rotulo="O que aconteceu" erroTexto="Escreva o que aconteceu."
          confirmar={(t) => devolver({ motivo: 'outro', texto: t, rotulo: vocab.outro })}
          voltar={() => setPasso('inicio')} />
      )}
      {passo === 'material' && lista && (
        <EscolherMaterial catalogo={lista} rotulo={vocab.faltou_material} confirmar={devolver}
          voltar={() => setPasso('inicio')} />
      )}
      {passo === 'inicio' && (
        <>
          <h2 className="h5 fw-bold">{titulo}</h2>
          <p className="small text-muted">O que aconteceu?</p>
          {ordem(vocab, dados.motivos_nao_feito_ordem).map((k) => (
            <button type="button" key={k} className="btn btn-outline-dark btn-lg w-100 fc-app-acao mb-2 fc-motivo"
              data-motivo={k} onClick={() => {
                if (k === 'faltou_material') { setLista(catalogo()); setPasso('material'); return; }
                if (k === 'outro') { setPasso('outro'); return; }
                devolver({ motivo: k, rotulo: vocab[k] });
              }}>{vocab[k]}</button>
          ))}
          <button type="button" className="btn btn-link w-100" onClick={() => devolver(null)}>Cancelar</button>
        </>
      )}
    </Folha>
  );
}
