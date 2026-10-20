# Roteiro do primeiro teste no jogo real

Para a versão **0.4.4** (commit `97e4a24`). Nada daqui foi validado ainda com o launcher e o cliente do
DDClássico: este roteiro serve para descobrir **o que funciona e o que não funciona**. Faça na ordem e pare na
primeira etapa que falhar: as seguintes dependem dela.

**Regra geral:** se o bot fizer qualquer coisa que você não esperava, aperte **F12** (parada de emergência) e
anote. Exemplos: tecla enviada com outra janela em foco, clique fora do lugar, disparo fora do seu turno, dois
disparos no mesmo turno, clique em loja, botão pago ou no launcher.

## 0. Baixar e conferir (5 min)

1. Logado no GitHub (o repositório é privado), baixe `JonFlow.zip` dos *Assets* da Release v0.4.4 e extraia numa
   pasta sua, por exemplo `C:\JonFlow` (não use *Arquivos de Programas*).
2. Opcional: no PowerShell, `Get-FileHash JonFlow.zip` deve dar
   `D942DBA13F25866BAA587CFDB0BBD406B50AD9384C7304B3422B0022312F50D7`.
3. No `cmd`, dentro da pasta: `JonFlow.exe --selftest`. A saída deve terminar sem erro.
4. Anote: versão do Windows, resolução, **escala** (Configurações > Tela: 100/125/150%) e se o jogo ou o launcher
   rodam **como administrador**. Se rodarem, abra o JonFlow também como administrador: sem isso o Windows bloqueia
   as teclas e talvez até o F12.

## 1. Emergência sem o jogo (2 min)

Na aba **Início**, marque **Modo demonstração**, clique em **Iniciar (F5)** e depois aperte **F12** com outra janela
em foco. A rotina deve parar e o rodapé não deve avisar que a tecla está indisponível. Desmarque o modo
demonstração.

## 2. Detectar a janela (10 min)

1. Abra **só o launcher** e clique em **Detectar jogo**. Esperado: o JonFlow se minimiza e mostra "Launcher aberto:
   aguardando o jogo" (ou pergunta se a prévia é o jogo: responda que é o launcher).
2. Com essa janela aberta, entre no jogo pelo launcher. Esperado: "Jogo conectado" com a prévia **do jogo** (não da
   moldura do launcher). Clique em **Pronto**.
3. Feche o jogo e deixe o launcher: em ~3 s o topo deve dizer que está aguardando o jogo. Abra o jogo de novo: deve
   reconectar sozinho.
4. Se não achar: **Mostrar onde está o jogo** e clique sobre o jogo (o clique não pode chegar ao jogo; Esc cancela).

**Anote** o programa, a classe e o tamanho mostrados na prévia, e tire um print da janela do Detectar jogo.

## 3. Diagnóstico visual, sem calibração (5 min)

Na aba **Diagnóstico**, clique em **Analisar agora** com o jogo no lobby e depois com o JonFlow por cima de parte
do jogo. Esperado: a imagem é a do jogo **inteira**, sem faixas pretas, sem pedaço do JonFlow, nítida (atenção se
a escala do Windows for 125% ou mais). Se aparecer "outra janela está na frente do jogo", anote: o jogo não aceita
captura por trás e precisa ficar visível.

## 4. Primeira calibração (30–60 min)

Com a janela do jogo **num tamanho fixo** (não mude mais depois), na aba **Calibração** > **Capturar tela do jogo**,
siga o "Passo 4" do LEIA-ME. Para o primeiro teste, o mínimo é:

| Onde | O que capturar |
|---|---|
| Lobby / menu | modelos de tela do lobby e do menu de instâncias; botões de abrir instâncias, confirmar e iniciar |
| Menu de instâncias | **Detectar opções** e **Criar atividade** só para a instância escolhida (ver o passo 6) |
| Batalha | regiões de ângulo, vento, barra de força, turno e área de jogo; marcadores do seu personagem, de um inimigo, do turno e das setas do vento; modelo da tela de batalha |
| Números | ângulo e vento: **Aprender** com vários valores até cobrir 0 a 9 |
| Fim | modelos de etapa concluída, recompensa, vitória, derrota; botões continuar, sair, fechar e carta de recompensa |

Depois, em **Diagnóstico** marque **Atualizar ao vivo** durante uma batalha **jogada por você** e confira se
ângulo, vento, turno, personagem e inimigo batem com o jogo e com confiança alta. Recapture o que vier errado.

## 5. Controles e mira, sem o bot jogar (15 min)

1. **Configurações**: confira as teclas do jogo (ângulo e disparo), leia o aviso, marque a autorização do modo
   automático e clique em **Salvar configurações**.
2. Numa batalha, **no seu turno**, use **Calibração > Testar teclas do ângulo** (aperta ↑ e ↓, não atira).
   Esperado: OK no Histórico e o ângulo volta ao valor inicial. Repita com o foco num campo do launcher: deve ser
   **recusado** ("foco do teclado está no launcher").
3. Em **Diagnóstico**, ligue **Mira assistida ao vivo (só sugere, não joga)** e atire você mesmo seguindo a
   sugestão por alguns turnos. Em **Mira e disparos**, registre se cada tiro **Acertou**, **Errou** ou onde
   **Caiu na distância**. Anote se as sugestões são razoáveis.

## 6. Uma única instância, controlada (15 min)

Escolha a instância **mais fácil** que você vence sozinho com folga (o Formigueiro, se for o caso; para ele,
capture também os alvos em **Calibração > Alvos**). Use uma conta e um horário em que perder não importa.

1. No **Início**: escolha **Instâncias**, a atividade criada e **Uma vez**. Deve aparecer "✓ Calibração completa
   para esta atividade". Se faltar algo, a lista diz o quê.
2. Clique em **Iniciar (F5)** com o **dedo no F12** e acompanhe sem mexer no mouse.
3. Confira: entrou na instância certa? Esperou o seu turno? Um disparo por turno? Reconheceu o fim de cada etapa e
   a recompensa? Voltou ao lobby e parou sozinho?
4. Se pausar, leia a faixa colorida e o **Histórico** antes de clicar em **Retomar (F6)**. Pausar quando não tem
   certeza é o comportamento esperado.

Problema conhecido (não é do jogo): logo depois de **Pausar** ou **Parar**, a janela do JonFlow às vezes fica parada
por alguns segundos. Anote se acontecer, mas não precisa repetir o teste por isso.

## O que mandar se algo falhar

Feche o JonFlow antes de copiar os arquivos (o log é gravado até o fim).

| O quê | Onde |
|---|---|
| Etapa e passo do roteiro, o que você esperava e o que aconteceu, hora aproximada | texto |
| Registro do programa | `dados\logs\ddbot.log` (a pasta exata aparece em Configurações) |
| Print do JonFlow na hora (faixa colorida + Histórico) e, se for leitura errada, da aba Diagnóstico | print |
| Telas que o bot não reconheceu | as imagens mais recentes de `dados\capturas` |
| Detecção: programa, classe e tamanho da prévia; escala do Windows; jogo como administrador? | texto/print |
| Leitura errada: o arquivo de configuração | `dados\config.json` |

As capturas podem mostrar o seu nome no jogo e o chat: confira (ou tarje) antes de enviar. No log, a sua pasta de
usuário aparece como `%USERPROFILE%`.

## Resultado (preencha)

| Etapa | OK / falhou / não testado | Observação |
|---|---|---|
| 0. Download e autoteste | | |
| 1. F12 no modo demonstração | | |
| 2. Detectar (launcher → jogo, reconectar) | | |
| 3. Diagnóstico visual (captura inteira) | | |
| 4. Calibração e leituras ao vivo | | |
| 5. Teclas do ângulo / recusa no launcher / mira assistida | | |
| 6. Uma instância | | |
