# Testes

Todos os testes daqui usam **simulação ou imagens sintéticas**. Nenhum deles foi executado contra o cliente real do
DDClássico: o ambiente de desenvolvimento é Linux, sem o jogo. A seção "No jogo real", no fim, diz o que ainda
precisa ser validado no cliente.

Para rodar: `python -m pytest -q tests` (com `PYTHONPATH=src`, ou pelo `build_windows.bat`). O `pytest.ini` fixa `--capture=sys`: com a captura padrão (`fd`), na suíte completa do Windows, criar um Tk às vezes falhava ("Can't find a usable init.tcl/tk.tcl"; diagnóstico 39530426640 em `PROGRESS.md`).

## O que cada arquivo cobre

| Arquivo | Tipo | O que verifica |
|---|---|---|
| `test_physics.py` | unitário | `solve_force` inverte `landing_x` (erro < 0,02 em 500 casos aleatórios); alvo impossível → NaN; vento a favor vai mais longe; mais força vai mais longe; alvo mais alto pede mais força; sem arrasto bate com a balística analítica |
| `test_knowledge_aiming.py` | unitário | tabelas 20/30/50/65 carregadas com fonte; regras de vento (65±2v, 50±2v, 30±1v, 20 sem vento, Alto 90−d±2v, exemplo ddladora d=10 v=−1,5 → 77°); modelo dentro de RMSE < 1,3 das tabelas; recomendação na célula documentada; terreno bloqueia tiros baixos (só com um perfil de terreno passado ao cálculo: a visão ainda não lê o terreno do jogo); arma mais forte pede menos força |
| `test_calibration_tracking.py` | unitário | banco de disparos; a correção aprende um erro sistemático de +0,8; o reajuste recupera uma velocidade 4% maior; a incerteza do alvo invisível cresce por turno; decisões atirar/ataque de área/aguardar/pedir intervenção |
| `test_safety_combat.py` | unitário/cenário | parada de emergência interrompe esperas; um disparo por turno; teclas soltas ao abortar ou perder o foco; modo assistido nunca atira; modo automático exige autorização; leitura com baixa confiança não atira; alvo oculto sem histórico espera; alvo oculto com histórico usa a região estimada; fim de batalha limpa o rastreador |
| `test_activities.py` | cenário | fluxo completo de 2 execuções; instância com 3 etapas; pop-up recuperado; tela desconhecida → pausa; botão ausente → pausa sem cliques repetidos; desconexão → para; limite de derrotas; limite de tempo; PvP e falta de autorização recusados; botão proibido bloqueado (e liberável); validação dos arquivos de definição; pausar/retomar/parar de outra thread; parada de emergência; captura salva na falha |
| `test_vision.py` | unitário | regiões; busca de modelo multi-escala; biblioteca de modelos; dígitos aprendidos e lidos (com persistência); barra de força; detecção das opções do menu; caminho com acentos; cena sintética completa (turno, personagens, régua, distância, altura e vento relativo, inclusive com o alvo à esquerda) |
| `test_integration.py` | integração | tela de jogo falsa que reage às teclas: captura → visão → mira → setas até o ângulo exibido bater → espaço segurado até a força; modo visual da barra; leitura de tela + clique com o deslocamento da janela; clique duplicado bloqueado; emergência durante a carga solta a tecla |
| `test_detection.py` | unitário | Detectar jogo sem nomes fixos: launcher aberto e jogo fechado; jogo aberto pelo launcher em outro processo (também com um processo intermediário sem janela); jogo dentro da janela do launcher (área interna, a mais funda); launcher fechado depois de abrir o jogo; janela nova durante a espera; duas candidatas parecidas → escolha; perfil salvo desempata; a janela do próprio bot nunca é escolhida; área recusada → espera; janela pequena ignorada; janela sob o ponto clicado (camada de seleção) |
| `test_demo_flows.py` | cenário | demonstração: uma partida e uma instância completas (lobby → menu → sala → batalha → resultado → lobby); três partidas seguidas; repetição contínua até parar; botão ausente no lobby → aviso em 5 s e pausa (sem laço infinito); opção ausente no menu → pausa; partida pela camada de serviço com threads e esperas reais |
| `test_windows_real.py` | integração (só Windows) | janelas e processos **reais** de teste, cada um identificado pelo pid real e hwnd que a própria janela informa e por uma etiqueta única no título (o pid do `Popen` pode ser o redirecionador do venv); limpeza só dos processos do próprio teste. Na CI também roda num venv com o Chrome aberto, cada teste 3 vezes: launcher que abre o jogo num processo filho (espera → conecta sozinho, launcher reconhecido, captura é do jogo); **dois launchers abertos, só o segundo abre o jogo** (o jogo é associado a ele); captura do jogo coberto por outra janela (pela janela ou recusa, nunca a janela da frente); janela sob o ponto conferida com o próprio Windows (`WindowFromPoint`) |
| `test_strategy.py` | unitário/cenário/visão | perfis de instância carregados, com fontes registradas; associação pelo nome respeitando a dificuldade; **Formigueiro** (onde há mais formigas; a rainha abre a etapa 2 só após leituras seguidas; na etapa da rainha não atira nas formigas); sem o modelo do alvo, mira qualquer inimigo e avisa uma vez; **Galinheiro** (o mais perto primeiro); **Bugou** (Barão imune de frente; escudo do Midas força ângulo ≥ 60; pavio do Matias pausa só após leituras seguidas); sem progresso pede ajuda; chefe que some espera e depois troca; papéis reconhecidos numa imagem sintética sem duplicar o marcador genérico; as três instâncias completas na simulação, 1 e 3 vezes seguidas, passando por todas as etapas; repetição contínua até parar; nenhum disparo anulado por escudo (sem a estratégia, o mesmo cenário desperdiça disparos); pavio pausa a rotina e, depois do gelo, Retomar termina; serviço: estratégia associada, alvos como recomendação, demonstração com pausa/retomada/parada |
| `test_audit_regressions.py` | regressão | cada defeito das auditorias. Na 0.4.0: pid do pai reaproveitado por outro launcher; vários launchers sem parentesco não são "chutados"; imagem da janela que mostra a janela da frente é recusada; captura simulada no Windows com cobertura entre os 5 pontos antigos |
| `test_gui_states.py` | unitário | textos da faixa de estado; demonstração sempre identificada como simulação (executando, pausada, concluída) |
| `test_catalogo.py` (0.5.0) | unitário/cenário | as **seis atividades pré-cadastradas** na ordem, Castelo do Reino de Bugou fora da lista principal; Olimpíadas Bugou ≠ Castelo (opção, modelos e associação pelo nome); opção e dificuldade clicadas em sequência; as dificuldades compartilham as capturas; etapas de cada perfil conforme as fontes; catálogo com erro mantém as entradas válidas; disponibilidade gravada e tolerante a arquivo ruim; serviço lista as seis sem jogo conectado, protege as pré-cadastradas e aceita a versão do usuário; pendências com instrução; **cada uma das seis completa na simulação** escolhendo só a própria opção e dificuldade, sem balão verde nem juiz atingidos; opção ou dificuldade ausente no menu pausa, não clica em outra e marca "não encontrada" (a demonstração não marca); clique recusado em opção ambígua; balões (melhor valor, nunca verde, pausa sem os modelos), Boxiador longe do juiz, corrida nos rivais agrupados, etapa escolhida pelo que a tela mostra |
| `test_autodetect.py` (0.5.0) | visão (imagens sintéticas) | sugestões da barra de força, do ângulo, do vento e da área de jogo (faixas dos dois lados); nada numa imagem vazia; ângulo pela diferença ao apertar a tecla (e nada quando a câmera anda) |
| `test_mira_calibracao.py` (0.5.0) | unitário | correção robusta (dois disparos marcados errado não arrastam o viés); cenários não se misturam (modo da força, cliente); disparo novo com cenário, instância, dificuldade, etapa e alvo; banco antigo atualizado e disparos antigos fora da correção; ângulo estável no turno; espera inicial da barra somada ao tempo |
| `test_gui_selecao.py` (0.5.0, precisa de tela) | interface | o Início lista as seis antes de conectar, com pendências e Iniciar desativado; página Pendências; fonte própria dos ícones da faixa; **seleção sem camada escura** (aviso pequeno, conta de novo com o mouse sobre ele, escolhe a janela sob o mouse); Apontar com o mouse esconde a janela Detectar jogo e a traz de volta para confirmar |
| `test_gui_layout.py` (0.5.0, precisa de tela 1920×1080) | interface/regressão | a auditoria do layout pega abas espremidas, painel cortado por outro painel e lista sem espaço para duas linhas (antes só via texto cortado e o que saía da janela); a janela em 1080p a **100%, 125% e 150%** (escala simulada com `DDBOT_UI_SCALE`) não tem nada cortado no Início (sem jogo, demonstração, combate), nas abas Diagnóstico, Mira, Configurações e Registro e nas seis páginas da Calibração; os botões das páginas abrem a página certa e acompanham Ver pendências. Reprova a interface do `8dc8c79` (abas da Calibração cortadas em 100% e 125%; Histórico sem linhas em 150%). Numa tela menor é pulado. As janelas ficam vivas até o fim do processo (fixture `tk_cleanup`: no Windows, liberar um Tk no meio da sessão derrubava o processo) |
| `test_simulation_service.py` | cenário/regressão/interface | a calibração melhora a precisão; o `--simulate` não perde o 1º turno de cada batalha; inimigos invisíveis na simulação; serviço completo em modo simulado (iniciar, pausar, retomar e parar em menos de 3,5 s); recusas sem janela e sem autorização (isoladas da área de trabalho real: antes, num PC com o DDTank aberto, o bot conectava no jogo e a recusa vinha pelas regras); demonstração sem autorização nem janela; emergência e reinício; `--selftest` pela linha de comando; **teste de interface** `--gui-smoke` (precisa de tkinter: roda na CI Windows e na CI Linux com Xvfb) |

## Testes de regressão de 2026-10-21 (caminho do Cais, aviso, reconhecimento e mira)

| Teste | O que garante |
|---|---|
| `test_catalogo.py::test_instance_goes_through_the_dock_and_chooses_inside_the_room_every_run` | lobby → Cais de Expedição → Criar sala → na sala, escolher a instância e a dificuldade → Iniciar; na volta à sala (que ainda mostra a instância anterior) escolhe de novo antes de Iniciar |
| `test_catalogo.py::test_start_in_a_room_without_instance_never_clicks_start_first` | começando numa sala vazia, o primeiro clique é escolher a instância, nunca Iniciar |
| `test_catalogo.py::test_solo_warning_pauses_without_permission_and_continues_after_it` | aviso de instância difícil (um jogador): sem permissão, pausa explicando e sem clicar; com a permissão, Retomar confirma e segue para a batalha na mesma ida (sem recomeçar) |
| `test_catalogo.py::test_solo_warning_permission_does_not_unlock_forbidden_buttons` | a permissão não libera um botão proibido |
| `test_activities.py::test_action_condition_parses_and_round_trips` | ações com `se` (`sem_escolha`/`com_escolha`) e as recusas de condição inválida |
| `test_readiness.py::test_instance_lists_the_expedition_dock_path_in_order` | Pendências na ordem do jogo (Lobby, botão do Cais, tela do Cais, Criar sala, Sala, escolher, Iniciar, escolha, opção) com instruções |
| `test_vision.py::test_template_with_a_wrong_learned_scale_is_searched_again` | **defeito corrigido**: um modelo com escala errada memorizada nunca mais era procurado nas outras escalas; reprova o código anterior |
| `test_vision.py::test_unrecognized_screen_explains_the_closest_calibrated_screens` | tela não reconhecida diz as telas calibradas mais parecidas, a nota e o mínimo (também no Diagnóstico) |
| `test_vision.py::test_dialogs_over_the_room_win_over_the_room` | escolha da instância e aviso de instância difícil, por cima da sala, valem mais que a sala |
| `test_safety_combat.py::test_unreadable_turn_is_explained_and_pauses_in_auto` | **defeito corrigido**: batalha com o turno ilegível ficava parada em silêncio; agora avisa em 20 s e pausa em 60 s no automático |
| `test_safety_combat.py::test_my_turn_without_aim_explains_and_pauses_after_two_turns` | seu turno sem personagem, inimigo ou régua: um aviso por turno com o motivo; dois turnos seguidos pausam no automático |
| `test_mira_calibracao.py::test_recommended_force_can_reach_100` | a força recomendada vai até 100 (antes, teto de 98); reprova o teto antigo |
| `test_gui_layout.py` | também com o botão "Confirmar o aviso e continuar" visível, em 100/125/150% |

## Testes de regressão do combate (2026-10-21, revisão do Formigueiro Fácil)

`test_combate_formigueiro.py`: estados em que o bot ficava parado sem pausar nem dizer o motivo. Os marcados como
**defeito corrigido** reprovam o código da 0.5.1 (conferido rodando o arquivo contra uma cópia dela); os outros
garantem proteções que já existiam.

| Teste | O que garante |
|---|---|
| `test_turn_never_recognized_warns_with_score_and_pauses` | **defeito corrigido**: indicador lido, mas o seu turno nunca reconhecido: antes nada acontecia até o limite da batalha (15 min); agora avisa em 60 s com a semelhança e o mínimo e pausa em 150 s |
| `test_turn_timer_restarts_after_each_of_my_turns` | **defeito corrigido**: o tempo sem turno recomeça a cada turno seu (não pausa uma batalha normal) |
| `test_no_target_of_the_stage_pauses_after_three_turns` | **defeito corrigido**: com estratégia e nenhum alvo da etapa na tela, esperava turno após turno; agora pausa depois de 3 turnos seus, dizendo o que capturar |
| `test_legit_wait_does_not_pause` | espera da estratégia com alvo na tela (chefe imune) continua só avisando |
| `test_planner_marks_missing_target` | **defeito corrigido**: a estratégia do Formigueiro Fácil marca "nenhum alvo" de forma distinta das outras esperas |
| `test_unread_wind_names_the_reading_and_pauses` | **defeito corrigido**: vento não lido dava "confiança visual baixa (0.00 < 0.7)" em todo turno, sem pausar; agora diz qual leitura (vento) e pausa depois de 2 turnos sem disparar |
| `test_cancelled_shot_counts_and_pauses` | **defeito corrigido**: disparo cancelado (ângulo não confirmado) se repetia todo turno; agora um por turno e pausa no segundo |
| `test_focus_and_blocked_input_reach_the_routine` | janela sem foco e entrada bloqueada sobem para a rotina e não liberam um segundo disparo no turno |
| `test_unconfirmed_shot_warns_then_pauses` | **defeito corrigido**: o disparo não era confirmado; agora, se o turno continua seu 5 s depois da espera pós-disparo, avisa, e no segundo seguido pausa |
| `test_shot_confirmed_when_turn_passes` | **defeito corrigido**: o turno passar depois do disparo vira "disparo confirmado" no Histórico |
| `test_vision_view_lists_weak_reads` | **defeito corrigido**: a leitura da tela lista as leituras abaixo do mínimo (alvo 0,60; vento sem direção) |
| `test_unknown_screen_in_battle_pauses_without_clicking_close` | **defeito corrigido**: tela desconhecida na batalha clicava no X reconhecido (podia sair da batalha); agora pausa |
| `test_solo_warning_without_confirm_button_pauses_without_cancelling` | **defeito corrigido**: no aviso de um jogador, com permissão e sem o botão de confirmar, a recuperação clicava no X e cancelava a ida; agora pausa |
| `test_blocked_input_during_combat_pauses_the_routine` | entrada bloqueada pelo Windows no combate pausa a rotina com o motivo |
| `test_generic_enemy_marker_optional_when_instance_targets_cover_every_stage` | **defeito corrigido**: com a formiga e a rainha capturadas, o marcador genérico de inimigo deixa de ser obrigatório |

## Teste de interface (`--gui-smoke`)

Abre a janela de verdade e, em modo de demonstração, aciona os botões: lista a demonstração, *Iniciar*, confere
"executando", *Pausar* (confere que as leituras param), *Retomar*, percorre todas as abas, usa a calculadora,
*Parar* (o clique precisa retornar em menos de 500 ms), abre *Detectar jogo* (a janela principal precisa ficar
minimizada) e fecha (precisa voltar ao normal, com o modo demonstração e a atividade preservados), troca entre
Partidas e Instâncias (a partida de demonstração aparece, o Iniciar fica ativo e a escolha de cada seção é mantida)
e por fim a parada de emergência com a rotina em andamento. Desde a 0.5.0 confere que as **seis atividades
pré-cadastradas** aparecem sem o jogo e sem o modo demonstração, que o Castelo do Reino de Bugou não está na
lista principal, que a seção Partidas automáticas existe, que a escolha é mantida ao trocar o modo demonstração
e que, sem o modo demonstração e sem o jogo, o Iniciar fica desativado e há pendências listadas. Durante o teste mede o atraso do laço de eventos da
janela: se passar de 1,5 s, a interface é considerada travada. O resultado vai para `DDBOT_SMOKE_OUT`.

As capturas da CI (`capturas-da-interface`) incluem a janela Detectar jogo nos estados procurando, escolher e
confirmar. Cada escala gera um `<escala>_layout.json` com a auditoria do layout (`gui/screenshots.py`): texto
cortado, abas espremidas, widget que passa da borda da janela ou do painel onde está e Treeview com menos de duas
linhas inteiras. Desde a 0.5.0 a CI **reprova** se algum relatório tiver problema (passo "Layout das capturas"),
com as fontes do Windows.

## Empacotamento

A CI (`.github/workflows/windows-build.yml`) compila com `build_windows.bat` e confere que o `.exe`, o ZIP, o
LEIA-ME e os dados embutidos existem. Depois extrai o ZIP numa pasta nova, tira o Python do `PATH` e roda o `.exe`
com `--selftest` (recursos, configuração, mira, visão e fluxo simulado) e com `--gui-smoke`. Por fim confere que a
pasta portátil `dados\config.json` foi criada ao lado do executável.

## Simulação de precisão (`--simulate N`)

`PYTHONPATH=src python -m ddbot --simulate N` joga N batalhas simuladas em modo automático duas vezes, sem e com
calibração, e imprime uma linha JSON para cada: disparos, acertos, vitórias, taxa de acerto na 1ª e na 2ª metade,
erro médio do impacto (em unidades da régua), disparos com o alvo oculto e turnos perdidos (o tempo do turno
esgotou sem disparo). O "jogo" tem constantes físicas diferentes das do modelo (velocidade +3%, vento +25%,
arrasto −5%) e ruído; o sorteio é fixo (semente 1), então a mesma versão dá o mesmo resultado.

Limitações: é um alvo único num terreno plano, sem a visão (as leituras chegam prontas, com ruído) e com um "jogo"
inventado. Mede se a mira e a calibração funcionam como programado; **não** mede a precisão no DDClássico.

Resultados de 2026-10-20 (commit `b17d179`): com 50 batalhas, 40,0% de acerto sem calibração e 96,2% com
calibração, sem turnos perdidos.

`--simulate 25` em 2026-10-20 (branch `feature/atividades-prioritarias`, código do commit `8dc8c79`): sem
calibração 166 disparos, 70 acertos (42,2%), 22 vitórias; com calibração 79 disparos, 75 acertos (94,9%), 25
vitórias; 0 turnos perdidos. O código da v0.4.4 dá os mesmos disparos, acertos e vitórias com 25 batalhas; só o
erro médio com calibração na 2ª metade muda (0,135 → 0,140), efeito dos pesos de Huber (sem outliers na
simulação, o ajuste robusto é um pouco menos eficiente; ele existe para disparos marcados errado no jogo real). Antes desse commit, o 1º turno de cada batalha era perdido no `--simulate`
(defeito da medição desde a 0.3.0; detalhes e comparação com versões anteriores em `PROGRESS.md`). Regressão:
`test_simulation_does_not_lose_the_first_turn_of_each_battle`.

## Rodar no Linux sem Xvfb instalado

No Rocky Linux 10 (ambiente de desenvolvimento) não há pacote do Xvfb. Os testes de interface e as capturas
rodam num container Ubuntu 24.04, igual ao runner da CI (use `docker run --init`: sem ele, o `xvfb-run` como
processo 1 do container pode ficar esperando o Xvfb para sempre). A tela precisa ser de 1920×1080 para o
`test_gui_layout.py` rodar (na CI também):

```bash
docker run --rm -v "$PWD":/src:ro ubuntu:24.04 ...   # apt install python3-tk xvfb; pip install -r requirements*.txt
xvfb-run -a -s "-screen 0 1920x1080x24" python -m pytest -q tests -rs
DDBOT_UI_SCALE=1.5 xvfb-run -a -s "-screen 0 1920x1080x24" python -m ddbot --screenshots capturas/
```

Sem gerenciador de janelas, minimizar não é verificável no Xvfb (conferido só no Windows).

## Resultados

Os resultados de cada execução estão em [`PROGRESS.md`](../PROGRESS.md).

## Launcher (pendente no Windows real)

A detecção foi testada com janelas simuladas (`test_detection.py`) e com janelas e processos reais de teste no
Windows da CI (`test_windows_real.py`), mas **não** com o launcher e o cliente do DDClássico. Para validar:

1. Abra só o launcher e o JonFlow. Clique em **Detectar jogo**: a janela do JonFlow deve se minimizar. Anote o que
   aparece: "Launcher aberto: aguardando o jogo" ou "É esta a janela do jogo?" com a prévia do launcher (nesse caso
   clique em **É o launcher**).
2. Com a janela Detectar jogo aberta, entre no jogo pelo launcher: em poucos segundos deve aparecer "Jogo
   conectado" com a prévia do jogo (lobby). Confira se a prévia é do jogo, e não da moldura do launcher. Clique em
   **Pronto**: a janela do JonFlow deve voltar como estava.
3. Feche o jogo e mantenha o launcher aberto: em até ~3 s o topo deve mostrar "launcher aberto, aguardando o
   jogo", e Iniciar deve ser recusado com essa mensagem.
4. Abra o jogo de novo: o topo deve mostrar "conectado" sozinho, sem detectar de novo.
5. Se a detecção não achar o jogo, use **Mostrar onde está o jogo** e clique sobre o jogo: o clique não pode chegar
   ao jogo, e Esc deve cancelar. Anote o programa e o tamanho mostrados.
6. Clique num campo ou botão do launcher (deixando o foco ali) e use Calibração > Testar teclas do ângulo: o
   teste deve ser recusado ("foco do teclado está no launcher"). Clique dentro do jogo e repita: deve funcionar.
7. Diagnóstico ao vivo com a janela do JonFlow por cima de parte do jogo: a imagem deve continuar sendo a do jogo
   (captura pela janela). Se aparecer "outra janela está na frente do jogo", o jogo não permite essa captura:
   anote, porque nesse caso a janela do jogo precisa ficar visível.
8. Inicie uma instância no jogo: a janela do JonFlow deve se minimizar e voltar quando a rotina pausar ou terminar.
9. Se o jogo rodar como administrador e o bot não, o envio de teclas é bloqueado pelo Windows: o bot deve
   pausar com essa explicação.

Anote o resultado de cada passo (e o programa e a classe mostrados) para ajustar o bot se algo não bater.

## No jogo real (pendente)

Ainda **não validado no cliente**: reconhecimento das telas e botões, leitura de ângulo, vento e turno, tempo de
carga da barra, precisão real, navegação até uma instância e uma execução completa. Roteiro sugerido para a
primeira validação:

1. Faça a calibração (README, "Passo 4 — Ensinar o bot a enxergar").
2. Aba Diagnóstico, *Ao vivo*: confira as leituras e as confianças em várias telas.
3. Mira assistida ao vivo durante uma partida: compare as sugestões com os tiros que você faz.
4. Marque a autorização e use Calibração > *Teste de controles* no seu turno. Depois rode uma instância **uma vez** e
   acompanhe com o dedo no F12.
5. Registre o resultado dos disparos para a calibração aprender.

### As seis atividades pré-cadastradas (pendente no cliente, 0.5.0)

1. Com o jogo no menu de instâncias, Calibração > Menu: capture, Detectar opções, escolha a opção e indique se
   é Formigueiro, Galinheiro ou Olimpíadas Bugou (uma vez por instância). Em Modelos, salve os botões de
   dificuldade Fácil, Normal e Difícil (uma vez para todas).
2. Ver opções conhecidas nesta captura: as atividades cuja opção aparece passam a "vista no menu". Confira se
   Formigueiro Fácil e Galinheiro Fácil existem no seu cliente (não há notícia oficial deles).
3. Calibração > Pendências: siga a lista da atividade escolhida no Início.
4. Rode **uma vez** cada uma com o dedo no F12 e anote: as etapas anunciadas no Histórico batem com as do jogo?
   No Galinheiro, a ordem das etapas; nas Olimpíadas, se o Normal tem a corrida, como aparecem os balões (cores,
   valores), quem é o "Meka" e onde fica o juiz. Se a atividade não estiver no menu, o bot deve pausar com
   "não foi encontrada no menu" sem clicar em outra.

### Instâncias com estratégia (pendente no cliente, desde a 0.4.0)

Para Formigueiro, Galinheiro e Castelo do Reino de Bugou (Normal):

1. Crie a atividade pela Calibração > Menu com o nome da instância: a estratégia é associada sozinha (confira em
   Calibração > Alvos).
2. Numa batalha da instância, capture em Calibração > Alvos cada alvo (rainha, formiga, frango, Barão, Midas...) e
   cada estado (escudo do Barão, escudo do Midas, pavio do Matias), com 2 ou 3 amostras.
3. Diagnóstico ao vivo: confira se cada inimigo aparece com o papel certo.
4. Rode **uma vez** com o dedo no F12 e anote: as etapas que o bot anunciou no Histórico batem com as do jogo? O
   Normal do Bugou tem mesmo 4 etapas? O bot esperou com o Barão de frente? Pausou no pavio?
