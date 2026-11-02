// As chaves da integração com o Trino Intelligence (Fase 4c; a tela antiga é
// templates/integracao/chaves.html, com os mesmos textos, campos e classes).
// Só o administrador. Os envios vão ao mesmo caminho da antiga abaixo de
// /api/v1 e chamam a mesma ação (integracao.telas.acao_criar e
// acao_revogar).
//
// A chave nova aparece UMA vez, como na antiga: o texto vem só na resposta
// do envio que a cria e fica só na memória desta tela (o estado do
// componente) — nunca no endereço, no histórico do navegador, na cópia dos
// dados (react-query), no armazenamento do aparelho nem no console. Sair da
// tela (ou qualquer navegação, como o "Revogar") a esquece.
import { useState } from 'react';
import { RecadosDoEnvio, enviar, useFormulario, useIr } from '../cadastros/comum';
import { Recados } from '../passagem/Recados';
import type { ChaveNova, DadosDaIntegracao } from './tipos';

const API = '/api/v1/admin/integracao';

export function Integracao({ dados, nova, aoCriar }: {
  dados: DadosDaIntegracao; nova: ChaveNova | null; aoCriar: (c: ChaveNova) => void;
}) {
  const { submeter, ocupado: revogando, aviso } = useFormulario();
  const ir = useIr();
  const [criando, setCriando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const criar = (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    if (criando) return;
    const form = ev.currentTarget;
    setCriando(true);
    setErro(null);
    enviar(`${API}/`, new FormData(form)).then(({ ok, dados: r }) => {
      setCriando(false);
      const chave = (r as { chave?: ChaveNova }).chave;
      if (ok && chave) {
        form.reset();
        const detalhes = form.closest('details');
        if (detalhes) detalhes.open = false;
        aoCriar({ nome: chave.nome, texto: chave.texto });
        window.scrollTo(0, 0);
        return;
      }
      // A recusa: o recado e a volta à tela, como o redirecionamento da antiga.
      if (r.destino) { ir(r.destino, r.recados); return; }
      setErro(r.error || 'Algo deu errado. Tente de novo.');
      window.scrollTo(0, 0);
    });
  };
  return (
    <div data-tela-pronta="integracao">
      <RecadosDoEnvio />{aviso}
      {erro && <Recados servidor={[{ tipo: 'danger', texto: erro }]} key={erro} />}
      <h1 className="fc-titulo">Integração com o Trino Intelligence</h1>
      <p className="fc-sub">Chaves de servidor da API só de leitura (<code>/api/integracao/v1</code>). Cada chave lê só os locais escolhidos; todo acesso fica registrado. O custo de material não sai pela API.</p>
      {nova && (
        <div className="alert alert-warning">
          <p className="fw-bold mb-1">Chave "{nova.nome}" criada. Copie agora: ela não aparece de novo.</p>
          <code className="d-block text-break user-select-all">{nova.texto}</code>
          <p className="small mb-0 mt-1">Guarde no cofre de segredos do Intelligence (variável de ambiente), nunca no código.</p>
        </div>
      )}
      <section className="fc-cartao mb-3" aria-labelledby="tit-ch">
        <h2 className="h6 fw-bold" id="tit-ch"><i className="bi bi-key"></i> Chaves</h2>
        {dados.chaves.length ? dados.chaves.map((c) => (
          <div className="d-flex flex-wrap gap-2 align-items-center border-top py-2" key={c.id}>
            <span className="fw-semibold">{c.nome}</span>
            <code className="small">{c.prefixo}</code>
            <span className="small text-muted">{c.locais} · criada {c.criada_em}{c.ultimo_uso_em && ` · último uso ${c.ultimo_uso_em}`}</span>
            {c.ativa ? (
              <form method="post" className="ms-auto" onSubmit={submeter(`${API}/${c.id}/revogar`)}>
                <button className="btn btn-outline-danger btn-sm" type="submit" disabled={revogando}>Revogar</button>
              </form>
            ) : <span className="badge text-bg-secondary ms-auto">revogada</span>}
          </div>
        )) : <p className="small text-muted">Nenhuma chave ainda.</p>}
        <details className="mt-2"><summary className="fw-semibold">Criar chave</summary>
          <form method="post" className="mt-2" onSubmit={criar} autoComplete="off">
            <label className="form-label small" htmlFor="kn">Nome</label>
            <input className="form-control mb-2" id="kn" name="nome" required maxLength={120} placeholder="Ex.: Trino Intelligence — produção" />
            <label className="d-flex gap-2 mb-2"><input type="checkbox" name="todos" value="1" /> Todos os locais (inclusive os cadastrados depois)</label>
            <fieldset><legend className="form-label small mb-1">Ou só estes locais</legend>
              <div className="d-flex flex-wrap gap-3">{dados.locais.map((l) => (
                <label className="d-flex gap-1" key={l.id}><input type="checkbox" name="client_id" value={l.id} /> {l.nome}</label>
              ))}</div>
            </fieldset>
            <button className="btn btn-primary fw-bold mt-2" type="submit" disabled={criando}>Criar chave</button>
          </form>
        </details>
      </section>
      <section className="fc-cartao p-0" aria-labelledby="tit-ac">
        <h2 className="h6 fw-bold px-3 pt-3" id="tit-ac"><i className="bi bi-clock-history"></i> Últimos acessos</h2>
        <div className="fc-mes-rolar"><table className="table table-sm mb-0">
          <thead><tr><th scope="col">Quando</th><th scope="col">Chave</th><th scope="col">Rota</th><th scope="col">Parâmetros</th><th scope="col">Resposta</th><th scope="col" className="text-end">Itens</th></tr></thead>
          <tbody>{dados.acessos.length ? dados.acessos.map((a) => (
            <tr key={a.id}><td className="text-nowrap small">{a.em}</td><td className="small">{a.chave}</td><td className="small">{a.rota}</td><td className="small">{a.parametros}</td><td className="small">{a.status}</td><td className="text-end small">{a.itens}</td></tr>
          )) : <tr><td colSpan={6} className="fc-vazio">Nenhum acesso ainda.</td></tr>}</tbody>
        </table></div>
      </section>
    </div>
  );
}
