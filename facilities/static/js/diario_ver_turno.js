/* Correção de passagem (era embutido no ver_turno.html; Fase 9A). */
  var VT_TURNO_ID = Number((document.getElementById('vt-modal-corrigir') || {dataset: {}}).dataset.turnoId || 0);
  function vtCorrigir() {
    new bootstrap.Modal(document.getElementById('vt-modal-corrigir')).show();
  }
  function vtEnviarCorrecao() {
    var v = function (id) { return document.getElementById(id).value; };
    if (!v('vt-c-motivo').trim()) {
      alert('Diga em uma linha o que estava errado.'); return;
    }
    var botao = document.getElementById('vt-c-enviar');
    botao.disabled = true;
    fetch('/passagem-de-turno/api/turnos/' + VT_TURNO_ID + '/corrigir', {
      method: 'POST',
      headers: {'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
      body: JSON.stringify({data_turno: v('vt-c-data'), turno: v('vt-c-turno'),
                            observacao: v('vt-c-obs'), motivo: v('vt-c-motivo')})
    }).then(function (r) { return r.json().then(function (x) { return {ok: r.ok, x: x}; }); })
      .then(function (res) {
        if (!res.ok) { alert(res.x.error || 'Não foi possível corrigir.'); botao.disabled = false; return; }
        location.reload();
      }).catch(function () { alert('Falha de rede.'); botao.disabled = false; });
  }
window.vtCorrigir = vtCorrigir;
window.vtEnviarCorrecao = vtEnviarCorrecao;
window.FC_ACOES = Object.assign(window.FC_ACOES || {}, {
  vtCorrigir: vtCorrigir, vtEnviarCorrecao: vtEnviarCorrecao
});
