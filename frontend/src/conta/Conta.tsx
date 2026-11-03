// O Início da gestão, os avisos, a segurança da conta e a troca de senha
// (Fase 6a; as telas antigas são templates/core/inicio.html, avisos.html,
// seguranca.html e trocar_senha.html, com os mesmos textos, campos e
// classes). Os envios vão ao mesmo caminho da antiga abaixo de /api/v1 e
// chamam a mesma ação (core.rotas.acao_* e core.auth.acao_*).
//
// O segredo da segunda etapa (o texto e o QR) vem só na resposta do envio
// que o prepara (POST /api/v1/conta/seguranca/codigo-novo) e fica só no
// estado desta tela — nunca no endereço, no histórico do navegador, na cópia
// dos dados (react-query), no armazenamento do aparelho nem no console.
// Ativar, sair da tela ou qualquer navegação o esquece.
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { enviarBruto } from '../api';
import { Ir, RecadosDoEnvio, enviar, useFormulario, useIr } from '../cadastros/comum';
import { Recados } from '../passagem/Recados';
import type {
  CodigoNovo, DadosDaSeguranca, DadosDaTrocaDeSenha, DadosDoInicio, DadosDosAvisos,
} from './tipos';

const API = '/api/v1';

// ── O Início ──────────────────────────────────────────────────────────────

export function InicioDaGestao({ dados }: { dados: DadosDoInicio }) {
  const adm = dados.administrador;
  return (
    <div data-tela-pronta="inicio">
      <RecadosDoEnvio />
      <div className="fc-ola">
        <div>
          <h1 className="fc-titulo">Olá, {dados.primeiro_nome}</h1>
          <p className="fc-sub mb-0">{dados.data} · {dados.perfil}{dados.locais_na_carteira !== null && ` · ${dados.locais_na_carteira} local(is) na sua carteira`}</p>
        </div>
        {dados.abrir_chamado && <Ir className="btn btn-primary fw-bold" href={dados.abrir_chamado}><i className="bi bi-plus-lg" aria-hidden="true"></i> Abrir chamado</Ir>}
      </div>

      {dados.numeros.length > 0 && (
        <>
          <h2 className="fc-secao">O que espera você hoje</h2>
          <div className="fc-numeros">
            {dados.numeros.map((x) => (
              <Ir className={`fc-numero fc-numero-${x.tom}${x.n ? '' : ' zerado'}`} href={x.url} key={x.rotulo}>
                <i className={`bi ${x.icone}`} aria-hidden="true"></i>
                <span className="fc-numero-n">{x.n}</span>
                <span className="fc-numero-r">{x.rotulo}</span>
              </Ir>
            ))}
          </div>

          <section className="fc-cartao p-0 mt-3" aria-labelledby="tit-primeiro">
            <div className="d-flex align-items-center justify-content-between px-3 pt-3 pb-2">
              <h2 className="h6 fw-bold m-0" id="tit-primeiro">Para resolver primeiro</h2>
              <Ir className="small fw-semibold" href={dados.fila}>Ver a fila inteira <i className="bi bi-arrow-right" aria-hidden="true"></i></Ir>
            </div>
            {dados.primeiro.length ? dados.primeiro.map((i, n) => (
              <Ir className="fc-fila-item" href={i.link} key={n}>
                <span className={`badge fc-dem fc-dem-${i.situacao}`}>{i.situacao_rotulo}</span>
                <span className="fc-fila-tit"><span className="small text-muted">{i.tipo_rotulo}{i.numero && ` · ${i.numero}`}</span>{i.titulo}</span>
                <span className="small text-muted fc-fila-local">{i.local}</span>
                <span className="small fc-fila-prazo">{i.prazo}</span>
              </Ir>
            )) : (
              <div className="fc-vazio"><i className="bi bi-check2-circle fs-3 d-block mb-1 text-success" aria-hidden="true"></i>Nada esperando. Tudo em dia.</div>
            )}
          </section>
        </>
      )}

      {dados.atalhos.length > 0 ? (
        <>
          <h2 className="fc-secao">Atalhos</h2>
          <div className="fc-modulos">
            {dados.atalhos.map((m) => (
              <Ir className="fc-cartao fc-modulo" href={m.url} key={m.nome}>
                <i className={`bi ${m.icone}`} aria-hidden="true"></i>
                <h3>{m.nome}</h3>
                <p>{m.texto}</p>
              </Ir>
            ))}
          </div>
        </>
      ) : dados.numeros.length === 0 && (
        <div className="fc-cartao fc-vazio">Seu perfil ainda não tem módulo liberado. Fale com o administrador.</div>
      )}

      {adm && (
        <div className="fc-cartao mt-3">
          <h2 className="h6 fw-bold mb-2">Primeiros passos do administrador</h2>
          <ol className="mb-0 small">
            <li>Cadastre a <Ir href={adm.empresas}>empresa do grupo</Ir>, o <Ir href={adm.clientes}>cliente</Ir> e ative os <Ir href={adm.estados}>estados</Ir> em uso.</li>
            <li>Cadastre os <Ir href={adm.locais}>locais</Ir> do cliente e, em cada um, a estrutura: setores, ambientes e pontos com QR.</li>
            <li>Cadastre as <Ir href={adm.pessoas}>pessoas</Ir> e vincule cada uma aos locais dela.</li>
            <li>Em cada local, configure a passagem de turno — ou use os modelos prontos de limpeza, portaria e manutenção.</li>
          </ol>
        </div>
      )}
    </div>
  );
}

// ── Os avisos ─────────────────────────────────────────────────────────────

export function Avisos({ dados }: { dados: DadosDosAvisos }) {
  const ir = useIr();
  const cliente = useQueryClient();
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  // Abrir um aviso (ou marcar todos) muda o número do sino da casca.
  const mandar = (url: string) => (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    if (ocupado) return;
    setOcupado(true);
    setErro(null);
    enviar(url, new FormData(ev.currentTarget)).then(({ dados: r }) => {
      setOcupado(false);
      cliente.invalidateQueries({ queryKey: ['eu'] });
      if (r.destino) { ir(r.destino, r.recados); return; }
      setErro(r.error || 'Algo deu errado. Tente de novo.');
    });
  };
  return (
    <div data-tela-pronta="avisos">
      <RecadosDoEnvio />
      {erro && <Recados servidor={[{ tipo: 'danger', texto: erro }]} key={erro} />}
      <div className="d-flex align-items-center justify-content-between flex-wrap gap-2 mb-2">
        <h1 className="fc-titulo">Avisos</h1>
        {dados.nao_lidos > 0 && (
          <form method="post" className="m-0" onSubmit={mandar(`${API}/avisos/ler-todos`)}>
            <button className="btn btn-sm btn-outline-secondary" type="submit" disabled={ocupado}>Marcar todos como lidos</button>
          </form>
        )}
      </div>
      <div className="fc-cartao p-0">
        {dados.avisos.length ? dados.avisos.map((a) => (
          <form method="post" className="m-0" key={a.id} onSubmit={mandar(`${API}/avisos/${a.id}/abrir`)}>
            <button type="submit" disabled={ocupado}
              className={`fc-aviso w-100 text-start border-0 ${a.nao_lido ? 'nao-lido' : 'bg-transparent'}`}>
              <div className="flex-grow-1">
                <h3>{a.titulo}</h3>
                {a.mensagem && <p>{a.mensagem}</p>}
              </div>
              <time>{a.em}</time>
            </button>
          </form>
        )) : <div className="fc-vazio">Nenhum aviso por aqui.</div>}
      </div>
    </div>
  );
}

// ── A segurança da conta ──────────────────────────────────────────────────

/** Pede o segredo novo ao servidor (o mesmo da tela antiga, pendente até
 * ativar, nunca no cookie). Um pedido por abertura da tela: o StrictMode roda o
 * efeito duas vezes, e dois pedidos ao mesmo tempo, sem segredo pendente,
 * sorteariam dois segredos diferentes. O segredo vive só enquanto esta tela
 * está aberta: sair dela (ou o envio, que leva de volta a ela) o esquece. */
function useCodigoNovo(pedir: boolean) {
  const [novo, setNovo] = useState<CodigoNovo | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const pedido = useRef<Promise<CodigoNovo | null> | null>(null);
  useEffect(() => {
    if (!pedir) return;
    let vivo = true;
    if (!pedido.current) {
      pedido.current = enviarBruto(`${API}/conta/seguranca/codigo-novo`, {
        method: 'POST', headers: { Accept: 'application/json' }, cache: 'no-store',
      }).then(async (r) => {
        if (r.status === 401) {
          const volta = window.location.pathname + window.location.search;
          window.location.assign(`/login?next=${encodeURIComponent(volta)}`);
          return null;
        }
        const j = (await r.json().catch(() => null)) as { novo?: CodigoNovo | null; error?: string } | null;
        if (!r.ok || !j) throw new Error((j && j.error) || 'Algo deu errado. Tente de novo.');
        return j.novo || null;
      });
    }
    pedido.current.then((n) => { if (vivo) setNovo(n); }).catch((e: Error) => {
      if (vivo) setErro(e.message || 'Sem conexão com o servidor. Confira a internet e tente de novo.');
    });
    return () => { vivo = false; };
  }, [pedir]);
  return { novo, erro };
}

export function Seguranca({ dados }: { dados: DadosDaSeguranca }) {
  const { submeter, ocupado, aviso } = useFormulario();
  const { novo, erro } = useCodigoNovo(!dados.ativo);
  const pronta = dados.ativo || novo !== null || erro !== null;
  return (
    <div data-tela-pronta={pronta ? 'seguranca' : undefined}>
      <RecadosDoEnvio />{aviso}
      {erro && <Recados servidor={[{ tipo: 'danger', texto: erro }]} key={erro} />}
      <h1 className="fc-titulo">Segurança da conta</h1>
      <p className="fc-sub">A segunda etapa pede, além da senha, um código de 6 números que muda a cada 30 segundos no seu celular. Com ela, quem descobrir a sua senha ainda não entra.</p>

      <div className="fc-cartao fc-estreito">
        {dados.ativo ? (
          <>
            <p className="fw-semibold text-success"><i className="bi bi-shield-check"></i> Segunda etapa ativada.</p>
            <p className="small">Para desligar, confirme a sua senha.</p>
            <form method="post" onSubmit={submeter(`${API}/conta/seguranca/desativar`)}>
              <label className="form-label small fw-semibold" htmlFor="senha">Sua senha atual</label>
              <input className="form-control mb-3" id="senha" name="senha" type="password" autoComplete="current-password" required />
              <button className="btn btn-outline-danger fw-bold" type="submit" disabled={ocupado}>Desativar a segunda etapa</button>
            </form>
          </>
        ) : (
          <>
            <ol className="small">
              <li>Instale no celular um aplicativo autenticador (Google Authenticator, Microsoft Authenticator ou outro).</li>
              <li>No aplicativo, escolha "adicionar conta" e leia o QR abaixo.</li>
              <li>Digite o código que aparecer e confirme.</li>
            </ol>
            {novo ? (
              <>
                <div className="fc-qr-totp" role="img" aria-label="QR para o aplicativo autenticador">
                  <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(novo.qr)}`} alt="" width={200} height={200} />
                </div>
                <p className="small text-muted">Sem câmera? Digite no aplicativo esta chave: <code className="user-select-all">{novo.segredo}</code></p>
              </>
            ) : !erro && <p className="small text-muted" role="status">Carregando…</p>}
            <form method="post" onSubmit={submeter(`${API}/conta/seguranca/ativar`)} autoComplete="off">
              <label className="form-label small fw-semibold" htmlFor="codigo">Código do aplicativo</label>
              <input className="form-control mb-3 fs-4 text-center" id="codigo" name="codigo" inputMode="numeric" pattern="[0-9 ]*" maxLength={7} autoComplete="one-time-code" required />
              <label className="form-label small fw-semibold" htmlFor="senha">Sua senha atual</label>
              <input className="form-control mb-1" id="senha" name="senha" type="password" autoComplete="current-password" required />
              <p className="form-text mb-3">A mesma senha que você usa para entrar. Ela confirma que é você mesmo quem está ligando a segunda etapa.</p>
              <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado || !novo}>Ativar a segunda etapa</button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

// ── Trocar a senha ────────────────────────────────────────────────────────

export function TrocarSenha({ dados }: { dados: DadosDaTrocaDeSenha }) {
  const ir = useIr();
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const enviarSenha = (ev: React.FormEvent<HTMLFormElement>) => {
    ev.preventDefault();
    if (ocupado) return;
    const form = ev.currentTarget;
    setOcupado(true);
    setErro(null);
    enviar(`${API}/trocar-senha`, new FormData(form)).then(({ dados: r }) => {
      setOcupado(false);
      // Como a antiga, que desenha a página de novo: os campos voltam vazios.
      form.reset();
      if (r.destino) { ir(r.destino, r.recados); return; }
      setErro(r.error || 'Algo deu errado. Tente de novo.');
      window.scrollTo(0, 0);
    });
  };
  return (
    <div className="fc-cartao fc-estreito" data-tela-pronta="trocar-senha">
      <RecadosDoEnvio />
      {erro && <Recados servidor={[{ tipo: 'danger', texto: erro }]} key={erro} />}
      <h1 className="fc-titulo">Trocar senha</h1>
      {dados.primeiro_acesso
        ? <p className="fc-sub">Este é o seu primeiro acesso (ou a senha foi redefinida). Escolha uma senha só sua para continuar.</p>
        : <p className="fc-sub">A senha nova vale em todos os aparelhos; os outros acessos abertos serão encerrados.</p>}
      <form method="post" onSubmit={enviarSenha}>
        <label className="form-label small fw-semibold" htmlFor="atual">Senha atual</label>
        <input className="form-control mb-3" id="atual" name="atual" type="password" autoComplete="current-password" required />
        <label className="form-label small fw-semibold" htmlFor="nova">Senha nova (mínimo {dados.minimo} caracteres)</label>
        <input className="form-control mb-3" id="nova" name="nova" type="password" minLength={dados.minimo} autoComplete="new-password" required />
        <label className="form-label small fw-semibold" htmlFor="confirma">Repita a senha nova</label>
        <input className="form-control mb-3" id="confirma" name="confirma" type="password" minLength={dados.minimo} autoComplete="new-password" required />
        <button className="btn btn-primary fw-bold" type="submit" disabled={ocupado}>Salvar senha</button>
      </form>
    </div>
  );
}
