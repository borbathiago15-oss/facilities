// O pedido de presença (D48): pergunta ao servidor a cada minuto com a tela à
// vista. O aviso no celular também chega; quem está com o app aberto vê aqui.
import { useCallback, useEffect, useState } from 'react';
import { chamar, ErroDaApi } from '../api';

type Pedido = { id: number; rota: string; ate: string };

export function Presenca() {
  const [pedido, setPedido] = useState<Pedido | null>(null);
  const [recado, setRecado] = useState('');
  const [enviando, setEnviando] = useState(false);

  const perguntar = useCallback(() => {
    if (document.hidden || navigator.onLine === false) return;
    chamar<{ pedido: Pedido | null }>('/app/api/presenca')
      .then((x) => setPedido(x.pedido))
      .catch(() => {});
  }, []);

  useEffect(() => {
    perguntar();
    const relogio = setInterval(perguntar, 60_000);
    document.addEventListener('visibilitychange', perguntar);
    return () => {
      clearInterval(relogio);
      document.removeEventListener('visibilitychange', perguntar);
    };
  }, [perguntar]);

  if (!pedido && !recado) return null;

  async function confirmar(p: Pedido) {
    setEnviando(true);
    try {
      const x = await chamar<{ mensagem: string }>(`/app/api/presenca/${p.id}`, { method: 'POST' });
      setPedido(null);
      setRecado(x.mensagem);
      setTimeout(() => { setRecado(''); perguntar(); }, 4000);
    } catch (e) {
      const erro = e as ErroDaApi;
      setRecado(erro.status === 0
        ? 'Sem sinal: a confirmação precisa de internet. Tente de novo.'
        : erro.message || 'Não foi possível confirmar.');
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="fc-presenca" role="alert">
      {recado && <div className="fw-semibold mb-2">{recado}</div>}
      {pedido && (
        <>
          {!recado && <div className="fw-semibold mb-2">Confirme que você está no posto (até {pedido.ate}).</div>}
          <button type="button" className="btn btn-light btn-lg w-100 fw-bold" disabled={enviando}
            onClick={() => confirmar(pedido)}>Estou no posto</button>
        </>
      )}
    </div>
  );
}
