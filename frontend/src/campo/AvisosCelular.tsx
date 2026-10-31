// Avisos no celular (Web Push): o aviso da hora de cada tarefa e do pedido de
// presença, mesmo com o aplicativo fechado. As mesmas regras de campo.js.
import { useEffect, useState } from 'react';
import { chamar } from '../api';

function deBase64(s: string) {
  const pad = '='.repeat((4 - (s.length % 4)) % 4);
  const bruto = atob((s + pad).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(bruto, (c) => c.charCodeAt(0));
}

async function inscrever(chave: string) {
  const reg = await navigator.serviceWorker.ready;
  const insc = (await reg.pushManager.getSubscription())
    || (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: deBase64(chave) }));
  await chamar('/app/api/push', { method: 'POST', body: JSON.stringify(insc.toJSON()) });
}

const PADRAO = 'Receba o aviso da hora de cada tarefa e do pedido de presença, mesmo com o aplicativo fechado.';

export function AvisosCelular() {
  const [texto, setTexto] = useState(PADRAO);
  const [chave, setChave] = useState<string | null>(null);
  const [botao, setBotao] = useState(false);

  useEffect(() => {
    const suporta = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
    if (!suporta) {
      setTexto('Este navegador não recebe avisos. No iPhone, instale o aplicativo na Tela de Início primeiro.');
      return;
    }
    chamar<{ chave: string | null }>('/app/api/push/chave').then((x) => {
      if (!x.chave) { setTexto('Os avisos no celular ainda não foram ligados no sistema.'); return; }
      if (Notification.permission === 'granted') {
        // Já autorizado: renova em nome de quem está logado (celular compartilhado).
        setTexto('Avisos ligados neste celular.');
        inscrever(x.chave).catch(() => {});
        return;
      }
      if (Notification.permission === 'denied') {
        setTexto('Os avisos estão bloqueados nas configurações do navegador para este site.');
        return;
      }
      setChave(x.chave);
      setBotao(true);
    }).catch(() => {});
  }, []);

  async function ligar() {
    try {
      const p = await Notification.requestPermission();
      if (p !== 'granted') { setTexto('Sem permissão, o aplicativo não consegue avisar.'); return; }
      await inscrever(chave!);
      setBotao(false);
      setTexto('Pronto: você vai receber os avisos da rota e da presença.');
    } catch {
      setTexto('Não foi possível ligar os avisos. Tente de novo.');
    }
  }

  return (
    <section className="fc-cartao mb-3" aria-labelledby="tit-avisos">
      <h2 className="h6 fw-bold" id="tit-avisos"><i className="bi bi-bell" aria-hidden="true"></i> Avisos no celular</h2>
      <p className="small text-muted mb-2" role="status">{texto}</p>
      {botao && (
        <button className="btn btn-outline-primary w-100 fc-app-acao" type="button" onClick={ligar}>
          <i className="bi bi-bell" aria-hidden="true"></i> Receber avisos neste celular
        </button>
      )}
    </section>
  );
}
