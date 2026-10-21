# Pesquisa — referências e conclusões

Este documento junta a pesquisa de 2026-10-15 (tabelas, regras de vento e modelo físico), a de 2026-10-16
(bots, calculadoras e fórmulas citados no pedido), a de 2026-10-19 (instâncias e mais uma calculadora) e a de
2026-10-20 (aimbots e bots pedidos na missão da 0.5.0, notícias oficiais do DDClássico e as seis instâncias
prioritárias). A lista de fontes legível pelo programa fica em `data/knowledge/sources.json`.

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
| Uma estratégia por atividade, com contrato comum (`FarmAction`) | DavidBarishev | perfis em `data/knowledge/instances.json` + `strategy.py::StrategyPlanner` (mesmo motor de mira) |
| Etapas e alvos prioritários por instância (formigas → rainha; Barão, Midas, Matias) | guias de instância (2012–2017) | `instances.json`, `strategy.py` |
| Chefe imune de frente, escudo que só se vence por cima, pavio que exige gelo | bielpontes 2012, ddtdjpj | estados `imune`, `so_por_cima`, `pausar` em `strategy.py` |
| Etapas e dificuldades de Formigueiro, Galinheiro e Olimpíadas (balões, corrida, Boxiador, juiz) | ddtdjpj (olim.html, 2015), ddtankdicasjogar 2013, shekinah 2011, emuladores (só apoio) | perfis por dificuldade em `instances.json` (herança `base`, `etapas_ids`); tipos de etapa `pontuacao`/`corrida`, papéis a `evitar` |
| Etapa escolhida pelo que a tela mostra (as fontes divergem na ordem) | contradições entre guia de 2013, vídeos e emulador no Galinheiro | `StrategyPlanner.update` troca de etapa por `entra_com`, inclusive para trás, sem largar um chefe visível |
| Barra de força do DDClássico em ~3,33 s com ~44–94 ms até começar | registro do AINBOT (2026) | padrão `automation.power_full_time_s` 3,33 e `power_start_delay_s` 0,06 (a confirmar no cliente) |
| Recalibrar pela mediana dos impactos reais | AINBOT (κ pela mediana) | `Calibrator._fit` com pesos de Huber |
| Regiões marcadas sobre uma captura; ângulo como a parte que muda ao apertar a tecla | DSS, AINBOT, PyPI `ddtank` (diferença entre quadros) | `vision/autodetect.py` (sugestões confirmadas pelo usuário) |

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

## Pesquisa de 2026-10-21, segunda parte (revisão do combate: referências do Formigueiro Fácil)

Procura de capturas, modelos de imagem, parâmetros de mira e estratégias prontas do Formigueiro Fácil, sem
repetir as fontes já registradas. **Nenhuma captura, modelo visual ou template novo pode ser reaproveitado:**
nenhum bot público traz modelos do DDClássico, os vídeos têm a licença padrão do YouTube e o §5 dos termos do
DDClássico proíbe distribuir a arte do jogo. Os modelos continuam sendo capturados pelo usuário.

| Fonte (aberta) | O que trouxe | Licença | Uso no JonFlow |
|---|---|---|---|
| YouTube WNv5GN-WxWI (Japa MMORPGs, 10/10/2026, DDClássico), narração | Formigueiro com **Fácil e Normal** no DDClássico (1ª evidência pública do Fácil), entrada no nível 8; etapa 1 com formigas dos dois lados; etapa 2 com a rainha no alto, alternando guardas e flecha; mira para a rainha 30/70 e 46/55 "dependendo do vento"; vida "uns 5.000 no Normal" (chute) | padrão do YouTube | fonte `transcricoes_ddclassico_2026`; o limite do Fácil em `instances.json` passou a citar o vídeo; as miras viraram só referência (sem posição nem vento) |
| YouTube sUhF80tf3EI (WallpaperTV, 31/08/2026, DDClássico), narração | tiro alto 90 − d ± 2·vento, força 95; 20° com d10 = 55 (tabela da comunidade: 54); turno de ~10 s (dito por ele) | padrão do YouTube | confirma verbalmente que as tabelas da comunidade valem no DDClássico (sem medição); o turno curto é o motivo de a confirmação do disparo esperar pouco |
| ddtankplay.blogspot.com (2012) e gigaddtank.webnode.page (sem data) | dois tipos de formiga (uma rápida e fraca, outra lenta e resistente); reforços até 20 | sem licença / direitos reservados | só reforça que a formiga pode ter **duas aparências**: capture amostras das duas em Alvos |
| ddtank.fandom.com/pt/wiki/Pandora (2022) | vida 8000 (igual ao Fácil do emulador) | texto CC BY-SA | não é o DDClássico; a vida da rainha diverge entre fontes (5.000, 8.000, 10.500) e não foi usada |
| GitHub gonfabfake (cópia do emulador 4.1), Onesbg/OnesBOT, peuz-br/ddtank-project | nada novo (cópia, repositório vazio, só README) | MIT / nenhuma | — |

Descartados: vídeo do "Formigueiro Difícil" de outro servidor, aimbot comercial sem dados, busca em chinês sem
resultado. Nenhuma tabela nova de ângulo × força × distância × vento.

## Pesquisa de 2026-10-21 (Formigueiro, caminho do Cais e aviso de jogador sozinho)

Feita por leitura de arquivos de texto (GitHub raw/API) e de 6 imagens; nenhum binário baixado nem executado.
Classificação: (a) comprovado para o DDClássico, (b) adaptável com validação, (c) sem validação suficiente.

| Fonte | O que trouxe | Licença | Classe |
|---|---|---|---|
| github.com/yutikeyux/ddt-34-csharp (servidor C#, DDTank 4.1) | Formigueiro (`AntCave*Game.cs`, missões KD/KT1120–1121, IA da rainha): só Fácil e Normal; etapa 1 com 20 formigas no total (até 10 vivas, reforços), formigas andam até o jogador; etapa 2 com a rainha à direita, guardas, tiro, ataque em área x10 em quem passa para a direita dela; 200 turnos por etapa; vida da rainha 8000/10500. Física: Euler dt 0,04 s, `vx = força·cos`, g 700 px/s², arrasto 0,2/s, vento 24 px/s² por ponto; vento muda até 1,0 por turno, alvo em [-4; 4) | MIT | (b) |
| github.com/yutikeyux/ddt-34-flash (cliente AS3 4.1, palco 1000×600) | Barra de força: 0 a 100 na tela (2000 internos), 20 por quadro; cheia, **volta a esvaziar**; se chegar a 0, perde o turno. Aviso de sala de instância com **1 jogador** em qualquer dificuldade (`DungeonRoomView.checkCanStartGame`) | MIT | (b) |
| github.com/thurdev/ddtank-reborn | Texto pt-BR do aviso: "Lembrete — Esta masmorra é muito difícil, recomendada para equipes de 2 ou mais pessoas, deseja participar mesmo assim?" (Confirmar, Cancelar, X; Enter confirma). Pagos em cupons: "Ir à última fase", "Tentar de novo", 3ª carta de recompensa. Capturas (Ruffle 1100×700, vietnamita) só como referência de layout | MIT no código; arte de terceiros | (b) |
| github.com/gustavoif0/ddtank_bot (jun/2025, "DDTank Brasil 3.6", marca 7teen) | Caminho: Central → sala → configurar o mapa → instância → dificuldade → OK → Início → OK do aviso de sozinho; Formigueiro com Fácil e Normal | **nenhuma** (só a ordem das telas foi usada) | (b), provável antecessor do DDClássico |
| github.com/Ring0eh/toolgunny-re-and-defense (`dumps/FORMULA.md`) | Mesma física por outra fonte (DragonTank) | NOASSERTION | (b) |
| ddtclassico.com/classic/terms | Sem cláusula sobre bots (remete às "Regras de Conduta", não encontradas); §5 proíbe copiar e distribuir arte e software do jogo | — | (a) |

Uso no JonFlow:

- **Caminho do Cais e aviso:** confirmam o que o usuário descreveu em 2026-10-21; viraram o fluxo padrão das
  instâncias e a tela `aviso_sozinho` (confirmada só com a permissão do usuário).
- **Formigueiro:** os fatos acima foram para `instances.json` como limites, com a fonte `emulador_ddt34_formigueiro`
  (confiança do perfil continua "media"). As posições do emulador são do mapa (que rola), não da tela: não viraram
  regiões.
- **Botões pagos:** `botao_ultima_fase`, `botao_tentar_novamente` e `carta_paga` entraram na lista de proibidos.
- **Física:** **não** substituiu o modelo do JonFlow. Comparação (1 distância ≈ 97 px, 105 casos de 20° a 80°,
  forças 40–95, vento −2/0/+2): diferença média +0,25 da régua, mediana 0,40, máximo 1,11 (maior com vento contra).
  Os dois reproduzem as tabelas da comunidade e nenhum foi medido no DDClássico; a calibração por disparos reais
  corrige o viés que sobrar. Candidata a teste quando houver disparos reais registrados.
- **Força:** a força recomendada vai até 100 (o usuário informou que a força vai de 0 a 100). Como a barra volta a
  esvaziar depois de cheia, mirar 100 com atraso de alguns milissegundos dá ~99, o mesmo erro de execução de
  qualquer outra força.
- **Capturas:** nenhuma imagem do DDClássico foi encontrada; as que existem são de outro cliente, resolução ou sem
  licença, e o §5 dos termos proíbe distribuir a arte do jogo. **Os modelos continuam sendo capturados pelo
  usuário**; não há perfil pronto com imagens.

Buscas sem resultado (não repetir): "DDClássico Formigueiro instância solo"; "弹弹堂 蚂蚁洞穴 副本 攻略 蚁后"; "Gunny
Huyệt Ma Kiến hướng dẫn"; GitHub "ddtank opencv", "ddt auto angle", "gunny bot"; notícias 41–46 do espelho não existem.
Descartados por serem de outro jogo ou sem conteúdo útil: 1141389743/ddtank-sniper, lcs-al/DDTankAutoPlay,
AlefeSam/ddtank_bot, Thom-0/DDT-TRIAL-BOT, rafaellyfsilva/ddtankbot, kahramanemir/bombom-hesap,
AndrusGerman/DDTankCalculator, Tziheng/DDTankAuto (AGPL, 新弹弹堂).

## Pesquisa de 2026-10-20 (missão da 0.5.0: aimbots, DDClássico e as seis instâncias)

Método: código e documentação lidos nos arquivos (API do GitHub, raw, PyPI), HTML bruto dos blogs e títulos,
descrições e capítulos de vídeos (nenhum vídeo foi assistido). Nada foi executado de código baixado. Licença
"nenhuma" = API do GitHub com `license: null` e sem arquivo LICENSE: todos os direitos reservados, só ideias
foram usadas. Nada aqui foi conferido no cliente do DDClássico.

### DDClássico: fontes oficiais

- `ddclassico.com` continua respondendo 403 (Cloudflare). O mesmo site responde em
  **`https://ddtclassico.com/classic/news/<n>`** (mesmo layout, `og:url` para ddclassico.com, mesmas redes e
  instalador em `download.ddclassico.com`). Confiança alta de que é o conteúdo oficial; não é prova formal de
  dono do domínio. Os termos de uso (`/classic/terms`) **ainda não foram lidos**.
- **Notícia 37 (16/10/2026, "Caça aos Clones das Sombras")**, lida: "Onde caçar: Formigueiro (Normal),
  Galinheiro (Difícil), Castelo do Reino de Bugou (Difícil), Covil do Dragão (Normal), Redemoinho (Fácil),
  Olimpíadas Boom (Difícil), Castelo Sombrio (Normal) e Tribo Piatan (Normal)"; evento de 16/10 a 22/10.
- Outras notícias: n13 (16/09) drops no "Castelo do Rei Bugou Normal"; n14 (25/09) "Explore 8 instâncias"
  (Central de Expedições); n30 (13/10) nível 33 liberado; n36 (15/10) "A dificuldade Difícil da Tribo Piatan
  será liberada hoje": **as dificuldades são liberadas aos poucos** (por isso a disponibilidade de cada atividade
  é conferida no cliente, por evidência). Nenhuma notícia descreve etapas, turnos, energia, ingressos ou solo.

### Nomenclatura: Olimpíadas Bugou × Olimpíadas Boom × Castelo do Reino de Bugou

**Olimpíadas Boom, Olimpíadas Bugou, Olimpíadas de Bogou e Desafio de Bugous são a mesma instância** (nome
interno `GuluOlympics`; confiança alta). O **Castelo do Reino de Bugou** (Castelo Bugou, do Rei Bugou;
`GuluKingdom`) é **outra** instância, com Fácil e com Barão, Midas e Matias (confiança alta). Evidências:
"Olimpíadas Boom (Desafio de Bugous)" na estreia (shekinahddtank, 26/09/2011); vídeo "OLIMPÍADAS BOOM (BUGOU)
DIFÍCIL" (2025); scripts `GuluOlympics` × `GuluKingdom` (crieddtank, 2012); a notícia 37 lista as duas
separadamente; jogadores do DDClássico usam "Olimpíadas Bugou" (vídeos de 06/09/2026, DDMira "OBN"/"OBD").
No JonFlow: modelo da opção `instancia_olimpiadas_bugou` ≠ `instancia_bugou_normal`, perfis com modelos de
alvo separados, e `match_profile` não associa "Bugou Normal" a nenhum dos dois.

### Instâncias prioritárias

| Instância | Dificuldades | Etapas | Confiança e contradições |
|---|---|---|---|
| Formigueiro | só Fácil e Normal (3 fontes clássicas); no DDClássico só o Normal tem notícia oficial | 1) formigas (um guia: 20); 2) só a rainha Pandora | alta para 2 etapas; diferença entre as dificuldades documentada só no nível recomendado (8–12 × 12–15); ataques da rainha e limite de turnos não descritos; solo feito em vídeos de 2011–2012 |
| Galinheiro (Pintinho Corre Rápido) | Fácil, Normal, Difícil; no DDClássico, Difícil (notícia 37) e Normal (vídeo de 07/09/2026) | guia de 2013: Fácil = pintinhos → Burrinho e gaiola; Normal = pintinhos → construção → Burrinho e gaiola; Difícil = pintinhos → Burrinho e gaiola → construção | **as fontes se contradizem**: vídeos e emulador mostram 4 etapas no Difícil e 3 em parte dos Fáceis; o nome Burrinho tem fonte única; o que faz perder não é descrito; recomendado 2 a 4 jogadores, há vídeo "Difícil SOLO" (2013) |
| Olimpíadas Bugou | Normal, Difícil, Avançado (sem Fácil); no DDClássico, Difícil (notícia 37) e Normal (vídeos, DDMira) | Normal clássico (olim.html, 2015): balões → corrida → Boxiador. Difícil/Avançado: balões → Boxiador → Juiz ladrão | média-alta para a estrutura; estreia (2011) e um servidor de 2025 falam em 4 etapas; o DDMira cita na 2ª etapa da OBN um alvo prioritário "Meka" que nenhuma outra fonte descreve |

Olimpíadas, por etapa (olim.html 2015 e shekinah 2011):
- **Balões**: 99 pontos; vermelhos somam 1 a 5, verdes tiram 1 a 4; um balão especial dobra (de flor, que dobra o
  total, ou com X, que dobra a rodada: as fontes divergem); 40 rodadas (2011) ou 10 turnos por jogador
  (emulador).
- **Corrida (só Normal)**: o seu time (rosa/vermelho) precisa levar todos ao pódio antes do rival (azul); ferir
  os rivais ("os muito feridos não andam", dica: ferir 3 por rodada); o seu time não toma dano dos seus tiros;
  se o rival chegar antes, recomeça.
- **Boxiador (Menino Torto)**: duas vidas; deixa cansado, selado e algemado; a torcida dopa o juiz, ataca e
  defende; **acordar o juiz** anula efeitos de dano e armadura, mas **na 3ª vez o personagem morre**.
- **Juiz ladrão (Difícil/Avançado)**: só recebe dano pelas costas (ou no alto do chapéu); bolha quando bebe.
- Solo: nenhuma fonte trata; os dados de base sugerem 3 a 4 jogadores.

Referências de mira da rainha (só referência, sem posição nem vento): 40/60 e 24/100 (guia), 23/100 (vídeo do
Fácil, 2015), 28/70 (vídeo do Normal, 2015).

### Bots e aimbots pedidos na missão

| Projeto | Licença | O que foi lido | Aproveitado (só ideias) | Não serve |
|---|---|---|---|---|
| [tkzt/ddt-sharp-shooter](https://github.com/tkzt/ddt-sharp-shooter) (arquivado; 2019–2025) | nenhuma | main.py, ocr.py, force.py, km.py, dss.spec, tags v1/v2 | modelo com arrasto linear em forma fechada (mesma família do nosso; constantes de 2025: R 1,05235, w 5,50187, g −163,566); unidade = largura do retângulo do minimapa / 10; README: barra cheia em 4,0–4,3 s em servidores antigos e skill de pet que acelera a barra quebra o disparo por tempo | regiões fixas (escala w/1500 com bug na origem), OCR genérico (ddddocr) com remendos, posições marcadas à mão, disparo sem conferência |
| [vitor-carvalho-ddt/DDTankBot-Clib](https://github.com/vitor-carvalho-ddt/DDTankBot-Clib) (2023) | nenhuma | README, main.py, wind_image_ocr.py, possible_wind_sets.py | só o vento é lido da tela: recortes em frações da janela, cinza ampliado 4×, `matchTemplate` ≥ 0,85 contra 121 moldes de dígitos (valor montado "d1.d2", sem sinal); moldes reescalados quando a janela difere de 942×646 | ângulo, força e turno por **leitura de memória** (fora do escopo, não detalhado); **compra itens sozinho**; módulo ausente no repositório; o README admite que o vento falha; nenhuma fórmula de mira |
| [DavidBarishev/DDtankFarmingBot](https://github.com/DavidBarishev/DDtankFarmingBot) | GPL-3.0 | conferência | nada novo (contrato de módulo `FarmAction`) | — |
| [qozi/ddtank-onhook](https://github.com/qozi/ddtank-onhook) (fork de windors/ddtank) | nenhuma | conferência | nada novo; windors avisou em 2025-09-30 que não haverá atualização | — |
| [DDMira](https://ddmira.com/aimbot-ddtank) (comercial, r454) | — | página, capturas da HUD | ideias de interface: prévia da trajetória, marcador na barra, "Configure fora da partida", sequência de atividades; nomes OBN/OBD | alegações de desempenho não verificáveis; anuncia **PvP automático** (o JonFlow não faz) |
| [DDTool](https://ddtanktool-br.blogspot.com/p/guia-de-uso.html) (2012-12-23) | — | guia e 3 imagens | invisíveis: alvo e origem fixados **à mão**; vento manual | não estima posição de invisíveis |
| [AINBOT, felpp25/ddtank-bot](https://github.com/felpp25/ddtank-bot) (2026-09-10, feito para o DDClássico) | nenhuma | README, solver.py, tables.py, calib.py, vision.py, tiro.py, log | **única medida do DDClássico**: barra cheia em 3,30–3,35 s e 44–94 ms até começar (navegador); vento 0,0 a 4,0 (dígito vermelho, ponto, dígito ciano); escala pela régua do rodapé e pelo minimapa; κ do vento pela mediana dos impactos; ângulo exibido com histerese | modelo sem arrasto (só corrige vento e desnível sobre as tabelas); posições ainda marcadas com F1/F2 |
| PyPI `ddtank` 1.1.3 / `ddtcv` | MIT declarado sem texto próprio | aim.py, status.py | desnível por referencial girado; o próprio personagem achado pela diferença entre duas capturas | coordenadas fixas 1000×600, cliente Flash |
| SoBadFish/DDT_YOLO_AI (AGPL-3.0), Mikasa1997/ddtCalculator, FogMoe/DDT.Helper (GPL-2.0) | — | arquivos principais | detecção em dois estágios com leituras estáveis; tempo por ponto de força varia por servidor (33 a 57,5 ms) | — |

Calculadoras reconferidas (ddladora, huongtx498, BoomShot): nenhuma fórmula mudou desde 2026-10-19.

**Correções a seções anteriores (texto integral do 52pojie, página 1, 2020-03-16):** os dados do ajuste usam
**tiro alto com força 90** (não 95) e, nos ângulos fixos, **F = tabela − vento**; o autor descarta o modelo sem
arrasto porque o erro depende do ângulo (não por "arredondamento das entradas", que não aparece na página 1); a
tabela de 65° que o autor usa é a do TechTudo (a citada como "52pojie" veio de uma resposta de 2020-04-18). Uma
reimplementação própria do modelo com arrasto, comparada às tabelas (vento 0, terreno plano), dá erro médio de
0,6 a 1,6 ponto de força conforme o ângulo, próximo do nosso ajuste (RMSE 1,01).

### O que virou código na 0.5.0 (não validado no jogo)

- Seis atividades pré-cadastradas (`data/knowledge/catalogo.json`) com perfis por dificuldade
  (`instances.json`, versão 2). Fácil e Normal do Formigueiro só diferem nos metadados (as fontes não mostram
  outra diferença).
- Olimpíadas Bugou Normal: balões como etapa de **pontuação** (mira o balão que mais soma contando a explosão,
  nunca um verde; valores médios das fontes: vermelho +3, verde −2,5, dobro +6), **corrida** contra os Bugous
  rivais (escolha "agrupado"), **Boxiador** com o **juiz como papel a evitar**. Sem os modelos dos balões
  verdes, dos rivais ou do juiz, a etapa pausa em vez de atirar.
- Galinheiro: etapas por dificuldade conforme o guia de 2013, com troca de etapa pelo que a tela mostra.
- Barra de força 3,33 s + 0,06 s como padrão para instalações novas; força recomendada limitada a 98.

### Ainda a avaliar

- No cliente: se Formigueiro Fácil e Galinheiro Fácil existem no DDClássico; as etapas reais do Galinheiro e se
  a OBN tem a corrida; o que é o "Meka"; o tempo real da barra (e se algum pet a acelera).
- Ideias ainda não implementadas: posições pelo **minimapa** (alvos fora da tela), escala pela **régua do
  rodapé**, próprio personagem pela **pulsação/diferença entre quadros**, prévia da trajetória na interface,
  fixar à mão alvo e origem de invisíveis (DDTool), tridente (±5°, força ×1,1/×0,9).
- Termos do DDClássico (`/classic/terms` pelo endereço espelho) sobre programas de automação.

---

## Pesquisa de 2026-10-19 (instâncias e calculadoras)

Método: as páginas foram baixadas e o texto foi lido do HTML bruto. Os resumos automáticos de ferramentas de busca
erraram pelo menos uma vez (disseram que a página do Formigueiro não tratava do Galinheiro, e tratava), por isso
nada foi aceito só pelo resumo. Licenças conferidas pela API do GitHub.

### Fontes de instâncias

| Fonte | Data | O que traz | Limitações | Confiança |
|---|---|---|---|---|
| [Índice de instâncias](https://ddtankdejogadorparajogador.blogspot.com/p/inst.html) (blog "DDTank de jogador para jogador") | barra lateral "Atualizado (10/2017)"; comentários de 2014–2024 | lista de instâncias; Redemoinho e Arena de Guerreiros sem página; bloco sem título (provavelmente da Arena): Pandora e Midas, depois Piatan | DDTank oficial, não o DDClássico; Redemoinho sem conteúdo | baixa |
| [Formigueiro e Galinheiro](https://ddtankdejogadorparajogador.blogspot.com/p/formigueiro.html) | idem | Formigueiro: "a instância mais fácil", atirar onde há mais formigas, rainha "a 40 - f 60" e "a 24 - f 100". Galinheiro (Pintinho Corre Rápido): matar os frangos "antes que te alcancem", galos e galinhas, veneno em área, "é bom ter ajuda de outros jogadores" | sem nível mínimo, sem número de turnos, posição do jogador não informada nos ângulos | média |
| [Castelo Bugou](https://ddtankdejogadorparajogador.blogspot.com/p/castelo-bugou.html) | idem | Avançado com 5 etapas (S3 = teste da chave), Difícil com 4; Barão imune de frente, "quase impossível com apenas um jogador"; Midas com duas vidas e escudo; Matias com detonação que só o gelo impede | **nenhuma fonte descreve a dificuldade Normal** | média |
| [Lição 1: Instancias](https://bielpontes.wordpress.com/2012/12/07/licao-1-instancias/) (XxGoldDragonxX, Servidor 18) | 2012-12-07 | Formigueiro: "Mate todas as formigas", depois "Apenas atire na rainha". Reino de Bugou em 4 etapas: Bugous, Barão ("ataque apenas o curativo... de frente usará um escudo"), Midas ("quando ele utilizar o escudo, ataque apenas por cima"), Matias ("quando acender o pavio, é necessário jogar gelo") | versão de 2012 | média (a mais antiga e independente) |
| [dicasddt.webnode.page](https://dicasddt.webnode.page/instancias/castelo-bugou/) (Formigueiro, Galinheiro, Bugou) | "© 2015" | o mesmo texto do blog, com dicas de consumíveis | **cópia**, não é fonte independente | baixa |
| Tribo Piatan, Castelo Sombrio, Covil do Dragão, Olimpíadas Boom, Ilha dos Enamorados (mesmo blog) | ~2014–2017 | etapas, chefes e mecânicas (planta curada com Dom de Anjo, barril com gelo, lobo/águia com proteção alternada, Minotauro de joelhos, Dragão só no olho, balões e corrida) | muitas etapas dependem de itens ou de outros jogadores | baixa |
| [ddclassico.com/classic/news](https://ddclassico.com/classic/news) e [/news/37](https://ddclassico.com/classic/news/37) | — | — | **HTTP 403 (Cloudflare) em todas as tentativas** (curl, WebFetch, proxy); Internet Archive fora do ar. A lista do evento da notícia 37 (Formigueiro Normal, Galinheiro Difícil, Bugou Difícil, Covil Normal, Redemoinho Fácil, Olimpíadas Difícil, Sombrio Normal, Piatan Normal) vem da mensagem do usuário, não de leitura própria | nenhuma leitura; disponibilidade atual **não confirmada** |
| App Store do DDClássico | versões 1.0–1.0.2 (ago–set) | endereço dos termos: https://ddclassico.com/classic/terms | os termos também deram 403: **as regras sobre automação não foram lidas** | — |

### O que virou estratégia

| Instância | Etapas no perfil | Regras implementadas | Dúvidas que só o cliente responde |
|---|---|---|---|
| **Formigueiro** | Formigas → Rainha | etapa 1: atira onde há mais formigas juntas; etapa 2 começa quando a rainha aparece (3 leituras seguidas) e só a rainha é alvo; se ela some, espera | se as duas etapas são batalhas separadas; quantas formigas; se a rainha aparece já na 1ª |
| **Galinheiro** | Frangos → Galos e galinhas → Chefe | mira primeiro o inimigo mais perto (os frangos avançam até você); para depois de derrotas seguidas | nome e mecânica do chefe; se é possível sozinho |
| **Castelo do Reino de Bugou — Normal** | Bugous → Barão → Midas → Matias (4 etapas, inferidas do guia de 2012 e da Difícil) | Barão com o escudo visível = imune (ataca outro inimigo ou espera); escudo do Midas = só tiro alto (ângulo ≥ 60) nas duas fases; pavio do Matias = pausa e pede o gelo (o bot não usa itens) | o número real de etapas do Normal; como é a imagem do escudo e do pavio no DDClássico |

As demais (Covil do Dragão, Tribo Piatan, Castelo Sombrio, Olimpíadas Boom, Ilha dos Enamorados, Redemoinho,
Arena de Guerreiros) ficaram registradas com `suporte: "pesquisa"`: o bot não joga sozinho com elas, porque várias
etapas são testes de habilidade, exigem itens (gelo, Dom de Anjo) ou outros jogadores.

### Calculadora nova: huongtx498/DDTank-ForceCalculate

- [Repositório](https://github.com/huongtx498/DDTank-ForceCalculate), Django 3.0.6, último push em 2020-05-14,
  **sem licença** (não copiar código). Cliente vietnamita (Gunny).
- `views.py`: `ângulo = floor(90 − floor(d) + 2·v + floor(h)/4)` e `força = 95 + 4·(d − floor(d))`. O tipo de tiro
  é lido e ignorado.
- Comparação: o tiro alto (90 − d ± 2v, força 95) é o mesmo da ddladora e do BoomShot. A novidade é o termo de
  altura h/4 e a regra de 4 pontos de força por unidade de distância. Ficaram registrados como **hipótese** em
  `mechanics.json` (`full_angle_height`); o bot continua usando o modelo físico para altura e fração da distância.
- Reconferidos no código: ddladora (`index.html`, `90 − d ± 2v`, força 95 fixa, limitado a 0–120) e BoomShot
  (`FORMULAS.md`: gravidade 400 px/s², arrasto 0,06, vento×10, Euler). Sem mudança no que já estava documentado.
- DavidBarishev (GPL-3.0) e qozi/ddtank-onhook (sem licença): nada novo em relação à seção de 2026-10-16.

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
