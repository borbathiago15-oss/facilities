# Segurança dos dados no banco

Pedido do dono (30/10/2026): "o banco de dados precisa estar criptografado,
não podemos deixar dados vazarem, nem senha".

## O que está protegido, e como

| Dado | Como fica guardado | Quem copia o banco vê |
|---|---|---|
| Senha | hash **scrypt** (Werkzeug; memória e CPU caras por tentativa). Não tem volta, nem com chave | um hash inútil |
| E-mail (pessoas e convites) | **cifrado** (Fernet: AES-128-CBC + HMAC-SHA256) + **índice cego** (HMAC-SHA256) para o login | texto cifrado e um HMAC |
| Segredo da segunda etapa (TOTP) | cifrado | texto cifrado |
| Telefone do convite, endereço do local | cifrados | texto cifrado |
| Chaves do aviso no celular (`p256dh`, `auth`) | cifradas | texto cifrado |
| Link do convite, token de reset | só o hash (já era assim) | um hash |
| Backup diário | arquivo inteiro cifrado (gpg AES-256, `BACKUP_SENHA`) | nada |
| Conexão app → banco | TLS obrigatório quando o banco está fora da rede interna | — |

Senhas: o sistema .NET da empresa usa o PBKDF2 do ASP.NET Identity; o scrypt
daqui é mais resistente a ataque com placa de vídeo. Não há importação de
senhas do .NET (decisão do dono, 30/10/2026).

O resto (nomes, registros da operação, fotos) segue protegido pelo acesso
ao banco e pelo backup cifrado. Cifrar mais colunas é só repetir o padrão
abaixo.

## As duas chaves, e onde ficam

| Variável | Para quê | Onde |
|---|---|---|
| `FIELD_ENCRYPTION_KEY` | cifra os campos do banco | Railway (`web` e `agendador`) **e** cofre offline |
| `BACKUP_SENHA` | cifra o arquivo do backup | Railway (`backup`) **e** cofre offline |

* **Sem a `FIELD_ENCRYPTION_KEY` o sistema não sobe** fora do SQLite de
  desenvolvimento (no dev, ela é criada em `instance/chave_dos_campos.key`).
* **Perder a chave = perder os dados cifrados.** Nem o backup devolve. Por
  isso a cópia no cofre offline vem ANTES do primeiro deploy.
* Gerar: `flask --app facilities chaves gerar`.
* Conferir se sobrou algo sem cifra: `flask --app facilities chaves conferir`
  (sai com erro e diz a tabela/coluna).

## Trocar a chave (rodízio)

Quando: suspeita de vazamento, saída de quem tinha acesso ao painel, ou uma
vez por ano.

1. Gere a nova (`chaves gerar`) e guarde no cofre.
2. No Railway (`web` e `agendador`): `FIELD_ENCRYPTION_OLD_KEYS` = a chave
   atual; `FIELD_ENCRYPTION_KEY` = a nova. Deploy. Tudo continua legível e
   o login funciona (procura o índice de todas as chaves).
3. `railway ssh --service web` e `flask --app facilities chaves girar`:
   recifra tudo e refaz os índices com a nova.
4. `flask --app facilities chaves conferir` → "Todos os campos sensíveis
   estão cifrados".
5. Tire a `FIELD_ENCRYPTION_OLD_KEYS` e faça o deploy. Os backups antigos
   continuam precisando da chave antiga: mantenha-a no cofre, marcada com a
   data, enquanto houver backup dela.

## Restaurar um backup

1. `gpg --batch --pinentry-mode loopback --passphrase-file senha.txt -d facilities-AAAA-MM-DD.dump.gpg > facilities.dump`
2. `pg_restore --clean --no-owner -d "$DATABASE_URL" facilities.dump`
3. O app que ler esse banco usa a `FIELD_ENCRYPTION_KEY` da época do backup
   (a atual, ou ela em `FIELD_ENCRYPTION_OLD_KEYS`).

## Regras para quem mexe no código

* Campo sensível novo: `db.Column(Cifrado())` (`facilities/core/cifra.py`),
  a coluna em `facilities/core/cifra_banco.CAMPOS` e uma migração que cifre
  as linhas existentes (modelo: `e1a7c3f5b9d2_cifra_dos_campos_sensiveis`).
* **Nunca filtrar, ordenar, agrupar nem usar LIKE em SQL numa coluna
  `Cifrado`**: o texto cifrado muda a cada gravação. E-mail se procura por
  `Modelo.email == x` / `filter_by(email=x)` / `User.por_email(x)`, que vão
  pelo índice cego; qualquer outra comparação dá erro de propósito.
* Teste de que o valor bruto no banco não contém o texto
  (`tests/test_cifra_campos.py`).
