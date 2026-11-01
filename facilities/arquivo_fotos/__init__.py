"""Arquivo das fotos antigas (decisão do dono, 01/11/2026).

O volume de fotos é o que mais cresce no sistema. As fotos com mais de
``ArquivoAjustes.dias`` dias (60 por padrão; o administrador muda na tela)
saem do armazenamento principal para um destino de arquivo configurado pelo
ambiente (``object_storage.arquivo_do_ambiente``). O registro da foto (a
linha da execução, do chamado, da visita...) NUNCA sai: só o arquivo muda de
lugar, e a leitura procura no arquivo quando não acha no principal
(``object_storage.ComArquivo``).

Quem começa é o administrador (``master``), na tela "Armazenamento de
fotos"; o trabalho anda em lotes pequenos dentro da rodada do agendador
(``servico.rodada``). Ver ``docs/ARQUIVO_FOTOS.md``.
"""
