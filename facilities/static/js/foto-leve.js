/* Foto leve (Fase 4 do app): a foto é reduzida no próprio celular antes de
 * subir.
 *
 * A câmera do celular entrega 4 a 12 MB por foto. No galpão, com 4G fraco,
 * isso é o upload que não termina — e, sem internet, é a fila do aparelho
 * (Fase 3) enchendo. Para provar "o 5S não foi feito" ou "o extintor está
 * vencido", 1600 px no lado maior sobram: é mais do que a tela de quem vai
 * abrir a evidência.
 *
 * Regras:
 *  - só IMAGEM é mexida; PDF, Excel e Word passam como vieram;
 *  - foto que já é leve (até 600 KB e 1600 px) passa como veio — não se
 *    perde qualidade à toa;
 *  - o resultado é JPEG. Isso também tira a localização GPS e os outros
 *    metadados que a câmera grava na foto, e transforma a foto HEIC do
 *    iPhone (que o servidor não aceita) em JPG;
 *  - se reduzir falhar (aparelho antigo, formato que o navegador não abre),
 *    fica o arquivo original — o servidor decide, como sempre decidiu.
 *
 * ATENÇÃO: arquivo estático, fora do Jinja.
 */
(function () {
  'use strict';

  var LADO_MAX = 1600;
  var LEVE_BYTES = 600 * 1024;
  var QUALIDADE = 0.82;

  function ehImagem(f) {
    return f && ((f.type && f.type.indexOf('image/') === 0) ||
                 /\.(jpe?g|png|webp|heic|heif)$/i.test(f.name || ''));
  }

  function carregar(f) {
    // createImageBitmap respeita a orientação gravada pela câmera (foto de
    // celular deitado não sai de lado). Sem ele, cai no <img>, que nos
    // navegadores atuais também respeita.
    if (window.createImageBitmap) {
      return createImageBitmap(f, {imageOrientation: 'from-image'}).catch(function () {
        return carregarPorImg(f);
      });
    }
    return carregarPorImg(f);
  }

  function carregarPorImg(f) {
    return new Promise(function (ok, falha) {
      var url = URL.createObjectURL(f);
      var img = new Image();
      img.onload = function () { URL.revokeObjectURL(url); ok(img); };
      img.onerror = function () { URL.revokeObjectURL(url); falha(new Error('não abriu')); };
      img.src = url;
    });
  }

  function nomeJpg(nome) {
    var base = String(nome || 'foto').replace(/\.[^.]+$/, '') || 'foto';
    return base + '.jpg';
  }

  function reduzir(f) {
    if (!ehImagem(f) || !window.HTMLCanvasElement) { return Promise.resolve(f); }
    var aceitoComoVeio = /^image\/(jpeg|png|webp)$/.test(f.type || '');
    return carregar(f).then(function (img) {
      var w = img.width, h = img.height;
      if (aceitoComoVeio && f.size <= LEVE_BYTES && Math.max(w, h) <= LADO_MAX) {
        return f;
      }
      var escala = Math.min(1, LADO_MAX / Math.max(w, h));
      var cw = Math.max(1, Math.round(w * escala));
      var ch = Math.max(1, Math.round(h * escala));
      var c = document.createElement('canvas');
      c.width = cw; c.height = ch;
      var ctx = c.getContext('2d');
      ctx.fillStyle = '#fff';             // PNG transparente não vira fundo preto
      ctx.fillRect(0, 0, cw, ch);
      ctx.drawImage(img, 0, 0, cw, ch);
      if (img.close) { img.close(); }
      return new Promise(function (ok) {
        c.toBlob(function (blob) { ok(blob); }, 'image/jpeg', QUALIDADE);
      }).then(function (blob) {
        if (!blob) { return f; }
        // Rara, mas acontece: a "reduzida" sai maior (imagem pequena e já
        // comprimida). Aí fica a original — se o servidor a aceita.
        if (aceitoComoVeio && blob.size >= f.size) { return f; }
        return new File([blob], nomeJpg(f.name), {type: 'image/jpeg',
                                                   lastModified: Date.now()});
      });
    }).catch(function () { return f; });
  }

  function reduzirTodos(lista) {
    return Promise.all([].slice.call(lista || []).map(reduzir));
  }

  function mb(bytes) {
    // Abaixo de 0,1 MB o "0,0 MB" parecia arquivo vazio: vai em KB.
    if (bytes < 0.1 * 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1).replace('.', ',') + ' MB';
  }

  // Troca os arquivos escolhidos num <input type=file> pelas versões leves.
  // Devolve o resumo para a tela ("2 fotos · 7,9 MB → 0,6 MB").
  function prepararEntrada(entrada) {
    var originais = [].slice.call(entrada.files || []);
    if (!originais.length) { return Promise.resolve(''); }
    return reduzirTodos(originais).then(function (leves) {
      try {
        if (window.DataTransfer) {
          var dt = new DataTransfer();
          leves.forEach(function (f) { dt.items.add(f); });
          entrada.files = dt.files;
        }
      } catch (e) { /* navegador antigo: sobe o original */ }
      return resumo(originais, [].slice.call(entrada.files || leves));
    });
  }

  function resumo(originais, finais) {
    var fotos = finais.filter(ehImagem).length;
    var docs = finais.length - fotos;
    var partes = [];
    if (fotos) { partes.push(fotos + (fotos > 1 ? ' fotos' : ' foto')); }
    if (docs) { partes.push(docs + (docs > 1 ? ' arquivos' : ' arquivo')); }
    var antes = originais.reduce(function (s, f) { return s + f.size; }, 0);
    var depois = finais.reduce(function (s, f) { return s + f.size; }, 0);
    var tamanho = depois < antes * 0.9 ? mb(antes) + ' → ' + mb(depois) : mb(depois);
    return partes.join(' e ') + ' · ' + tamanho;
  }

  window.TrinoFoto = {
    reduzir: reduzir,
    reduzirTodos: reduzirTodos,
    prepararEntrada: prepararEntrada,
    resumo: resumo
  };
})();
