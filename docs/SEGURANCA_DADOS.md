# Segurança dos dados no banco

Pedido do dono (30/10/2026): "o banco de dados precisa estar criptografado,
não podemos deixar dados vazarem, nem senha". A cifra se liga em **qualquer
lugar onde o banco estiver** (Railway, servidor da empresa, outra nuvem,
Docker local). Nada aqui depende de hospedagem: são variáveis de ambiente e
comandos do próprio sistema.

> **ATENÇÃO — a cifra passou a ser OBRIGATÓRIA na produção** (pacote rápido
> da linha de base do Grupo, aprovado pelo dono em 06/11/2026). A imagem
> Docker (`EXIGIR_DATABASE_URL=1`) **não sobe** sem `FIELD_ENCRYPTION_KEY`:
> o `web` e o `agendador` param no boot com a mensagem do que fazer.
> **Publicar esta versão antes de pôr a chave no `web` E no `agendador`
> derruba o sistema.** Siga a ordem de "Primeira vez em produção", abaixo,
> ANTES do deploy. No desenvolvimento e nos testes (sem a marca de
> produção) a chave continua opcional.

## Primeira vez em produção (a ordem importa)

1. **Gerar a chave no seu computador** (no ambiente de desenvolvimento, que
   sobe sem ela): `flask --app facilities chaves gerar`, ou
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   Não gere nem cole a chave em conversa, e-mail, chamado ou repositório.
2. **Guardar a cópia no cofre offline** (1Password/Bitwarden do dono, ou
   envelope lacrado), com a data. Perder a chave = perder os campos cifrados.
3. **Pôr a chave na hospedagem**, a MESMA nos dois serviços:
   Railway › `web` › *Variables* › `FIELD_ENCRYPTION_KEY=<chave>` e
   Railway › `agendador` › *Variables* › a mesma linha (ou
   `FIELD_ENCRYPTION_KEY=${{web.FIELD_ENCRYPTION_KEY}}`).
4. **Só agora o deploy** da versão que exige a chave.
5. **Cifrar o que já existe**, uma vez: `railway ssh --service web` e
   `flask --app facilities chaves girar`. Até isso rodar, o sistema funciona
   normalmente (as linhas antigas ficam abertas, as novas já nascem
   cifradas, e o login acha as duas).
6. **Conferir:** `flask --app facilities chaves conferir` → "Todos os campos
   sensíveis estão cifrados". E entrar no sistema com uma conta antiga.

**Saída de emergência:** `CIFRA_OPCIONAL=1` nas variáveis faz a imagem de
produção subir sem a chave, com um alerta (`CRITICAL`) no log a cada boot
dizendo que os campos estão em texto aberto. Serve só para pôr o sistema de
pé se a chave ainda não chegou ou foi publicada a versão antes da hora.
Tire a variável assim que a chave estiver no lugar. **Nunca** use
`CIFRA_OPCIONAL=1` num banco que já tem dado cifrado: aí o problema é a
chave que sumiu (ponha de volta a do cofre), e o sistema não abriria esses
campos de qualquer jeito.

## O que já vale sempre, e o que vem com a cifra

| Dado | Sempre | Com a cifra ligada |
|---|---|---|
| Senha | hash **scrypt** (sem volta, nem com chave); senha óbvia recusada; hash antigo refeito no login | — |
| Link do convite, token de nova senha | só o hash | — |
| E-mail (pessoas e convites) | texto aberto + índice para o login | **cifrado** (Fernet: AES-128-CBC + HMAC-SHA256) + índice cego (HMAC-SHA256) |
| Segredo da segunda etapa (TOTP) | texto aberto | cifrado |
| Telefone do convite, endereço do local | texto aberto | cifrados |
| Chaves do aviso no celular (`p256dh`, `auth`) | texto aberto | cifradas |
| Conexão app → banco | TLS exigido quando o banco está fora da rede interna (imagem de produção) | — |
| Backup | depende do comando (abaixo) | opcional: arquivo cifrado com gpg |

Não há importação de senhas do .NET (decisão do dono, 30/10/2026). O scrypt
daqui resiste mais a ataque com placa de vídeo que o PBKDF2 do ASP.NET
Identity.

## Ligar a cifra (qualquer servidor, inclusive fora do Railway)

1. **Gerar a chave:** `flask --app facilities chaves gerar` (ou
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
2. **Guardar a cópia no cofre offline ANTES de usar** (1Password/Bitwarden do
   dono, ou envelope lacrado). Perder a chave = perder os campos cifrados;
   nem o backup devolve.
3. **Pôr a chave no ambiente** de TODO processo do sistema que abre o banco
   (o site e o agendador): `FIELD_ENCRYPTION_KEY=<chave>`.
   * Railway: *Variables* do `web` e do `agendador`.
   * Servidor da empresa / Docker: no `.env` ou no `docker run -e`, nunca no
     repositório.
4. **Reiniciar** e rodar uma vez, no mesmo ambiente:
   `flask --app facilities chaves girar` — cifra o que já estava aberto.
5. **Conferir:** `flask --app facilities chaves conferir` → "Todos os campos
   sensíveis estão cifrados".

Sem a chave: no desenvolvimento o sistema sobe e avisa no log que esses
campos estão abertos; na imagem de produção ele não sobe (salvo
`CIFRA_OPCIONAL=1`, acima). Ligada a cifra, **não tire a chave**: o sistema para de abrir esses campos
(erro claro, nunca dado trocado) até ela voltar.

## Trocar a chave (rodízio)

Quando: suspeita de vazamento, saída de quem tinha acesso ao servidor, ou uma
vez por ano.

1. Gere a nova e guarde no cofre.
2. `FIELD_ENCRYPTION_OLD_KEYS` = a chave atual; `FIELD_ENCRYPTION_KEY` = a
   nova (nos mesmos processos). Reinicie: tudo continua legível e o login
   funciona.
3. `flask --app facilities chaves girar` e `chaves conferir`.
4. Tire a `FIELD_ENCRYPTION_OLD_KEYS`. Guarde a antiga no cofre, com a data,
   enquanto houver backup feito com ela.

## Mudar o banco de lugar

O banco cifrado vai inteiro (`pg_dump` / `pg_restore`); o sistema no destino
só precisa da MESMA `FIELD_ENCRYPTION_KEY`. Banco num servidor fora da rede
interna: a conexão ganha `sslmode=require` sozinha; `DATABASE_SSLMODE`
muda (ex.: `verify-full` com o certificado da empresa).

## Backup cifrado (opcional)

Precisa de `pg_dump` e `gpg` (os dois vêm na imagem oficial `postgres`).
Senha do backup na variável `BACKUP_SENHA`, com cópia no cofre:

```
sh -c 'set -e; : "${BACKUP_SENHA:?defina BACKUP_SENHA}"; umask 077; d=/tmp/facilities.dump; pg_dump "$DATABASE_URL" -Fc -f "$d"; printf %s "$BACKUP_SENHA" > /tmp/senha; gpg --batch --yes --pinentry-mode loopback --passphrase-file /tmp/senha --symmetric --cipher-algo AES256 -o /backup/facilities-$(date +%F).dump.gpg "$d"; rm -f "$d" /tmp/senha; find /backup -name "*.dump.gpg" -mtime +14 -delete; ls -lh /backup'
```

Restaurar:

1. `gpg --batch --pinentry-mode loopback --passphrase-file senha.txt -d facilities-AAAA-MM-DD.dump.gpg > facilities.dump`
2. `pg_restore --clean --no-owner -d "$DATABASE_URL" facilities.dump`
3. Com a cifra ligada, o sistema que ler esse banco usa a
   `FIELD_ENCRYPTION_KEY` da época do backup (a atual, ou ela em
   `FIELD_ENCRYPTION_OLD_KEYS`).

Depois do primeiro backup cifrado conferido, apague os backups abertos
antigos.

## Fotos antigas no arquivo

As fotos com mais de 60 dias podem sair do armazenamento principal para um
arquivo (tela *Armazenamento de fotos*, só do administrador). O destino vem
SÓ do ambiente (`ARQUIVO_R2_*` de um bucket separado, ou
`ARQUIVO_FOTOS_PASTA` para teste), nunca da tela; cada foto é conferida pelo
SHA-256 antes de sair do principal, e nenhuma linha do banco é apagada. As
chaves do bucket do arquivo ficam só nas variáveis do serviço, como as do R2
principal. Ver `docs/ARQUIVO_FOTOS.md`.

## Contas e sessões

O cookie da sessão (Flask) é **assinado, não cifrado**: quem o copia não
consegue alterá-lo, mas lê tudo o que vai nele. Por isso (auditoria da
Fase 6a, 03/11/2026, valendo nas telas antigas e nas novas, que chamam as
mesmas funções em `core/auth.py` e `core/admin.py`):

* **Nenhum segredo no cookie.** A senha temporária (cadastrar e "Gerar
  senha temporária") aparece só na resposta do envio que a cria
  (`Cache-Control: no-store`), nunca no recado (`flash`), que mora no
  cookie. O segredo da segunda etapa ainda não ativado fica na linha da
  pessoa (`users.totp_segredo`, cifrado com a `FIELD_ENCRYPTION_KEY` quando
  ligada) enquanto `totp_ativo` é falso — o login só pede o código com
  `totp_ativo`, e com a etapa ativada nada mexe no segredo; na sessão vai
  só uma marca dele (HMAC com a `SECRET_KEY`), que o prende à sessão que o
  pediu: outra sessão que abra a tela sorteia outro segredo, e o primeiro
  deixa de valer.
* **Quem é obrigado a usar a segunda etapa** (o código do aplicativo
  autenticador): administrador, gerente, coordenador, diretoria, cliente e,
  desde 05/11/2026 (regra R2 do dono), o **supervisor** — ele vê os locais
  da equipe, o painel e o custo de material, e distribui chamados. Até
  ativar o código, quem é obrigado só abre "Segurança da conta" (e trocar a
  senha, sair), e não pode desligá-lo. Encarregado/ASG e técnico continuam
  sem a obrigação, mesmo com "acesso a todos os locais" (que para eles vale
  só os locais da cadeia acima, R1). A lista mora em
  `facilities/core/models.PERFIS_COM_SEGUNDA_ETAPA`; antes de publicar a
  mudança, avise os supervisores de que o próximo login pedirá o código.
* **Ligar e desligar a segunda etapa pedem a senha atual.** Só com a
  sessão (um cookie copiado, um computador esquecido aberto) ninguém
  cadastra o próprio autenticador nem tranca o dono fora.
* **As ações do administrador que entregam a conta de outra pessoa**
  ("Gerar senha temporária" e "Desligar a segunda etapa", para qualquer
  pessoa, inclusive outro administrador) pedem a senha do **próprio**
  administrador. A senha temporária não vale para a própria conta: a
  própria senha se troca em "Trocar senha".
* **Senha errada conta no bloqueio da conta**, no mesmo contador do login
  (`failed_login_count`, atualizado no banco): trocar a senha, ligar ou
  desligar o código e as ações do administrador (no contador dele). No 5º
  erro, somando as duas telas, a conta bloqueia por 15 minutos e a sessão
  cai.
* **Limite por hora dividido entre as duas telas.** Rota com limite do
  Flask-Limiter que tem gêmea em `/api/v1` usa `limiter.shared_limit` com
  o mesmo escopo nas duas (convidar para a equipe: 60/h; abrir cobrança no
  portal: 30/h). Um `limit` em cada uma dobraria o teto
  (`tests/test_telas_cadastros.py::test_nenhuma_tela_nova_dobra_o_limite_da_antiga`).

## Regras para quem mexe no código

* Campo sensível novo: `db.Column(Cifrado())` (`facilities/core/cifra.py`),
  a coluna em `facilities/core/cifra_banco.CAMPOS` e uma migração que cifre
  as linhas existentes (modelo: `e1a7c3f5b9d2_cifra_dos_campos_sensiveis`).
* **Nunca filtrar, ordenar, agrupar nem usar LIKE em SQL numa coluna
  `Cifrado`**: o texto cifrado muda a cada gravação. E-mail se procura por
  `Modelo.email == x` / `filter_by(email=x)` / `User.por_email(x)`, que vão
  pelo índice; qualquer outra comparação dá erro de propósito.
* Teste de que o valor bruto no banco não contém o texto, com a cifra ligada
  (`tests/test_cifra_campos.py`).

## Erros no log

O log da hospedagem é lido por mais gente que o banco. Por isso
(`facilities/core/log_seguro.py`): erro do banco vai para o log só com a
classe, o SQLSTATE e um motivo curto ("tempo esgotado", "conexão recusada"),
nunca a mensagem do driver (que traz host, usuário e nome do banco) nem a
consulta com os parâmetros (que podem ter e-mail e nome). Nos outros erros,
URL com senha, e-mail e host/usuário entre aspas são apagados. Falha de
e-mail registra só o domínio do destinatário e o código SMTP. Código novo
que registra erro: use `log_seguro.resumo(erro)`, nunca `str(erro)` de erro
do banco.
