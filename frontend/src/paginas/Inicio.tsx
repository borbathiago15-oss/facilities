// Início das telas novas: por enquanto, o atalho para os módulos (as telas
// antigas). Cada módulo migrado passa a abrir aqui dentro.
import type { Eu } from '../api';

export function Inicio({ eu }: { eu: Eu }) {
  const modulos = eu.menu.flatMap((g) => g.itens).filter((i) => i.endpoint !== 'core.inicio');
  return (
    <section>
      <h1 className="h4 mb-1">Olá, {eu.primeiro_nome}</h1>
      <p className="text-muted mb-4">
        Estas são as telas novas do sistema, que chegam módulo por módulo. Enquanto
        isso, os módulos abaixo abrem na tela de sempre.
      </p>
      {modulos.length === 0 ? (
        <p>Nenhum módulo liberado para o seu perfil. Se precisa de acesso, peça ao administrador.</p>
      ) : (
        <div className="row g-3">
          {modulos.map((m) => (
            <div className="col-12 col-sm-6 col-lg-4" key={m.endpoint}>
              <a className="card h-100 text-decoration-none" href={m.url}>
                <div className="card-body d-flex align-items-center gap-3">
                  <i className={`bi ${m.icone} fs-4`} aria-hidden="true"></i>
                  <span className="fw-semibold">{m.rotulo}</span>
                </div>
              </a>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
