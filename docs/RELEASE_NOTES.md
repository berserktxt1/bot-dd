**JonFlow** (antes *DDClássico Bot*): aplicativo para Windows 10/11 (64 bits) que joga partidas e instâncias PvE do DDTank (servidor DDClássico) sozinho, com mira calculada e calibrada pelos seus disparos e interface em português.

## Novidades da 0.3.0

- Novo nome e logo: **JonFlow**.
- **Detectar jogo**: um botão só. O bot acha a janela do jogo aberto pelo launcher (em outra janela ou dentro do launcher), espera o jogo abrir quando só o launcher está aberto e mostra uma prévia para conferir. Só pergunta quando não tem certeza.
- A janela do JonFlow não fica mais na frente: se minimiza ao detectar o jogo e durante a rotina, e volta ao terminar ou pausar. A captura é feita pela própria janela do jogo.
- Partidas de demonstração funcionam do lobby ao resultado (antes paravam no lobby). Instâncias e partidas guardam a escolha de cada seção, e o Iniciar só fica ativo com uma atividade válida.
- Aviso em poucos segundos quando um botão esperado não aparece, em vez de ficar parado em silêncio.

> **Ainda não foi testado no DDClássico real.** Esta versão foi validada com testes automatizados, simulação e o `.exe` rodando no Windows da CI, sem o jogo. Antes de usar o modo automático, leia os Termos do servidor: as regras sobre programas de automação não puderam ser verificadas.

## Qual arquivo baixar

| Arquivo | Para quê |
|---|---|
| **JonFlow.zip** | Recomendado. Pasta completa: extraia e abra `JonFlow/JonFlow.exe`. Abre mais rápido e traz o LEIA-ME. |
| **JonFlow.exe** | Arquivo único que roda sozinho. Coloque numa pasta só para ele, porque ele cria a pasta `dados` ao lado de si. Abre um pouco mais devagar. |
| SHA256SUMS.txt | Somas para conferir os downloads. |
| build-info.json | Registro da compilação: commit, execução da CI e versões. |

Não precisa instalar Python. Para conhecer a interface sem o jogo, ligue **Modo demonstração**. A primeira configuração está no `LEIA-ME.md` dentro do ZIP. Parada de emergência: tecla **F12**.

O executável não tem assinatura digital. Se o Windows mostrar "O Windows protegeu o computador", clique em *Mais informações* › *Executar assim mesmo*.

## Verificação desta compilação

- Commit: `{COMMIT}`
- Execução da CI: {RUN_URL}
- Testes no Windows: {TESTES}
- `.exe` da pasta extraída do ZIP e `.exe` de arquivo único sozinho numa pasta vazia, os dois sem Python no PATH: autoteste e teste de interface aprovados.
- Detecção testada no Windows da CI com janelas e processos reais de teste (launcher que abre o jogo em outro processo, janela cobrindo o jogo). **Não** testada com o launcher e o cliente reais do DDClássico.

SHA-256:
- `JonFlow.zip`: `{SHA_ZIP}`
- `JonFlow.exe`: `{SHA_EXE}`

Detalhes da auditoria, das correções e das limitações em `PROGRESS.md`.
