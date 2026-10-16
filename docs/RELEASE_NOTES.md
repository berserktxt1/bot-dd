Aplicativo para Windows 10/11 (64 bits) que joga partidas e instâncias PvE do DDClássico sozinho, com mira calculada e calibrada pelos seus disparos e interface em português.

> **Ainda não foi testado no DDClássico real.** Esta versão foi validada com testes automatizados, simulação e o `.exe` rodando no Windows da CI, sem o jogo. Antes de usar o modo automático, leia os Termos do servidor: as regras sobre programas de automação não puderam ser verificadas.

## Qual arquivo baixar

| Arquivo | Para quê |
|---|---|
| **DDClassicoBot.zip** | Recomendado. Pasta completa: extraia e abra `DDClassicoBot/DDClassicoBot.exe`. Abre mais rápido e traz o LEIA-ME. |
| **DDClassicoBot.exe** | Arquivo único que roda sozinho. Coloque numa pasta só para ele, porque ele cria a pasta `dados` ao lado de si. Abre um pouco mais devagar. |
| SHA256SUMS.txt | Somas para conferir os downloads. |
| build-info.json | Registro da compilação: commit, execução da CI e versões. |

Não precisa instalar Python. Para conhecer a interface sem o jogo, ligue **Modo demonstração**. A primeira configuração está no `LEIA-ME.md` dentro do ZIP. Parada de emergência: tecla **F12**.

O executável não tem assinatura digital. Se o Windows mostrar "O Windows protegeu o computador", clique em *Mais informações* › *Executar assim mesmo*.

## Verificação desta compilação

- Commit: `{COMMIT}`
- Execução da CI: {RUN_URL}
- Testes no Windows: {TESTES}
- `.exe` da pasta extraída do ZIP e `.exe` de arquivo único sozinho numa pasta vazia, os dois sem Python no PATH: autoteste e teste de interface aprovados.

SHA-256:
- `DDClassicoBot.zip`: `{SHA_ZIP}`
- `DDClassicoBot.exe`: `{SHA_EXE}`

Detalhes da auditoria, das correções e das limitações em `PROGRESS.md`.
