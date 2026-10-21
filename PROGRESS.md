# Andamento

Última atualização: 2026-10-20. Versão: **0.5.0** (**JonFlow**, antes *DDClássico Bot*), publicada pela tag
`v0.5.0` (ver a primeira seção). A anterior é a 0.4.4.

> **Nada foi testado no cliente real do DDClássico nem com o launcher real.** Os resultados abaixo vêm de
> testes unitários, simulações, imagens sintéticas, janelas e processos de teste no Windows da CI e da
> execução do `.exe` no Windows da CI (sem o jogo). O ambiente de desenvolvimento é Linux, sem o jogo.

## Versão 0.5.0 (2026-10-20): seis atividades prioritárias pré-cadastradas

### Onde parou (retomar daqui)

| Item | Estado em 2026-10-20 |
|---|---|
| Versão | **0.5.0** (`src/ddbot/__init__.py`, `packaging/version_info.txt`, `docs/RELEASE_NOTES.md`) |
| Git Flow | `feature/atividades-prioritarias` mesclada em `develop` (`37e2151`); `release/0.5.0` saiu de `develop` e vai para `main` (tag `v0.5.0`) e de volta para `develop`. A pedido do usuário, as branches temporárias (`feature/atividades-prioritarias`, `release/0.5.0` e a de diagnóstico `diag/layout-windows`) são apagadas depois da publicação |
| Release | a tag `v0.5.0` dispara a CI que publica a Release; a conferência fica na seção "Publicação" abaixo |
| Commits desta fase | `8dc8c79` (atividades, estratégias, interface), `c47061c` (layout: páginas da Calibração e Histórico em 150%), `6fd3e2a` (texto das pendências), `fab2d2a` (espaços em janela baixa; janelas de teste vivas), `d78c520` (`pytest.ini` com captura `sys`) e os de documentação |
| CI da branch de trabalho | 39476307312 (`8dc8c79`) aprovada, mas as capturas do Windows mostraram os defeitos de layout. 39525965108 (`c73d753`) e 39528958704 (`fab2d2a`): falharam no Windows (Histórico em 150% com a Segoe UI; Tk que não abre ou derruba o processo nos testes). Diagnósticos 39527994935, 39529912761, 39530194693 e 39530426640. **39531730837 (`d78c520`) aprovada**: Linux 307 aprovados e 4 pulados; Windows 307 aprovados e 4 pulados na tela de 1024×768 (os 4 de layout) e **311 de 311 em 125%** (1920×1080, com os de layout); janelas reais 12 de 12 em 100% e em 125%; `.exe` da pasta e de arquivo único com autoteste e interface OK (atraso máximo 41 e 87 ms; pasta somente leitura 228 ms); **layout das capturas sem problemas em 100%, 125% e 150%** |
| CI do commit `8dc8c79` | execução 39476307312 **aprovada**: Linux 302 aprovados e 4 pulados; Windows 306 de 306 em 100% e em 125%; janelas reais num venv com o Chrome aberto 12 de 12 nas duas escalas; `.exe` da pasta e de arquivo único com autoteste e interface OK (atraso máximo 104 e 41 ms); pasta somente leitura OK. As capturas da interface no Windows mostraram dois defeitos de layout que a auditoria não pegou (seção seguinte) |
| Documentos de usuário | `README.md` (LEIA-ME do pacote), `docs/ROTEIRO_TESTE_REAL.md` e `docs/RELEASE_NOTES.md` descrevem a interface da 0.5.0 (`c73d753`), com os nomes dos botões conferidos no código |

### Publicação

CI da `release/0.5.0`: a execução 39534334539 (`build: versão 0.5.0`) falhou só na suíte em 125% do Windows, em
`test_vision_to_keyboard_shot`: a força saiu 6,4 pontos acima (tolerância 6) numa rodada lenta (442 s; o normal é
240–300 s). O jogo falso desse teste enchia a barra em 0,5 s, então 6 pontos eram só 30 ms; os outros testes de
força já usavam 2 s. O teste passou a usar 2 s (o programa não mudou; no jogo real, com 3,33 s, 32 ms são ~1 ponto).

A tag `v0.5.0` (no merge da `release/0.5.0` em `main`) dispara a CI que compila, testa e publica a Release com
`JonFlow.exe`, `JonFlow.zip`, `SHA256SUMS.txt`, `build-info.json` e os relatórios. A conferência da Release
publicada (assets, somas, `build-info.json`, links do README) é registrada aqui, em `develop`, depois da publicação.

### O que foi implementado e corrigido (commit `8dc8c79`)

**Atividades pré-cadastradas** (`src/ddbot/catalog.py`, `data/knowledge/catalogo.json`)
- As seis atividades aparecem no Início **antes de conectar ao jogo**, na seção **Instâncias**: Formigueiro —
  Fácil, Formigueiro — Normal, Galinheiro — Fácil, Galinheiro — Normal, Galinheiro — Difícil e Olimpíadas
  Bugou — Normal. A seção **Partidas automáticas** mostra só as modalidades capturadas do cliente (e a partida
  de demonstração no modo demonstração).
- **Castelo do Reino de Bugou — Normal saiu da lista principal** (registrado em `fora_da_lista_principal`); o
  perfil `bugou_normal` continua para atividades capturadas pelo menu.
- O fluxo usa modelos compartilhados: a opção da instância (`instancia_<instancia>`, uma captura para todas as
  dificuldades) e o botão da dificuldade (`dificuldade_facil|normal|dificil`, uma captura para todas as
  instâncias). Um arquivo do usuário com o mesmo id em `instancias/` substitui a versão do catálogo.
- **Disponibilidade só por evidência** (`dados/atividades_estado.json`): "vista no menu" (opção reconhecida numa
  captura ou escolhida pela rotina), "não encontrada no menu" (a rotina procurou e não achou), "indisponível"
  (marcada pelo usuário). A demonstração não muda nada disso.
- Opção ou dificuldade ausente no menu: a rotina **pausa** com "… não foi encontrada no menu do jogo …: o bot não
  escolhe outra atividade no lugar" (sem tentar fechar avisos). O clique numa opção (instância, partida ou
  dificuldade) é **recusado** quando outra opção do mesmo tipo casa no mesmo lugar quase tão bem (diferença menor
  que 0,03): evita confundir Olimpíadas Bugou com o Castelo de Bugou.

**Estratégias** (`src/ddbot/strategy.py`, `data/knowledge/instances.json` versão 2)
- Perfis por dificuldade com herança (`base`, `etapas_ids`, `ajustes_etapas`, `limites_extra`, `fontes_extra`);
  as dificuldades usam as mesmas capturas de alvos (`modelos`: `alvo_formigueiro_rainha` serve ao Fácil e ao
  Normal).
- A etapa é a que a tela mostra (`entra_com`), inclusive voltando para uma etapa anterior quando nada da atual
  está na tela; nunca larga uma etapa com o chefe dela visível. Motivo: as fontes divergem na ordem das etapas.
- Tipos de etapa novos: `pontuacao` (alvos com pontos: mira o que mais soma contando o que a explosão pega em
  volta e nunca um alvo que tira pontos) e `corrida`. Papéis a `evitar` (o juiz): nenhum disparo perto deles.
  Etapas que não são combate comum exigem os modelos (`requer`): sem eles, **pausa** em vez de atirar. Efeito novo
  `vulneravel` (prioridade).
- `match_profile`: com dificuldade no nome, prefere o perfil daquela dificuldade; sem dificuldade, só o perfil
  geral (nunca chuta uma dificuldade); "Bugou Normal" sozinho não associa nenhuma das duas instâncias.

**Interface** (`gui/main_window.py`, `gui/detect_dialog.py`, `gui/theme.py`, `gui/widgets.py`, `gui/states.py`)
- Início em três colunas: **Atividades** (seções Instâncias e Partidas automáticas, com o estado de cada uma:
  pronta, calibrar, não achada, indisponível, demo), **detalhes** (estratégia, conexão, disponibilidade, quantos
  itens obrigatórios já são reconhecidos, pendências, "Ver pendências", "Não aparece no meu jogo", quantas vezes,
  Iniciar/Pausar-Retomar/Parar) e **Andamento** (contadores e mira).
- Calibração: página **Pendências** (primeira) com cada item, o "como fazer" e **Fazer agora** (abre a página
  certa com o item escolhido e captura a tela se preciso); página Menu associa a opção a uma instância do
  catálogo; Regiões com **Sugerir regiões** e **Ângulo pelas teclas**; Alvos mostra a estratégia fixa das
  pré-cadastradas e marca os alvos obrigatórios.
- Mira e disparos: colunas Previsto, Origem e Instância; estatística só do cenário atual e quantos disparos são
  de outros cenários.

**Defeitos corrigidos**
- **Camada escura na seleção da janela** (relatado em versões anteriores): a causa era a `PickOverlay`, uma janela
  preta semitransparente sobre todos os monitores. Removida. Agora: **Escolher pela imagem** (galeria com a
  prévia de cada janela candidata) e, como exceção, **Apontar com o mouse** (a janela Detectar jogo sai da
  frente, a principal continua minimizada, um aviso pequeno no canto conta 3 s e escolhe a janela sob o mouse,
  sem clique; volta com a prévia para confirmar).
- **Parada intermitente do `--gui-smoke` no Windows** (1,7 a 5,3 s depois de Pausar, aberta desde a 0.3.0): o
  ícone "❚❚" da faixa não existe na Bahnschrift e o Tk varria as fontes do sistema (556 ms frio medido na CI de
  diagnóstico 39440415870). O ícone ganhou fonte própria (`Segoe UI Symbol`, `theme.ICON_FAMILIES`) e os ícones
  são medidos na abertura. Na CI 39476307312 o teste da interface passou nas 4 execuções no Windows (suíte em
  100% e em 125%, `.exe` da pasta e de arquivo único; atraso máximo 104 ms). Como a parada era intermitente, uma
  execução não prova que acabou: continuar observando.
- Captura da tela na Calibração e "Salvar captura" rodavam na thread do Tk; agora em thread. Se a captura for
  recusada porque a janela do JonFlow cobre o jogo, ela se minimiza só durante a captura e volta.

**Mira e calibração** (`aiming.py`, `combat.py`, `calibration.py`, `game_io.py`, `vision/autodetect.py`)
- Sugestão de regiões por conteúdo da imagem (barra de força, ângulo, vento, área de jogo com faixas dos dois
  lados) e ângulo pela diferença ao apertar ↑/↓ no seu turno (não atira). Sempre confirmadas pelo usuário; regiões
  já marcadas não são trocadas (só o Ângulo pelas teclas, pedido explícito, troca a do ângulo).
- Cada disparo registra instância, dificuldade, etapa, alvo e **cenário** (modo de controlar a força + programa do
  cliente). A correção usa só disparos do mesmo cenário e da mesma arma; bancos antigos ganham as colunas e os
  disparos antigos (sem cenário) ficam fora da correção. Ajuste com **pesos de Huber** (robusto a disparos
  marcados errado).
- Ângulo recomendado **estável no turno** (só troca se outro for 5 pontos de chance melhor). Força recomendada
  limitada a **98** (perto do fim a barra volta a esvaziar).
- Padrão da barra para instalações novas: **3,33 s** até 100 e **0,06 s** até começar a encher (medida de
  terceiros no DDClássico, AINBOT 2026; antes 4,0 s). Quem já tem `config.json` mantém o tempo salvo (4,0 s),
  mas passa a usar a espera inicial de 0,06 s, que é um campo novo (Configurações > Força do disparo). A
  confirmar no cliente.

### Defeitos de layout achados nas capturas do Windows (CI 39476307312) e corrigidos

As capturas da interface que a CI tira no Windows (Segoe UI, 1920×1080, escala simulada com `DDBOT_UI_SCALE`)
mostraram defeitos que a auditoria automática não acusava. Medidas no container (DejaVu, janela de 1830×948 em
150%, como num PC 1080p a 150% com a barra de tarefas):

| Defeito | Causa encontrada | Correção (commit `c47061c`) |
|---|---|---|
| Abas da Calibração cortadas ("Pendênc", "Regiõ", "Mer", "Alvc") em **100%, 125% e 150%** | Com a página Pendências, seis abas não cabiam na coluna de 390 px (pediam 446 px em 100% e 562 px em 125%); o ttk espreme as abas e corta os nomes. A auditoria só olhava labels e botões | As páginas são escolhidas por **botões em duas linhas** (`Segment.TRadiobutton`, com a moldura dos botões comuns); o caderno continua trocando o conteúdo, sem abas (layout `null`), e o seletor acompanha as trocas feitas pelo código (Ver pendências, Fazer agora) |
| Em **1080p a 150%** o Histórico do Início ficava sem nenhuma linha (0,8 linha, cabeçalho cortado) | Na 0.5.0 o Início ganhou três colunas e o Andamento, mais estreito, empilhava os contadores em 2×2 com o rótulo embaixo e a situação numa linha própria: a linha de cima pedia 468–490 px, e a janela a 150% tem só ~630 px lógicos de altura. O grid corta o que não cabe | Andamento: situação e barra na mesma linha, contadores com o rótulo ao lado. Detalhes: espaçamentos menores, atalhos mais baixos (`Small.TButton`) e "Falta calibrar" numa linha (o primeiro item; a lista completa fica em Ver pendências). Atividades com barra de rolagem, pedindo 8 linhas em janela baixa. Mínimo do Histórico para o título, o cabeçalho e duas linhas. No container isso deu 2,5–2,8 linhas em 150%, mas **no Windows não bastou** (CI 39525965108: as linhas da Segoe UI são ~14% mais altas que as da DejaVu). Por isso, em janela baixa, a barra do topo, a faixa de estado, o espaço entre os painéis e as margens dos painéis do Início também ficam menores (commit `fab2d2a`): 4,2–4,5 linhas no container e, no Windows (diagnóstico 39527994935, Segoe UI), nada cortado em 100%, 125% e 150%, com 3 a 4 linhas visíveis no combate em 150% |
| Lista dos disparos registrados (aba Mira) com menos de uma linha em 150% (**já era assim na 0.4.4**) | As opções de disparo pediam 7 linhas fixas | Em janela baixa (`MainWindow.compact`: menos de 700 px lógicos de altura, como 1080p a 150%) pedem 5, com rolagem; em 100% e 125% continuam as 7 |
| Auditoria cega a esses casos | Só via texto cortado e widget fora da janela; e o `lookup` do ttk devolve tupla, que era lida como zero | `audit_layout` também acusa abas espremidas (largura natural das abas maior que o caderno), widget cortado pelo painel onde está e Treeview com menos de duas linhas inteiras; só o widget mais externo de cada corte é listado |

Testes novos em `tests/test_gui_layout.py` (precisam de tela de 1920×1080; pulados em telas menores): a auditoria
pega os três tipos de defeito; a janela em 100%, 125% e 150% não tem nada cortado no Início (sem jogo,
demonstração e combate), nas abas e nas seis páginas da Calibração; os botões das páginas abrem a página certa.
Com a interface do `8dc8c79` eles **reprovam** (abas 446 > 366 px em 100% e 562 > 458 px em 125%; Histórico com
0,83 linha em 150%). A CI agora roda o Linux com tela de 1920×1080 e tem o passo **"Layout das capturas"**, que
reprova se algum relatório de layout das capturas do Windows tiver problema.

**Queda do processo de testes no Windows** (CI 39525965108, rodada em 125%, na primeira vez que os testes de layout
rodaram lá): `Windows fatal exception: code 0x80000003`, o *panic* do Tcl. A pilha mostra a coleta de lixo rodando
na thread de procura do jogo (`refresh_windows` → `auto_connect`) de uma janela de teste já fechada: ela liberou o
interpretador Tk fora da thread que o criou. Uma primeira correção (esperar as threads e coletar o lixo na thread
principal) trocou o problema por outro, visto no diagnóstico 39527994935: liberado no meio da sessão, o Tk criado
em seguida às vezes não lia os próprios arquivos ("Can't find a usable init.tcl … couldn't read file … No error").
Com as janelas guardadas vivas até o fim do processo (fixture `tk_cleanup`, `fab2d2a`), a queda sumiu, mas o Tk
seguinte ainda falhou na CI 39528958704 (5º Tk do processo, sem nenhuma janela do JonFlow montada antes). Dois
diagnósticos no Windows isolaram a causa:

| Experimento | Resultado |
|---|---|
| 39529912761: fora do pytest, 12 `Tk()` por processo em 7 cenários (vivos, destruídos, coletados, com o tema e com a janela do JonFlow, 2 vezes cada) | **nenhuma falha** |
| 39530194693: só os testes de interface, 4 vezes com a captura `fd` (padrão do pytest) e 4 com `sys` | nenhuma falha |
| 39530426640: suíte completa, 2 vezes com `fd` e 2 com `sys` | `fd`: **1 de 2 falhou** ("Can't find a usable tk.tcl"); `sys`: 2 de 2 passaram |

A captura `fd` troca os *handles* padrão do Windows a cada teste e fecha os anteriores; o Tcl guarda os canais
padrão com esses *handles*, e a falha aparece quando a suíte inteira já abriu e fechou muitos arquivos antes. O
`pytest.ini` novo fixa `--capture=sys` (vale para a CI, o `build_windows.bat` e quem roda localmente). Ficam as duas
proteções: captura `sys` e janelas de teste vivas até o fim. **Só os testes eram afetados**: o programa abre um
único Tk, que só é liberado na saída, e não troca os *handles* padrão.

Também corrigido: as instruções das pendências diziam "Deixe o jogo **em a** tela principal" / "em o menu"
(`readiness.STATE_HINTS` agora vem com a contração; commit `6fd3e2a`, com teste).

A afirmação anterior deste arquivo ("nenhum texto cortado" nas capturas do container) valia só para o que a
auditoria antiga olhava: as abas da Calibração já estavam espremidas também no container.

### As seis atividades prioritárias

| Atividade | Perfil e etapas | No DDClássico (fontes lidas) | Simulação | Jogo real |
|---|---|---|---|---|
| Formigueiro — Fácil | `formigueiro_facil`: formigas → rainha | **sem notícia oficial**; existia na versão clássica | completa (1 e 3 execuções) | não testado |
| Formigueiro — Normal | `formigueiro_normal`: formigas → rainha | notícia oficial 37 (16/10/2026) | completa | não testado |
| Galinheiro — Fácil | `galinheiro_facil`: pintinhos → chefe e gaiola | **sem notícia oficial** | completa | não testado |
| Galinheiro — Normal | `galinheiro_normal`: pintinhos → construção → chefe e gaiola | vídeo de jogador (07/09/2026) | completa | não testado |
| Galinheiro — Difícil | `galinheiro_dificil`: pintinhos → galos e galinhas → chefe e gaiola → construção (ordem suposta) | notícia oficial 37 | completa | não testado |
| Olimpíadas Bugou — Normal | `olimpiadas_bugou_normal`: balões (pontuação) → corrida (rivais) → Boxiador (juiz a evitar) | Difícil na notícia 37; Normal em vídeos e no DDMira | completa, sem balão verde nem juiz atingidos | não testado |

"Simulação" = cenários **fictícios** (vida, posições e quantidades inventadas) que exercitam a lógica; não dizem
nada sobre o jogo real. Para jogar no cliente, cada atividade ainda depende das capturas listadas em
Calibração > Pendências (telas, botões, opção da instância, botão da dificuldade, regiões, números, marcadores e,
nas Olimpíadas, os modelos obrigatórios dos balões verdes, dos rivais e do juiz).

### Testes executados nesta sessão

| Verificação | Onde | Resultado |
|---|---|---|
| `python -m pyflakes src tools tests` | Linux (dev) | sem avisos |
| pytest, suíte completa | Linux (dev, Rocky 10, sem tela) | **296 aprovados, 6 pulados** (2 sem tela, 4 só no Windows), 271 s |
| pytest, suíte completa | container Ubuntu 24.04 + Xvfb (imagem `jonflow-ci`) | **302 aprovados, 4 pulados** (só Windows), 270 s |
| `--selftest` | Linux (dev) | OK; as seis atividades e os três perfis gerais completam na simulação (~25 s nessa etapa); também aprovado dentro da suíte (`test_selftest_cli`) no código do `8dc8c79` |
| `--gui-smoke 8` | container + Xvfb | OK, atraso máximo 100 ms numa execução avulsa; também aprovado dentro da suíte (`test_gui_smoke`) no código do `8dc8c79` |
| `--screenshots` em 100%, 125% e 150% (1920×1080) | container + Xvfb | nenhum texto cortado nem elemento fora da janela pela auditoria **da época** (que não olhava abas nem cortes por painel: ver "Defeitos de layout") |
| `--simulate 25` | Linux (dev) | ver abaixo |
| CI GitHub Actions (Linux + Windows, exe, capturas) | execução 39476307312 | aprovada (números na tabela "Onde parou") |

Depois das correções de layout e dos testes (código do `d78c520`, 2026-10-20 à noite):

| Verificação | Onde | Resultado |
|---|---|---|
| `python -m pyflakes src tools tests` | Linux (dev) | sem avisos |
| pytest, suíte completa | Linux (dev, sem tela) | 296 aprovados, 7 pulados (3 sem tela, 4 só no Windows), na `release/0.5.0` com a versão 0.5.0 |
| pytest, suíte completa | container Ubuntu 24.04 + Xvfb 1920×1080 | **307 aprovados, 4 pulados** (só Windows), com o `pytest.ini` |
| `--gui-smoke 8` | container + Xvfb | OK, 29 verificações, atraso máximo 88 ms |
| `--selftest` | Linux (dev) | OK |
| `--screenshots` em 100%, 125% e 150% | container + Xvfb | auditoria nova sem problemas (19 capturas por escala) |
| Capturas e testes de layout com a Segoe UI | Windows, diagnóstico 39527994935 | nada cortado em 100%, 125% e 150% |
| CI completa | execução 39531730837 (`d78c520`) | aprovada (números na tabela "Onde parou") |

O `--simulate` não foi repetido: nada da mira nem da simulação mudou depois do `8dc8c79`.

`--simulate 25` (semente fixa 1; "jogo" simulado com velocidade +3%, vento +25%, arrasto −5% em relação ao modelo):

| | Disparos | Acerto | Vitórias | Erro médio 1ª / 2ª metade (régua) | Turnos perdidos |
|---|---|---|---|---|---|
| sem calibração, `8dc8c79` | 166 | 42,2% (70) | 22 | 0,671 / 0,593 | 0 |
| com calibração, `8dc8c79` | 79 | 94,9% (75) | 25 | 0,185 / 0,140 | 0 |
| sem calibração, v0.4.4 (mesmo comando) | 166 | 42,2% (70) | 22 | 0,672 / 0,593 | 0 |
| com calibração, v0.4.4 (mesmo comando) | 79 | 94,9% (75) | 25 | 0,184 / 0,135 | 0 |

- Mesmos disparos, acertos e vitórias que a v0.4.4. Isolando cada mudança, só os **pesos de Huber** mudam o
  resultado: erro da 2ª metade com calibração 0,135 → 0,140 (a simulação não tem disparos marcados errado; o
  ajuste robusto troca um pouco de eficiência por resistência a eles). O teto de força 98 e o ângulo estável não
  mudaram nada nestas 25 batalhas.
- Histórico: 50 batalhas na 0.4.2–0.4.4 deram 40,0% / 96,2%; 15 batalhas, 41,4% / 91,8%. Com 25, 42,2% / 94,9%:
  as diferenças vêm do número de batalhas (o sorteio é o mesmo, a amostra é outra). `--simulate 50` não foi
  executado nesta sessão, como pedido.
- É simulação: um alvo num terreno plano, leituras com ruído e sem a visão. **Não mede a precisão no DDClássico.**

### DDTankBot-Clib: o que foi aproveitado e o que falta avaliar

- Lido: README, `main.py`, `wind_image_ocr.py`, `possible_wind_sets.py` (2023, sem licença: nada copiado).
- Aproveitado como ideia (já existia no JonFlow de forma equivalente): ler números por moldes de dígitos com
  limiar de semelhança (no JonFlow, `DigitReader` com glifos aprendidos e confiança mínima) e reescalar moldes
  quando a janela muda de tamanho (no JonFlow, busca em várias escalas com a escala memorizada).
- Não aproveitado: ângulo, força e turno por **leitura de memória** (fora do escopo; o JonFlow só usa a tela),
  compra automática de itens (bloqueada no JonFlow), regiões fixas em frações de uma janela de 942×646, valor do
  vento sem sinal montado como "d1.d2".
- A avaliar: se o vento do DDClássico tem o mesmo formato (dígito, ponto, dígito; o AINBOT descreve dígito
  vermelho, ponto e dígito ciano) e se o leitor de dígitos do JonFlow lê o ponto decimal nesse visor. Precisa de
  capturas reais.

### Limitações conhecidas

- **Nada foi validado no jogo nem no launcher reais.** Detecção, captura, telas, botões, leitura, disparos,
  etapas e disponibilidade só foram testados com simulação, imagens sintéticas e janelas de teste.
- As etapas vêm de guias de 2011–2015, notícias oficiais (sem mecânicas) e vídeos de 2026 (só títulos); o
  DDClássico diz ter reconstruído os sistemas do zero. A ordem do Galinheiro Difícil e a corrida da OBN são
  incertas; o "Meka" é desconhecido.
- Valores dos balões (vermelho +3, verde −2,5, dobro +6) são médias das fontes, não leituras do jogo; a meta de
  99 pontos não é lida da tela.
- Sugestões automáticas de regiões só foram testadas em imagens sintéticas; o indicador de turno e os marcadores
  continuam dependendo de captura manual.
- Corrida e balões exigem modelos capturados no cliente; sem eles a etapa pausa (seguro, mas não joga).
- O bot nunca acorda o juiz das Olimpíadas (tática que os guias recomendam até 2 vezes): o usuário faz isso com a
  rotina pausada.
- Regras do servidor sobre automação: os termos (`/classic/terms`) ainda não foram lidos.

### Próximos passos (em ordem)

Feitos nesta fase: CI conferida (e os defeitos que ela mostrou, corrigidos), documentos de usuário atualizados e
publicação da 0.5.0 pelo Git Flow (conferência na seção "Publicação").

1. **Primeiro teste no cliente real** (usuário): roteiro em `docs/ROTEIRO_TESTE_REAL.md` e a seção "As seis
   atividades pré-cadastradas" de `docs/TESTES.md`: Detectar jogo, capturar a opção de cada instância e os
   botões de dificuldade, seguir a página Pendências, uma execução de cada atividade com o dedo no F12.
2. **Medir no cliente** o tempo da barra e a espera inicial (padrão 3,33 s + 0,06 s vem de terceiros), a faixa e
   o formato do vento, e conferir se Formigueiro Fácil e Galinheiro Fácil existem.
3. **Investigar com capturas reais**: etapas do Galinheiro por dificuldade, se a OBN tem a corrida e o que é o
   "Meka", como aparecem os balões e o juiz; ajustar `instances.json` (sem mexer no código) e os cenários da
   simulação.
4. Observar a parada da interface depois de Pausar no Windows (causa provável corrigida na 0.5.0; era
   intermitente) e o Tk dos testes no Windows (`pytest.ini` com captura `sys`; se voltar, o `faulthandler` da CI
   mostra a pilha).
5. Ler os termos do DDClássico pelo endereço espelho (`https://ddtclassico.com/classic/terms`).
6. Ideias da pesquisa ainda não implementadas: posições pelo minimapa (alvos fora da tela), escala pela régua do
   rodapé, próprio personagem pela pulsação, prévia da trajetória na interface, fixar à mão o alvo invisível.

## Versão 0.4.4

### Conferência da distribuição (2026-10-20, antes do teste no jogo real)

| Item | Resultado |
|---|---|
| Release | v0.4.4 publicada como *Latest*, não é rascunho nem pré-release |
| Tag × `main` | `v0.4.4` = `origin/main` = `97e4a24` (merge da `release/0.4.4`); `develop` sem diferença de código para a `main` |
| Assets | `JonFlow.exe` (75.377.582 bytes), `JonFlow.zip` (75.690.692 bytes), `SHA256SUMS.txt`, `build-info.json`, `relatorios-de-teste.zip` |
| Integridade | baixados de novo pelo `gh`: SHA-256 conferem com `SHA256SUMS.txt`; o ZIP tem `JonFlow/JonFlow.exe`, `_internal/`, `LEIA-ME.md` e `COMO-USAR.txt` |
| `build-info.json` | versão 0.4.4, commit `97e4a24`, `refs/tags/v0.4.4`, CI 39437768488 (sucesso), Windows 254 de 254 |
| Links diretos | só abrem **logado numa conta com acesso** (repositório privado): sem login, `releases/download/v0.4.4/JonFlow.exe` e `.zip` respondem 404 |
| CI da `develop` 39437781992 (mesmo código) | falhou só no `--gui-smoke` do Windows (interface parada 5,3 s depois de Parar): o defeito intermitente já conhecido do ícone da faixa. Correção adiada para a próxima versão |

Roteiro do primeiro teste com o launcher e o cliente reais: [`docs/ROTEIRO_TESTE_REAL.md`](docs/ROTEIRO_TESTE_REAL.md).
Nada foi validado no jogo ainda.

### Captura do jogo com a escala do Windows acima de 100%

Falha relatada no PC do usuário: a captura do jogo de teste tinha média BGR 43, 108, 22 (64% do verde da janela
de teste, o resto preto). O runner da CI roda em 100% e não a reproduzia. `tools/display_scale.py` passou a mudar a
escala do Windows na CI sem sair da sessão (e sai com erro se o DPI efetivo não mudou). Em 125%, a CI 39422650761
reproduziu a falha, sem a correção: DPI janela/monitor 96/120, BGR 43, 108, 22.

| Causa encontrada | Correção |
|---|---|
| Um programa sem suporte a DPI (a janela de teste e muitos jogos) desenha no tamanho de 100% e o Windows amplia a imagem na tela. O `PrintWindow` era pedido no tamanho da tela: a imagem do jogo vinha 80% menor, num canto, com o resto preto. A conferência com a tela tolera 40% de diferença (por causa da animação) e aceitava essa imagem | `winapi.print_window` pede a imagem no DPI da própria janela (`SetThreadDpiAwarenessContext` só na thread da captura, desfeito em seguida) e `capture.fit_to_area` a amplia para a área do jogo na tela, igual nos dois eixos, como o Windows faz; proporção diferente é recusada. `check_window_image` recusa imagem com faixas pretas à direita e embaixo que a tela não tem (com o jogo coberto, a captura pausa com o motivo). O registro técnico anota uma vez quando o jogo desenha num tamanho e o Windows o amplia |

Testes novos: `test_window_drawn_at_100_percent_on_125_percent_screen` e `test_fit_to_area_only_scales_like_windows`
(sem Windows, em `test_audit_regressions.py`). Os testes de janelas reais exigem a imagem do tamanho da área do jogo
e verde até os cantos; quando reprovam, salvam a captura e o DPI da janela e do monitor (vão para os relatórios
da CI).

Na CI, um passo novo roda em **125%** os testes de janelas reais (num venv, 3 vezes cada) e depois a suíte
completa, e volta a escala para 100% no fim.

### "O `.exe` não está no GitHub, só o `.bat`"

Investigado antes de mudar qualquer coisa. A compilação e a publicação **funcionavam**: a Release v0.4.3 (CI
39362371149, commit `1000526`) tem `JonFlow.exe` (75.374.179 bytes, PE32+ x86-64 GUI), `JonFlow.zip` (pasta
`JonFlow/` com `JonFlow.exe`, `_internal/` com `python312.dll` e o LEIA-ME, 1156 arquivos), `SHA256SUMS.txt` e
`build-info.json`. Baixados de novo, as somas SHA-256 conferem e o `build-info.json` aponta o commit e a execução
da tag. Os builds de desenvolvimento ficam no artefato `JonFlow-windows` de cada execução do Actions.

| Causa encontrada | Correção |
|---|---|
| Os programas só existem nos *Assets* da Release (`release/` está no `.gitignore` de propósito: binário não entra no histórico). Na aba *Code* aparece o `build_windows.bat`, e o README só dizia "baixe na página de Releases", sem link. O repositório é **privado**: os links só abrem logado numa conta com acesso | O README abre com uma tabela **Baixar** com links diretos (`releases/latest/download/JonFlow.zip` e `.exe`, que sempre apontam para a última Release) e explica que o `.bat` é só para compilar. As notas da Release dizem que os arquivos ficam em *Assets* e que "Source code" não traz o programa. Teste novo `test_release_publishes_the_programs_and_readme_links_them`: o job `release` anexa os 4 arquivos, confere o commit, e o README mantém os links |

### Parada da interface no `--gui-smoke` (Windows)

O teste da interface falhou 2 vezes na CI desta branch (39422650761 e 39425409626) com a interface parada 2,4 a
4,3 s logo depois de Pausar, sem mudança no código da interface. O `--gui-smoke` ganhou uma vigia: se a interface
para mais de 1 s, o relatório guarda onde cada thread estava (`pilhas_no_atraso`). Um diagnóstico com 20 rodadas
no Windows (CI 39429246572) passou nas 20 (atraso máximo 557 ms) e não reproduziu a parada; nas execuções
seguintes ela também não voltou. **Causa ainda não encontrada**: se voltar, o relatório mostra onde.

### Resultados (CI 39429245255, commit `6742b03`, antes da versão)

| Onde | Resultado |
|---|---|
| Windows, suíte completa (100%) | 253 de 253 aprovados |
| Windows, janelas reais num venv com o Chrome aberto, 4 testes, 3 rodadas | 12 de 12 aprovados |
| Windows em **125%**: janelas reais, 4 testes, 3 rodadas | 12 de 12 aprovados |
| Windows em **125%**: suíte completa | 253 de 253 aprovados |
| `.exe` da pasta e de arquivo único | autoteste e interface OK (atraso máximo 322 e 197 ms); pasta somente leitura OK |
| Capturas da interface (100%, 125%, 150%) | geradas |
| Linux (`ubuntu-24.04`, Xvfb) | 249 aprovados, 4 pulados (só no Windows) |
| Linux dev: `pyflakes`, `--selftest` | sem avisos; OK |
| Linux dev: `--simulate 50` | 40,0% sem calibração, 96,2% com calibração, 0 turnos perdidos (igual à 0.4.3) |

CI da branch `release/0.4.4` (execução 39434463429, commit `19e32e9`, com a versão 0.4.4 e os links de
download): Windows 254 de 254 aprovados em 100% e em 125%; janelas reais num venv com o Chrome aberto 12 de 12 e
em 125% 12 de 12; `.exe` da pasta e de arquivo único com a versão 0.4.4, autoteste e interface OK (atraso máximo
259 e 197 ms); Linux 250 aprovados, 4 pulados (só no Windows). Os números da compilação publicada estão no
`build-info.json` da Release.

Documentação: o README foi reescrito passo a passo para quem nunca usou o programa (como o bot funciona, passos
numerados, teclas de atalho, problemas comuns e glossário). O AGENTS.md registra a regra da escala do Windows, os
passos da CI no Windows e a vigia do `--gui-smoke`.

Limite: a captura em 125% foi testada com a janela **de teste** (`tests/fixtures/fake_window.py`), sem suporte a
DPI. O cliente e o launcher reais do DDClássico continuam sem validação, inclusive em 125% e 150%.

## Versão 0.4.3

### As três falhas dos testes de janelas reais no Windows do usuário

Reproduzidas na CI antes da correção (execução 39358228747, commit `ecb6b71`): um passo novo roda os testes de
janelas reais **dentro de um venv** e com o **Chrome maximizado**, como no PC do usuário, cada teste sozinho e 3
vezes. A e C falharam nas 3 rodadas, nas mesmas linhas relatadas (79 e 146). Na CI comum elas passavam porque o
Python do `setup-python` não é um venv.

| Falha | Causa encontrada | Correção |
|---|---|---|
| **A** `test_launcher_then_game_in_child_process`, linha 79: `found.launcher` apontava "outro launcher" | No Windows, o `python.exe` de um venv é um **redirecionador** que abre o Python base como processo filho; quem cria a janela é o filho. O teste comparava `found.launcher.pid` (5028, o dono da janela, que de fato abriu o jogo) com `Popen.pid` (1548, o redirecionador, sem janela). A detecção estava associando o launcher certo; a identidade usada pelo teste é que era a errada | As janelas de teste informam o **pid real** e o hwnd (`--ready`). O teste agora confere que o jogo encontrado é o que este launcher abriu, que ele descende do processo dono da janela do launcher e que `found.launcher` é essa janela (pid e hwnd) |
| **B** `test_pick_at_real_window`, linha 134: `pick_at` devolvia "Intermediate D3D Window" do Chrome | `pick_at` seguia só a ordem das janelas do `EnumWindows`, que inclui janelas que não aparecem no ponto: ocultas pelo DWM (outra área de trabalho virtual, apps suspensos) e janelas transparentes ao clique. E o teste supunha o jogo na frente depois de `SetForegroundWindow`, que o Windows recusa quando o processo do teste não está em primeiro plano: um navegador maximizado continuava sobre o ponto. Não reproduzida no runner (o Chrome dele não ficou sobre o ponto) | No clique, vale a janela que **o próprio Windows** diz estar no ponto (`WindowFromPoint`, com a camada de seleção escondida), e só ela e as janelas internas dela entram. Janelas ocultas pelo DWM e janelas principais transparentes ao clique não contam como visíveis (`winapi.shown`). O teste põe o jogo acima das janelas comuns (`--topmost`), confere o cenário com `WindowFromPoint` antes de chamar `pick_at` e testa os dois modos (clique e contorno). Teste novo sem Windows: navegador antes do jogo na lista |
| **C** `test_two_launchers_game_linked_to_the_one_that_opened_it`, linha 146: `StopIteration` | A mesma do A: nenhuma janela tem o pid do redirecionador | Mesma identidade real (`--ready`). Com dois launchers, o teste confere pid e hwnd do segundo e que o jogo **não** descende do primeiro |

Isolamento dos testes: os títulos levam uma etiqueta única por teste (janelas de execuções anteriores ou de outros
programas nunca batem), as palavras-chave do serviço usam essa etiqueta, e a limpeza (em `finally`) encerra só a
árvore de processos do próprio teste e os pids que as janelas dele informaram. Nenhum tempo de espera foi
aumentado: as esperas existentes passaram a aguardar a identidade informada pela janela.

Aviso de depreciação: com o MSS 10.2.0 fixado, `mss.mss()` está obsoleto; a captura usa `mss.MSS` (e
`mss.mss` só em versões antigas). A suíte do Windows passou a rodar sem avisos.

### Resultados (commit `776ed0e`, antes da versão)

| Onde | Resultado |
|---|---|
| CI 39358839810, Windows: os 4 testes de janelas reais, cada um sozinho, 3 rodadas, num venv com o Chrome aberto | **12 de 12 aprovados** |
| CI 39358839810, Windows, suíte completa | 251 de 251 aprovados, 0 pulados, sem avisos |
| CI 39358839810, `.exe` da pasta e de arquivo único | autoteste e interface OK (atraso máximo 56 e 72 ms) |
| CI 39358839810, Linux (`ubuntu-24.04`, Xvfb) | 247 aprovados, 4 pulados (só no Windows) |
| Container Ubuntu 24.04 + Xvfb (dev) | 247 aprovados, 4 pulados; `--gui-smoke 8` OK (25 verificações, 103 ms) |
| Linux dev: `pyflakes`, `--selftest` | sem avisos; OK |
| Linux dev: `--simulate 50` | 40,0% de acerto sem calibração, 96,2% com calibração, 0 turnos perdidos (igual à 0.4.2: o código da simulação não mudou) |

CI da branch `release/0.4.3` (execução 39360961060, commit `77b2db4`, com a versão 0.4.3): Windows 251 de 251
aprovados, sem avisos; janelas reais num venv com o Chrome aberto, 12 de 12; Linux 247 aprovados, 4 pulados (só no
Windows); `.exe` da pasta e de arquivo único aprovados. Os números da compilação publicada estão no
`build-info.json` da Release.

A **v0.4.2** ficou sem Release: a publicação foi cancelada quando estas falhas foram relatadas. A 0.4.3 inclui a
correção do `--simulate` da 0.4.2.

Limite: os testes usam janelas e processos **de teste** (`tests/fixtures/fake_window.py`); o launcher e o cliente
reais do DDClássico continuam sem validação.

## Versão 0.4.2 (sem Release)

Publica a correção do `--simulate` descrita abaixo (commit `b17d179`). O programa no jogo real, a demonstração e
as estratégias não mudaram. CI da branch `release/0.4.2` (execução 39355727642, commit `dee0c3f`): Linux 246 aprovados, 4 pulados (só no Windows); Windows 250 aprovados (0 pulados), com compilação e testes do `.exe` (pasta e arquivo único) aprovados. Os números da compilação publicada estão no `build-info.json` da Release.

## Correção do `--simulate` (entrou na 0.4.2)

### Simulação de precisão (`--simulate`) e defeito encontrado nela

Executado em 2026-10-20 no commit `b17d179` (Linux de desenvolvimento). É **simulação**: um "jogo" de mentira
com constantes físicas diferentes das do modelo (velocidade +3%, vento +25%, arrasto −5%) e ruído de leitura e de
execução, com sorteio fixo (semente 1). Não diz nada sobre a precisão no DDClássico.

**Defeito encontrado:** antes da correção, `--simulate 50` perdia 40 turnos (sem calibração) e 49 (com
calibração), sempre o **1º turno de cada batalha** a partir da 2ª. Causa: o laço de `run_simulation` lia o fim
da batalha uma vez só, mas desde a auditoria da 0.3.0 o motor só aceita o fim após leituras seguidas; o
`reset_battle()` não rodava e o turno da batalha anterior (já com disparo) continuava valendo. Só a medição do
`--simulate` era afetada: a rotina e a demonstração zeram a batalha pelo `on_battle_start`. Corrigido em
`b17d179` (o laço zera a batalha como o `ActivityRunner`), com o teste de regressão
`test_simulation_does_not_lose_the_first_turn_of_each_battle`, que falha no código anterior.

| `--simulate 50` | Disparos | Acerto | Vitórias | Erro médio (1ª / 2ª metade, régua) | Turnos perdidos |
|---|---|---|---|---|---|
| sem calibração, antes da correção | 365 | 37,0% | 41 | 0,711 / 0,686 | 40 |
| com calibração, antes da correção | 155 | 96,8% | 50 | 0,177 / 0,136 | 49 |
| **sem calibração, corrigido** | 350 | **40,0%** | 43 | 0,639 / 0,682 | **0** |
| **com calibração, corrigido** | 156 | **96,2%** | 50 | 0,160 / 0,139 | **0** |

Comparação com versões anteriores, `--simulate 15` medido agora na mesma máquina:

| Código | Sem calibração | Com calibração | Turnos perdidos |
|---|---|---|---|
| v0.2.1 | 41,4% (erro 2ª metade 0,664) | 88,2% (0,175) | 0 / 0 |
| v0.3.0 | 39,6% (1,036) | 91,8% (0,159) | 12 / 14 |
| `b17d179` | 41,4% (0,664) | 91,8% (0,136) | 0 / 0 |

- O defeito entrou na 0.3.0. Com a correção, o resultado sem calibração volta a ser idêntico ao da 0.2.1 (mesmo
  sorteio, mesma mira sem correção).
- O ganho com calibração em relação à 0.2.1 (88% → 92%) vem das correções de mira da auditoria da 0.3.0.
- O valor antigo deste arquivo (35% → 85% em 15 batalhas) **não se reproduz** nem na v0.2.1: foi medido num
  commit anterior. A referência passa a ser a tabela acima.
- A calibração aprende a diferença entre o "jogo" simulado e o modelo; no jogo real, ela só ajuda depois de
  disparos reais registrados.

### Outras verificações no mesmo commit

| Verificação | Resultado |
|---|---|
| `pyflakes src tools tests` | sem avisos |
| `--selftest` | OK (recursos, mira, visão, simulação, estratégias, entrada, interface) |
| pytest, Linux de desenvolvimento (sem tela) | 245 aprovados, 5 pulados (interface: sem display; 4 só no Windows) |
| pytest, container Ubuntu 24.04 + Xvfb | 246 aprovados, 4 pulados (só no Windows) |
| `--gui-smoke 8` (container + Xvfb) | OK: 25 verificações, atraso máximo 108 ms |
| CI 39351639925, Linux (`ubuntu-24.04`, Xvfb) | 246 aprovados, 4 pulados (só no Windows) |
| CI 39351639925, Windows (`windows-2025`), código-fonte | 250 de 250 aprovados, 0 pulados (inclui interface e janelas/processos reais de teste) |
| CI 39351639925, `.exe` da pasta e de arquivo único | autoteste e interface OK (atraso máximo 119 ms) |

A CI rodou no commit `8f187e8` (só documentação sobre `b17d179`, mesmo código). Publicada na 0.4.2.

## Versão 0.4.1 (hotfix)

A CI da tag `v0.4.0` (execução 39346270446) falhou em `test_launcher_then_game_in_child_process`: a cor média da
captura do jogo de teste foi BGR (139, 202, 118), verde predominante (é o jogo, não o launcher azul nem outra
janela), mas mais clara que o verde puro. O teste capturava no instante em que a janela acabava de aparecer,
ainda na animação de abertura do Windows; nas três execuções anteriores, com o mesmo código, passou. O teste agora
espera o jogo terminar de desenhar (até 10 s) e continua reprovando se a imagem nunca for a do jogo. O programa
não mudou. A tag `v0.4.0` ficou sem Release (o pacote dela não passou na CI); a Release é a `v0.4.1`.

CI 39347014865 (commit `70aef23`, branch `hotfix/0.4.1`): Linux e Windows aprovados (245 passed, 4 skipped in 136.29s (0:02:16) / 249 passed, 2 warnings in 290.64s (0:04:50)), compilação e testes do `.exe` (pasta e arquivo único) aprovados. Os números finais da Release estão no `build-info.json` publicado com ela.

## Versão 0.4.0

### Problemas investigados e causas

| Problema | Causa encontrada | Correção | Teste de regressão |
|---|---|---|---|
| `test_service_simulated_run` recebia "automação não autorizada" em vez de "janela" | A mensagem ("…nas Configurações") vem de `CombatEngine.auto_allowed`, alcançada só **depois** de `auto_connect()` conectar a uma janela: no PC com o DDTank (ou outra janela com "DDTank" no título) aberto, o teste conectava nela. A ordem do serviço está certa; o teste não era isolado da área de trabalho | Teste isolado (`inventory` simulado) e um teste novo para "jogo conectado sem autorização → regras"; a demonstração continua sem janela e sem autorização | `test_simulation_service.py` |
| Jogo associado ao launcher errado | (1) `process_parents` confiava no pid do pai guardado pelo Windows, que reaproveita pids: se o processo que abriu o jogo terminou e o pid passou a outro launcher aberto depois, o jogo parecia filho dele; (2) sem parentesco, `launcher_for` escolhia o maior launcher conhecido | Ligação descartada quando o "pai" é mais novo que o filho (`GetProcessTimes`); com vários launchers e sem parentesco, launcher desconhecido em vez de chute | `test_audit_regressions.py` (pid reaproveitado; vários launchers) e `test_windows_real.py` (dois launchers reais, só o segundo abre o jogo) |
| Captura do jogo coberto trazia a janela da frente | (1) `covered()` testava só 5 pontos: uma janela menor entre eles passava e a cópia da tela trazia os pixels dela; (2) a imagem do `PrintWindow` era aceita sem conferência (alguns drivers e sessões remotas devolvem o que está na tela) | Grade de 8×6 pontos; a imagem da janela é conferida com a tela: onde há outra janela por cima não pode ser igual à tela, onde o jogo está descoberto precisa coincidir. Sem confirmação, a captura recusa e explica | `test_audit_regressions.py` (falham no código antigo) |
| `test_actor_refuses_click_when_window_resized` | Já corrigido na 0.2.1 (o teste consultava o Windows de verdade no ponto do clique; a área de trabalho agora é simulada, com os casos tamanho errado, janela por cima e fora da tela) | — | continua passando |
| Partida de demonstração parada no lobby | Já corrigido na 0.3.0 (o simulador não tinha o menu de partidas) | — | `test_demo_flows.py` (uma, três seguidas, contínua) |
| `test-linux` com exit code 1 | Primeiro erro real: `test_gui_smoke` (atraso de 1985 ms após "Detectar jogo": minimizar no Xvfb sem gerenciador de janelas trava o Tk). Runner já era `ubuntu-24.04` (imagem 20261012.334.1): **não** era a migração do `ubuntu-latest`. Corrigido em `7f7143e` | Agora os jobs Linux estão fixados em `ubuntu-24.04` (o `ubuntu-latest` vira Ubuntu 26 a partir de 2026-10-19) e o Windows em `windows-2025` | CI |
| Iniciar travava a interface no jogo real | `svc.start` rodava na thread do Tk e esperava até 2 s o jogo vir para a frente | Iniciar no jogo real em thread | — (o teste de interface só cobre a demonstração) |
| Iniciar ativo sem pré-requisitos | Habilitado com qualquer atividade; a recusa só vinha depois do clique | No jogo real, só com o jogo conectado e a calibração obrigatória completa | `--gui-smoke` (`iniciar_bloqueado_sem_jogo`) |

### Estratégias por instância

`strategy.py` + `data/knowledge/instances.json` (fontes em `sources.json`, pesquisa em `docs/RESEARCH.md`).

| Instância | Estado | O que foi validado |
|---|---|---|
| Formigueiro | estratégia implementada (formigas → rainha) | simulação e imagem sintética |
| Galinheiro / Pintinho Corre Rápido | estratégia implementada (frangos → galos e galinhas → chefe; o mais perto primeiro) | simulação |
| Castelo do Reino de Bugou — Normal | estratégia implementada (Bugous → Barão → Midas → Matias; imune, só por cima, pausa no pavio) | simulação; o número de etapas do Normal é **inferido** |
| Covil, Piatan, Sombrio, Olimpíadas, Ilha, Redemoinho, Arena | só pesquisa (não jogam sozinhas) | — |

Os cenários simulados são fictícios (vida, posições e quantidades inventadas para exercitar a lógica); passar
neles não diz nada sobre o jogo real.

### Resultados

Confirmados na CI 39344826477 (commit `875fd21`, branch `feature/estrategias-instancias`):

| Onde | Resultado |
|---|---|
| Linux (CI, `ubuntu-24.04`, Xvfb) | 245 aprovados, 4 pulados (só Windows) |
| Windows (CI, `windows-2025`), código-fonte | 249 de 249 aprovados, 0 pulados; inclui o teste de interface e os 4 testes com janelas e processos reais (novo: dois launchers, só o segundo abre o jogo → associado a ele) |
| `.exe` da pasta (ZIP extraído, sem Python no PATH) | autoteste OK (inclui as três estratégias simuladas); interface OK (atraso máximo 103 ms) |
| `.exe` de arquivo único | autoteste OK; interface OK (atraso máximo 197 ms) |
| Linux (dev, Rocky 10, sem tela) | 244 aprovados, 5 pulados (interface e só Windows) |
| Linux (dev, container Ubuntu 24.04 + Xvfb) | 240 aprovados, 4 pulados; `--gui-smoke` OK (25 verificações, atraso máximo 105 ms); capturas a 100/125/150% em 1920×1080 sem texto cortado nem área fora da janela (fontes DejaVu, não Segoe UI) |

Falha encontrada pela CI durante o trabalho (execução 39342416224): no Windows, `test_capture_of_covered_game_is_the_game`
recusou a imagem **certa** da janela, porque o jogo de teste passava da borda do monitor do runner (1024×768) e os
pontos fora da tela contavam como "descobertos". A recusa era segura; corrigido em `893107f` (pontos fora da tela
saem da conferência; sem a imagem da janela, a cópia da tela não é usada). Uma revisão independente do diff achou
mais 7 pontos (o principal: o pavio do Matias era ignorado quando o chefe saía só pelo marcador genérico),
corrigidos com testes em `875fd21`.

### O que ainda depende do seu computador

1. Tudo o que está na lista da 0.3.0 abaixo (launcher real, calibração, uma execução real com o dedo no F12).
2. Capturar os alvos e estados das três instâncias e conferir no Diagnóstico ao vivo.
3. Confirmar no cliente as etapas de cada instância (em especial as 4 etapas do Bugou Normal) e como aparecem o
   escudo do Barão, o escudo do Midas e o pavio do Matias.
4. Ler os termos do DDClássico (https://ddclassico.com/classic/terms): o site bloqueou todas as leituras.

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

### Resultados confirmados (CI 38987570650, commit `c53d980`, branch `release/0.3.0`)

| Onde | Resultado |
|---|---|
| Linux (Xvfb) | 210 aprovados, 3 pulados (só Windows) |
| Windows, código-fonte | 213 de 213 aprovados, 0 pulados; inclui o teste de interface e os 3 testes com janelas e processos reais |
| Detecção com janelas reais (Windows da CI) | launcher de teste sozinho → "é o launcher" → espera; o launcher abre o jogo num processo filho → conectado sozinho, launcher reconhecido, captura é a do jogo; jogo coberto por outra janela → a captura nunca traz a janela da frente |
| `.exe` da pasta (ZIP extraído, sem Python no PATH) | autoteste OK; interface OK (atraso máximo 103 ms), incluindo Detectar jogo minimizando e restaurando a janela principal |
| `.exe` em pasta sem permissão de escrita | interface OK, dados em `%LOCALAPPDATA%\JonFlow` |
| `.exe` de arquivo único | autoteste OK; interface OK (atraso máximo 88 ms) |
| Capturas da interface (100%, 125%, 150%) | sem texto cortado nem área fora da janela; inclui a janela Detectar jogo (procurando, escolher, confirmar) |
| Linux sem gerenciador de janelas | minimizar não é verificável no Xvfb: conferido só no Windows |

Desempenho medido no ambiente de desenvolvimento: recomendação de mira 89 ms (antes 266 ms); classificação
da tela com 11 modelos 0,16 s a 1000×600 (antes 1,3 s) e 0,46 s a 1080p (antes 4,6 s).

### O que foi simulado (e não prova o jogo real)

- Demonstração: cliente simulado com lobby, menus, sala, batalha, resultado e falhas (pop-up, tela
  desconhecida, desconexão, perda de foco, clique ignorado). Testadas uma partida, três seguidas, repetição
  contínua até parar, uma instância completa, pausa, retomada e emergência.
- Detecção: janelas e processos de teste no Windows (`tests/fixtures/fake_window.py`), não o launcher real.
- Visão e mira: imagens sintéticas e tabelas da comunidade, não capturas do DDClássico.

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
