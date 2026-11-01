# Arquivo das fotos antigas

Decisão do dono (01/11/2026): o volume de fotos é o que mais cresce no
sistema. As fotos com mais de **60 dias** (o administrador muda o número na
tela; fica no banco) saem do armazenamento do dia a dia para um **arquivo**.
O registro de cada foto (a linha da execução, do chamado, da visita...) nunca
sai do banco: só o arquivo muda de lugar, e todas as telas, antigas e novas,
continuam mostrando a foto.

Tela: menu **Administração do sistema › Armazenamento de fotos**
(`/novo/admin/armazenamento`), só do administrador (`master`).

## O destino (só pelo ambiente)

O lugar do arquivo **não se digita na tela**, por segurança. Um dos dois, nas
variáveis do serviço:

| Destino | Variáveis | Para quê |
|---|---|---|
| Bucket do Cloudflare R2 **separado** | `ARQUIVO_R2_ENDPOINT`, `ARQUIVO_R2_ACCESS_KEY_ID`, `ARQUIVO_R2_SECRET_ACCESS_KEY`, `ARQUIVO_R2_BUCKET` (opcional `ARQUIVO_R2_PREFIX`) | o arquivo de verdade: libera espaço do volume/bucket principal |
| Pasta do servidor | `ARQUIVO_FOTOS_PASTA=/data/arquivo-fotos` | **só para testar o caminho**: no mesmo disco das fotos não libera espaço nenhum (a tela avisa) |

Sem nenhum dos dois, o arquivo fica desligado e a tela diz como ligar. O
sistema **recusa** (e a tela mostra o motivo):

* os dois destinos ao mesmo tempo, ou um R2 com variável faltando;
* o bucket do arquivo igual ao principal (`R2_BUCKET` no mesmo
  `R2_ENDPOINT`) — arquivar ali gravaria a cópia por cima do original e
  depois apagaria os dois;
* a pasta do arquivo dentro da pasta das fotos (`UPLOAD_FOLDER`), ou ela
  dentro da pasta do arquivo, pelo mesmo motivo;
* a pasta em **outro disco** que o das fotos, sem `ARQUIVO_FOTOS_PASTA_OUTRO_DISCO=1`.
  Num contêiner, pasta fora do volume some no próximo deploy — com as fotos
  dentro. Só confirme se o disco é permanente.

**Não tire as variáveis depois de arquivar**: sem o destino, as fotos
arquivadas não abrem (a tela avisa quantas são).

## Como anda

1. O administrador abre a tela, confere quantas fotos e quantos MB passaram
   do prazo e confirma ("Arquivar N fotos" › "Confirmar e começar"). Abre um
   **lote** com a data de corte daquele momento.
2. O trabalho anda **na rodada do agendador** (`flask agendador rodar`, a cada
   5 minutos), no máximo 200 fotos ou 40 segundos por rodada
   (`ARQUIVO_FOTOS_POR_RODADA` muda o número). Nunca numa requisição longa.
3. Cada foto, nesta ordem: lê do armazenamento principal → grava no arquivo →
   lê de volta do arquivo e compara o SHA-256 → registra em
   `fotos_arquivadas` → **na rodada seguinte**, depois de o registro estar
   gravado no banco e de conferir que a cópia continua lá, apaga do principal.
4. Qualquer falha (destino fora do ar, cópia que não confere, foto que não
   existe): a foto **fica no principal**, o erro fica no lote e ela é tentada
   de novo nas rodadas seguintes. Depois de 3 tentativas no mesmo lote, o lote
   termina como "Concluído, com fotos que não saíram"; um lote novo tenta de
   novo.
5. Ler: quando a foto não está no principal, o sistema busca no arquivo
   (`object_storage.ComArquivo`). Nenhuma tela muda.

Entram: fotos da execução da rota, da visita de supervisão, os anexos de
**imagem** do chamado e da passagem de turno, a foto do aviso do público e a
do pedido de material. **Nunca** entram: PDF e planilhas, as fotos de
referência do checklist, POP/FIT, logos dos clientes e relatórios.

Rodar de novo não duplica nada (`storage_key` única em `fotos_arquivadas`).
A retenção que apaga a foto do aviso do público resolvido (`core/retencao.py`)
apaga também a cópia do arquivo e o registro.

## Onde roda (atenção no Railway com volume)

O passo precisa **enxergar as fotos**. Com `STORAGE_BACKEND=r2`, o
`agendador` enxerga o bucket e basta. Com `STORAGE_BACKEND=local` (volume
`/data` do `web`), o `agendador` **não** tem o volume: ele pula a vez sem
mexer em nada, e quem anda com o lote é o próprio `web`, com
`ARQUIVO_FOTOS_NO_WEB=1` (um laço no `docker-entrypoint.sh` chama
`flask --app facilities anexos arquivar` a cada `ARQUIVO_FOTOS_INTERVALO`
segundos, padrão 300). Se o agendador e o web pegarem o mesmo lote na mesma
hora, um deles pula a vez (trava da linha do lote no Postgres).

Para forçar um passo agora: `flask --app facilities anexos arquivar`.

## O que o banco guarda

* `arquivo_fotos_ajustes`: o prazo (uma linha);
* `arquivo_fotos_lotes`: cada arquivamento (quem, quando, corte, destino,
  situação, contagens, bytes, último erro);
* `fotos_arquivadas`: cada foto no arquivo (chave, tabela e linha de origem,
  tamanho, SHA-256, lote, quando saiu do principal);
* `arquivo_fotos_falhas`: as que não conseguiram sair, com o erro.
