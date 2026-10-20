**JonFlow** (antes *DDClássico Bot*): aplicativo para Windows 10/11 (64 bits) que joga partidas e instâncias PvE do DDTank (servidor DDClássico) sozinho, com mira calculada e calibrada pelos seus disparos e interface em português.

## Novidades da 0.4.4

- **Escala do Windows em 125%, 150%...:** a captura do jogo acompanha a escala. Um jogo sem suporte a DPI desenha
  no tamanho de 100% e o Windows o amplia na tela; antes, a imagem lida pelo bot vinha menor, num canto, com o
  resto preto. Agora ela é pedida no tamanho em que o jogo desenha e ampliada como o Windows faz. Se ainda vier
  incompleta, o bot não a usa: pausa e explica. Testado com janelas de teste em 125% na CI, **ainda não com o
  cliente do DDClássico**.
- **LEIA-ME passo a passo** para quem nunca usou o programa: como o bot funciona, passos numerados, teclas de
  atalho, problemas comuns e um glossário.
- A CI passou a rodar os testes de janelas reais e a suíte completa também com a escala do Windows em 125%.

## Novidades da 0.4.3

- **Mostrar onde está o jogo:** o clique escolhe a janela que o Windows diz estar sob o ponto. Janelas ocultas pelo
  Windows (outra área de trabalho virtual) e sobreposições transparentes de outros programas não são mais
  escolhidas no lugar do jogo.
- Testes com janelas reais do Windows corrigidos para PCs que rodam o Python num venv (a identidade do processo
  vinha do redirecionador do venv) e isolados das janelas de outros programas. Na CI eles também rodam num venv com
  o navegador aberto, 3 vezes cada.
- Captura sem o aviso de função obsoleta do MSS.
- Inclui a correção da 0.4.2 (que não teve Release):

### Novidades da 0.4.2

- Correção da simulação de precisão (`--simulate`): desde a 0.3.0 ela perdia o 1º turno de cada batalha (o fim da
  batalha anterior não era aceito pelo motor, que exige leituras seguidas). Com 50 batalhas: 40,0% de acerto sem
  calibração e 96,2% com calibração, sem turnos perdidos. É uma medição em jogo **simulado**, não no DDClássico.
- A rotina no jogo, a demonstração e as estratégias das instâncias não mudaram: elas já começavam cada batalha do
  zero.

## Novidades da 0.4.0 (publicada como 0.4.1)

A 0.4.1 traz o mesmo programa da 0.4.0, com um teste de janelas reais do Windows corrigido (ele capturava a
janela do jogo ainda na animação de abertura). A tag v0.4.0 não teve Release porque esse teste falhou na CI.

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

Os arquivos ficam em **Assets**, no fim desta página. "Source code" é só o código-fonte, sem o programa pronto, e não é preciso rodar o `build_windows.bat`.

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
