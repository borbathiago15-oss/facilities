// O que as telas da Fase 1d do aplicativo de campo têm em comum: a página na
// moldura do campo (a navegação embaixo), uma busca por abertura (depois de
// cada envio a tela se refaz, como a antiga depois do redirecionamento) e os
// recados do envio no topo.
//
// Sem cópia no aparelho, como as antigas (o service worker não guarda estas
// telas): sem sinal, a busca diz "Sem conexão" e o envio não sai — o que a
// pessoa preencheu continua na tela.
import { type ReactNode, useState } from 'react';
import type { Eu } from '../../api';
import { RecadosDoEnvio, enviar, useDados, useIr } from '../../cadastros/comum';
import { Recados } from '../../passagem/Recados';
import { CascaCampo } from '../CascaCampo';
import type { LinksDoCampo } from '../tipos';

export function PaginaDoCampo<T extends { links: LinksDoCampo }>({ eu, api, titulo, children }: {
  eu: Eu; api: string; titulo: string; children: (dados: T) => ReactNode;
}) {
  const q = useDados<T>(api);
  return (
    <CascaCampo eu={eu} links={q.data?.links ?? null}>
      {q.isPending && (
        <>
          <h1 className="fc-titulo">{titulo}</h1>
          <p className="fc-sub" role="status">Carregando…</p>
        </>
      )}
      {q.isError && (
        <div className="fc-cartao" role="alert">
          <p>{q.error.message}</p>
          <button className="btn btn-primary" type="button" onClick={() => q.refetch()}>Tentar de novo</button>
        </div>
      )}
      {q.data && (
        <>
          <RecadosDoEnvio />
          {children(q.data)}
        </>
      )}
    </CascaCampo>
  );
}

/** O envio das telas do campo: o corpo vai ao caminho da API e a tela vai ao
 * endereço de volta com o recado (como a antiga depois do POST). Sem endereço
 * (falta de sinal, erro do servidor), o recado aparece aqui e nada se perde. */
export function useEnvioDoCampo() {
  const ir = useIr();
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const mandar = (url: string, corpo: FormData) => {
    if (ocupado) return;
    setOcupado(true);
    setErro(null);
    enviar(url, corpo).then(({ dados }) => {
      setOcupado(false);
      if (dados.destino) { ir(dados.destino, dados.recados); return; }
      setErro(dados.error || 'Algo deu errado. Tente de novo.');
      window.scrollTo(0, 0);
    });
  };
  const aviso = erro ? <Recados servidor={[{ tipo: 'danger', texto: erro }]} key={erro} /> : null;
  return { mandar, ocupado, aviso };
}
