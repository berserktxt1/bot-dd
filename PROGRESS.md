# Andamento

Última atualização: 2026-10-16. Versão 0.3.0 (**JonFlow**, antes *DDClássico Bot*).

> **Nada foi testado no cliente real do DDClássico nem com o launcher real.** Os resultados abaixo vêm de
> testes unitários, simulações, imagens sintéticas, janelas e processos de teste no Windows da CI e da
> execução do `.exe` no Windows da CI (sem o jogo). O ambiente de desenvolvimento é Linux, sem o jogo.

## Versão 0.3.0

### Problemas relatados e causas encontradas

| Problema | Causa real | Correção |
|---|---|---|
| Partida de demonstração parava no lobby | O cliente simulado só tinha o caminho lobby → menu de **instâncias**. O clique em "abrir partidas" falhava em silêncio e o bot só reclamaria depois de 30 s. | Caminho lobby → menu de partidas → sala no simulador; opção certa por tipo; aviso em 5 s quando um botão obrigatório não aparece. |
| Escolher entre "Launcher" e "Jogo" confundia e não resolvia | A identificação dependia do usuário saber qual janela é qual. | **Detectar jogo** (`detection.py`): parentesco de processos (o launcher abre o jogo, inclusive por um processo intermediário sem janela), janela que aparece durante a espera, área interna onde o jogo é desenhado, perfil confirmado e palavras-chave só como ponto de partida. Escolhe sozinho com evidência forte; senão pergunta com prévia ("É o jogo" / "É o launcher" / "Não é esta") ou mostra a lista. |
| A janela do bot ficava na frente e impedia a seleção | O assistente era uma janela por cima da principal, e a prévia e a captura copiavam a **tela** (MSS): o que estava na frente do jogo, inclusive o próprio bot, era o que aparecia. | A janela principal minimiza ao detectar e volta ao fechar; camada "Mostrar onde está o jogo" (o clique fica na camada, não chega ao jogo; Esc cancela); captura pedida à própria janela (`PrintWindow`); se o jogo não permitir, a cópia da tela só é usada com a área do jogo descoberta. Durante a rotina real a janela do bot minimiza e volta ao pausar/terminar. |
| Partidas e Instâncias difíceis de usar | A lista voltava sempre ao primeiro item ao trocar de seção; Iniciar ficava ativo sem atividade; sem calibração a rotina real começava, lia tudo como "tela desconhecida" e pausava sem dizer o que faltava. | Escolha mantida por seção; Iniciar só com atividade válida; orientação quando a lista está vazia; **verificação de calibração** (`readiness.py`): o Início lista o que falta (telas, botões, ângulo, vento, setas, turno, marcadores) e Iniciar no jogo real é recusado com essa lista. |
| Nome | — | **JonFlow**, com logo e ícone próprios (canhão de artilharia com o disparo em arco, no estilo DDTank; a logo oficial do DDTank é marca registrada e não foi copiada). Dados antigos em `%LOCALAPPDATA%\DDClassicoBot` continuam sendo usados. |

### Auditoria do jogo automático (combate, visão, mira)

Revisão sistemática de `combat.py`, `game_io.py`, `automation/`, `vision/`, `capture.py`, `aiming.py`,
`physics.py`, `calibration.py` e `tracking.py`. Cada defeito confirmado ganhou teste de regressão.

| Área | Defeito | Efeito no jogo | Correção |
|---|---|---|---|
| Combate | Um quadro de explosão lido como "vitória" zerava o turno | Segundo disparo no mesmo turno | Fim de batalha só com leituras seguidas; intervalo mínimo mantido |
| Combate | Alvo seguido morto/sumido com outro inimigo visível | Batalha travada até o tempo máximo (900 s) | Troca para um inimigo visível depois de ~2 s, com histórico novo |
| Combate | Barra de força ilegível (lê 0) no modo visual | Todo disparo ~10% forte | Sem leitura boa, solta pelo tempo |
| Combate | Falha de captura durante a carga | Disparo fraco e não registrado | Falha conta como leitura perdida; segue pelo tempo |
| Combate | Leituras de ângulo que nunca coincidem eram aceitas | Ângulo errado | Sem confirmação, não atira |
| Combate | 3 leituras ruins no começo do turno (câmera) | Turno perdido | Só desiste após 3 leituras **e** 5 s |
| Visão | Seta do vento precisava estar na região dos números | Vento nunca lido (ou dígitos impossíveis de treinar) | Setas procuradas ao lado dos números |
| Visão | Sinal lido como dígito somado ao sentido da seta | Vento com sinal invertido | Sentido só pelas setas; "-" não é aprendido no vento |
| Visão | Marcador com amostras de tamanhos diferentes | Personagens não encontrados | Escala da amostra vencedora |
| Visão | Busca de modelos em 7 escalas na tela inteira a cada leitura | 1,3 s (1000×600) e 4,6 s (1080p) por leitura | Escala memorizada + meia resolução: 0,16 s e 0,46 s |
| Visão | Faixa de vitória sobre o painel da batalha | Fim de batalha atrasado | Vitória/derrota/desconexão vencem a batalha |
| Visão | Janela do jogo fechada entre leitura e clique | Clique em coordenadas da área de trabalho | Clique cancelado |
| Mira | Tabela de 20° ignorava o vento | Viés de ±0,3 da régua com vento 3 | Força corrigida pelo vento |
| Mira | Viés geral da arma aumentava a confiança de métodos nunca usados | Probabilidade otimista | Só disparos do próprio método |
| Mira | Vento NaN derrubava o cálculo; alvo colado no personagem | Erro / tiro em si mesmo | Recusados com motivo |
| Mira | 0,27 s por recomendação | Menos tempo no turno | 0,09 s, mesmas escolhas |
| Calibração | Histórico inteiro recalculado a cada disparo | Custo crescente em sessões longas | Previsões memorizadas |

**O que o código não faz (limites honestos):** não enxerga o terreno, paredes nem teto (o bloqueio por
terreno só funciona com um perfil passado ao cálculo); usa um conjunto global de constantes físicas
ajustado a tabelas da comunidade, não ao DDClássico; para inimigo invisível, só estima a partir da última
posição vista e espera quando a incerteza é grande; não trata habilidades e armas especiais além de
fatores configuráveis por arma; as probabilidades de acerto só passam a significar algo depois de
disparos reais registrados.

### Resultados (preenchidos com a CI)

RESULTADOS_030

### O que ainda depende do seu computador

1. Detectar jogo com o launcher real (roteiro em `docs/TESTES.md`, seção "Launcher").
2. Calibração no cliente real (telas, botões, números, setas, marcadores) e o Diagnóstico ao vivo.
3. Uma instância e uma partida PvE do início ao fim, com o dedo no F12, e depois várias seguidas.
4. Conferir se a captura pela janela funciona com o cliente (se aparecer "outra janela está na frente do
   jogo", o jogo não permite e precisa ficar visível).
5. Regras do servidor sobre automação (não verificadas).

## Versão 0.2.1

### Falha de `test_actor_refuses_click_when_window_resized`

| | |
|---|---|
| Sintoma | No Windows do usuário, o segundo clique (janela já com o tamanho certo) era recusado como "outra janela sobre o jogo". |
| Causa | O teste usava uma janela de jogo falsa, mas a checagem de sobreposição consultava o Windows de verdade (`WindowFromPoint`) no ponto (990, 815). Na CI esse ponto ficava fora da tela pequena do runner (resposta: nenhuma janela) e o teste passava; num monitor 1080p havia uma janela real ali. |
| Defeito real encontrado junto | Com o ponto do clique fora de qualquer monitor (jogo parcialmente fora da tela), o clique era **aceito**. Agora é recusado. |
| Correção | A consulta ao Windows é injetável no `GameActor`. O teste simula a área de trabalho de forma explícita, com três casos: tamanho errado, outra janela por cima e ponto fora da tela. Nenhuma proteção foi removida. |

### Jogo aberto pelo launcher

- **Assistente "Identificar janela":** lista as janelas principais e internas com programa, classe, tamanho e prévia da captura. O usuário marca o jogo e o launcher; o perfil (executável, classe, interna ou principal) fica salvo, sem nomes presumidos nem coordenadas.
- **Estados:**
  - jogo encontrado;
  - launcher aberto sem o jogo (aguarda; Iniciar é recusado com explicação);
  - nada aberto;
  - janela ainda não identificada.

  A procura roda a cada ~3 s, em thread, e reconecta sozinha. Se o jogo for reaberto durante uma pausa, Retomar reconecta à janela nova.
- **Comandos:**
  - clique só se a janela sob o ponto for a área do jogo ou uma janela interna dela (botões do launcher na mesma janela principal são recusados);
  - teclas só com o foco do teclado dentro da área do jogo.
- **Validação:** `tests/test_launcher.py` (19 testes) com listas de janelas **simuladas**. **Não houve teste com o launcher real**; o roteiro está em `docs/TESTES.md`, seção "Launcher".

### Distribuição

- Além do ZIP, um `DDClassicoBot.exe` de **arquivo único** que roda sozinho (cria `dados/` ao lado de si; abre alguns segundos mais devagar).
- `SHA256SUMS.txt` e `build-info.json` (commit, execução da CI, versões, resultado dos testes) em cada build.
- Release automática quando uma tag `v*` é enviada: o job `release`, o único com `contents: write`, publica os arquivos já testados.

### Resultados confirmados (CI 38966300566, commit `3affe8c`, branch `hotfix/0.2.1`)

| Verificação | Resultado |
|---|---|
| pytest no Windows | 172 de 172 aprovados, 0 pulados |
| pytest no Linux (CI, Xvfb) | aprovado |
| pytest no Linux (dev) | 171 aprovados, 1 pulado (interface: sem tkinter) |
| `.exe` da pasta (ZIP extraído, sem Python no PATH) | autoteste OK; teste de interface OK; pasta não gravável OK |
| `.exe` de arquivo único, sozinho numa pasta vazia, sem Python no PATH | autoteste OK; teste de interface OK; criou `dados/config.json` ao lado |
| Capturas 100/125/150% | nenhum texto cortado nem elemento fora da janela |

## Tipos de validação

| Tipo | Onde | Situação |
|---|---|---|
| Unitários, integração com tela sintética, cenários simulados | Linux (dev) e CI Linux + Windows | aprovados |
| Interface real (Tkinter), botões, pausa/parada/emergência, responsividade | CI Windows (código-fonte e `.exe`) e CI Linux (Xvfb) | aprovados |
| Empacotamento: `.exe` extraído do ZIP, sem Python no PATH, pasta não gravável | CI Windows | aprovado |
| Revisão visual por capturas em 100%, 125% e 150% | CI Windows (1920×1080) | feita; correções aplicadas |
| **No jogo real** (telas, botões, leitura, disparos, instância completa) | — | **pendente: sem Windows com o cliente** |
| **Com o launcher real** (identificação da janela, espera, foco, reconexão) | — | **pendente: roteiro em `docs/TESTES.md`** |

## Auditoria de 2026-10-16

Três revisões independentes (automação/concorrência, mira/visão, segurança/build). Os itens marcados como
"reproduzido" foram confirmados com scripts antes da correção. Cada correção tem teste de regressão em
`tests/test_audit_regressions.py`, `tests/test_activities.py`, `tests/test_safety_combat.py` ou `tests/test_vision.py`.

### Críticos e altos corrigidos

| Problema | Correção |
|---|---|
| Um quadro mal lido como "vitória" no meio da batalha contava vitória e reiniciava o combate (reproduzido) | tela só vale após leituras seguidas iguais; resultado fica pendente e só é contado ao voltar ao início; derrota prevalece |
| Leitura de turno oscilando (True, None, True) liberava 2º disparo no mesmo turno (reproduzido) | turno confirmado por 2 leituras; None mantém o estado; intervalo contado do fim do disparo |
| Primeiro turno de cada batalha nova era pulado (reproduzido) | trava de turno reiniciada a cada batalha |
| Limites de tempo/derrotas/quantidade nunca disparavam sem tela de resultado reconhecida (reproduzido: rodou 50 batalhas com limite de 3 s) | execução conta como "sem resultado" ao voltar ao início; limite de tempo conferido fora das transições; pausa não conta |
| ESC enviado às cegas na recuperação (podia sair da batalha ou da sala) | recuperação só clica no botão fechar se ele for reconhecido; senão pausa |
| Combate seguia com tela desconhecida (diálogo por cima) | com a tela incerta, o motor só observa e sugere, não dispara |
| Alt+Tab/minimizar encerrava a rotina como "parada de emergência" | perda de foco, janela minimizada/fechada e envio bloqueado pausam com o motivo |
| Disparo com ângulo não confirmado na tela (reproduzido) | ângulo confirmado por leitura estável; sem confirmação, cancela e passa o turno |
| Direção do personagem herdada da batalha anterior | direção e ângulo reiniciados a cada batalha; teclas de virar com padrão |
| Modo de força visual soltava a 100% se a barra não fosse lida | nunca segura além do tempo estimado + 10% |
| Turno não revalidado antes de carregar a força | turno conferido logo antes da carga |
| Clique em coordenadas desatualizadas ou sobre outra janela | tamanho da janela conferido; ponto dentro da área cliente e sobre a janela do jogo |
| Pausa/parada não interrompiam um disparo em andamento | interrupção entre teclas; espera pós-disparo interrompível; disparo registrado antes da espera |
| Alvo invisível: atirava para a direita, sem vento e sem altura | direção, vento relativo e altura vêm da região estimada; incerteza da região somada |
| Correção da arma aplicada duas vezes (reproduzido) | resíduo com a arma e o ângulo efetivos; modelos por (arma, método) |
| Terreno plano bloqueava tiros altos com vento contra (reproduzido) | trajetória cortada no impacto |
| Leitor de dígitos aceitava ruído como "0"; vento sem direção recebia sinal "+" | confiança mínima; vento fora da faixa ou sem direção não é usado |
| Vazamento de handles GDI do MSS a cada thread (diagnóstico ao vivo esgotaria em minutos) | instâncias registradas e liberadas por thread e no fechamento |
| `config.json` com BOM, vazio ou corrompido impedia o app de abrir (reproduzido) | leitura tolerante; original guardado como `.corrompido`; tipos inválidos voltam ao padrão |
| Tecla de emergência podia falhar em silêncio | estado real mostrado no rodapé; modo automático no jogo bloqueado sem ela; autoteste do exe testa o pynput |
| Exceções sumiam no `.exe` sem console | ganchos de exceção do Tk, de threads e do processo gravam no log |
| CI podia travar 40 min num diálogo; actions por tag mutável; dependências sem versão fixa | timeouts, nenhum diálogo em modo automático, actions por SHA, versões fixas, `permissions: contents: read` |

### Médios e baixos corrigidos (resumo)

- **Interface e execução:** clique ignorado pelo jogo é repetido; botão "adiado" não é tratado como ausente; erros passageiros tolerados (3 seguidos pausam); tentativas de recuperação esquecidas quando a tela avança; teste de controles recusado com a rotina ativa; mira assistida que para é mostrada na interface.
- **Mira e calibração:**
  - incerteza preditiva correta da calibração;
  - correção geral só de viés;
  - reajuste com limites físicos e ancorado nas tabelas;
  - raio do alvo oculto pelo deslocamento máximo;
  - identidade do alvo por proximidade;
  - extrapolação das tabelas até +0,5;
  - arredondamento comum;
  - refinamento da busca física;
  - critério único de acerto.
- **Visão:** marcador em outra escala; supressão de vizinhos; barra de força contínua; ROI inválida avisada; ordenação das opções do menu.
- **Arquivos e dados:**
  - gravação atômica (configuração, modelo, glifos, atividades);
  - arquivos corrompidos restaurados da cópia do programa;
  - dados de conhecimento atualizados em versões novas só se o usuário não os editou;
  - instância única;
  - capturas limitadas a 200;
  - pasta do usuário mascarada nos logs;
  - nomes com `../` recusados;
  - colisão de nomes de atividades resolvida com sufixo.
- **Build:** `.bat` confere cada passo e recusa `dados/` dentro do pacote; ZIP com separadores padrão; SHA-256 do ZIP publicado; metadados de versão no `.exe`.

### Não corrigidos (conscientemente)

- Vetorizar a avaliação de candidatos (recomendação ~0,25 s). Com cache por turno, roda uma vez por turno; não é gargalo.
- `marker_to_feet` removido da configuração (não era usado). Diferença de altura entre marcadores de tipos
  diferentes continua não compensada.
- Usuários de versões anteriores (sem manifesto) mantêm as tabelas antigas; apagar `dados/knowledge` atualiza.
- Possíveis erros de digitação nas tabelas publicadas (50° d=10: 48,3; 30° d=17: 65,7) mantidos como na fonte.
- O runtime empacotado é o Python 3.12.10 (último 3.12 com instalador Windows); migrar para 3.13 depois.

## Redesign da interface

Feito com a skill `frontend-design` (marketplace oficial da Anthropic, lida em disco).

- **Sistema visual** (`gui/theme.py`): fundo cinza frio, painéis brancos, azul-aço para a ação principal e latão
  só nos números da mira. Tipografia: Bahnschrift (Windows) nos números e títulos, Segoe UI no texto. Todas as
  combinações de cor passam em contraste ≥ 4,5:1 (teste automático).
- **Faixa de estado** com cor, ícone e texto juntos para: jogo não encontrado, escolha o que jogar, pronto,
  executando, combate (seu turno / adversário), tela não reconhecida, pausado (com o que fazer), concluído,
  interrompido (com o que fazer) e parada de emergência.
- **Início** com três áreas: "O que jogar" (Instâncias | Partidas automáticas, quantas vezes, Iniciar/Pausar-Retomar/Parar),
  "Progresso" e "Mira". Atalhos F5/F6/F8. Calibração, diagnóstico e configurações em abas separadas.
- **Escala:** tamanhos ajustados ao DPI; janela limitada à área de trabalho.

Revisão pelas capturas da CI. Problemas encontrados e corrigidos:
1. Fontes dos estilos ignoradas (títulos, contadores e mira no tamanho do texto): `option_add("*Font")` anulava os estilos.
2. Em 150%, a janela passava da área de trabalho e o rodapé com a tecla de emergência ficava escondido.
3. Mostrador da mira desalinhado; sub-abas da calibração cortadas em 125%; status da janela cortado.
4. Histórico com nomes internos; números da mira antigos exibidos depois de parar; opções repetidas na calculadora.

Na segunda e na terceira rodada de capturas foram corrigidos:
- o histórico espremido em 150% (Progresso e Mira viraram um só painel, "Andamento");
- a mensagem de desconexão repetida;
- o título "Pausado: pausado pelo usuário".

Na última rodada (CI 38959754545), o auditor automático de layout não encontrou nenhum texto cortado nem nenhum elemento fora da janela em 100%, 125% e 150%.

## Resultados

| Verificação | Resultado |
|---|---|
| pytest no Linux (dev) | 150 aprovados, 1 pulado (interface: sem tkinter neste Linux) |
| pytest na CI Linux com Xvfb | aprovado, incluindo o teste de interface |
| pytest na CI Windows | 145 de 145 aprovados, 0 pulados, incluindo o teste de interface real |
| `.exe` extraído do ZIP, sem Python no PATH: `--selftest` | OK (recursos, mira, visão, fluxo simulado, tecla global pynput) |
| `.exe`: `--gui-smoke` | OK nos 16 pontos: demonstração, iniciar, faixa de estado, pausar (leituras param), retomar, abas, calculadora, parar sem travar, histórico, emergência. Atraso máximo da interface: 306 ms |
| `.exe` com a pasta do programa não gravável | OK: dados em `%LOCALAPPDATA%\DDClassicoBot` |
| ZIP | separadores `/`, sem `dados/` pessoais, SHA-256 publicado junto |
| Lint (pyflakes) | sem avisos |
| Simulação de precisão (15 batalhas, "jogo" com constantes diferentes do modelo) | sem calibração 35% de acerto; com calibração 85% (medido antes da auditoria; a auditoria não mudou o modelo físico) |

As CIs que falharam durante a auditoria, e por quê:
- **38953455994:** um teste com tolerância de tempo apertada demais para o relógio do Windows. Corrigido o teste; a trava do bot estava certa.
- **38953966244:** `$args` é uma variável automática do PowerShell, então o exe abria sem argumentos. Corrigido o workflow.
- **38954781477:** negar escrita com `icacls` impedia o Windows de criar o processo. A pasta não gravável passou a ser simulada de outro jeito.

A compilação final é a da CI da `main` (ver a mensagem de entrega).

## Limitações que dependem do jogo real

- Reconhecimento das telas, botões e marcadores (modelos capturados pelo usuário).
- Leitura de ângulo, vento e turno; tempo de carga da barra de força; teclas de virar (andam um pouco no DDTank).
- Precisão real da mira (as tabelas são de versões antigas; a calibração com disparos reais é necessária).
- Navegação até uma instância e uma execução completa; comportamento do jogo com várias etapas e recompensas.
- Regras do servidor sobre automação (site bloqueado na pesquisa).
- Escalas de exibição reais de um usuário (a CI simula 125% e 150% pelo Tk numa tela 1920×1080 em 100%).
