// Os recados de uma vez só, no topo do conteúdo, como nas telas antigas
// (templates/base.html): o ``fc-aviso`` que uma tela deixa antes de trocar
// de página (static/js/base.js: "Passagem encerrada", "Modelo salvo") e os
// recados do servidor (o flash, aqui vindo pela API).
import { useEffect, useState } from 'react';

type Recado = { tipo: string; texto: string };

const TIPOS = ['success', 'danger', 'warning', 'info'];

function tipoDe(t: string) {
  return t === 'error' ? 'danger' : (TIPOS.includes(t) ? t : 'success');
}

/** O ``fc-aviso`` guardado, sem apagar (quem apaga é o efeito: o StrictMode
 * chama o inicializador duas vezes). */
function lerAviso(): Recado | null {
  try {
    const bruto = sessionStorage.getItem('fc-aviso');
    if (!bruto) return null;
    const aviso = JSON.parse(bruto);
    const texto = aviso && String(aviso.texto || '').trim();
    return texto ? { tipo: tipoDe(aviso.tipo), texto } : null;
  } catch {
    return null;
  }
}

function Caixa({ r, fechar, flash }: { r: Recado; fechar: () => void; flash?: boolean }) {
  const tipo = tipoDe(r.tipo);
  return (
    <div className={`alert alert-${tipo} alert-dismissible fade show`}
      role={flash || tipo === 'danger' ? 'alert' : 'status'}>
      {r.texto}
      <button type="button" className="btn-close" aria-label="Fechar" onClick={fechar}></button>
    </div>
  );
}

export function Recados({ servidor = [] }: { servidor?: Recado[] }) {
  const [aviso, setAviso] = useState<Recado | null>(lerAviso);
  const [flash, setFlash] = useState<Recado[]>(servidor);
  useEffect(() => {
    try { sessionStorage.removeItem('fc-aviso'); } catch { /* aba privada */ }
  }, []);
  return (
    <>
      {flash.map((r, n) => (
        <Caixa r={r} key={n} flash fechar={() => setFlash((l) => l.filter((_, i) => i !== n))} />
      ))}
      <div id="fc-aviso-js">
        {aviso && <Caixa r={aviso} fechar={() => setAviso(null)} />}
      </div>
    </>
  );
}
