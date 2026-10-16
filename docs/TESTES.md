# Testes

Todos os testes daqui usam **simulação ou imagens sintéticas**. Nenhum deles foi executado contra o cliente real do
DDClássico: o ambiente de desenvolvimento é Linux, sem o jogo. A seção "No jogo real", no fim, diz o que ainda
precisa ser validado no cliente.

Para rodar: `python -m pytest -q tests` (com `PYTHONPATH=src`, ou pelo `build_windows.bat`).

## O que cada arquivo cobre

| Arquivo | Tipo | O que verifica |
|---|---|---|
| `test_physics.py` | unitário | `solve_force` inverte `landing_x` (erro < 0,02 em 500 casos aleatórios); alvo impossível → NaN; vento a favor vai mais longe; mais força vai mais longe; alvo mais alto pede mais força; sem arrasto bate com a balística analítica |
| `test_knowledge_aiming.py` | unitário | tabelas 20/30/50/65 carregadas com fonte; regras de vento (65±2v, 50±2v, 30±1v, 20 sem vento, Alto 90−d±2v, exemplo ddladora d=10 v=−1,5 → 77°); modelo dentro de RMSE < 1,3 das tabelas; recomendação na célula documentada; terreno bloqueia tiros baixos; arma mais forte pede menos força |
| `test_calibration_tracking.py` | unitário | banco de disparos; a correção aprende um erro sistemático de +0,8; o reajuste recupera uma velocidade 4% maior; a incerteza do alvo invisível cresce por turno; decisões atirar/ataque de área/aguardar/pedir intervenção |
| `test_safety_combat.py` | unitário/cenário | parada de emergência interrompe esperas; um disparo por turno; teclas soltas ao abortar ou perder o foco; modo assistido nunca atira; modo automático exige autorização; leitura com baixa confiança não atira; alvo oculto sem histórico espera; alvo oculto com histórico usa a região estimada; fim de batalha limpa o rastreador |
| `test_activities.py` | cenário | fluxo completo de 2 execuções; instância com 3 etapas; pop-up recuperado; tela desconhecida → pausa; botão ausente → pausa sem cliques repetidos; desconexão → para; limite de derrotas; limite de tempo; PvP e falta de autorização recusados; botão proibido bloqueado (e liberável); validação dos arquivos de definição; pausar/retomar/parar de outra thread; parada de emergência; captura salva na falha |
| `test_vision.py` | unitário | regiões; busca de modelo multi-escala; biblioteca de modelos; dígitos aprendidos e lidos (com persistência); barra de força; detecção das opções do menu; caminho com acentos; cena sintética completa (turno, personagens, régua, distância, altura e vento relativo, inclusive com o alvo à esquerda) |
| `test_integration.py` | integração | tela de jogo falsa que reage às teclas: captura → visão → mira → setas até o ângulo exibido bater → espaço segurado até a força; modo visual da barra; leitura de tela + clique com o deslocamento da janela; clique duplicado bloqueado; emergência durante a carga solta a tecla |
| `test_simulation_service.py` | cenário/regressão/interface | a calibração melhora a precisão; inimigos invisíveis na simulação; serviço completo em modo simulado (iniciar, pausar, retomar e parar em menos de 3,5 s); recusas sem janela e sem autorização; emergência e reinício; `--selftest` pela linha de comando; **teste de interface** `--gui-smoke` (precisa de tkinter: roda na CI Windows e na CI Linux com Xvfb) |

## Teste de interface (`--gui-smoke`)

Abre a janela de verdade e, em modo de demonstração, aciona os botões: lista a demonstração, *Iniciar*, confere
"executando", *Pausar* (confere que as leituras param), *Retomar*, percorre todas as abas, usa a calculadora,
*Parar* (o clique precisa retornar em menos de 500 ms) e por fim a parada de emergência com a rotina em andamento.
Durante o teste mede o atraso do laço de eventos da janela: se passar de 1,5 s, a interface é considerada travada.
O resultado vai para o arquivo indicado em `DDBOT_SMOKE_OUT`.

## Empacotamento

A CI (`.github/workflows/windows-build.yml`) compila com `build_windows.bat` e confere que o `.exe`, o ZIP, o
LEIA-ME e os dados embutidos existem. Depois extrai o ZIP numa pasta nova, tira o Python do `PATH` e roda o `.exe`
com `--selftest` (recursos, configuração, mira, visão e fluxo simulado) e com `--gui-smoke`. Por fim confere que a
pasta portátil `dados\config.json` foi criada ao lado do executável.

## Resultados

Os resultados de cada execução estão em [`PROGRESS.md`](../PROGRESS.md).

## Launcher (pendente no Windows real)

O jogo é aberto por um launcher. A identificação da janela, o estado "launcher aberto sem jogo", a regra de
foco do teclado e a recusa de cliques sobre o launcher estão cobertos por `tests/test_launcher.py`, mas com
listas de janelas **simuladas**: não houve acesso a um Windows com o launcher. Para validar:

1. Abra só o launcher e o bot. Use Identificar janela e anote o que aparece (programa, classe, se há janelas
   internas). Feche o assistente: a faixa deve mostrar "Identifique a janela do jogo".
2. Entre no jogo pelo launcher. Abra Identificar janela de novo:
   - descubra se o jogo é uma **janela principal de outro programa** ou uma **janela interna** do launcher;
   - confira na prévia que a captura mostra a batalha, e não a moldura do launcher;
   - marque o jogo e o launcher e salve.
3. Feche o jogo e mantenha o launcher aberto: em até ~3 s a faixa deve mostrar "Launcher aberto, aguardando o
   jogo", e Iniciar deve ser recusado com essa mensagem.
4. Abra o jogo de novo: o topo deve mostrar "conectado" sozinho, sem identificar de novo.
5. Clique num campo ou botão do launcher (deixando o foco ali) e use Calibração > Testar teclas do ângulo: o
   teste deve ser recusado ("foco do teclado está no launcher"). Clique dentro do jogo e repita: deve funcionar.
6. Diagnóstico ao vivo: as capturas devem acompanhar o jogo quando a janela é movida ou redimensionada.
7. Se o jogo rodar como administrador e o bot não, o envio de teclas é bloqueado pelo Windows: o bot deve
   pausar com essa explicação.

Anote o resultado de cada passo (e o programa/classe identificados) para ajustar o bot se algo não bater.

## No jogo real (pendente)

Ainda **não validado no cliente**: reconhecimento das telas e botões, leitura de ângulo, vento e turno, tempo de
carga da barra, precisão real, navegação até uma instância e uma execução completa. Roteiro sugerido para a
primeira validação:

1. Faça a calibração (README, "Primeira configuração").
2. Aba Diagnóstico, *Ao vivo*: confira as leituras e as confianças em várias telas.
3. Mira assistida ao vivo durante uma partida: compare as sugestões com os tiros que você faz.
4. Marque a autorização e use Calibração > *Teste de controles* no seu turno. Depois rode uma instância **uma vez** e
   acompanhe com o dedo no F12.
5. Registre o resultado dos disparos para a calibração aprender.
