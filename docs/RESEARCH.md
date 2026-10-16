# Pesquisa — referências e conclusões

Este documento junta a pesquisa de 2026-10-15 (tabelas, regras de vento e modelo físico) e a de 2026-10-16
(bots, calculadoras e fórmulas citados no pedido). A lista de fontes legível pelo programa fica em
`data/knowledge/sources.json`.

## Como a pesquisa orientou a implementação

| Ideia encontrada | Origem | Onde está no bot |
|---|---|---|
| Distância em 1/10 da largura da tela visível | guias TechTudo, ddcalc, qozi | `ruler.units_per_screen`, `vision/perception.py::to_ruler` |
| Vento relativo ao disparo (inverte quando o alvo está à esquerda) | qozi, ddcalculator | `to_ruler` (testado em `tests/test_vision.py`) |
| Tabelas 20/30/50/65 e fórmulas Alto (95, 90−d±2v) e Médio (60, 90−2d±2v) | TechTudo, ddtankdicaset, ddladora, BoomShot | `data/knowledge/angle_tables.json`, `knowledge.py` |
| Gravidade + arrasto linear + vento como aceleração | caderno-de-tiro, BoomShot, Stardust, 52pojie | `physics.py` (ajuste em `tools/fit_model.py`) |
| Tabelas variam por servidor → calibrar com disparos reais | 52pojie × TechTudo (65° difere 1–2 pontos) | `calibration.py` (correção por método + reajuste das constantes) |
| Ângulo inteiro; a fração vai para a força | TechTudo 2013, mesterddtank | `aiming.py::_evaluate` resolve a força para o ângulo inteiro |
| Máquina de estados que lê a tela a cada iteração | qozi (`need*`), DavidBarishev (`FarmAction`) | `activities.py::ActivityRunner` |
| Força por leitura da barra (malha fechada) e por tempo como alternativa | qozi (pixel), HexorCatZ (tempo) | `game_io.py::KeyboardShooter.charge_and_fire` (`power_mode` visual/timed, `power_offset`) |
| Ângulo por dígitos aprendidos + verificação após ajustar | HexorCatZ, qozi | `vision/digits.py`, `KeyboardShooter.set_angle` |
| Passar o turno quando não consegue ler o ângulo | qozi | tecla `automation.keys.pass_turn` |
| Detecção de travamento e recuperação | qozi (log parado 240 s) | `stuck_timeout_s`, `_recover` (fecha aviso/ESC, depois pausa) |
| Guardar a tela das falhas para re-treino | qozi | `on_failure_frame` → `dados/capturas/falha_*.png` |

**Licenças.** Nenhum código de terceiros foi copiado: qozi/windors, HexorCatZ, BoomShot e ddcalculator não têm
licença (todos os direitos reservados); DavidBarishev é GPL-3.0 e Stardust é AGPL-3.0; ddladora declara MIT sem
arquivo de licença. Só ideias e fórmulas de conhecimento comum entre jogadores foram reimplementadas.

**O que não foi possível pesquisar.** O site do DDClássico (ddclassico.com) respondeu HTTP 403 (Cloudflare) em
todas as tentativas, então as regras do servidor, a lista de instâncias, chefes, armas, pets, pérolas e efeitos como
invisibilidade **não foram confirmados**. Por isso:

- o modo automático vem desligado e exige confirmação das regras em Configurações;
- a lista de instâncias/partidas não é fixa no código: ela é criada a partir das opções que o próprio cliente
  mostra (Calibração > Opções do menu);
- armas/munições são parâmetros configuráveis (`weapons` na configuração) a calibrar no cliente;
- a invisibilidade é tratada só com o que a tela mostra (última posição + incerteza crescente), sem nenhuma
  tentativa de revelar o alvo.

**Modalidades.** A matéria do Mobile Gamer (08/2026) confirma PvE (instâncias), PvP por turnos, ranqueadas e
partidas casuais. O bot só joga sozinho atividades das categorias PvE/solo. Fila e PvP envolvem outros jogadores:
nesses casos o bot oferece apenas a mira assistida e nunca entra sozinho em ranqueadas.

---

## Pesquisa de 2026-10-15 (resumo)

- Tabelas 30°/50°/65° (distância 1–20) e fórmulas de vento: ddtankdicaset (2013), webpixel5 (2013), TechTudo (2015).
- Modelo físico com arrasto linear: caderno-de-tiro (GitHub), RMSE de 1,08 de força nas tabelas.
- Nosso ajuste (`tools/fit_model.py`) agora inclui também a tabela de 20°: RMSE 1,01 de força nas 80 células;
  76 de 80 dentro de ±2 (detalhes em `data/knowledge/model_params.json`).

---

## Pesquisa de 2026-10-16 (bots, calculadoras e fórmulas)

Data da pesquisa: 2026-10-16. Toda afirmação traz a fonte. Licenças conferidas na página do repositório e na API do GitHub (`/repos/{r}` e `/repos/{r}/license`). Quando a API devolve `license: null` / 404, o repositório é tratado como **sem licença**, ou seja, todos os direitos reservados. Nesse caso só reaproveitamos ideias e não copiamos código.

---

### 1. qozi/ddtank-onhook (fork de windors/ddtank)

- **URL:** https://github.com/qozi/ddtank-onhook (fork de https://github.com/windors/ddtank)
- **Licença:** **sem licença**. A API retorna `license: null` e `/license` dá 404, tanto no fork quanto no repositório original. Não copiar código.
- **Linguagem:** Java (Spring Boot com Thymeleaf). Automação via plugin COM chinês **大漠 (Dm)**, 32 bits, acessado pela ponte Jacob. Hotkeys globais via JIntelliType. Fonte: README.
- **Estado:** o autor diz que está sem tempo e que planeja uma refatoração (README). O último push foi em 2024-04-18.
- **Escopo:** farm de **instâncias PvE** (副本) no cliente chinês 弹弹堂, versões "10.4", "2.3" e "2.4".

#### Como funciona (lido do código-fonte)

**Janela e coordenadas**
- O Dm "faz bind" no handle da janela, o que permite captura em segundo plano.
- Se o modo de fundo não funciona (navegador com kernel "极速"), o bot cai para modo de primeiro plano. Nesse modo ele **corrige o offset**: procura uma imagem de referência ("需要激活窗口.bmp" ou "矫正标识.bmp") e subtrai a posição padrão dela, (465,343) ou (381,572). O resultado vira `offsetX/offsetY`, aplicado ao mouse e às buscas (`DDTankCoreTask.init`).
- Todas as coordenadas são fixas, num cliente de cerca de 1000×600.

**Separação percepção / decisão / execução**
- `DDTankPic`: percepção. Busca de imagem, OCR e busca de cor.
- `DDTankOperate`: execução e decisão local. Escolhe mapa, ajusta ângulo, ataca e calcula ângulo e força.
- `DDTankCoreTask`: laço de estados.
- `DDTankCoreScript`: supervisor. Reinicia, reconecta e detecta travamento.
- `handler/*`: estratégias plugáveis, como andar quando não acha o inimigo ou mover-se quando o ângulo não muda.

**Navegação de menus** (laço em `DDTankCoreTask.run`)
- Cada iteração testa, em sequência, templates do tipo "need*": `needActiveWindow` → `needGoingToWharf` → `needCreateRoom` → `needChooseMap` → `needCloseTip` → `needClickPrepare` → `needClickStart` → `isEnterLevel` (combate) → `needDraw` (virar cartas = fim da instância).
- Cada `need*` clica no ponto encontrado e retorna true.
- É uma máquina de estados "reativa": o estado atual vem da tela, não de uma variável interna.
- A escolha de mapa usa coordenadas fixas de grade (linha/coluna, paginação por cliques no scroll) e a dificuldade como fração (`DDtankOperate10_4.chooseMap`).

**Detecção de turno**
- Template `isMyRound`.
- Fora do próprio turno, o bot **pré-ajusta o ângulo** (`preAngleAdjust`) e guarda a última posição conhecida do inimigo.

**Leitura de ângulo, vento e direção**
- Ângulo: OCR do Dm com dicionário de fontes, na região (23,552)-(77,590).
- Vento: OCR em (461,20)-(536,42). O sinal vem da cor da seta (`eaeaea|848484`) no lado esquerdo ou direito do mostrador (`DDTankPic10_4.getWind`).
- O vento é **arredondado para cima ao múltiplo de 0,5** quando `exactWind` = false. O sinal é **invertido quando o personagem olha para a esquerda**, o que dá um vento relativo à direção do tiro.
- Direção do personagem: busca de linha vermelha no mostrador de ângulo (`getToward`).
- Observação: em `attackAuto` existe `double wind = 0; ddtankPic.getWind();` e o retorno não é atribuído. Na prática, o vento usado é sempre 0, o que parece um bug.

**Medida de distância**
- O bot mede a **largura do retângulo branco (cor 999999) do minimapa**, que marca a área visível. Essa largura dividida por 10 vale **1 "屏距" (unidade de distância)** (`calcUnitDistance`).
- Ele coleta várias amostras e usa a **moda**. Se não houver amostra, usa o padrão 10.0.
- As posições "eu" e "inimigo" são procuradas **no minimapa**, por cor ou blob.
- Δx e Δy entre eu e o inimigo são divididos pela unidade (2 casas decimais).
- Isso bate com a convenção dos guias brasileiros: "divida a tela em 10 partes iguais" (TechTudo 2015, ver §7).

**Escolha de ângulo** (`getBestAngle`)
- Usa o ângulo geométrico θ = atan(Δy/Δx) até o inimigo e mapeia para ângulos "de tabela":
  - θ<5 → 20°
  - θ≤20 → 30°
  - θ≤26 → 40°
  - θ≤32 → 45°
  - θ≤50 → 50°
  - θ≤65 → 65°
  - acima disso → θ−5
- Some-se um offset configurável. Há também modos de ângulo fixo ou manual.

**Força**
- `getStrength(angle, wind, dx, dy)` chama um executável externo, `C:\tmp\getStrength.exe`, que **não está no repositório**.
- O resultado entra num cache serializado em disco, com chave "ângulo|vento|dx|dy".
- O cálculo roda numa thread assíncrona porque leva cerca de 1,5 s.

**Disparo**
- O controle de força é feito **pela barra, por pixel, e não por tempo**.
- O bot pressiona espaço (`keyDown(' ')`) antes de ter a força pronta.
- Depois lê a cor média em `x = startX + (endX−startX)/100 × força − 1`, faixa y 574–590.
- Quando a cor muda além de uma tolerância (`303030`), ele **solta espaço**.
- Em seguida espera a cor se estabilizar, verificando `isMyRound` a cada 1 s.
- Há uma variante, `attack2`, que compara com cores fixas da barra e limita a força a 3–96.
- O bot também envia as teclas de habilidade e itens configuradas antes de soltar.

**Vitória, derrota e fim**
- O fim da instância é detectado pela **tela de virar cartas** (`needDraw`): o bot clica em cartas aleatórias e incrementa `passes`.
- Não encontrei detecção explícita de derrota. O laço volta ao lobby pelos templates.

**Recuperação de falhas**
- Ângulo não lido: salva um recorte para depuração e **passa o turno com a tecla 'p'**.
- Ângulo que não muda após 3 tentativas: entende que precisa andar e chama o handler de movimento.
- Se nada funcionar: "原地飞" (tecla 'f' e `attack(5)`).
- Inimigo não encontrado: usa a última posição conhecida e, se não houver, anda.
- Supervisor (`DDTankCoreScript` e `DDTankStuckCheckDetectionByLog`) considera o bot **travado** quando o log fica 240 s sem novidade, ou quando há mais de 10 mensagens que repetem o mesmo ciclo de no máximo 3 mensagens. Nesse caso ele reencontra ou reabre a janela do navegador, faz login de novo e reinicia a tarefa.
- O bot também faz reinício periódico, para não vazar memória.
- Qualquer exceção é logada, seguida de `sleep(1s)`, e o laço continua.

#### O que aproveitar e o que não se aplica

**Aproveitável (como ideia)**
- Unidade de distância = largura do retângulo de visão no minimapa / 10, usando a moda das amostras.
- Posições lidas no minimapa.
- Pré-ajuste do ângulo fora do turno.
- Pressionar espaço cedo e soltar ao **observar a barra atingir o pixel-alvo**. É uma malha fechada, imune a jitter de tempo.
- Cache de soluções.
- Detector de travamento por log repetitivo.
- Fallback "passar turno".
- Snapshot de falhas de OCR.

**Não se aplica**
- Dm/COM, que é chinês, 32 bits e roda só em Windows.
- Coordenadas fixas do cliente chinês.
- O executável externo de força.
- Spring Boot.

---

### 2. DavidBarishev/DDtankFarmingBot

- **URL:** https://github.com/DavidBarishev/DDtankFarmingBot
- **Licença:** **GPL-3.0** (API `spdx_id: GPL-3.0`; o README diz "GNU GENERAL PUBLIC LICENSE Version 3"). Copiar código obrigaria o nosso projeto a ser GPL-3.0, então prefira só ideias.
- **Linguagem:** Python 2-era, com `pyautogui`. O último push foi em 2016-07-18.
- **Escopo:** **não tem combate**. Os módulos cobrem eventos de lobby: TreasureFarm, TreasureMap (lançar dados grátis) e WealthTree. O README lista "combat farming" e "PVE farming (boatyard)" apenas no roadmap.

#### Como funciona

**Janela**
- A região do jogo é configurada manualmente (`conf.Screen`), com tamanho fixo de 999×599 (`Globals.py`).
- Na inicialização, o bot valida a região localizando templates (`Fun.png`, `Event.png`). Se não encontrar, lança `GlobalNotFoundException`.

**Percepção, decisão e execução**
- `Framework/Capture.py`: screenshot por região.
- `Imging.py`: `pyautogui.locate` em escala de cinza opcional.
- `Clicking.py`: clique relativo à região do jogo.
- Cada módulo implementa a interface `FarmAction` (`Logic.py`) com os métodos `is_available()`, `get_to_event()`, `run()`, `exit_event()` e `after_run()`.

**Turno e disparo:** não existem.

**Recuperação:** mínima. Usa `sleep`s fixos e "click back button".

#### O que aproveitar e o que não se aplica

- **Aproveitável:** a interface de módulo (`is_available` / `enter` / `run` / `exit` / `after_run`) é um bom contrato para "atividades" do nosso bot, como instâncias e coleta diária.
- **Não se aplica:** todo o resto. O bot é antigo e não tem combate.

---

### 3. Yagasaki7K/website-ddladora (calculadora "Full Angle")

- **URL:** https://github.com/Yagasaki7K/website-ddladora (arquivos: `README.md` e `index.html`)
- **Licença:**
  - O README diz "MIT License. See the LICENSE file".
  - Porém **não existe arquivo LICENSE**: o raw `LICENSE` dá 404, e a API retorna `license: null` e 404 em `/license`.
  - Juridicamente, a declaração no README indica intenção de MIT, mas sem o texto da licença. Por cautela, trate como "MIT declarado, sem arquivo".
  - Não precisamos do código: a fórmula é trivial e de domínio público entre jogadores.
- **Linguagem:** HTML, CSS e JavaScript puro, em arquivo único.

#### Fórmula (lida no `index.html`)

```js
ajusteVento = vento * 2;
angulo = (direcao === 'favor') ? 90 - distancia + ajusteVento
                               : 90 - distancia - ajusteVento;
angulo = Math.round(angulo); clamp [0, 120]; força = 95 (fixa)
```

**Convenções**
- Distância de 0 a 20, passo 0,5, nas unidades de "distância" do jogo (régua de 1/10 da tela).
- Vento de 0,0 a 5,0, em valor absoluto, mais a direção "contra (←)" ou "a favor (→)".
- O README avisa: "simplified estimation… wind values above 5.0 may be less accurate".
- Exemplo do README: distância 10, vento 1,5 contra → 90 − 10 − 3 = **77°**, força 95.

**Aproveitável:** confirma a fórmula de tiro alto que já usamos (90 − d ± 2v, força 95).

---

### 4. chramos/BoomShot — FORMULAS.md

- **URL:** https://github.com/chramos/BoomShot/blob/main/FORMULAS.md
- **Licença:** **sem licença** (API `license: null`, `/license` 404). Não copiar código.
- **Linguagem:** JavaScript com PixiJS.
- **O que é:** um **clone jogável** "DDTank-inspired" (`.claude/PROJECT_CONTEXT.md`), e não um bot. Contém um submódulo `DDTank41` sem URL acessível, que pelo nome sugere uma fonte do DDTank 4.1. As constantes são do clone. As alegações "matches DDTank" não são verificáveis.

#### Fórmulas e constantes (copiadas do FORMULAS.md)

**Constantes**
- GRAVITY = 400 px/s²
- MAX_POWER = 800 px/s (velocidade com a barra em 100%)
- CHARGE_RATE = 0,25/s, ou seja, **a barra enche de 0 a 100% em cerca de 4 s e depois esvazia**. Se chegar a 0% descendo, o turno é pulado ("same as DDTank").
- ANGLE_SPEED = 15°/s segurando ↑/↓
- GRID_SIZE = 40 px por "quadrado de distância"
- **WIND range −4,0 a +4,0**

**Lançamento**

```
vx = cos(angle) × (power × MAX_POWER) × facing
vy = −sin(angle) × (power × MAX_POWER)
```

- power vai de 0 a 1.
- Ângulo de 0 a 180°, com 90 = vertical.

**Integração por quadro** ("wind as force with air drag, DDTank model")

```
accel_x = wind × WIND_POWER − AIR_DRAG × vx
accel_y = GRAVITY − AIR_DRAG × vy
```

- WIND_POWER = 10
- AIR_DRAG = 0,06
- Euler explícito

É o **mesmo formato do nosso modelo**: gravidade, arrasto linear e vento como aceleração horizontal constante.

**Distância:** `round(|x2 − x1| / GRID_SIZE)` quadrados. "Each square corresponds to 1 unit in the DDTank aiming formula tables."

**Tridente ("matches DDTank source")**
- Centro: ângulo +0°, velocidade ×1,0
- Esquerda: −5°, ×0,9
- Direita: +5°, ×1,1

**Dano**
- base = round((1 − dist/(raio+20)) × 40 + 10), com raio de 50 px
- crítico: 20% de chance, ×1,5
- multiplicadores: Double ×0,9, Triple ×0,6, Trident ×0,5
- boosts de +10 a +50% acumulam de forma multiplicativa

**Fórmulas de mira manuais**

| Tiro | Força | Ângulo |
|---|---|---|
| Médio | sempre 60 | `90 − dist×2 ± wind×2` |
| Alto | sempre 95 | `90 − dist ± wind×2` |

Sinal **+** quando o vento empurra em direção ao alvo e **−** quando é contra.

#### O que aproveitar e o que não se aplica

- **Aproveitável:**
  - Confirma o formato do modelo físico e as duas fórmulas que já temos.
  - A barra leva cerca de 4 s para encher. No clone isso é constante; no jogo real precisa ser medido.
  - O tridente usa ±5° com velocidades ×0,9 e ×1,1.
  - Faixa de vento de cerca de ±4 no clone. O 52pojie usa até ±5,9 e a ddladora aceita até 5.
- **Não se aplica:** os valores numéricos das constantes (400, 800, 10, 0,06). São da escala de pixels do clone e não servem como parâmetros do DDClássico. Nosso ajuste às tabelas continua sendo a referência.

---

### 5. ddcalculator.abacusai.app

- **URL:** https://ddcalculator.abacusai.app/
- **Abriu?** Sim, via WebFetch. Não há código-fonte nem licença visíveis; é um app hospedado na Abacus.AI. **Sem licença conhecida.**
- **Funcionalidade:** estima ângulo e força a partir da distância e do vento, com três entradas:
  - (1) screenshot enviado ou colado;
  - (2) "tempo real": compartilha a janela do jogo, captura um frame a cada cerca de 2 s e analisa **com IA**;
  - (3) manual: distância, vento, se o tanque está à esquerda ou à direita do alvo, direção da seta do vento, ângulo inicial e um toggle "inverter convenção".
- **Convenção:** vento de cauda (soprando para o inimigo) soma à correção; vento de frente subtrai.
- **Fórmulas:** **não são mostradas na página**. Não consegui extrair números.
- **Aproveitável:** a forma de definir o sinal do vento (posição relativa do alvo combinada com a direção da seta) é a mesma que precisamos implementar. Nada numérico.

---

### 6. Outros bots e ferramentas encontrados

#### HexorCatZ/DDT_WB_BOSS

- **URL:** https://github.com/HexorCatZ/DDT_WB_BOSS
- **Licença:** **sem licença** (API `license` ausente, `/license` 404).
- **Linguagem:** Python com `pyautogui`. Joga o "world boss" no ddtanktwo.com. Push em 2024-01-03.

**Janela**
- Faz screenshot da tela inteira e localiza a caixa de chat (`LockChat.png`, `LockChat2.png` ou `LockChat-InGame.png`) com confiança 0,9.
- Deriva a origem do jogo por offsets calibrados e assume uma área de 1000×600.
- O mesmo teste também classifica a tela entre lobby trancado, lobby destrancado e em jogo.

**Turno**
- Template `Plus2.png` na região (950,115,45,55).
- A cada 5 tentativas sem turno, confere se ainda está na sala pelo `GearLogo.png`. Se não estiver, sai do laço.

**Ângulo**
- Usa **templates de dígitos** 0–9 em duas posições fixas: dezenas em (33,556,21,21) e unidades em (46,556,21,21).
- Ajusta com 'w' e 's', uma tecla por grau, e verifica de novo.

**Disparo: força por TEMPO**

```python
keyDown('space'); for f in range(force - 4): sleep(0.04); ...; keyUp('space')
```

- São **40 ms por ponto de força**, com uma calibração de −4. Isso equivale a cerca de 4 s para 100, coerente com o BoomShot.
- Antes de soltar, digita '4445678' (itens e habilidades).
- Usa 'b' para o ataque especial quando o ícone `pow.png` não está presente.

**Recuperação:** laços com `sleep`. Considera o jogo encerrado quando passa mais de 15 s fora da partida.

**Avaliação:** como ideia, serve de referência para detecção de estado por template e para os dígitos do ângulo. A temporização em malha aberta é **frágil**: `sleep` no Windows tem granularidade de cerca de 15 ms, e o frame rate do Flash varia. A abordagem por pixel do qozi é melhor.

#### ChenZhu-Xie/Stardust_DDTank

- **URL:** https://github.com/ChenZhu-Xie/Stardust_DDTank
- **Licença:** **AGPL-3.0** (API).
- **Linguagem:** 易语言 (EPL) e E4A (Android). Usa o plugin 大漠 (`dm.dll`). Projeto de 2017–2018.
- **Modelo (README):** "External ballistic model with air resistance proportional to −kv", ou seja, arrasto linear como o nosso. Resolve por método numérico (tópicos: newton-iteration-method, numerical-solution).
- **Detalhes citados:** posição da boca do canhão, trajetórias esquerda e direita do tridente e "abnormal throwing tactics".
- **Referências externas que o README aponta:**
  - "浅析弹弹堂物理模型", em 52pojie (ver abaixo);
  - "制作十万个数据的力度表" (Bilibili BV1ze4y1J7Hu).
- **O que não aparece:** o README não descreve detecção de turno nem disparo. É uma ferramenta de **auxílio** com botões rápidos e não um bot autônomo.

#### 52pojie "浅析弹弹堂物理模型"

- **URL:** https://www.52pojie.cn/thread-1132459-1-1.html (lido via WebFetch, resumido; não consegui o texto integral).

**Modelo 1**
- V0 = Fn·F, sem arrasto, com aceleração horizontal a = Fw·W.
- Ajuste por mínimos quadrados: Fn ≈ 0,7077, Fw ≈ 3,9226, g ≈ 121,76.
- O autor nota que os parâmetros **não são únicos**: com g = 10000, Fn ≈ 6,41 e Fw ≈ 322,14. O fator g escala com Fn².

**Modelo 2** (com arrasto R, massa 1)
- R ≈ 0,8993, W ≈ 5,8709, g ≈ −172,07 (convenção de sinal negativa).
- Usa `fsolve` para o tempo e para a força.

**Dados e conclusões**
- Ângulos 30, 45, 50, 65 e 90 ("alto"), distâncias de 1 a 20 e **vento de −5,9 a +5,9 com passo de 0,1**.
- O autor concluiu que o modelo simples não bate com o tempo de voo observado. O modelo com arrasto ficou melhor.
- Ele atribui desvios ao arredondamento das entradas pelo jogo.

**Tabela 65° citada numa resposta** (sem vento, distâncias de 1 a 20):

| d | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F | 12 | 21 | 27 | 33 | 37 | 42 | 46 | 50 | 54 | 57 | 60 | 63 | 66 | 69 | 72 | 76 | 78 | 81 | 84 | 87 |

Ela difere um pouco da tabela brasileira (§7). Provavelmente é outra versão ou servidor, o que mostra que **as tabelas variam por servidor** e precisam de calibração.

#### Outros

- **GitHub topic "ddtank"** (https://github.com/topics/ddtank): além dos repositórios acima, só launchers (C#, Rust), downloaders de Flash e gerenciadores de torneio. Nenhum bot de combate.
- **PyPI `ddtank`** e **`ddtcurve`**, vistos de passagem na busca. O primeiro é um helper de script que apenas pressiona teclas; o segundo é uma "strength" de atributos e não de tiro. Não aprofundei.
- **Fonte do servidor DDTank (C#, classes de física):** procurei para confirmar as constantes reais (gravidade, arrasto e vento por mapa) e **não encontrei fonte pública indexada**. Não afirmo nada sobre ela.

---

### 7. Tabelas públicas de força por distância (guias em pt-BR)

**Convenção de distância comum a todos os guias:** 1 distância = **1/10 da largura da tela visível**. O guia TechTudo 2015 manda "dividir a tela em 10 partes iguais" e, se o alvo estiver mais longe, começar novo quadrado a partir do fim do anterior. Distâncias fracionárias são interpoladas.

#### 20° — TechTudo 2013

Fonte: https://www.techtudo.com.br/noticias/2013/05/ddtank-veja-como-completar-tarefas-do-laboratorio-de-combate.ghtml. Segundo o guia, a 20° **o vento não altera o ângulo**, e a ddcalc.blogspot também diz que "o vento não influencia no ângulo 20". Isso é uma aproximação: fisicamente o vento ainda desloca o projétil, só que pouco em tiros rasos e curtos.

| Dist | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Força | 10 | 19 | 25 | 30 | 36 | 40 | 44 | 48 | 51 | 54 | 57 | 60 | 63 | 66 | 69 | 72 | 74 | 76 | 78 | 80 |

#### 65° — TechTudo 2013 e 2015 (mesmos números), vento 0

Fontes: link acima e https://www.techtudo.com.br/noticias/2015/05/ddtank-aprenda-como-jogar-usando-o-angulo-de-65-graus-nas-partidas.ghtml

| Dist | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Força | 13 | 21 | 26 | 31,5 | 37 | 41 | 44 | 48,5 | 53 | 56 | 58 | 61 | 64 | 67 | 70 | 73 | 76 | 79 | 82 | 85 |

#### Regras de vento nos guias

**65°:** ângulo = 65 ± 2·vento, ou "a cada 0,5 de vento, 1 grau". Soma com vento a favor e subtrai contra (TechTudo 2013 e 2015; webpixel5 forum).

**50°:** ângulo = 50 ± 2·vento. Exemplo: d=20 com vento 2,5 a favor → 55; contra → 45 (https://webpixel5.forumeiros.com/t4-tutorial-jogando-com-os-angulos-de-20-30-50-e-65). O mesmo guia diz que a força a 50° "é parecida com a de 30°".

**30°:** ângulo = 30 ± **1**·vento. Exemplo: vento 2 a favor, d=10 → ângulo 32, força **47,5**; contra → 28 com a mesma força (webpixel5). Atenção: o fator é 1 e não 2.

**Tiro alto ("Full", 90°):** ângulo = 90 − d ± 2·vento, força 95 (TechTudo 2013; mesterddtank; ddladora).

**Regra de arredondamento do tiro alto**
- TechTudo 2013: se a fração do ângulo for de .1 a .4, arredonde para baixo e **aumente** a força; nos demais casos, arredonde para cima e **reduza** a força.
- mesterddtank (http://mesterddtank.blogspot.com/p/angulos-do-ddtank.html): pegue metade da sobra do vento; se ela estiver contra você, use força 96 em vez de 95. Exemplo: d=20, vento 1,6 contra → 70 − 3,2 → ângulo 67; a sobra de 0,2 dá 0,1, e a força fica 96.

**Diferença de altura** (todos os guias): alvo mais baixo pede menos força ou ângulo; alvo mais alto pede mais. Nenhum guia dá fórmula, o que reforça o uso do nosso simulador com Δy.

#### Tabelas que existem só como imagem

Encontrei tabelas que aparecem apenas como imagem e não consegui ler os números:
- 20° e 30° no mesterddtank;
- todas as tabelas no fórum webpixel5;
- ddcalc.blogspot (http://ddcalc.blogspot.com/p/guia.html).

Uma página do Google Sites ("drdbrasil2013… angulo-full") redireciona para login do Google e não abriu.

---

### 8. DDClássico (ddclassico.com)

**Acesso ao site**
- https://ddclassico.com/, https://ddclassico.com/preregister e https://beta.ddclassico.com/ retornaram **HTTP 403 com o desafio Cloudflare "Just a moment…"**, tanto no WebFetch quanto no curl.
- **Não consegui ler o site, os termos de uso nem as regras.**

**O que foi possível confirmar por fontes externas**
- Matéria Mobile Gamer Brasil (https://www.mobilegamer.com.br/2026/08/ddtank-classico.html):
  - lançamento em **29/08 (2026), às 19h**, para PC, celular e navegador, com **crossplay** entre mobile, navegador e launcher de PC;
  - revival do DDTank original com foco na era de **~2013 / Torneio Mundial**;
  - modos: **PvE (instâncias** em equipe contra criaturas controladas pelo jogo), **PvP** por turnos com tempo curto por turno, **ranqueadas** com ELO e temporadas de 45 dias (a 1ª terminou em 5/out) e partidas casuais;
  - Passe Clássico com 60 níveis;
  - mira manual de ângulo e força, vento, terreno destrutível ("tatuza") e ataque especial que carrega ao receber dano;
  - parceria com o rapper Raffa Moreira (skin);
  - **a matéria não cita** desenvolvedora, armas, pets, gemas/pérolas, chefes nem regras.
- Google Play, app "DD Classico" (`com.seventeengames.classico`):
  - descrição: "jogo de batalha casual que combina pontaria, estratégia e competição em partidas rápidas… escolhem suas armas… temporadas temáticas, rankings competitivos";
  - o pacote sugere a desenvolvedora "Seventeen Games", mas isso não está confirmado no texto.
  - Um resumo de busca chegou a descrever esse app como battle royale da B4YOU Games. A descrição lida diretamente no Play Store fala em DDClássico, então esse resumo parece incorreto.
- Existe canal oficial no YouTube (https://www.youtube.com/@ddtankclassico), com vídeos de códigos de resgate. Há também vídeos de terceiros anunciando "HACK DDCLASSICO" (https://www.youtube.com/watch?v=vVELQGgQCos), o que indica que o servidor deve ter interesse em coibir esse tipo de software.

**Regras sobre programas de terceiros**
- **Não encontrei o texto das regras do DDClássico.**
- Como referência de prática no ecossistema: o servidor DDT3 BR afirma que, "caso detectado o uso de programas ilegais dentro do jogo, o usuário será imediatamente punido com banimento permanente" (https://ddtbr3.com/tos/).
- Recomendação: o usuário deve ler os Termos do DDClássico logado no navegador antes de usar o bot. Bots em **PvP/ranqueadas** são o caso mais provável de punição e de prejuízo a outros jogadores.

**Sem dados encontrados:** lista de instâncias e chefes, armas, pets, gemas/pérolas e invisibilidade no DDClássico. Não invento.

---

### 9. Comparação dos mecanismos de disparo

| Projeto | Controle de força | Leitura do ângulo | Turno |
|---|---|---|---|
| qozi/ddtank-onhook | Segura espaço e **solta quando o pixel da barra na posição-alvo muda de cor** (malha fechada) | OCR Dm (dicionário de fonte) e teclas W/S | Template `isMyRound` |
| HexorCatZ/DDT_WB_BOSS | Segura espaço por **(força − 4) × 40 ms** (malha aberta) | Templates de dígitos (dezenas e unidades) e W/S | Template `Plus2.png` |
| BoomShot (clone) | Barra enche em cerca de 4 s e depois esvazia (soltar = disparar) | n/a | n/a |

---

### 10. Conclusões para a implementação

- **Fórmulas confirmadas** em várias fontes independentes (ddladora, BoomShot, TechTudo, mesterddtank):
  - **Alto:** força 95, ângulo `90 − d ± 2v`.
  - **Médio:** força 60, ângulo `90 − 2d ± 2v`.
  - **65°:** ângulo `65 ± 2v`, força pela tabela.
  - **50°:** ângulo `50 ± 2v`.
  - **30°:** ângulo `30 ± 1·v` (fator 1, segundo uma única fonte, o fórum webpixel5).
  - **20°:** ignora o vento no ângulo, força pela tabela.
- **Convenções:**
  - "+" quando o vento sopra **em direção ao alvo**.
  - d em unidades de **1/10 da largura da tela visível**, faixa usual de 0 a 20. Fracionário é interpolado.
  - Vento usual: 0 a 5 na ddladora, ±4 no BoomShot e ±5,9 nos dados do 52pojie.
  - Calcule sempre o vento **relativo à direção do tiro**: inverta o sinal se o alvo estiver à esquerda, como faz o qozi.
- **Arredondamento no tiro alto:** como o ângulo é inteiro, compense a fração com a força (95 ± 1), seguindo TechTudo e mesterddtank. O nosso simulador pode fazer isso exatamente: fixe o ângulo inteiro mais próximo e resolva a força contínua.
- **Adicionar a tabela de 20°** (10, 19, 25, 30, 36, 40, 44, 48, 51, 54, 57, 60, 63, 66, 69, 72, 74, 76, 78, 80) como alvo de ajuste e validação do modelo físico, junto com as de 30/50/65.
  - A tabela 65° do 52pojie (12, 21, 27, 33…87) difere da brasileira em 1–2 pontos. **As tabelas variam por servidor, então calibre no DDClássico** com tiros de teste.
- **Modelo físico:** nosso formato (gravidade, arrasto linear −kv e vento como aceleração horizontal) é o mesmo usado por BoomShot, Stardust ("−kv") e pelo modelo 2 do 52pojie, que se ajustou melhor que o modelo sem arrasto. Os parâmetros não são únicos (escala g ∝ Fn²), então fixe um deles.
- **Disparo:**
  - Implementar no estilo do qozi: `keyDown(space)` e depois amostragem em alta frequência (MSS em ROI pequeno) do pixel da barra em `x = x0 + (x1 − x0) × força/100`, com `keyUp` assim que esse pixel "acender".
  - Fazer fallback por tempo calibrado. A referência é cerca de 40 ms por ponto, mas é preciso medir a taxa real da barra no DDClássico.
  - Considerar a **latência de reação** (frame + SendInput) como offset de força calibrável, como o `offsetStrength` do qozi e o `calibrate = 4` do HexorCatZ.
  - Lembrar que a barra **volta a esvaziar** e que, ao chegar a 0, o turno é perdido (BoomShot).
- **Distância:** medir pela largura do retângulo de visão no minimapa / 10 e localizar eu e o inimigo **no minimapa**, como faz o qozi. Isso é robusto ao scroll da câmera. Usar a moda de várias amostras.
- **Ângulo:** ler com os nossos dígitos aprendidos (como os templates por posição do HexorCatZ), ajustar por W/S e verificar de novo. Se o ângulo não mudar após cerca de 3 tentativas, o bot está bloqueado por terreno ou no limite e deve andar ou trocar a estratégia.
- **Turno e pré-ajuste:** detectar o turno por template. Fora do turno, pré-ajustar o ângulo e memorizar a última posição do inimigo.
- **Máquina de estados reativa:** cada iteração identifica a tela por templates (lobby → sala → preparar/iniciar → combate → cartas de recompensa) em vez de confiar só no estado interno. A tela de cartas marca o fim da instância.
- **Robustez:**
  - Watchdog de "log/estado sem progresso" (o qozi usa 240 s e repetição de ciclo).
  - Ações de fuga: passar turno; fechar pop-ups com templates `need*`.
  - Snapshot automático de falhas de OCR e template para re-treino.
  - Correção de offset da janela por uma âncora visual.
- **Licenças:**
  - Não copiar código de qozi/windors, HexorCatZ, BoomShot nem ddcalculator (sem licença).
  - Nem de Stardust (AGPL-3.0) ou DavidBarishev (GPL-3.0), salvo se aceitarmos copyleft.
  - ddladora tem "MIT" só declarado. A fórmula em si é conhecimento comum.
  - Reimplementar as ideias com código próprio.
- **DDClássico:**
  - O site está atrás do Cloudflare e não foi lido.
  - Há PvE (instâncias), PvP, ranqueadas e crossplay (Mobile Gamer).
  - Regras sobre terceiros, instâncias, pets, gemas e chefes **não foram encontradas**. O usuário deve ler os Termos e restringir o bot a PvE e solo.
