export function NaoEncontrada({ inicio }: { inicio: string }) {
  return (
    <section>
      <h1 className="h4">Página não encontrada</h1>
      <p>Não encontramos o que você procurou. O link pode estar velho, ou a tela ainda não
        chegou nesta versão.</p>
      <a className="btn btn-primary" href={inicio}>Voltar ao início</a>
    </section>
  );
}
