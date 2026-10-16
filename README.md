# DDClássico Bot

Aplicativo para Windows 10/11 (64 bits) que joga **partidas e instâncias PvE do DDClássico sozinho**. Você escolhe
a atividade, clica em **Iniciar** e o bot navega pelos menus, entra na atividade, reconhece os turnos, mira e
atira, avança as etapas, reconhece vitória e derrota e recomeça até completar a quantidade configurada.

> **Aviso importante.** As regras do DDClássico sobre programas de automação **não puderam ser verificadas**
> (o site bloqueou o acesso durante a pesquisa). Muitos servidores punem o uso de bots com banimento. Leia os
> Termos do servidor antes de usar o modo automático. O uso é por sua conta e risco.

---

## Para quem vai só usar

### 1. Abrir

1. Baixe o arquivo **`DDClassicoBot.zip`** e extraia em uma pasta (botão direito → *Extrair tudo*).
2. Abra a pasta `DDClassicoBot` e clique duas vezes em **`DDClassicoBot.exe`**.
   Não precisa instalar Python nem nenhum outro programa.
3. Se o Windows mostrar "O Windows protegeu o computador", clique em *Mais informações* → *Executar assim mesmo*
   (o executável não tem assinatura digital).

Quer conhecer a tela antes de configurar o jogo? Marque **Demonstração (simulada, não usa o jogo)** no topo e
clique em **Iniciar**. Nesse modo nada é enviado ao jogo.

### 2. Primeira configuração (uma vez só)

O bot "enxerga" o jogo por imagens que **você captura do seu próprio cliente**. Por isso funciona com a sua
resolução e a sua versão do jogo, e nada é inventado. Com o jogo aberto, deixe a janela num tamanho fixo e:

1. No topo, escolha a **janela do jogo** (clique em *Atualizar* se ela não aparecer).
2. Aba **Calibração** → *Capturar tela do jogo*. Arraste o mouse sobre a imagem para selecionar e salve:
   - **Regiões:** número do ângulo, indicador de vento, barra de força, indicador de turno e a área de jogo
     (a "régua" de 10 partes da tela).
   - **Modelos de tela** (`estado_...`): capture um pedaço característico de cada tela: lobby, menu de
     instâncias, menu de partidas, sala, carregando, batalha, etapa concluída, recompensa, vitória, derrota e
     desconectado.
   - **Botões:** abrir instâncias, abrir partidas, confirmar, iniciar, continuar, sair, fechar (X) e a carta de
     recompensa.
   - **Marcadores:** o marcador do seu personagem, de um inimigo, o indicador de turno e as setas do vento.
   - **Números:** selecione o ângulo e o vento, digite o valor que aparece e clique em *Aprender*. Repita com
     valores diferentes até cobrir os dígitos de 0 a 9.
3. **Opções do menu.** Abra no jogo o menu de instâncias (ou de partidas), capture e clique em *Detectar opções*.
   Escolha cada opção na lista, dê um nome, escolha o tipo e a categoria e clique em *Criar atividade*. É assim que
   a lista do Início é montada: só aparece o que o seu jogo realmente mostra.
4. Aba **Diagnóstico** → *Analisar agora*: confira se o bot encontra seu personagem, o inimigo, o vento, o ângulo
   e o turno. Cada leitura mostra a confiança.
5. Aba **Configurações**: confira as teclas (ângulo, disparo), leia o aviso, marque a autorização do modo
   automático e clique em *Salvar*.

### 3. Jogar sozinho

Na aba **Início**:

1. Escolha **Partidas automáticas** ou **Instâncias** e a atividade na lista.
2. Escolha **Uma vez**, uma **Quantidade** ou **Contínuo (até parar)**.
3. Clique em **Iniciar**. Use **Pausar**, **Retomar** e **Parar** quando quiser.
4. **Parada de emergência: tecla F12**, a qualquer momento, mesmo com o jogo em foco.

A tela mostra a etapa atual, o progresso, o turno, o alvo, o ângulo, a força, o vento, a sugestão de mira e os
contadores de vitórias, derrotas e atividades concluídas. O histórico lista partidas, resultados e erros.

### O que o bot faz e o que ele não faz

- Joga sozinho só atividades **PvE/solo**. Em partidas contra outros jogadores (fila/PvP) ele **não** joga sozinho;
  use a *Mira assistida ao vivo* (aba Diagnóstico), que só sugere ângulo e força.
- **Nunca** compra itens, gasta moeda premium ou entra em ranqueadas. Botões como comprar e loja ficam bloqueados.
  Para liberar um botão pago específico, digite o nome dele em Configurações.
- Só envia teclas e cliques com a **janela do jogo em foco**, no máximo **um disparo por turno**, e não repete o
  mesmo clique em sequência.
- Se não reconhecer a tela, um botão não aparecer ou a tela não avançar, ele tenta recuperar pelos meios normais
  (fechar aviso, ESC). Se não conseguir, **pausa**, mostra o motivo e salva a imagem em `dados\capturas`.
- Com o inimigo invisível, usa a última posição vista e calcula o quanto ele pode ter andado. Se a incerteza for
  grande, espera o inimigo reaparecer em vez de atirar às cegas.
- Desconexão: para e avisa. Ele não faz login sozinho.

### Melhorar a mira

Cada disparo fica registrado na aba **Mira e disparos**. Marque *Acertou* ou *Errou*, ou digite onde o tiro
caiu. Com 3 disparos medidos o bot já corrige o erro sistemático; com 15 ou mais, *Reajustar modelo* recalcula as
constantes físicas. A calculadora da mesma aba mostra as opções (tabelas 20/30/50/65, tiro alto, tiro médio e
busca física) com a probabilidade estimada de acerto.

### Onde ficam os dados

Tudo fica na pasta **`dados`**, ao lado do `DDClassicoBot.exe`: configuração, imagens capturadas, atividades,
histórico de disparos e registros (`dados\logs\ddbot.log`). Para levar para outro computador, copie a pasta
`DDClassicoBot` inteira. Para atualizar o programa, substitua os arquivos e **mantenha a pasta `dados`**.

---

## Para quem vai compilar ou manter

- Código em `src/ddbot`, testes em `tests`, documentação em `docs`.
- **Compilar no Windows:** instale o Python 3.12 64 bits e clique duas vezes em **`build_windows.bat`**. O script
  cria um ambiente isolado, instala `requirements.txt` e `requirements-dev.txt`, roda os testes e gera:
  - `release\DDClassicoBot\DDClassicoBot.exe`
  - `release\DDClassicoBot.zip`
- **CI:** `.github/workflows/windows-build.yml` testa no Linux e no Windows, compila, extrai o ZIP numa pasta sem
  Python, roda o autoteste e o teste de interface do `.exe` e publica o ZIP como artefato.
- **Rodar do código-fonte:** `pip install -r requirements.txt` e `python -m ddbot` (com `PYTHONPATH=src`).
  - `--selftest`: verifica recursos, mira, visão e um fluxo simulado completo.
  - `--simulate N`: compara a precisão com e sem calibração em N batalhas simuladas.
  - `--gui-smoke S`: abre a interface e exercita Iniciar/Pausar/Retomar/Parar/Emergência em modo simulado.
- **Testes:** `python -m pytest -q tests`. Detalhes em [`docs/TESTES.md`](docs/TESTES.md).
- **Arquitetura:**
  - percepção: `capture.py`, `vision/`;
  - decisão: `aiming.py`, `physics.py`, `calibration.py`, `tracking.py`, `combat.py`, `activities.py`;
  - execução: `automation/` (SendInput com travas);
  - interface: `service.py` e `gui/`.
- **Pesquisa e fontes:** [`docs/RESEARCH.md`](docs/RESEARCH.md). **Andamento:** [`PROGRESS.md`](PROGRESS.md).

### Fluxo de trabalho (Git Flow)

- `main` — produção; recebe merges de `release/*` e `hotfix/*` (com tag de versão).
- `develop` — integração; base para novas features.
- `feature/<nome>` — sai de `develop`, volta para `develop` via PR.
- `release/<versão>` — sai de `develop`, vai para `main` (com tag) e `develop`.
- `hotfix/<versão>` — sai de `main`, vai para `main` (com tag) e `develop`.
