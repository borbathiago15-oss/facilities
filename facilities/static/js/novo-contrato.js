// Novo contrato › Equipe: cada função mostra só os campos dela. Cliente
// escolhe o cliente (não tem superior nem locais); a equipe escolhe a quem
// responde e os locais; a diretoria vê tudo e não escolhe nada. Sem
// JavaScript, todos os campos aparecem e o servidor ignora o que não vale.
(function () {
  var funcao = document.getElementById('role');
  if (!funcao) return;
  function mostrar() {
    var papel = funcao.value;
    document.querySelectorAll('[data-so-cliente]').forEach(function (el) {
      el.hidden = papel !== 'cliente';
    });
    document.querySelectorAll('[data-so-equipe]').forEach(function (el) {
      el.hidden = papel === 'cliente' || papel === 'visualizador';
    });
  }
  funcao.addEventListener('change', mostrar);
  mostrar();
})();
