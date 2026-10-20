<p align="center"><img src="assets/jonflow-logo.png" alt="JonFlow, bot para DDTank" width="440"></p>

# JonFlow

**JonFlow** (antes chamado *DDClássico Bot*) é um programa para Windows 10/11 (64 bits) que **joga sozinho as
partidas e instâncias PvE do DDTank no servidor DDClássico**. Você escolhe o que jogar, clica em **Iniciar** e o
bot entra na atividade, mira, atira, passa as etapas, reconhece vitória e derrota e recomeça quantas vezes você
pedir.

> ⚠️ **Leia antes de usar.** Não foi possível verificar as regras do DDClássico sobre programas de automação (o site
> bloqueou o acesso durante a pesquisa). Muitos servidores punem bots com banimento. Leia os Termos do servidor
> antes de usar o modo automático. **O uso é por sua conta e risco.**

### Sumário

1. [Como o bot funciona (em 1 minuto)](#como-o-bot-funciona-em-1-minuto)
2. [Antes de começar](#antes-de-começar)
3. [Passo a passo](#passo-a-passo): baixar, experimentar, conectar, ensinar, conferir, autorizar, jogar
4. [Teclas de atalho](#teclas-de-atalho)
5. [O que o bot faz e o que ele nunca faz](#o-que-o-bot-faz-e-o-que-ele-nunca-faz)
6. [Melhorar a mira](#melhorar-a-mira)
7. [Problemas comuns](#problemas-comuns)
8. [Onde ficam os seus dados](#onde-ficam-os-seus-dados)
9. [Palavras que aparecem no programa](#palavras-que-aparecem-no-programa)
10. [Para quem vai compilar ou manter](#para-quem-vai-compilar-ou-manter)

---

## Como o bot funciona (em 1 minuto)

O bot faz o que você faria olhando para a tela, repetidas vezes:

```
  1. OLHA          2. ENTENDE                3. DECIDE              4. AGE
  copia a imagem → compara com as imagens  → calcula ângulo e     → aperta as teclas e
  do jogo          que VOCÊ ensinou          força do disparo       clica nos botões
                   (tela, turno, vento...)
```

O ponto principal é o passo 2: **o bot só reconhece o que você mostrou a ele.** Na primeira vez, você captura
pedaços da tela do seu próprio jogo (o botão "Iniciar", a tela de vitória, o número do vento...). Por isso ele
funciona com a sua resolução e a sua versão do jogo. Essa etapa se chama **calibração** e é feita uma vez só.

Se o bot não reconhecer alguma coisa, ele **pausa e explica o que aconteceu** em vez de chutar.

## Antes de começar

Você vai precisar de:

- ✅ Windows 10 ou 11 de 64 bits;
- ✅ o DDClássico instalado e a sua conta funcionando;
- ✅ uns minutos com o jogo aberto para a calibração (só na primeira vez).

**Não** precisa instalar Python nem nenhum outro programa.

---

## Passo a passo

### Passo 1 — Baixar e abrir

Baixe na página de **Releases** do repositório no GitHub. Escolha **um** dos dois formatos:

| Formato | Como usar | Quando escolher |
|---|---|---|
| **`JonFlow.zip`** (recomendado) | Clique com o botão direito → *Extrair tudo*. Abra a pasta `JonFlow` e clique duas vezes em **`JonFlow.exe`**. Não tire o `.exe` de dentro da pasta: ele precisa da pasta `_internal` ao lado. | Na maioria dos casos. Abre mais rápido. |
| **`JonFlow.exe`** (arquivo único) | Coloque-o numa pasta só para ele (ele cria a pasta `dados` ao lado de si) e clique duas vezes. | Se você prefere um arquivo só. Abre alguns segundos mais devagar. |

Se aparecer **"O Windows protegeu o computador"**, clique em *Mais informações* → *Executar assim mesmo*. O aviso
aparece porque o programa não tem assinatura digital.

> Já usava o *DDClássico Bot*? Substitua os arquivos e **mantenha a pasta `dados`**. Se os seus dados estavam em
> `%LOCALAPPDATA%\DDClassicoBot`, o JonFlow continua usando essa pasta.

### Passo 2 — Experimentar sem o jogo (opcional, recomendado)

Quer conhecer o programa antes de configurar? Marque **Modo demonstração**, no canto superior direito, e clique em
**Iniciar**. Aparecem o Formigueiro, o Galinheiro e o Castelo de Bugou (Normal) simulados, além de uma instância e
uma partida de demonstração.

Nesse modo **nada é enviado ao jogo**: a faixa no alto diz "Demonstração" e os resultados são de um jogo simulado,
não do DDClássico. Desmarque quando for usar o jogo de verdade.

### Passo 3 — Conectar o jogo

1. Abra o DDClássico pelo launcher, como de costume.
2. No JonFlow, clique em **Detectar jogo** (no topo). A janela do JonFlow se minimiza para não atrapalhar.
3. O bot procura o jogo sozinho e mostra uma **prévia** para você conferir:

| O que está aberto | O que o bot faz |
|---|---|
| O jogo | Conecta e mostra a prévia. |
| Só o launcher | Avisa e **espera**: entre no jogo pelo launcher e ele conecta quando o jogo aparecer. |
| Algo que ele não tem certeza | Pergunta: **Sim, é o jogo** ou **Não, é o launcher**. |
| Várias janelas parecidas | Mostra a lista com prévias para você escolher. |
| Nada encontrado | Use **Mostrar onde está o jogo**: a tela escurece e você clica sobre o jogo (o clique não chega ao jogo; Esc cancela). |

Pronto: daqui em diante o bot reencontra o jogo sozinho, mesmo se você fechar e abrir de novo pelo launcher.

<details>
<summary>Como ele reconhece o jogo? (curiosidade)</summary>

Ele usa várias pistas: qual programa abriu qual (o launcher abre o jogo), a janela que aparece enquanto ele espera,
a área interna onde o jogo é desenhado, o programa que você confirmou da última vez e as palavras "DDTank" e
"DDClássico" no título da janela (editáveis em `window.title_keywords`).
</details>

### Passo 4 — Ensinar o bot a enxergar (calibração)

Deixe a janela do jogo **num tamanho fixo** (se mudar o tamanho depois, refaça as capturas). Vá à aba
**Calibração** e clique em **Capturar tela do jogo**. Em cada item abaixo: **arraste o mouse sobre a imagem** para
marcar a área e salve.

| O que capturar | Exemplos | Para que serve |
|---|---|---|
| **Regiões** | número do ângulo, vento, barra de força, indicador de turno, área de jogo | Dizer ao bot **onde** olhar na tela. |
| **Modelos de tela** (`estado_...`) | lobby, menu de instâncias, menu de partidas, sala, carregando, batalha, etapa concluída, recompensa, vitória, derrota, desconectado | Saber **em que tela** o jogo está. Capture um pedaço que só aparece naquela tela. |
| **Botões** | abrir instâncias, abrir partidas, confirmar, iniciar, continuar, sair, fechar (X), carta de recompensa | Saber **onde clicar**. |
| **Marcadores** | seu personagem, um inimigo, indicador de turno, setas do vento | Achar **quem é quem** na batalha e o sentido do vento. |
| **Números** | ângulo e vento | Ler os **valores**. Marque o número, digite o valor que aparece e clique em **Aprender**. Repita com valores diferentes até cobrir os dígitos de 0 a 9. |

> 💡 No **vento**, marque **só os números**, sem a seta. O sentido vem das setas que você salvou em Marcadores.

Depois, monte a lista do que jogar:

1. **Opções do menu.** No jogo, abra o menu de instâncias (ou de partidas). No JonFlow, capture a tela e clique em
   **Detectar opções**. Escolha cada opção, dê um nome, escolha o tipo e a categoria e clique em
   **Criar atividade**. Só aparece no Início o que o seu jogo realmente mostra.
2. **Alvos das instâncias com estratégia** (Formigueiro, Galinheiro, Castelo do Reino de Bugou — Normal). Se o
   nome que você deu contém o nome da instância, a estratégia dela é escolhida sozinha (o Histórico avisa).
   Confira em Calibração > **Alvos**. Numa batalha dessa instância, capture cada alvo (rainha, formiga, frango,
   Barão, Midas...) e cada estado especial (escudo do Barão, escudo do Midas, pavio do Matias). Sem essas imagens,
   o bot mira em qualquer inimigo visível e avisa.

### Passo 5 — Conferir o que o bot enxerga

Na aba **Diagnóstico**, clique em **Analisar agora**. Veja se ele encontra o seu personagem, o inimigo, o vento, o
ângulo e o turno. Cada leitura mostra a **confiança**: se alguma estiver baixa ou errada, volte ao Passo 4 e
capture aquele item de novo (para números, ensine mais exemplos).

### Passo 6 — Autorizar o modo automático

Na aba **Configurações**, confira as teclas do jogo (ângulo e disparo), **leia o aviso**, marque a autorização do
modo automático e clique em **Salvar**. Sem essa autorização o bot não joga sozinho.

### Passo 7 — Jogar sozinho

Na aba **Início**:

1. Em **O que jogar**, escolha **Instâncias** ou **Partidas automáticas** e a atividade na lista.
   Logo abaixo aparece **o que ainda falta calibrar** (por exemplo "tela Lobby, números do vento"), com um atalho
   para a Calibração.
2. Em **Quantas vezes**, escolha **Uma vez**, **Repetir N vezes** ou **Até eu parar**.
3. Clique em **Iniciar** (F5).

Durante a rotina a janela do JonFlow se minimiza para não cobrir o jogo e volta sozinha quando a rotina pausa,
termina ou precisa de você.

Como acompanhar:

- A **faixa colorida no alto** diz o que o bot está fazendo e, quando precisa de você, o que fazer (sempre com
  ícone e texto, não só cor).
- **Progresso**: concluídas, vitórias, derrotas e batalhas. **Mira**: ângulo, força e vento durante o combate.
- **Histórico**: partidas, resultados, avisos e erros.

## Teclas de atalho

| Tecla | O que faz |
|---|---|
| **F5** | Iniciar |
| **F6** | Pausar / Retomar |
| **F8** | Parar a rotina |
| **F12** | 🛑 **Parada de emergência**: funciona a qualquer momento, mesmo com o jogo em foco (a tecla pode ser trocada) |

O rodapé mostra se a tecla de emergência está funcionando. Se o Windows não deixar registrá-la, o modo automático
no jogo fica bloqueado.

## O que o bot faz e o que ele nunca faz

**Segurança em primeiro lugar.** Na dúvida, o bot para e explica.

| ✅ Ele faz | 🚫 Ele nunca faz |
|---|---|
| Joga sozinho atividades **PvE/solo**. | Jogar sozinho contra outros jogadores (fila/PvP). Ali use a *Mira assistida ao vivo* (aba Diagnóstico), que só **sugere** ângulo e força. |
| Envia teclas e cliques **só com o jogo em foco**, no máximo **um disparo por turno**. | Comprar itens, gastar moeda premium ou entrar em ranqueadas. Botões como comprar e loja ficam bloqueados (para liberar um botão pago específico, digite o nome dele em Configurações). |
| Só aceita uma tela depois de reconhecê-la em leituras seguidas (uma explosão ou animação não conta vitória nem dispara de novo). | Apertar teclas às cegas. Se uma tela ou botão não aparece, ele só fecha avisos pelo botão **X** que você capturou; se não resolver, **pausa**, mostra o motivo e salva a imagem em `dados\capturas`. |
| **Pausa** se você trocar de janela (Alt+Tab) ou minimizar o jogo, e espera você clicar em Retomar. | Mandar comandos ao launcher: só clica dentro da área do jogo e só envia teclas com o foco dentro do jogo. Se o foco estiver no launcher, pausa e pede para você clicar uma vez no jogo. |
| Com o inimigo invisível, usa a última posição vista e calcula quanto ele pode ter andado. | Atirar às cegas: se a incerteza for grande, espera o inimigo reaparecer. |
| Pede a imagem à própria janela do jogo, mesmo com outra janela por cima. | Ler a janela errada: se o jogo não permitir e outra janela cobrir o jogo, pausa e avisa. |
| Para e avisa se o jogo desconectar. | Fazer login sozinho. |

**Instâncias com estratégia própria** (Formigueiro, Galinheiro, Bugou Normal): o bot anuncia cada etapa no
Histórico e escolhe o alvo certo (só a rainha no fim do Formigueiro; o mais perto no Galinheiro). No Castelo de
Bugou, não atira no Barão de frente com escudo, usa só tiro por cima no Midas com escudo e **pausa** quando o Matias
acende o pavio (só o gelo resolve, e o bot não usa itens). Se disparar várias vezes numa etapa sem diminuir os
inimigos, pausa e pede para você conferir. As etapas vêm de guias de jogadores de 2012–2017 e **não foram
confirmadas no DDClássico** (veja [`docs/RESEARCH.md`](docs/RESEARCH.md)). As demais instâncias ainda não têm
estratégia própria.

## Melhorar a mira

Cada disparo fica registrado na aba **Mira e disparos**. Quanto mais você informar, melhor ele mira:

1. Marque **Acertou** ou **Errou**, ou digite onde o tiro caiu.
2. Com **3 disparos** medidos, o bot já corrige o erro que se repete.
3. Com **15 ou mais**, clique em **Reajustar modelo** para recalcular as constantes físicas.

A calculadora da mesma aba mostra as opções de tiro (tabelas 20/30/50/65, tiro alto, tiro médio e busca física)
com a chance estimada de acerto de cada uma.

## Problemas comuns

<details>
<summary><b>O botão Iniciar está cinza (desativado)</b></summary>

No jogo real, Iniciar só fica ativo com o **jogo conectado** (Passo 3), uma **atividade escolhida** e a
**calibração completa** para ela. Veja logo abaixo da lista do Início o que ainda falta calibrar; o atalho leva
direto à Calibração.
</details>

<details>
<summary><b>O bot pausou sozinho</b></summary>

É de propósito: ele pausa quando não tem certeza. A faixa colorida e o Histórico dizem o motivo e o que fazer.
Motivos comuns: você trocou de janela, o foco ficou no launcher, uma tela não foi reconhecida (a imagem fica em
`dados\capturas`; capture essa tela em Calibração) ou outra janela cobriu o jogo. Resolva e clique em
**Retomar** (F6).
</details>

<details>
<summary><b>O bot não encontra o jogo</b></summary>

Confira se o jogo já abriu (não só o launcher) e use **Mostrar onde está o jogo** na janela do Detectar jogo para
clicar sobre ele.
</details>

<details>
<summary><b>Leituras erradas no Diagnóstico (ângulo, vento, turno)</b></summary>

Confira se a janela do jogo está do mesmo tamanho de quando você calibrou. Recapture a região ou o modelo
problemático e, para números, ensine mais exemplos em Calibração > Números.
</details>

<details>
<summary><b>A escala do Windows está em 125% ou 150%</b></summary>

Desde a 0.4.4 a captura acompanha a escala do Windows: a imagem do jogo é ampliada do mesmo jeito que o Windows a
mostra na tela. Se mesmo assim a imagem vier incompleta, o bot pausa e explica em vez de usar a imagem errada.
Isso foi testado com janelas de teste em 125%, **ainda não com o cliente do DDClássico**: se tiver problema,
conte e envie o arquivo `dados\logs\ddbot.log`.
</details>

<details>
<summary><b>"O Windows protegeu o computador"</b></summary>

Clique em *Mais informações* → *Executar assim mesmo*. O programa não tem assinatura digital; confira o
`SHA256SUMS.txt` da Release se quiser ter certeza de que o arquivo é o publicado.
</details>

<details>
<summary><b>A tecla de emergência não funciona</b></summary>

O rodapé avisa quando o Windows não deixa registrar a tecla (outro programa pode estar usando). Troque a tecla em
Configurações. Enquanto ela não funcionar, o modo automático no jogo fica bloqueado.
</details>

## Onde ficam os seus dados

Tudo fica na pasta **`dados`**, ao lado do `JonFlow.exe`: configuração, imagens capturadas, atividades, histórico
de disparos e registros (`dados\logs\ddbot.log`). O caminho exato aparece na aba Configurações.

- **Pasta sem permissão de gravar** (por exemplo, dentro de *Arquivos de Programas*): os dados vão para
  `%LOCALAPPDATA%\JonFlow` e o Histórico avisa.
- **Levar para outro computador:** copie a pasta `JonFlow` inteira.
- **Atualizar o programa:** substitua os arquivos e **mantenha a pasta `dados`**. As tabelas novas entram sozinhas,
  a menos que você as tenha editado.
- **Configuração corrompida** (por exemplo, editada à mão): o programa abre com os valores padrão e guarda o
  arquivo antigo como `config.corrompido-<data>.json`.

> 🔒 As capturas (`dados\capturas`, só as 200 mais recentes) podem mostrar seu nome no jogo e o chat. Confira antes
> de enviar a pasta `dados` para alguém. Nos registros, a sua pasta de usuário aparece como `%USERPROFILE%`.

## Palavras que aparecem no programa

| Palavra | O que quer dizer |
|---|---|
| **Atividade** | Algo que o bot sabe jogar: uma instância ou um tipo de partida do menu do seu jogo. |
| **Calibração** | Ensinar o bot a enxergar o seu jogo, capturando pedaços da tela. |
| **Região** | Uma área da tela onde o bot deve olhar (por exemplo, onde fica o número do vento). |
| **Modelo** | Uma imagem pequena que o bot procura na tela (uma tela, um botão, um personagem). |
| **Confiança** | O quanto o bot tem certeza de uma leitura. Leitura com confiança baixa não faz o bot agir. |
| **Launcher** | O programa que você usa para entrar no DDClássico. O bot nunca clica nele. |
| **PvE** | Jogar contra o computador (monstros, instâncias). O bot só joga sozinho PvE. |
| **PvP** | Jogar contra outras pessoas. O bot não joga sozinho; só sugere a mira. |
| **Modo demonstração** | Jogo simulado para conhecer o programa. Nada é enviado ao jogo. |

---

## Para quem vai compilar ou manter

Agentes de código (Claude Code, Codex etc.) devem ler também o [`AGENTS.md`](AGENTS.md).

- **Pastas:** código em `src/ddbot` (o pacote Python manteve o nome `ddbot`), testes em `tests`, documentação em
  `docs`, logo e ícone em `assets` (`jonflow-icon.svg` é o original; os PNG e o `.ico` saem dele).
- **Compilar no Windows:** instale o Python 3.12 64 bits e clique duas vezes em **`build_windows.bat`**. O script
  cria um ambiente isolado, instala `requirements.txt` e `requirements-dev.txt`, roda os testes e gera:
  - `release\JonFlow\JonFlow.exe` (pasta) e `release\JonFlow.zip`;
  - `release\JonFlow.exe` (arquivo único).
- **Rodar do código-fonte:** `pip install -r requirements.txt` e `python -m ddbot` (com `PYTHONPATH=src`).
  - `--selftest`: verifica recursos, mira, visão e um fluxo simulado completo.
  - `--simulate N`: compara a precisão com e sem calibração em N batalhas simuladas.
  - `--gui-smoke S`: abre a interface e exercita Iniciar/Pausar/Retomar/Parar/Emergência em modo simulado.
- **Testes:** `python -m pytest -q tests`. O que cada um cobre: [`docs/TESTES.md`](docs/TESTES.md).
- **CI:** `.github/workflows/windows-build.yml` testa no Linux e no Windows (também com a escala do Windows em
  125%), compila, extrai o ZIP numa pasta sem Python, roda o autoteste e o teste de interface do `.exe` e publica
  o ZIP como artefato.
- **Publicar uma versão:** atualize `src/ddbot/__init__.py`, `packaging/version_info.txt`,
  `docs/RELEASE_NOTES.md` e `PROGRESS.md`, faça o merge na `main` e envie uma tag `vX.Y.Z`
  (`git tag vX.Y.Z && git push origin vX.Y.Z`). A CI compila, testa os dois executáveis e cria a Release com o
  ZIP, o `.exe`, `SHA256SUMS.txt`, `build-info.json` e os relatórios de teste.
- **Arquitetura:**
  - jogo e launcher: `detection.py` (detectar jogo), `game_window.py` (perfil, foco), `winapi.py`;
  - percepção: `capture.py`, `vision/`;
  - decisão: `aiming.py`, `physics.py`, `calibration.py`, `tracking.py`, `combat.py`, `activities.py`;
  - execução: `automation/` (SendInput com travas);
  - interface: `service.py` e `gui/`.
- **Pesquisa e fontes:** [`docs/RESEARCH.md`](docs/RESEARCH.md). **Andamento:** [`PROGRESS.md`](PROGRESS.md).

### Fluxo de trabalho (Git Flow)

- `main`: produção; recebe merges de `release/*` e `hotfix/*` (com tag de versão).
- `develop`: integração; base para novas features.
- `feature/<nome>`: sai de `develop` e volta para `develop`.
- `release/<versão>`: sai de `develop`, vai para `main` (com tag) e `develop`.
- `hotfix/<versão>`: sai de `main`, vai para `main` (com tag) e `develop`.
