// A moldura do aplicativo de campo: topo curto, o selo "Sem sinal", a pessoa,
// a faixa do pedido de presença e a navegação embaixo, ao alcance do polegar.
// As mesmas classes da tela antiga (campo/base_app.html).
import { type ReactNode, useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router';
import type { Eu } from '../api';
import { useComSinal } from '../sinal';
import { Presenca } from './Presenca';

type Links = { ler_qr: string; site: string; instalar: string; passagem: string | null; chamados: string | null };

export function CascaCampo({ eu, links, children }: { eu: Eu; links: Links | null; children: ReactNode }) {
  const comSinal = useComSinal();
  const [menu, setMenu] = useState(false);
  const local = useLocation();

  // O corpo com a cara de app (a tela antiga usa a mesma classe).
  useEffect(() => {
    document.body.classList.remove('fc-com-menu');
    document.body.classList.add('fc-app');
    return () => {
      document.body.classList.remove('fc-app');
      document.body.classList.add('fc-com-menu');
    };
  }, []);

  const noInicio = local.pathname === '/app' || local.pathname === '/app/';

  return (
    <>
      <header className="fc-app-topo">
        <Link className="fc-marca" to="/app">
          <img src="/static/pwa/icone-192.png" alt="" />
          <span>Facilities <small>Campo</small></span>
        </Link>
        {!comSinal && (
          <span className="fc-app-rede" role="status"><i className="bi bi-wifi-off" aria-hidden="true"></i> Sem sinal</span>
        )}
        <div className="dropdown ms-auto">
          <button className="fc-app-pessoa dropdown-toggle" type="button" aria-expanded={menu}
            onClick={() => setMenu(!menu)}>
            <i className="bi bi-person-circle" aria-hidden="true"></i> {eu.primeiro_nome}
          </button>
          <ul className={`dropdown-menu dropdown-menu-end${menu ? ' show' : ''}`}>
            <li><span className="dropdown-item-text small text-muted">{eu.nome}<br />{eu.perfil}</span></li>
            <li><hr className="dropdown-divider" /></li>
            {links && <li><a className="dropdown-item" href={links.site}><i className="bi bi-display"></i> Abrir o site</a></li>}
            {links && <li><a className="dropdown-item" href={links.instalar}><i className="bi bi-phone"></i> Instalar no celular</a></li>}
            <li><a className="dropdown-item" href={eu.links.trocar_senha}><i className="bi bi-key"></i> Trocar senha</a></li>
            <li><hr className="dropdown-divider" /></li>
            <li>
              <form method="post" action={eu.links.sair} className="m-0">
                <input type="hidden" name="csrf_token" value={eu.csrf} />
                <button className="dropdown-item" type="submit"><i className="bi bi-arrow-left-right"></i> Sair / trocar de pessoa</button>
              </form>
            </li>
          </ul>
        </div>
      </header>

      <main className="fc-conteudo" id="conteudo">{children}</main>

      <Presenca />
      <nav className="fc-app-nav" aria-label="Aplicativo de campo">
        <Link to="/app" className={noInicio ? 'ativo' : undefined} aria-current={noInicio ? 'page' : undefined}>
          <i className="bi bi-house" aria-hidden="true"></i><span>Início</span>
        </Link>
        {links && <a href={links.ler_qr}><i className="bi bi-qr-code-scan" aria-hidden="true"></i><span>Ler QR</span></a>}
        {links?.passagem && <a href={links.passagem}><i className="bi bi-journal-check" aria-hidden="true"></i><span>Passagem</span></a>}
        {links?.chamados && <a href={links.chamados}><i className="bi bi-tools" aria-hidden="true"></i><span>Chamados</span></a>}
      </nav>
    </>
  );
}
