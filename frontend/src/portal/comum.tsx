// O que as telas do portal e as cobranças da equipe têm em comum (Fase 5):
// as abas da tela de cobranças, os filtros, os avisos pelo QR e a trilha
// (``templates/portal/_abas_cobrancas.html`` e ``_trilha.html``).
import { Ir } from '../cadastros/comum';
import type { AvisoPeloQr, Abas, Evento, Filtro } from './tipos';

export function AbasDasCobrancas({ abas, ativa }: { abas: Abas; ativa: 'cobrancas' | 'qr' }) {
  const aba = (nome: 'cobrancas' | 'qr', conteudo: React.ReactNode) => (
    <li className="nav-item"><Ir className={`nav-link ${ativa === nome ? 'active' : ''}`}
      aria-current={ativa === nome ? 'page' : undefined} href={abas[nome]}>{conteudo}</Ir></li>
  );
  return (
    <ul className="nav nav-tabs mb-3">
      {aba('cobrancas', 'Cobranças')}
      {aba('qr', <><i className="bi bi-qr-code" aria-hidden="true"></i> Avisos pelo QR</>)}
    </ul>
  );
}

export function Filtros({ filtros }: { filtros: Filtro[] }) {
  return (
    <div className="d-flex flex-wrap gap-2 mb-3">
      {filtros.map(([rotulo, url, ativo]) => (
        <Ir className={`btn btn-sm ${ativo ? 'btn-primary' : 'btn-outline-primary'}`} href={url} key={rotulo}>{rotulo}</Ir>
      ))}
    </div>
  );
}

/** A lista dos avisos pelo QR: o cliente vê o resolvido e a resolução; a
 * equipe, o "Fora do prazo", quem ficou com a tarefa e o link para o dia. */
export function AvisosPeloQr({ avisos }: { avisos: AvisoPeloQr[] }) {
  return (
    <div className="fc-cartao p-0">
      {avisos.length ? avisos.map((o) => {
        const dentro = (
          <>
            <span className={`badge fc-sit fc-ocor-${o.status}`}>{o.situacao}</span>
            {o.atrasada && <span className="badge fc-dem fc-dem-atrasada">Fora do prazo</span>}
            <span className="fw-semibold">{o.titulo}</span>
            <span className="small text-muted">{o.onde}{o.texto && ` · "${o.texto}"`}</span>
            <span className="small ms-auto">{o.quando}
              {o.resolvido && <> · resolvido {o.resolvido}{o.resolucao && `: ${o.resolucao}`}</>}
              {o.responsavel && ` · tarefa de ${o.responsavel}`}</span>
          </>
        );
        const classe = 'd-flex flex-wrap gap-2 align-items-center border-bottom px-3 py-2';
        return o.url
          ? <Ir className={`${classe} text-reset text-decoration-none`} href={o.url} key={o.id}>{dentro}</Ir>
          : <div className={classe} key={o.id}>{dentro}</div>;
      }) : <div className="fc-vazio">Nenhum aviso pelo QR aqui.</div>}
    </div>
  );
}

export function Trilha({ eventos }: { eventos: Evento[] }) {
  return (
    <>
      <h2 className="h5 fw-bold mt-4">Histórico</h2>
      <ol className="list-unstyled fc-cartao">
        {eventos.map((e, n) => (
          <li className={`${n ? 'border-top pt-2 ' : ''}pb-2`} key={e.id}>
            <div className="small text-muted">{e.quando} · {e.autor} · <span className="fw-semibold">{e.tipo}</span>{e.prazo && ` · prazo ${e.prazo}`}</div>
            {e.texto && <div className="fc-texto-livre">{e.texto}</div>}
          </li>
        ))}
      </ol>
    </>
  );
}
