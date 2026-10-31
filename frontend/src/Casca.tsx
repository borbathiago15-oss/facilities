// A moldura de toda tela nova: o menu lateral (moldura preta, faixa de quatro
// cores) e a barra do topo — o mesmo desenho e as mesmas classes do site
// (facilities/templates/_menu.html). Quem vê cada item vem do servidor
// (facilities/core/menu.py), a mesma regra das telas antigas.
import { type ReactNode, useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router';
import type { Eu, ItemDoMenu } from './api';

const BASE = '/novo';

function Item({ item, ativo }: { item: ItemDoMenu; ativo: boolean }) {
  const conteudo = (
    <>
      <i className={`bi ${item.icone}`} aria-hidden="true"></i>
      <span>{item.rotulo}</span>
    </>
  );
  const classe = `fc-lat-item${ativo ? ' ativo' : ''}`;
  // Tela já migrada: navega sem recarregar. Tela antiga: abre normalmente.
  if (item.url.startsWith(`${BASE}/`)) {
    return (
      <Link className={classe} to={item.url.slice(BASE.length)} aria-current={ativo ? 'page' : undefined}>
        {conteudo}
      </Link>
    );
  }
  return (
    <a className={classe} href={item.url} aria-current={ativo ? 'page' : undefined}>
      {conteudo}
    </a>
  );
}

export function Casca({ eu, children }: { eu: Eu; children: ReactNode }) {
  const [aberto, setAberto] = useState(false);
  const local = useLocation();
  const botao = useRef<HTMLButtonElement>(null);
  const lateral = useRef<HTMLElement>(null);
  const aqui = BASE + (local.pathname === '/' ? '/' : local.pathname);

  // A gaveta do celular: a classe no <body> é a mesma do site (app.css).
  useEffect(() => {
    document.body.classList.toggle('fc-menu-aberto', aberto);
    if (aberto) {
      lateral.current?.querySelector<HTMLElement>('.fc-lat-item.ativo, .fc-lat-item')?.focus();
    }
  }, [aberto]);

  useEffect(() => {
    if (!aberto) return;
    const tecla = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') {
        setAberto(false);
        botao.current?.focus();
      }
    };
    document.addEventListener('keydown', tecla);
    return () => document.removeEventListener('keydown', tecla);
  }, [aberto]);

  useEffect(() => setAberto(false), [local.pathname]);

  const marca = eu.cliente ? 'Portal do cliente' : 'Grupo Trino';
  const avisos = eu.avisos_nao_lidos;

  return (
    <>
      <a className="fc-pular" href="#conteudo">Pular para o conteúdo</a>
      <aside className="fc-lateral" id="fc-lateral" aria-label="Menu do sistema" ref={lateral}
        onClick={(ev) => {
          if ((ev.target as HTMLElement).closest('.fc-lat-item')) setAberto(false);
        }}>
        <a className="fc-lat-marca" href={eu.links.inicio}>
          <img src="/static/pwa/icone-192.png" alt="" width={36} height={36} />
          <span><b>Trino</b> Facilities<small>{marca}</small></span>
        </a>
        <nav className="fc-lat-nav" aria-label="Módulos">
          {eu.menu.map((g, n) => {
            const itens = g.itens.map((i) => (
              <Item key={i.endpoint} item={i} ativo={i.url === aqui} />
            ));
            if (g.fixo) {
              return (
                <div className="fc-lat-grupo-fixo" key={n}>
                  {g.titulo && <span className="fc-lat-titulo">{g.titulo}</span>}
                  {itens}
                </div>
              );
            }
            return (
              <details className="fc-lat-grupo" key={n} open={g.aberto}>
                <summary className="fc-lat-titulo">{g.titulo}</summary>
                {itens}
              </details>
            );
          })}
        </nav>
        <div className="fc-lat-rodape">O posto em ordem, todo dia.</div>
      </aside>
      <div className="fc-lat-fundo" hidden={!aberto} onClick={() => setAberto(false)}></div>

      <header className="fc-barra">
        <button className="fc-barra-menu" type="button" ref={botao} aria-controls="fc-lateral" aria-label="Menu"
          aria-expanded={aberto} onClick={() => setAberto(!aberto)}>
          <i className="bi bi-list" aria-hidden="true"></i><span>Menu</span>
        </button>
        <a className="fc-barra-marca" href={eu.links.inicio}>
          <img src="/static/pwa/icone-192.png" alt="" width={28} height={28} />
          <span>Trino Facilities</span>
        </a>
        <div className="fc-direita">
          <a className="fc-sino" href={eu.links.avisos}
            aria-label={avisos ? `Avisos: ${avisos} não lido(s)` : 'Avisos'}>
            <i className="bi bi-bell" aria-hidden="true"></i>
            {avisos > 0 && <span className="n">{avisos < 100 ? avisos : '99+'}</span>}
          </a>
          <Usuario eu={eu} />
        </div>
      </header>

      <main className="fc-conteudo" id="conteudo">{children}</main>
    </>
  );
}

function Usuario({ eu }: { eu: Eu }) {
  const [aberto, setAberto] = useState(false);
  return (
    <div className="dropdown fc-usuario">
      <button className="dropdown-toggle" type="button" aria-expanded={aberto}
        onClick={() => setAberto(!aberto)}>
        <span className="fc-avatar" aria-hidden="true">{eu.nome.slice(0, 1).toUpperCase()}</span>
        <span className="d-none d-sm-inline">{eu.primeiro_nome}</span>
      </button>
      <ul className={`dropdown-menu dropdown-menu-end${aberto ? ' show' : ''}`}>
        <li><span className="dropdown-item-text small text-muted">{eu.nome}<br />{eu.perfil}</span></li>
        <li><hr className="dropdown-divider" /></li>
        <li><a className="dropdown-item" href={eu.links.trocar_senha}><i className="bi bi-key"></i> Trocar senha</a></li>
        <li><a className="dropdown-item" href={eu.links.seguranca}><i className="bi bi-shield-lock"></i> Segurança da conta</a></li>
        <li><hr className="dropdown-divider" /></li>
        <li>
          <form method="post" action={eu.links.sair} className="m-0">
            <input type="hidden" name="csrf_token" value={eu.csrf} />
            <button className="dropdown-item" type="submit"><i className="bi bi-box-arrow-right"></i> Sair</button>
          </form>
        </li>
      </ul>
    </div>
  );
}
