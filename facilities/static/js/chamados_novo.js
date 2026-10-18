/* Abrir chamado: as áreas do contrato escolhido (era embutido; Fase 9A). */
(function () {
  var areas = JSON.parse(document.getElementById('areas-por-contrato').textContent || '{}');
  var cont = document.getElementById('client_id'), sel = document.getElementById('area_id');
  function preencher() {
    var lista = areas[cont.value] || [];
    sel.innerHTML = '<option value="">—</option>' + lista.map(function (a) {
      return '<option value="' + a.id + '">' + esc(a.nome) + '</option>';
    }).join('');
    sel.disabled = !lista.length;
  }
  cont.addEventListener('change', preencher);
  preencher();
})();
