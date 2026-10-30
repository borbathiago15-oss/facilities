# Segurança dos dados no banco

Pedido do dono (30/10/2026): "o banco de dados precisa estar criptografado,
não podemos deixar dados vazarem, nem senha". Decisão do mesmo dia: a cifra
é uma **opção**, que se liga em **qualquer lugar onde o banco estiver**
(Railway, servidor da empresa, outra nuvem, Docker local). Nada aqui depende
de hospedagem: são variáveis de ambiente e comandos do próprio sistema.

## O que já vale sempre, e o que é opcional

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

## Ligar a cifra (qualquer servidor)

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

Sem a chave, o sistema sobe e avisa no log que esses campos estão abertos.
Ligada a cifra, **não tire a chave**: o sistema para de abrir esses campos
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
