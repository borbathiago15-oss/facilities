// Leitor de QR do aplicativo de campo (a tela antiga é static/js/leitor-qr.js).
//
// A câmera de trás abre na própria página (getUserMedia). Cada quadro vai
// para o BarcodeDetector do navegador, quando existe (Chrome do Android), ou
// para o jsQR (static/vendor/jsqr, carregado só nesta tela), que funciona em
// qualquer navegador — inclusive no Safari do iPhone.
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { CODIGO, destino } from './qr';

let jsQrCarregando: Promise<void> | null = null;

/** O jsQR, do arquivo de sempre (a CSP só aceita script deste site). */
function carregarJsQr(): Promise<void> {
  if (window.jsQR) return Promise.resolve();
  if (!jsQrCarregando) {
    jsQrCarregando = new Promise((ok) => {
      const s = document.createElement('script');
      s.src = '/static/vendor/jsqr/jsQR.js';
      s.onload = () => ok();
      s.onerror = () => { jsQrCarregando = null; ok(); };
      document.head.appendChild(s);
    });
  }
  return jsQrCarregando;
}

export function LerQr() {
  const navegar = useNavigate();
  const video = useRef<HTMLVideoElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [msg, setMsg] = useState('Abrindo a câmera…');
  const [tentar, setTentar] = useState(false);
  const [codigo, setCodigo] = useState('');
  // As funções do leitor vivem enquanto a tela está aberta: o laço dos
  // quadros não pode depender de um desenho do React.
  const leitor = useRef<{ iniciar: () => void; abrir: (texto: string, digitado?: boolean) => boolean } | null>(null);

  useEffect(() => {
    let fluxo: MediaStream | null = null;
    let detector: InstanceType<NonNullable<Window['BarcodeDetector']>> | null = null;
    let lendo = false;
    let vivo = true;
    const dizer = (texto: string) => { if (vivo) setMsg(texto); };

    function parar() {
      lendo = false;
      if (fluxo) { fluxo.getTracks().forEach((t) => t.stop()); fluxo = null; }
    }

    // ``digitado``: o código foi escrito à mão, não lido pela câmera — a
    // execução fica com a hora do celular (marcada para a gestão), sem o selo
    // do servidor, que vale como "leu o QR no ponto".
    function abrir(texto: string, digitado = false) {
      const alvo = destino(texto);
      if (!alvo) {
        dizer('Este QR não é do Trino Facilities. Procure a etiqueta do local.');
        return false;
      }
      parar();
      dizer('QR lido. Abrindo…');
      if (navigator.vibrate) { try { navigator.vibrate(80); } catch { /* sem vibração */ } }
      // No aplicativo, o QR abre o turno já no ponto lido.
      navegar('/app/turno?ponto=' + encodeURIComponent(alvo.slice(3)) + (digitado ? '' : '&lido=camera'));
      return true;
    }

    function quadro() {
      const v = video.current, c = canvas.current;
      if (!lendo || !vivo || !v || !c) return;
      if (v.readyState < 2) { requestAnimationFrame(quadro); return; }
      if (detector) {
        detector.detect(v).then((achados) => {
          if (achados.length && abrir(achados[0].rawValue)) return;
          setTimeout(quadro, 150);
        }).catch(() => { detector = null; setTimeout(quadro, 150); });
        return;
      }
      if (!window.jsQR) { dizer('O leitor não carregou. Digite o código da etiqueta abaixo.'); return; }
      const w = v.videoWidth, h = v.videoHeight;
      const escala = Math.min(1, 640 / Math.max(w, h));
      c.width = Math.round(w * escala);
      c.height = Math.round(h * escala);
      const ctx = c.getContext('2d', { willReadFrequently: true })!;
      ctx.drawImage(v, 0, 0, c.width, c.height);
      const img = ctx.getImageData(0, 0, c.width, c.height);
      const achado = window.jsQR(img.data, img.width, img.height, { inversionAttempts: 'dontInvert' });
      if (achado && abrir(achado.data)) return;
      setTimeout(quadro, 120);
    }

    function iniciar() {
      setTentar(false);
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        dizer('Este navegador não abre a câmera. Digite o código da etiqueta abaixo.');
        return;
      }
      dizer('Abrindo a câmera…');
      navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
        .then((s) => {
          if (!vivo) { s.getTracks().forEach((t) => t.stop()); throw new Error('fechou'); }
          fluxo = s;
          video.current!.srcObject = s;
          return video.current!.play();
        })
        .then(() => {
          if (window.BarcodeDetector) {
            try { detector = new window.BarcodeDetector({ formats: ['qr_code'] }); } catch { detector = null; }
          }
          return detector ? undefined : carregarJsQr();
        })
        .then(() => {
          if (!vivo || !fluxo) return;
          lendo = true;
          dizer('Aponte para o QR. A leitura é automática.');
          quadro();
        })
        .catch((erro) => {
          if (!vivo) return;
          parar();
          setTentar(true);
          dizer(erro && erro.name === 'NotAllowedError'
            ? 'O celular não deixou usar a câmera. Libere a câmera para este site nas configurações do navegador, ou digite o código abaixo.'
            : 'Não foi possível abrir a câmera. Tente de novo ou digite o código abaixo.');
        });
    }

    leitor.current = { iniciar, abrir };
    const visibilidade = () => { if (document.hidden) parar(); else if (!fluxo) iniciar(); };
    document.addEventListener('visibilitychange', visibilidade);
    window.addEventListener('pagehide', parar);
    iniciar();
    return () => {
      vivo = false;
      parar();
      document.removeEventListener('visibilitychange', visibilidade);
      window.removeEventListener('pagehide', parar);
    };
  }, [navegar]);

  return (
    <div data-tela-pronta="ler-qr">
      <h1 className="fc-titulo">Ler o QR do local</h1>
      <p className="fc-sub">Aponte a câmera para a etiqueta do Trino Facilities.</p>
      <div className="fc-leitor" id="fc-leitor">
        <video id="fc-leitor-video" playsInline muted ref={video}></video>
        <canvas id="fc-leitor-canvas" hidden ref={canvas}></canvas>
        <div className="fc-leitor-mira" aria-hidden="true"></div>
      </div>
      <p className="mt-3 mb-2" id="fc-leitor-msg" role="status">{msg}</p>
      <button className="btn btn-outline-primary w-100 fc-app-acao mb-2" id="fc-leitor-tentar" type="button"
        hidden={!tentar} onClick={() => leitor.current?.iniciar()}>
        <i className="bi bi-camera"></i> Tentar de novo
      </button>
      <details className="fc-cartao mt-2">
        <summary className="fw-semibold">A câmera não abre? Digite o código</summary>
        <form className="mt-2 d-flex gap-2" id="fc-leitor-form" onSubmit={(ev) => {
          ev.preventDefault();
          const l = leitor.current;
          if (!l) return;
          const bruto = (codigo || '').trim();
          if (CODIGO.test(bruto)) { l.abrir(location.origin + '/q/' + bruto, true); return; }
          if (!l.abrir(bruto, true)) setMsg('Código inválido. Confira as letras embaixo do QR.');
        }}>
          <label className="visually-hidden" htmlFor="fc-leitor-codigo">Código da etiqueta</label>
          <input className="form-control" id="fc-leitor-codigo" autoComplete="off" autoCapitalize="off"
            spellCheck={false} placeholder="O código embaixo do QR" value={codigo}
            onChange={(e) => setCodigo(e.target.value)} />
          <button className="btn btn-primary" type="submit">Abrir</button>
        </form>
      </details>
    </div>
  );
}
