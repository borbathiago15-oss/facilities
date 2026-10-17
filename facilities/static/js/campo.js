// Aplicativo de campo: o aviso "Sem sinal" no topo.
//
// Sem sinal o aplicativo continua funcionando: a passagem de turno abre da
// cópia guardada e o que a pessoa lança fica na fila do aparelho
// (fila-offline.js), que sobe sozinha quando o sinal volta.
(function () {
  var selo = document.getElementById('fc-app-rede');
  if (!selo) return;
  function atualizar() { selo.hidden = navigator.onLine !== false; }
  window.addEventListener('online', atualizar);
  window.addEventListener('offline', atualizar);
  atualizar();
})();
