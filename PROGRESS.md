# Andamento

Última atualização: 2026-10-16. Branch `feature/bot-core`.

## Concluído

| Etapa | Situação | Validação |
|---|---|---|
| Pesquisa (bots, calculadoras, fórmulas, licenças) | feito: `docs/RESEARCH.md` | — |
| Base de conhecimento (tabelas 20/30/50/65, Alto, Médio, fontes) | feito | testes de conhecimento |
| Modelo físico ajustado às 4 tabelas | feito: RMSE 1,01 de força, 76/80 células dentro de ±2 | `tools/fit_model.py`, testes de física |
| Solver de força: 3–4× mais rápido, sem raízes falsas para alvos inalcançáveis | feito | 4000 casos aleatórios, erro < 0,02 |
| Mira: tabelas + fórmulas + busca física, probabilidade de acerto, terreno, arma | feito | testes de mira |
| Calibração com disparos (correção por método + reajuste das constantes) | feito | testes + simulação |
| Alvos invisíveis (última posição + incerteza crescente, aguardar/área/atirar) | feito | testes + simulação |
| Combate automático (turno, um disparo por turno, confiança mínima, cache) | feito | testes de cenário e integração |
| Controlador de estados para partidas e instâncias, com recuperação e limites | feito: `activities.py` | 15 testes de cenário |
| Descoberta das opções do menu a partir da captura (sem lista fixa) | feito: `vision/menu.py` | teste com menu sintético |
| Execução real: leitura de telas, cliques por modelo, teclado com travas | feito: `game_io.py` | integração com tela falsa que reage às teclas |
| Interface gráfica em português | feito: `gui/main_window.py` | **só na CI** (sem tkinter no Linux de desenvolvimento) |
| Autoteste (`--selftest`) e teste de interface (`--gui-smoke`) | feito | selftest OK no Linux |
| Empacotamento: PyInstaller, `build_windows.bat`, workflow Windows | feito | **pendente: a CI não pôde ser enviada (ver bloqueios)** |
| README pt-BR, `docs/TESTES.md`, `docs/USO.txt` | feito | — |

## Resultados dos testes (Linux, Python 3.12, 2026-10-16)

- `pytest`: **68 aprovados, 1 pulado** (o teste de interface precisa de tkinter, que não existe neste Linux).
- `pyflakes`: sem avisos.
- `--selftest`: OK (recursos, mira, visão, fluxo simulado completo).
- Simulação de precisão (`--simulate 15`). O "jogo" simulado tem constantes diferentes das do modelo
  (velocidade +3%, vento +25%, arrasto −5%) e ruído de leitura e de execução:

| | Disparos | Acerto | Vitórias | Erro médio do impacto (1ª metade → 2ª metade) |
|---|---|---|---|---|
| Sem calibração | 113 | 35% | 12/15 | 0,72 → 0,78 |
| Com calibração | 53 | 85% | 15/15 | 0,30 → 0,17 |

- Cenários de atividade simulados: fluxo completo, várias etapas, pop-up, tela desconhecida, botão ausente,
  desconexão, limites de derrotas e de tempo, PvP recusado, botão proibido, pausar/retomar/parar e emergência.
  Todos passaram.

**Nada disso foi testado no cliente real do DDClássico.**

## Bloqueios

1. **Compilação Windows (CI).** O `git push` foi recusado porque o token do GitHub CLI não tem o escopo
   `workflow`, necessário para enviar `.github/workflows/windows-build.yml`. Para liberar:
   `gh auth refresh -h github.com -s workflow`. Sem isso, o `.exe` e o ZIP não puderam ser gerados.
   Alternativa: rodar `build_windows.bat` num Windows com Python 3.12.
2. **Cliente real.** Não há Windows com o DDClássico neste ambiente. Calibração, navegação, disparos e uma
   execução completa de instância ainda precisam ser validados no jogo (roteiro em `docs/TESTES.md`).
3. **Regras do servidor.** O site do DDClássico respondeu 403. O modo automático continua exigindo confirmação
   explícita.

## Limitações conhecidas

- Instâncias e partidas não foram validadas no cliente; cada atividade criada fica marcada "não validada".
- Perfil do terreno: a mira aceita obstáculos (`ShotContext.terrain`), mas a visão ainda não extrai o terreno da
  tela.
- Armas, habilidades, pets e pérolas: só como parâmetros configuráveis (`weapons`); não há mecânicas específicas do
  DDClássico porque nenhuma fonte foi encontrada.
- Força por tempo depende de medir `power_full_time_s` no cliente; o modo visual (`power_mode: visual`) lê a barra.
- Desconexão: o bot para e avisa; não faz login sozinho.
