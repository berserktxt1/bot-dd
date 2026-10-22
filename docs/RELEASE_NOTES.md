**JonFlow** (antes *DDClássico Bot*): aplicativo para Windows 10/11 (64 bits) que joga partidas e instâncias PvE do DDTank (servidor DDClássico) sozinho, com mira calculada e calibrada pelos seus disparos e interface em português.

## Novidades da 0.5.3

Correção do caminho das expedições pelo Cais, a partir do log de um jogador (ainda não conferida no jogo):

- **O bot não para mais depois de clicar na instância.** Depois do clique em Formigueiro, a janela de escolha muda
  (a instância fica marcada e as dificuldades aparecem) e era lida como tela desconhecida ("Escolha da instância
  0,75, mínimo 0,80"): o bot nunca clicava na dificuldade e pausava em 20 s. Agora ele segue pela mesma janela
  quando ela continua a mais parecida e o botão da dificuldade aparece nela. O mínimo de 0,80 não mudou.
- **Caminho na ordem do jogo:** Central → Jogar → escolher a instância → instância → dificuldade → **OK** →
  **Início** → OK do lembrete → batalha. O OK passou a ser obrigatório e só é clicado depois da dificuldade:
  Formigueiro — Normal nunca começa no Fácil.
- **Nova tela opcional "Escolha da dificuldade"** em Calibração > Modelos (a janela de escolha depois do clique na
  instância). Os nomes da Calibração usam os do jogo: Central, Jogar, Início e lembrete.
- **Navegação mais rápida:** a tela é conferida a cada 0,25 s, as esperas depois de cada clique caíram para 0,6-0,8 s
  e, entre as telas antes da batalha, o bot pausa em 10 s (tela desconhecida) ou 12 s (botão ausente) em vez de 20
  e 30 s. Depois de Início, enquanto a batalha carrega, continua o limite de 20 s.
- **Pausas que explicam:** na escolha da instância e na sala que já tem uma instância escolhida o bot pausa dizendo o
  que foi clicado, o que faltou e o que capturar, sem clicar no X. O Histórico diz qual clique cada tela confirmou
  e em quanto tempo.
- **Derrota lida no meio da navegação** (sem batalha) não é mais tratada como resultado: antes o bot podia clicar em
  Sair no meio da sala.

## Novidades da 0.5.2

Revisão do combate automático, para o caso "entra na instância, mas não joga" (ainda não conferida no jogo):

- **O bot não fica mais parado em silêncio na batalha.** Se o seu turno não for reconhecido, ele avisa em 60 s
  com a semelhança do indicador de turno ("0,55, mínimo 0,80") e pausa em 2 min e meio. Sem nenhum alvo da etapa
  na tela, pausa depois de 3 turnos seus; com uma leitura ruim ou um disparo cancelado, depois de 2.
- **Diz qual leitura falhou:** em vez de só "confiança visual baixa", o Histórico diz se foi o vento (não lido ou
  sem direção), o seu personagem, o alvo ou o indicador de turno.
- **Confirma o disparo:** depois de cada tiro o turno precisa passar. Se continuar seu, o bot avisa que o jogo pode
  não ter recebido as teclas e, no segundo disparo assim, pausa. Quando passa, o Histórico mostra "disparo
  confirmado".
- **Recuperação mais segura:** na batalha e no aviso de instância difícil o bot nunca clica no X (sairia da
  batalha ou cancelaria a ida): pausa e explica.
- **Menos calibração no Formigueiro:** com a formiga e a rainha capturadas em Alvos, o marcador genérico de
  inimigo deixa de ser obrigatório.

## Novidades da 0.5.1

Correções do primeiro uso no cliente real (ainda não conferidas no jogo):

- **Caminho do Cais de Expedição:** as instâncias seguem o caminho do jogo, **lobby → Cais de Expedição → Criar
  sala → escolher a instância e a dificuldade na sala → Iniciar**. Em Calibração > Modelos entraram as telas
  **Cais de Expedição**, **Escolha da instância** e **Aviso de instância difícil (um jogador)** e os botões do
  Cais, **Criar sala**, o da sala que abre a escolha e o **confirmar do aviso**. A cada ida o bot escolhe a
  instância de novo, para nunca iniciar outra.
- **Aviso de jogador sozinho:** o bot pausa e explica, sem clicar em nada. Para seguir, clique em **Confirmar o
  aviso e continuar** no Início: a rotina continua da mesma tela. A permissão fica em Configurações > Automação e
  só vale para esse aviso.
- **Explicações quando o bot não age:** tela não reconhecida mostra as telas calibradas mais parecidas e a nota
  (também no Diagnóstico); na batalha, turno ilegível ou mira sem personagem, inimigo ou régua avisam o motivo e
  pausam se continuar assim.
- **Reconhecimento de telas:** um modelo que tinha memorizado uma escala errada voltava a ser procurado só ao
  reabrir o programa; agora a busca completa volta sozinha.
- **Força até 100** (antes 98). Os botões pagos **última fase**, **tentar novamente** e **carta paga** ficam
  bloqueados.

## Novidades da 0.5.0

- **Seis instâncias cadastradas**, sempre na lista do Início, mesmo antes de conectar o jogo: **Formigueiro** —
  Fácil e Normal, **Galinheiro** — Fácil, Normal e Difícil, e **Olimpíadas Bugou** — Normal, cada uma com a
  estratégia da sua dificuldade. O Castelo do Reino de Bugou saiu da lista principal (a estratégia dele continua
  valendo para uma atividade capturada pelo menu).
- **Nunca joga outra atividade no lugar:** se a opção da instância ou o botão da dificuldade não aparecer no menu
  do seu jogo, ou se duas opções parecidas casarem no mesmo lugar, o bot **pausa** e explica. A lista mostra o
  estado de cada atividade: pronta, calibrar, não achada (o bot procurou e não achou) ou indisponível (marcada por
  você em **Não aparece no meu jogo**).
- **Olimpíadas Bugou — Normal:** nos balões, mira onde a explosão soma mais pontos e nunca num balão verde; na
  corrida, os Bugous do time rival; contra o Boxiador, nunca atira perto do juiz. Sem as capturas obrigatórias
  dessas etapas, pausa em vez de atirar.
- **Calibração > Pendências:** lista o que falta para a atividade escolhida, com a instrução de cada item e
  **Fazer agora**. Na página Regiões, **Sugerir regiões** e **Ângulo pelas teclas** ajudam a marcar as regiões
  (sempre confirmadas por você). Os botões de dificuldade e a opção de cada instância são capturados uma vez só.
- **Detectar jogo sem a tela escura:** **Escolher pela imagem** mostra as janelas abertas com prévia; **Apontar
  com o mouse** tira o JonFlow da frente e um aviso pequeno no canto conta 3 s e escolhe a janela sob o mouse, sem
  clique.
- **Mira:** cada disparo guarda instância, dificuldade, etapa, alvo e cenário (modo da força e programa do jogo); a
  correção usa só disparos do mesmo cenário e pesa menos os marcados errado. O ângulo recomendado não fica trocando
  no meio do turno e a força recomendada vai até 98. Para quem instala agora, a barra de força padrão é de 3,33 s
  até 100, com 0,06 s até começar a encher (medidas de outro programa no DDClássico, ainda não conferidas).
- **Interface:** Início em três colunas (Atividades, detalhes e Andamento); as seis páginas da Calibração são
  escolhidas por botões em duas linhas (como abas, os nomes ficavam cortados no Windows); em 1080p a 150% o
  Histórico e a lista dos disparos voltaram a mostrar linhas. Corrigida a causa provável da janela parada por
  alguns segundos depois de Pausar (o ícone da faixa não existia na fonte e o Windows procurava em todas as fontes
  do sistema). A CI agora reprova a versão se a auditoria do layout achar algo cortado em 100%, 125% ou 150%.

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

> **Ainda não foi testado no DDClássico real.** Esta versão foi validada com testes automatizados, simulação e o `.exe` rodando no Windows da CI, sem o jogo. As etapas das instâncias vêm de guias de jogadores (2011–2017), notícias oficiais e vídeos, e precisam ser conferidas no cliente. Antes de usar o modo automático, leia os Termos do servidor: as regras sobre programas de automação não puderam ser verificadas.

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
- Testes no Windows: {TESTES}. Os pulados são os testes de layout (`test_gui_layout.py`), que precisam de tela 1920×1080: nessa rodada a tela do runner é 1024×768; eles rodam no passo com a escala em 125% e no Linux.
- `.exe` da pasta extraída do ZIP e `.exe` de arquivo único sozinho numa pasta vazia, os dois sem Python no PATH: autoteste e teste de interface aprovados.
- Estratégias das instâncias: validadas **só em simulação** (cenários fictícios com os papéis de cada perfil) e com imagens sintéticas.
- Interface: auditada em 1080p a 100%, 125% e 150% com as fontes do Windows (nada cortado).
- Detecção testada no Windows da CI com janelas e processos reais de teste (launcher que abre o jogo em outro processo, dois launchers abertos, janela cobrindo o jogo). **Não** testada com o launcher e o cliente reais do DDClássico.

SHA-256:
- `JonFlow.zip`: `{SHA_ZIP}`
- `JonFlow.exe`: `{SHA_EXE}`

Detalhes da auditoria, das correções e das limitações em `PROGRESS.md`.
