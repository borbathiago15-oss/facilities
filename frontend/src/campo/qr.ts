// O destino de um QR lido no aplicativo de campo. Só abre QR DO PRÓPRIO
// SISTEMA: o endereço lido precisa ser deste site e do caminho /q/<código>.
// Um QR qualquer colado na parede (propaganda, golpe) não leva o celular do
// posto para fora daqui. (O mesmo de static/js/leitor-qr.js.)

/** O código escrito à mão, embaixo do QR. */
export const CODIGO = /^[A-Za-z0-9_-]{8,32}$/;

/** ``/q/<código>``, ou null se o QR não for deste sistema. */
export function destino(texto: string | null | undefined, aqui: string = location.href): string | null {
  let url: URL;
  try { url = new URL(String(texto || '').trim(), aqui); } catch { return null; }
  if (url.origin !== new URL(aqui).origin) return null;
  const m = /^\/q\/([A-Za-z0-9_-]{8,32})\/?$/.exec(url.pathname);
  return m ? '/q/' + m[1] : null;
}
