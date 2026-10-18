/* A porta do sistema (login e código): mostrar a senha e o aviso de envio.
   Arquivo estático por causa da CSP (sem script embutido nas telas). */
(function () {
  document.querySelectorAll('[data-ver-senha]').forEach(function (b) {
    const campo = document.getElementById(b.getAttribute('data-ver-senha'));
    if (!campo) return;
    b.addEventListener('click', function () {
      const mostrar = campo.type === 'password';
      campo.type = mostrar ? 'text' : 'password';
      b.setAttribute('aria-pressed', mostrar ? 'true' : 'false');
      b.setAttribute('aria-label', mostrar ? 'Esconder a senha' : 'Mostrar a senha');
      const i = b.querySelector('i');
      if (i) i.className = mostrar ? 'bi bi-eye-slash' : 'bi bi-eye';
    });
  });
  /* Clique duplo não manda duas vezes; a pessoa vê que está indo. */
  document.querySelectorAll('form[data-porta]').forEach(function (f) {
    f.addEventListener('submit', function () {
      const b = f.querySelector('[data-enviando]');
      if (!b) return;
      setTimeout(function () {
        b.disabled = true;
        b.textContent = b.getAttribute('data-enviando');
      }, 0);
    });
  });
})();
