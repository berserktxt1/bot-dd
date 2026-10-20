**JonFlow** (antes *DDClássico Bot*): aplicativo para Windows 10/11 (64 bits) que joga partidas e instâncias PvE do DDTank (servidor DDClássico) sozinho, com mira calculada e calibrada pelos seus disparos e interface em português.

## Novidades da 0.4.0

- **Estratégia própria para três instâncias**, com o mesmo motor de mira: **Formigueiro** (formigas, depois só a
  rainha), **Galinheiro / Pintinho Corre Rápido** (o inimigo mais perto primeiro, porque eles avançam até você) e
  **Castelo do Reino de Bugou — Normal** (não atira no Barão de frente com o escudo, só tiro por cima no Midas com
  escudo, pausa quando o Matias acende o pavio). O bot anuncia cada etapa no Histórico e pausa quando dispara várias
  vezes sem progresso.
- Calibração > **Alvos**: escolha a estratégia da atividade e capture os alvos e estados de cada instância. A
  estratégia é associada sozinha quando o nome da atividade contém o nome da instância.
- Modo demonstração com as três instâncias simuladas; a faixa de estado sempre diz "Demonstração".
- Correções: a captura do jogo coberto nunca usa a imagem da janela da frente (conferência com a tela e grade de
  48 pontos); o jogo não é mais associado ao launcher errado quando há vários abertos; Iniciar no jogo real não
  trava a interface e só fica ativo com o jogo conectado e a calibração completa.
- Covil do Dragão, Tribo Piatan, Castelo Sombrio, Olimpíadas Boom, Ilha dos Enamorados, Redemoinho e Arena de
  Guerreiros ficaram registradas como pesquisa: o bot ainda não joga sozinho com elas.

> **Ainda não foi testado no DDClássico real.** Esta versão foi validada com testes automatizados, simulação e o `.exe` rodando no Windows da CI, sem o jogo. As etapas das instâncias vêm de guias de jogadores de 2012–2017 e precisam ser conferidas no cliente. Antes de usar o modo automático, leia os Termos do servidor: as regras sobre programas de automação não puderam ser verificadas.

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
- Estratégias das instâncias: validadas **só em simulação** (cenários fictícios com os papéis de cada perfil) e com imagens sintéticas.
- Detecção testada no Windows da CI com janelas e processos reais de teste (launcher que abre o jogo em outro processo, dois launchers abertos, janela cobrindo o jogo). **Não** testada com o launcher e o cliente reais do DDClássico.

SHA-256:
- `JonFlow.zip`: `{SHA_ZIP}`
- `JonFlow.exe`: `{SHA_EXE}`

Detalhes da auditoria, das correções e das limitações em `PROGRESS.md`.
