<p align="center"><img src="assets/jonflow-logo.png" alt="JonFlow, bot para DDTank" width="440"></p>

# JonFlow

**JonFlow** (antes chamado *DDClássico Bot*) é um programa para Windows 10/11 (64 bits) que **joga sozinho as
partidas e instâncias PvE do DDTank no servidor DDClássico**. Você escolhe o que jogar, clica em **Iniciar** e o
bot entra na atividade, mira, atira, passa as etapas, reconhece vitória e derrota e recomeça quantas vezes você
pedir.

Seis instâncias já vêm cadastradas, com estratégia própria: **Formigueiro** (Fácil e Normal), **Galinheiro**
(Fácil, Normal e Difícil) e **Olimpíadas Bugou** (Normal). Outras instâncias e partidas você acrescenta capturando
o menu do seu jogo.

### Baixar (última versão)

| Arquivo | Link direto |
|---|---|
| **`JonFlow.zip`** (recomendado) | [**Baixar JonFlow.zip**](https://github.com/berserktxt1/bot-dd/releases/latest/download/JonFlow.zip) |
| `JonFlow.exe` (arquivo único) | [Baixar JonFlow.exe](https://github.com/berserktxt1/bot-dd/releases/latest/download/JonFlow.exe) |
| Conferência (SHA-256) | [SHA256SUMS.txt](https://github.com/berserktxt1/bot-dd/releases/latest/download/SHA256SUMS.txt) |

Todas as versões e notas: [**Releases**](https://github.com/berserktxt1/bot-dd/releases/latest). Os
programas prontos ficam **só** lá: na lista de arquivos do código (aba *Code*) não há `.exe`, e o
`build_windows.bat` que aparece ali serve só para quem quer compilar. Não precisa rodá-lo.

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

Baixe pelos [links do topo](#baixar-última-versão) ou na página de
[**Releases**](https://github.com/berserktxt1/bot-dd/releases/latest), em *Assets* (não use "Source code":
é só o código, sem o programa). Escolha **um** dos dois formatos:

| Formato | Como usar | Quando escolher |
|---|---|---|
| **`JonFlow.zip`** (recomendado) | Clique com o botão direito → *Extrair tudo*. Abra a pasta `JonFlow` e clique duas vezes em **`JonFlow.exe`**. Não tire o `.exe` de dentro da pasta: ele precisa da pasta `_internal` ao lado. | Na maioria dos casos. Abre mais rápido. |
| **`JonFlow.exe`** (arquivo único) | Coloque-o numa pasta só para ele (ele cria a pasta `dados` ao lado de si) e clique duas vezes. | Se você prefere um arquivo só. Abre alguns segundos mais devagar. |

Se aparecer **"O Windows protegeu o computador"**, clique em *Mais informações* → *Executar assim mesmo*. O aviso
aparece porque o programa não tem assinatura digital.

> Já usava o *DDClássico Bot*? Substitua os arquivos e **mantenha a pasta `dados`**. Se os seus dados estavam em
> `%LOCALAPPDATA%\DDClassicoBot`, o JonFlow continua usando essa pasta.

### Passo 2 — Experimentar sem o jogo (opcional, recomendado)

Quer conhecer o programa antes de configurar? Marque **Modo demonstração**, no canto superior direito. Na lista
**Atividades** as seis instâncias aparecem marcadas como **▶ demo**, mais uma partida de demonstração: escolha uma e
clique em **Iniciar**.

Nesse modo **nada é enviado ao jogo**: a faixa no alto diz "Demonstração" e os resultados são de um jogo simulado,
não do DDClássico. Desmarque quando for usar o jogo de verdade.

### Passo 3 — Conectar o jogo

1. Abra o DDClássico pelo launcher, como de costume.
2. No JonFlow, clique em **Detectar jogo** (no topo). A janela do JonFlow se minimiza para não atrapalhar.
3. O bot procura o jogo sozinho e mostra uma **prévia** para você conferir:

| O que está aberto | O que o bot faz |
|---|---|
| O jogo | Conecta e mostra a prévia. Confira e clique em **Pronto**. |
| Só o launcher | Avisa e **espera**: entre no jogo pelo launcher e ele conecta quando o jogo aparecer. |
| Algo que ele não tem certeza | Mostra a prévia e pergunta: **Sim, é o jogo**, **É o launcher** ou **Não é esta**. |
| Várias janelas parecidas | Mostra as prévias lado a lado: clique na que mostra o jogo, confira a imagem grande e clique em **Usar esta janela**. |
| Nada encontrado | Clique em **Escolher pela imagem**: aparecem as janelas abertas, cada uma com a prévia, as mais prováveis primeiro. Escolha a do jogo e clique em **Usar esta janela**. |

Se nem assim der certo, use **Apontar com o mouse**: a janela do Detectar jogo sai da frente e um aviso pequeno, no
canto da tela, conta 3 segundos. Deixe o mouse parado sobre o jogo (não precisa clicar: nada é enviado ao jogo) e a
janela volta com a prévia para você confirmar. A tela não escurece e nada fica por cima do jogo.

Pronto: daqui em diante o bot reencontra o jogo sozinho, mesmo se você fechar e abrir de novo pelo launcher.

<details>
<summary>Como ele reconhece o jogo? (curiosidade)</summary>

Ele usa várias pistas: qual programa abriu qual (o launcher abre o jogo), a janela que aparece enquanto ele espera,
a área interna onde o jogo é desenhado, o programa que você confirmou da última vez e as palavras "DDTank" e
"DDClássico" no título da janela (editáveis em `window.title_keywords`).
</details>

### Passo 4 — Ensinar o bot a enxergar (calibração)

Deixe a janela do jogo **num tamanho fixo** (se mudar o tamanho depois, refaça as capturas). Vá à aba
**Calibração**. À direita ficam o botão **Capturar tela do jogo** e seis páginas, escolhidas pelos botões logo
abaixo dele: **Pendências**, **Regiões**, **Modelos**, **Números**, **Menu** e **Alvos**. Em cada item: capture a
tela, **arraste o mouse sobre a imagem** para marcar a área e salve.

**O caminho mais fácil é seguir as Pendências.** No Início, escolha a atividade e clique em **Ver pendências**. A
página **Pendências** lista tudo o que falta para ela (os obrigatórios em vermelho) e, embaixo, como fazer o item
escolhido. **Fazer agora** abre a página certa já com o item escolhido e captura a tela, se ainda não houver imagem.

| O que capturar | Exemplos | Para que serve |
|---|---|---|
| **Regiões** | número do ângulo, vento, barra de força, indicador de turno, área de jogo | Dizer ao bot **onde** olhar na tela. |
| **Modelos de tela** (`estado_...`) | lobby, Cais de Expedição, sala, escolha da instância, aviso de instância difícil, menu de partidas, carregando, batalha, etapa concluída, recompensa, vitória, derrota, desconectado | Saber **em que tela** o jogo está. Capture um pedaço que só aparece naquela tela (na escolha da instância e no aviso, um pedaço da própria janela, não da sala atrás dela). |
| **Botões** | Cais de Expedição (no lobby), Criar sala, o botão da sala que abre a escolha da instância, confirmar, Iniciar, confirmar do aviso de instância difícil, abrir partidas, continuar, sair, fechar (X), carta de recompensa e os botões de dificuldade **Fácil**, **Normal** e **Difícil** | Saber **onde clicar**. Cada botão de dificuldade é capturado uma vez e serve para todas as instâncias. |
| **Marcadores** | seu personagem, um inimigo, indicador de turno, setas do vento | Achar **quem é quem** na batalha e o sentido do vento. |
| **Números** | ângulo e vento | Ler os **valores**. Marque o número, digite o valor que aparece e clique em **Aprender**. Repita com valores diferentes até cobrir os dígitos de 0 a 9. |

> 💡 No **vento**, marque **só os números**, sem a seta. O sentido vem das setas que você salvou em Modelos.

> 💡 Ajuda para as regiões, na página **Regiões**: numa batalha, **Sugerir regiões** procura sozinho a barra de força,
> o ângulo, o vento e a área de jogo; confira as sugestões e clique em **Usar as sugestões** (o que você já marcou não
> é trocado). No seu turno, **Ângulo pelas teclas** aperta ↑ e ↓ (não atira), vê onde o número mudou e mostra essa
> região na imagem; confira e clique em **Usar as sugestões** (nesse caso a região do ângulo é trocada).

Depois, ligue as atividades ao menu do seu jogo:

1. **Opções do menu (página Menu).** No jogo, entre numa sala pelo Cais de Expedição e abra a escolha da
   instância. No JonFlow, capture a tela e clique em
   **Detectar opções**. Escolha uma opção na lista e diga em **Esta opção é** o que ela é:
   - **Formigueiro**, **Galinheiro** ou **Olimpíadas Bugou**: a atividade cadastrada passa a usar essa captura (uma
     captura serve para todas as dificuldades da instância);
   - **Outra instância (nova atividade)** ou **Uma partida (nova atividade)**: dê um nome e a categoria. A partida
     aparece no Início em **Partidas automáticas**.

   Clique em **Salvar opção**. **Ver opções conhecidas nesta captura** marca as atividades cuja opção aparece no seu
   menu ("vista no menu").
2. **Alvos (página Alvos).** Numa batalha da instância, capture cada alvo (rainha, formiga, pintinho, chefe...) e
   cada estado especial, 2 ou 3 amostras de cada. As dificuldades da mesma instância usam as mesmas capturas. Sem
   essas imagens, o bot mira em qualquer inimigo visível e avisa. Nas **Olimpíadas Bugou** elas são obrigatórias
   (balão verde, Bugou do time rival e juiz): sem elas, o bot pausa nessas etapas em vez de atirar.

### Passo 5 — Conferir o que o bot enxerga

Na aba **Diagnóstico**, clique em **Analisar agora**. Veja se ele encontra o seu personagem, o inimigo, o vento, o
ângulo e o turno. Cada leitura mostra a **confiança**: se alguma estiver baixa ou errada, volte ao Passo 4 e
capture aquele item de novo (para números, ensine mais exemplos).

### Passo 6 — Autorizar o modo automático

Na aba **Configurações**, confira as teclas do jogo (ângulo e disparo), **leia o aviso**, marque a autorização do
modo automático e clique em **Salvar**. Sem essa autorização o bot não joga sozinho.

### Passo 7 — Jogar sozinho

Na aba **Início**:

1. Na lista **Atividades**, escolha a atividade. Ela tem duas seções, **Instâncias** e **Partidas automáticas**, e
   as seis instâncias cadastradas aparecem sempre, mesmo antes de conectar o jogo. Ao lado de cada uma aparece o
   estado:

   | Estado | Quer dizer |
   |---|---|
   | **✓ pronta** | A calibração está completa. Com o jogo conectado, pode iniciar. |
   | **! calibrar** | Falta calibrar algo. O painel ao lado mostra o primeiro item; **Ver pendências** mostra a lista. |
   | **✕ não achada** | O bot procurou a opção no menu do seu jogo e não achou. |
   | **✕ indisponível** | Você marcou **Não aparece no meu jogo**. |
   | **▶ demo** | Modo demonstração: roda no jogo simulado. |

   O painel ao lado mostra a estratégia, se o jogo está conectado, se a atividade já foi vista no seu menu e o
   que ainda falta calibrar.
2. Em **Quantas vezes**, escolha **Uma vez**, **Repetir** (e o número de vezes) ou **Até eu parar**.
3. Clique em **Iniciar** (F5).

O caminho das instâncias é o do jogo: **lobby → Cais de Expedição → Criar sala → na sala, escolher a instância e a
dificuldade → Iniciar**. A cada execução o bot escolhe a instância de novo dentro da sala, mesmo que ela já esteja
escolhida, para nunca iniciar outra.

Se, ao clicar em Iniciar, o jogo avisar que a **instância é difícil para um jogador**, o bot **pausa** e pergunta.
Para continuar sozinho mesmo assim, clique em **Confirmar o aviso e continuar** (aparece no Início durante a pausa;
a rotina segue da mesma tela, sem recomeçar). A permissão fica em Configurações > Automação e pode ser desmarcada.
Ela só vale para esse aviso, reconhecido pelo modelo que você capturou: não libera nenhum outro botão nem bloqueio.

Durante a rotina a janela do JonFlow se minimiza para não cobrir o jogo e volta sozinha quando a rotina pausa,
termina ou precisa de você.

Como acompanhar:

- A **faixa colorida no alto** diz o que o bot está fazendo e, quando precisa de você, o que fazer (sempre com
  ícone e texto, não só cor).
- **Andamento**: concluídas, vitórias, derrotas e batalhas. **Mira**: ângulo, força e vento durante o combate.
- **Histórico**: etapas, partidas, resultados, avisos e erros.

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

**As seis instâncias cadastradas têm estratégia própria.** O bot anuncia cada etapa no Histórico e escolhe o alvo
certo:

| Instância | O que o bot faz |
|---|---|
| **Formigueiro** (Fácil, Normal) | Formigas primeiro (onde há mais delas juntas), depois só a rainha. |
| **Galinheiro** (Fácil, Normal, Difícil) | O inimigo mais perto primeiro (eles avançam até você); as etapas mudam com a dificuldade (pintinhos, galos e galinhas, construção, chefe e gaiola). |
| **Olimpíadas Bugou** (Normal) | Nos balões, mira onde a explosão soma mais pontos e **nunca** num balão verde (tira pontos); na corrida, os Bugous do time rival; contra o Boxiador, **nunca** atira perto do juiz. O bot não acorda o juiz: se quiser fazer isso, faça você com a rotina pausada. |

- A etapa vale pelo que aparece na tela: se o chefe de uma etapa ainda está lá, o bot não passa para a próxima.
- Se a opção da instância ou o botão da dificuldade **não aparecer no menu do seu jogo**, o bot **pausa** e avisa que
  não encontrou: ele **nunca escolhe outra atividade** no lugar. A atividade passa a "✕ não achada".
- Se disparar várias vezes numa etapa sem diminuir os inimigos, pausa e pede para você conferir.
- As etapas vêm de guias de jogadores (2011–2017), notícias oficiais do DDClássico e vídeos, e **não foram
  conferidas no jogo** (veja [`docs/RESEARCH.md`](docs/RESEARCH.md)). Não há notícia oficial do Formigueiro Fácil
  nem do Galinheiro Fácil: se eles não existirem no seu jogo, clique em **Não aparece no meu jogo**.
- O **Castelo do Reino de Bugou** (outra instância, diferente das Olimpíadas) saiu da lista principal, mas a
  estratégia dele continua valendo para uma atividade capturada pelo menu. As demais instâncias ainda não têm
  estratégia própria: o bot mira o inimigo visível.

## Melhorar a mira

Cada disparo fica registrado na aba **Mira e disparos**, com a instância, a dificuldade, a etapa, o alvo e o
**cenário** (o jeito de controlar a força e o programa do jogo). Quanto mais você informar, melhor ele mira:

1. Escolha o disparo na tabela e marque **Acertou** ou **Errou**, ou digite em **Caiu na distância** onde o tiro
   caiu e clique em **Salvar**.
2. Com **3 disparos** medidos, o bot já corrige o erro que se repete. Só contam os disparos do mesmo cenário, e um
   disparo marcado errado por engano pesa menos.
3. Com **15 ou mais**, clique em **Reajustar o modelo** para recalcular as constantes físicas.

Na tabela, **Previsto** é onde o bot esperava que o tiro caísse e **Origem** diz de onde veio o disparo ("jogo
real" ou "simulado"). Disparos simulados, como os da demonstração, nunca corrigem a mira do jogo.

A calculadora da mesma aba mostra as opções de tiro (tabelas 20/30/50/65, tiro alto, tiro médio e busca física)
com a chance estimada de acerto de cada uma.

**Força do disparo.** Em Configurações > **Força do disparo**, o padrão para quem instala agora é **3,33 s** até a
força 100 e **0,06 s** até a barra começar a encher (medidas de outro programa no DDClássico, ainda não conferidas
pelo JonFlow). Quem já usava o JonFlow mantém o tempo que estava salvo. Se os tiros saem sempre fortes ou sempre
fracos, meça no seu jogo e ajuste esses dois valores.

## Problemas comuns

<details>
<summary><b>O botão Iniciar está cinza (desativado)</b></summary>

No jogo real, Iniciar só fica ativo com o **jogo conectado** (Passo 3), uma **atividade escolhida** e a
**calibração completa** para ela. O painel ao lado da lista mostra o que ainda falta; **Ver pendências** leva à
lista completa, com o como fazer de cada item.
</details>

<details>
<summary><b>A atividade aparece como "✕ não achada"</b></summary>

O bot abriu o menu do seu jogo e não encontrou a opção dessa instância (ou o botão da dificuldade), então pausou em
vez de escolher outra. Se a instância existe no seu jogo, capture a opção de novo em Calibração > **Menu** ou
clique em **Aparece no meu jogo**. Se ela realmente não existe no seu servidor, deixe como está.
</details>

<details>
<summary><b>O bot pausou sozinho</b></summary>

É de propósito: ele pausa quando não tem certeza. A faixa colorida e o Histórico dizem o motivo e o que fazer.
Motivos comuns: você trocou de janela, o foco ficou no launcher, uma tela não foi reconhecida (a imagem fica em
`dados\capturas`; capture essa tela em Calibração) ou outra janela cobriu o jogo. Resolva e clique em
**Retomar** (F6).

Quando a tela não é reconhecida, o Histórico diz quais telas calibradas mais se pareceram e com que nota (por
exemplo "mais parecidas: Lobby 0,62, Sala/preparação 0,55 (mínimo 0,80)"). Uma nota baixa em todas quer dizer que
falta capturar aquela tela em Calibração > Modelos; a aba Diagnóstico mostra as mesmas notas ao vivo
("telas_parecidas"). Na batalha, se o bot não consegue ler o seu turno ou mirar (personagem, inimigo ou régua não
encontrados), ele avisa o motivo e, se continuar assim, pausa.
</details>

<details>
<summary><b>O bot não encontra o jogo</b></summary>

Confira se o jogo já abriu (não só o launcher). Na janela do Detectar jogo, clique em **Escolher pela imagem** e
escolha a prévia que mostra o jogo. Se a prévia não aparecer (jogo minimizado ou coberto), use **Apontar com o
mouse** e deixe o mouse parado sobre o jogo por 3 segundos.
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
| **Atividade** | Algo que o bot sabe jogar: uma das instâncias cadastradas ou uma instância ou partida que você capturou do menu do seu jogo. |
| **Calibração** | Ensinar o bot a enxergar o seu jogo, capturando pedaços da tela. |
| **Pendências** | O que ainda falta calibrar para a atividade escolhida jogar sozinha (Calibração > Pendências). |
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
  125%), compila, extrai o ZIP numa pasta sem Python, roda o autoteste e o teste de interface do `.exe`, tira as
  capturas da interface em 100%, 125% e 150% e reprova se a auditoria do layout achar algo cortado, e publica o ZIP
  como artefato.
- **Publicar uma versão:** atualize `src/ddbot/__init__.py`, `packaging/version_info.txt`,
  `docs/RELEASE_NOTES.md` e `PROGRESS.md`, faça o merge na `main` e envie uma tag `vX.Y.Z`
  (`git tag vX.Y.Z && git push origin vX.Y.Z`). A CI compila, testa os dois executáveis e cria a Release com o
  ZIP, o `.exe`, `SHA256SUMS.txt`, `build-info.json` e os relatórios de teste.
- **Publicar sem a CI** (quando o GitHub Actions não roda): num PC com Windows, Python 3.12 64 bits, git e o
  [`gh`](https://cli.github.com/) logado, na pasta do projeto (qualquer branch), rode
  `powershell -ExecutionPolicy Bypass -File tools\compilar_local.ps1`. Ele compila a tag da versão numa pasta
  separada (`build-tag\vX.Y.Z`), roda os testes no Windows, testa os dois `.exe` sem Python no PATH, audita o
  layout em 100%, 125% e 150% (tela de 1920×1080 ou maior) e gera `SHA256SUMS.txt`, `build-info.json` e as notas.
  Deu tudo certo? Rode de novo com `-Publicar` para criar a Release.
- **Arquitetura:**
  - jogo e launcher: `detection.py` (detectar jogo), `game_window.py` (perfil, foco), `winapi.py`;
  - percepção: `capture.py`, `vision/`;
  - decisão: `aiming.py`, `physics.py`, `calibration.py`, `tracking.py`, `combat.py`, `activities.py`;
  - estratégias e atividades cadastradas: `strategy.py`, `catalog.py`, `readiness.py` (com os dados em
    `data/knowledge/instances.json` e `catalogo.json`);
  - execução: `automation/` (SendInput com travas);
  - interface: `service.py` e `gui/`.
- **Pesquisa e fontes:** [`docs/RESEARCH.md`](docs/RESEARCH.md). **Andamento:** [`PROGRESS.md`](PROGRESS.md).

### Fluxo de trabalho (Git Flow)

- `main`: produção; recebe merges de `release/*` e `hotfix/*` (com tag de versão).
- `develop`: integração; base para novas features.
- `feature/<nome>`: sai de `develop` e volta para `develop`.
- `release/<versão>`: sai de `develop`, vai para `main` (com tag) e `develop`.
- `hotfix/<versão>`: sai de `main`, vai para `main` (com tag) e `develop`.
