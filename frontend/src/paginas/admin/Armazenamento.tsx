// A tela "Armazenamento de fotos" (só do administrador): quanto as fotos
// ocupam, o que passou do prazo e o arquivamento. Os números e as regras vêm
// do servidor (facilities/arquivo_fotos/servico.py); aqui só se mostra e envia.
import { type FormEvent, useState } from 'react';
import { barras, diasValidos, fotos, porQueNaoComeca, progresso, resumoDoPrazo, tamanho } from './regras';
import type { Lote, PainelDoArmazenamento } from './tipos';

type Props = {
  dados: PainelDoArmazenamento;
  salvarDias: (dias: number) => Promise<unknown>;
  arquivar: () => Promise<unknown>;
};

export function Armazenamento({ dados, salvarDias, arquivar }: Props) {
  const d = dados;
  return (
    <section data-tela-pronta="armazenamento">
      <h1 className="h4 mb-1">Armazenamento de fotos</h1>
      <p className="text-muted mb-4">
        As fotos são o que mais cresce no sistema. As antigas podem sair do armazenamento do dia a
        dia para um arquivo: elas continuam abrindo em todas as telas, só mudam de lugar.
      </p>

      <div className="row g-3 mb-4">
        <Numero titulo="Guardado ao todo" valor={tamanho(d.total.bytes)} detalhe={fotos(d.total.fotos)} />
        <Numero titulo="No armazenamento do dia a dia" valor={tamanho(d.no_principal_bytes)}
          detalhe="o que ainda ocupa espaço" />
        <Numero titulo="Já no arquivo" valor={tamanho(d.arquivadas.bytes)} detalhe={fotos(d.arquivadas.fotos)} />
        <Numero titulo={`Com mais de ${d.dias} dias`} valor={tamanho(d.pendentes.bytes)}
          detalhe={d.pendentes.fotos ? `${fotos(d.pendentes.fotos)} para arquivar` : 'nada para arquivar'} />
      </div>
      {d.total.sem_tamanho > 0 && (
        <p className="small text-muted">
          {fotos(d.total.sem_tamanho)} (avisos do público e pedidos de material) não têm o tamanho
          anotado e ficam fora das somas.
        </p>
      )}

      <Destino destino={d.destino} arquivadas={d.arquivadas.fotos} />
      <Arquivar dados={d} salvarDias={salvarDias} arquivar={arquivar} />
      {d.em_andamento && <EmAndamento lote={d.em_andamento} />}

      <div className="row g-3 mb-4">
        <div className="col-12 col-lg-7">
          <PorMes meses={d.por_mes} />
        </div>
        <div className="col-12 col-lg-5">
          <Locais locais={d.locais} />
        </div>
      </div>

      <Historico lotes={d.lotes} />
    </section>
  );
}

function Numero({ titulo, valor, detalhe }: { titulo: string; valor: string; detalhe: string }) {
  return (
    <div className="col-6 col-lg-3">
      <div className="card h-100">
        <div className="card-body">
          <div className="small text-muted">{titulo}</div>
          <div className="fs-4 fw-semibold">{valor}</div>
          <div className="small text-muted">{detalhe}</div>
        </div>
      </div>
    </div>
  );
}

function Destino({ destino, arquivadas }: { destino: PainelDoArmazenamento['destino']; arquivadas: number }) {
  if (!destino.disponivel) {
    return (
      <div className="alert alert-warning" role="status">
        <p className="fw-semibold mb-1">O arquivo ainda não está ligado neste servidor.</p>
        {destino.problema && <p className="mb-1">{destino.problema}</p>}
        <p className="mb-1">
          O lugar do arquivo não se escolhe nesta tela (por segurança): quem cuida do servidor
          define nas variáveis de ambiente um bucket do Cloudflare R2 separado
          (<code>ARQUIVO_R2_ENDPOINT</code>, <code>ARQUIVO_R2_ACCESS_KEY_ID</code>,{' '}
          <code>ARQUIVO_R2_SECRET_ACCESS_KEY</code>, <code>ARQUIVO_R2_BUCKET</code>) ou, só para
          testar, uma pasta (<code>ARQUIVO_FOTOS_PASTA</code>). O passo a passo está em{' '}
          <code>docs/ARQUIVO_FOTOS.md</code>.
        </p>
        {arquivadas > 0 && (
          <p className="mb-0 fw-semibold">
            Atenção: {fotos(arquivadas)} já estão no arquivo e não abrem enquanto ele estiver
            desligado.
          </p>
        )}
      </div>
    );
  }
  return (
    <div className="card mb-4">
      <div className="card-body">
        <h2 className="h6 mb-1">Para onde vão as fotos antigas</h2>
        <p className="mb-0">{destino.rotulo}</p>
        {destino.tipo === 'pasta' && (
          <p className={`mb-0 mt-2 ${destino.mesmo_disco ? 'alert alert-warning' : 'small text-muted'}`}>
            {destino.mesmo_disco
              ? 'Esta pasta fica no mesmo disco das fotos: arquivar aqui não libera espaço nenhum. Serve só para testar o caminho. Para liberar espaço de verdade, use um bucket do R2.'
              : 'Uma pasta do servidor serve para testar o caminho. Para liberar espaço de verdade, use um bucket do R2.'}
          </p>
        )}
      </div>
    </div>
  );
}

function Arquivar({ dados, salvarDias, arquivar }: Props) {
  const d = dados;
  const [dias, setDias] = useState(String(d.dias));
  const [confirmando, setConfirmando] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [recado, setRecado] = useState<{ tipo: 'success' | 'danger'; texto: string } | null>(null);
  const bloqueio = porQueNaoComeca(d);

  async function enviar<T>(acao: () => Promise<T>, ok: string) {
    setOcupado(true);
    setRecado(null);
    try {
      await acao();
      setRecado({ tipo: 'success', texto: ok });
      return true;
    } catch (e) {
      setRecado({ tipo: 'danger', texto: (e as Error).message });
      return false;
    } finally {
      setOcupado(false);
    }
  }

  async function aoSalvar(ev: FormEvent) {
    ev.preventDefault();
    const n = diasValidos(dias, d.dias_min, d.dias_max);
    if (n === null) {
      setRecado({ tipo: 'danger', texto: `Escreva um número de ${d.dias_min} a ${d.dias_max}.` });
      return;
    }
    await enviar(() => salvarDias(n), 'Prazo salvo.');
  }

  async function aoConfirmar() {
    if (await enviar(arquivar, 'Arquivamento começou. Ele anda aos poucos, a cada 5 minutos.')) {
      setConfirmando(false);
    }
  }

  return (
    <div className="card mb-4">
      <div className="card-body">
        <h2 className="h6">Arquivar as fotos antigas</h2>
        <form className="d-flex flex-wrap align-items-end gap-2 mb-3" onSubmit={aoSalvar}>
          <div>
            <label className="form-label mb-1" htmlFor="arquivo-dias">Arquivar fotos com mais de</label>
            <div className="input-group">
              <input id="arquivo-dias" className="form-control" inputMode="numeric" value={dias}
                onChange={(ev) => setDias(ev.target.value)} aria-describedby="arquivo-dias-ajuda" />
              <span className="input-group-text">dias</span>
            </div>
          </div>
          <button className="btn btn-outline-secondary" type="submit" disabled={ocupado}>Salvar prazo</button>
        </form>
        <p className="small text-muted" id="arquivo-dias-ajuda">
          Hoje entram as fotos tiradas antes de {d.corte}: {resumoDoPrazo(d.pendentes)}.
        </p>

        {!confirmando ? (
          <>
            <button className="btn btn-primary" type="button" disabled={!!bloqueio || ocupado}
              onClick={() => setConfirmando(true)}>
              Arquivar {fotos(d.pendentes.fotos)}
            </button>
            {bloqueio && <p className="small text-muted mt-2 mb-0">{bloqueio}</p>}
          </>
        ) : (
          <div className="alert alert-info mb-0" role="alertdialog" aria-label="Confirmar o arquivamento">
            <p className="mb-2">
              Vão para o arquivo {resumoDoPrazo(d.pendentes)}. Cada foto é copiada, conferida e
              só então sai do armazenamento do dia a dia; as telas continuam mostrando todas. O
              trabalho anda aos poucos, a cada 5 minutos — pode fechar esta tela.
            </p>
            <div className="d-flex flex-wrap gap-2">
              <button className="btn btn-primary" type="button" disabled={ocupado} onClick={aoConfirmar}>
                Confirmar e começar
              </button>
              <button className="btn btn-outline-secondary" type="button" disabled={ocupado}
                onClick={() => setConfirmando(false)}>
                Cancelar
              </button>
            </div>
          </div>
        )}
        {recado && (
          <div className={`alert alert-${recado.tipo} mt-3 mb-0`} role={recado.tipo === 'danger' ? 'alert' : 'status'}>
            {recado.texto}
          </div>
        )}
      </div>
    </div>
  );
}

function EmAndamento({ lote }: { lote: Lote }) {
  const pct = lote.previstas ? Math.min(100, Math.round((lote.arquivadas / lote.previstas) * 100)) : 0;
  return (
    <div className="card mb-4">
      <div className="card-body">
        <h2 className="h6">Arquivamento em andamento</h2>
        <div className="progress mb-2" role="progressbar" aria-label="Fotos arquivadas"
          aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="progress-bar" style={{ width: `${pct}%` }}></div>
        </div>
        <p className="mb-1">{progresso(lote.arquivadas, lote.previstas)} · {tamanho(lote.bytes)}</p>
        <p className="small text-muted mb-0">
          {lote.ultima_rodada_em
            ? `Última rodada: ${lote.ultima_rodada_em}.`
            : 'Ainda não houve rodada. Se continuar assim depois de 10 minutos, confira se o serviço que roda o arquivo enxerga as fotos (docs/ARQUIVO_FOTOS.md).'}
        </p>
        {lote.ultimo_erro && <p className="small text-danger mt-2 mb-0">Último erro: {lote.ultimo_erro}</p>}
      </div>
    </div>
  );
}

function PorMes({ meses }: { meses: PainelDoArmazenamento['por_mes'] }) {
  const larguras = barras(meses);
  return (
    <div className="card h-100">
      <div className="card-body">
        <h2 className="h6">Fotos novas por mês</h2>
        <table className="table table-sm mb-0">
          <thead><tr><th scope="col">Mês</th><th scope="col">Fotos</th><th scope="col">Tamanho</th></tr></thead>
          <tbody>
            {meses.map((m, i) => (
              <tr key={m.mes}>
                <td>{m.mes}</td>
                <td className="text-nowrap">{m.fotos.toLocaleString('pt-BR')}</td>
                <td className="w-50">
                  <div className="d-flex align-items-center gap-2">
                    <div className="progress flex-grow-1" aria-hidden="true">
                      <div className="progress-bar" style={{ width: `${larguras[i]}%` }}></div>
                    </div>
                    <span className="small text-nowrap">{tamanho(m.bytes)}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Locais({ locais }: { locais: PainelDoArmazenamento['locais'] }) {
  return (
    <div className="card h-100">
      <div className="card-body">
        <h2 className="h6">Locais com mais fotos</h2>
        {locais.length === 0 ? (
          <p className="text-muted mb-0">Ainda não há fotos guardadas.</p>
        ) : (
          <table className="table table-sm mb-0">
            <tbody>
              {locais.map((l) => (
                <tr key={l.local}><td>{l.local}</td><td className="text-end text-nowrap">{tamanho(l.bytes)}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Historico({ lotes }: { lotes: Lote[] }) {
  return (
    <div className="card">
      <div className="card-body">
        <h2 className="h6">Arquivamentos feitos</h2>
        {lotes.length === 0 ? (
          <p className="text-muted mb-0">Nenhum arquivamento ainda.</p>
        ) : (
          <ul className="list-unstyled mb-0">
            {lotes.map((l) => (
              <li key={l.id} className="border-bottom py-2">
                <div className="fw-semibold">{l.iniciado_em} · {l.situacao_rotulo}</div>
                <div className="small">
                  {progresso(l.arquivadas, l.previstas)} · {tamanho(l.bytes)} · fotos de antes de {l.corte}
                  {l.quem && ` · por ${l.quem}`}
                </div>
                <div className="small text-muted">{l.destino}{l.concluido_em && ` · terminou em ${l.concluido_em}`}</div>
                {l.nao_arquivadas > 0 && (
                  <div className="small text-danger">
                    {fotos(l.nao_arquivadas)} não saíram e continuam no armazenamento do dia a dia.
                    {l.ultimo_erro && ` Último erro: ${l.ultimo_erro}`}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
