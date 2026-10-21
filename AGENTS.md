# AGENTS.md

Guia para agentes de código (Claude Code, Codex etc.) que trabalham neste repositório. Para usuários finais, veja
o [`README.md`](README.md): ele vai no pacote como `LEIA-ME.md` e é escrito passo a passo para quem nunca usou o
programa (linguagem simples, tabelas, problemas comuns e glossário). Ao mudar algo que o usuário vê, atualize o
README nesse mesmo tom e confira os nomes de botões e abas no código da interface.

## O projeto

**JonFlow** (antes *DDClássico Bot*): app para Windows 10/11 64 bits que joga sozinho partidas e instâncias PvE
do DDTank no servidor DDClássico. Captura a tela do jogo, reconhece estados e turnos por modelos de imagem
capturados pelo usuário, calcula a mira e envia teclas/cliques com travas de segurança. Interface em Tkinter,
empacotado com PyInstaller.

- O pacote Python continua se chamando `ddbot` (`src/ddbot`); o nome do produto é `APP_NAME` em
  `src/ddbot/__init__.py`.
- O ambiente de desenvolvimento é **Linux, sem o jogo**. Nada foi validado no cliente nem no launcher reais:
  todos os testes usam simulação, imagens sintéticas ou janelas de teste. Não afirme que algo "funciona no jogo".
- Andamento e pendências: [`PROGRESS.md`](PROGRESS.md). Pesquisa e fontes da física/mira:
  [`docs/RESEARCH.md`](docs/RESEARCH.md). O que cada teste cobre: [`docs/TESTES.md`](docs/TESTES.md).
- **Estado em 2026-10-20:** a 0.5.0 (seis atividades pré-cadastradas) está na branch
  `feature/atividades-prioritarias`, ainda sem Release; a versão no código continua 0.4.4. Antes de continuar,
  leia a primeira seção do `PROGRESS.md` ("Onde parou" e "Próximos passos").

## Idioma

Tudo em **português do Brasil**: textos da interface, mensagens de log, docstrings, comentários, documentação e
mensagens de commit. Identificadores de código (funções, classes, variáveis) em inglês, como no código existente.

## Estrutura

```
src/ddbot/
  detection.py, game_window.py, winapi.py   jogo e launcher (Detectar jogo, perfil, foco, Win32)
  capture.py, vision/                       percepção (captura, regiões, modelos, dígitos, menu,
                                            sugestão automática de regiões em vision/autodetect.py)
  aiming.py, physics.py, calibration.py,    decisão (mira, modelo físico, calibração,
  tracking.py, combat.py, activities.py     rastreio de alvo, combate, fluxo das atividades)
  strategy.py                               estratégias por instância e dificuldade (etapas, alvos, estados)
  catalog.py                                atividades pré-cadastradas e disponibilidade no cliente
  readiness.py                              o que falta calibrar antes de jogar sozinho (com instruções)
  automation/                               execução: SendInput (input.py) e travas (safety.py)
  service.py, gui/                          camada de serviço e interface Tkinter
  simulation.py                             jogo simulado (modo demonstração, testes, --selftest)
  app.py                                    linha de comando e ponto de entrada
data/knowledge/                             tabelas de ângulo, mecânicas, parâmetros do modelo, fontes,
                                            perfis das instâncias (instances.json) e catálogo (catalogo.json)
config/default_config.json                  configuração padrão
packaging/                                  specs do PyInstaller, version_info.txt, run_ddbot.py
tests/                                      pytest (fixtures em conftest.py e fixtures/)
tools/fit_model.py                          reajuste das constantes físicas
tools/display_scale.py                      muda a escala do Windows (100/125/150%...) sem sair da sessão (CI)
```

## Comandos

```bash
source .venv/bin/activate                     # ou: pip install -r requirements.txt -r requirements-dev.txt
python -m pyflakes src tools tests            # lint (a CI falha com qualquer aviso)
python -m pytest -q tests -rs                 # testes; no Linux sem tela: xvfb-run -a python -m pytest -q tests -rs
PYTHONPATH=src python -m ddbot --selftest     # recursos, mira, visão e fluxo simulado
PYTHONPATH=src python -m ddbot --simulate 50  # precisão com e sem calibração
PYTHONPATH=src python -m ddbot --gui-smoke 8  # exercita a interface em modo simulado (precisa de tkinter)
```

Variáveis de ambiente: `DDBOT_HOME` (pasta de dados; os testes usam a fixture `home`), `DDBOT_HEADLESS`,
`DDBOT_UI_SCALE`, `DDBOT_SELFTEST_OUT`, `DDBOT_SMOKE_OUT`.

No Linux de desenvolvimento (Rocky 10) não há Xvfb: os testes de interface (`test_gui_smoke`,
`tests/test_gui_selecao.py`) e as capturas rodam no container local `jonflow-ci` (Ubuntu 24.04, venv em
`/venv`), copiando o repositório para dentro (a pasta `dados/` local não deve entrar nos testes):

```bash
docker run --rm -v "$PWD":/src:ro jonflow-ci bash -lc 'cp -r /src /tmp/w && cd /tmp/w && rm -rf dados && \
  xvfb-run -a -s "-screen 0 1920x1080x24" /venv/bin/python -m pytest -q tests -rs'
# capturas: DDBOT_UI_SCALE=1.5 DDBOT_HOME=/tmp/h xvfb-run ... /venv/bin/python -m ddbot --screenshots /out
```

O build do `.exe` só roda no Windows (`build_windows.bat`); a CI (`.github/workflows/windows-build.yml`) testa no
Linux com Xvfb e no Windows, compila e testa os executáveis. `test_windows_real.py` e alguns testes de interface
só rodam no Windows: são pulados no Linux, e isso é esperado.

No Windows a CI roda, além da suíte completa:

- os testes de janelas reais **num venv e com o navegador aberto**, 3 vezes cada (como no PC do usuário). No
  Windows, o `python.exe` de um venv é um redirecionador que abre o Python base como processo filho: `Popen.pid`
  não é o dono da janela. Use o pid e o hwnd que a janela de teste informa (`--ready`);
- os mesmos testes e a suíte completa com a **escala do Windows em 125%** (`tools/display_scale.py`). O runner
  roda em 100%, e falhas de DPI só aparecem acima disso. Capturas recusadas por esses testes vão para os
  relatórios da CI.

Para acompanhar a CI: `gh run list --limit 5`, `gh run view <id>`, `gh run view <id> --log-failed`. Registre no
`PROGRESS.md` o número da execução e o commit de cada resultado citado.

## Regras do código

- **Segurança vem antes de tudo.** Não enfraqueça as travas de `automation/safety.py` e de `combat.py`/
  `activities.py`: parada de emergência, entrada só com o jogo em foco, um disparo por turno, autorização explícita
  do modo automático, nada de PvP automático, botões pagos/loja bloqueados, nenhum comando ao launcher, nenhuma
  tecla às cegas. Na dúvida, o bot **pausa e explica** em vez de agir.
- **Nada inventado sobre o jogo.** Coordenadas, telas e botões vêm das capturas do usuário; constantes físicas
  vêm de `data/knowledge` com fonte registrada em `sources.json`. Não fixe nomes de janela/processo nem posições.
  Sugestões automáticas (regiões, etapas) são só sugestões: o usuário confirma, e o que ele já marcou não é trocado.
- **Atividades pré-cadastradas** (`catalogo.json`): aparecem sempre, mas a disponibilidade no cliente só muda
  com evidência (opção vista no menu, não encontrada pela rotina, marcada pelo usuário). Opção ou dificuldade
  ausente ou ambígua no menu **pausa**: o bot nunca escolhe outra atividade no lugar. Olimpíadas Bugou
  (`GuluOlympics`) e Castelo do Reino de Bugou (`GuluKingdom`) são instâncias diferentes.
- **Estratégias** (`instances.json`): mudanças de etapas, alvos e dificuldades vão para os dados, com fonte e
  confiança; as dificuldades herdam da instância (`base`) e usam as mesmas capturas de alvos. Etapas que não são
  combate comum (pontuação, corrida, papéis a evitar) pausam sem os modelos obrigatórios.
- **Calibração por resultados**: cada disparo guarda instância, dificuldade, etapa, alvo e cenário (modo da força
  e cliente); a correção só usa disparos do mesmo cenário. Disparos simulados nunca corrigem a mira do jogo real
  e resultados simulados nunca são apresentados como do jogo.
- Telas e fins de batalha só valem após leituras seguidas; leitura com baixa confiança não dispara.
- **Escala do Windows (DPI).** Um programa sem suporte a DPI (como a janela de teste e muitos jogos) desenha no
  tamanho de 100% e o Windows amplia a imagem na tela. A imagem pedida à janela (`winapi.print_window`) vem no DPI
  dela e é ampliada para a área do jogo (`capture.fit_to_area`); imagem com faixas pretas que a tela não tem é
  recusada. Qualquer código que relacione coordenadas ou tamanhos da janela com os da tela precisa considerar a
  escala, e o teste correspondente deve rodar também em 125%.
- A interface nunca pode travar: trabalho pesado fica fora da thread do Tk (o `--gui-smoke` falha se o laço de
  eventos atrasar mais de 1,5 s). Quando a interface para mais de 1 s, o relatório do `--gui-smoke`
  (`DDBOT_SMOKE_OUT`) guarda em `pilhas_no_atraso` onde cada thread estava: use isso em vez de repetir a execução.
- Dados do usuário: use `paths.py` (pasta `dados` portátil ao lado do `.exe` ou `%LOCALAPPDATA%\JonFlow`, com
  compatibilidade com `DDClassicoBot`). Gravação atômica; não grave caminhos pessoais nos logs.
- Dependências com versão fixa em `requirements*.txt`; actions da CI fixadas por SHA. Não adicione dependência sem
  necessidade clara.
- Todo defeito corrigido ganha teste de regressão (ver `tests/test_audit_regressions.py`). Mudanças de interface
  devem continuar cabendo em 1080p a 100/125/150% de escala.
- Siga o estilo vizinho: `from __future__ import annotations`, `logging.getLogger(__name__)`, docstrings curtas.

## Git e versões

Git Flow: `main` (produção, com tags `vX.Y.Z`), `develop` (integração), `feature/*` a partir de `develop`,
`release/*` e `hotfix/*` mesclados em `main` e `develop`. Commits no estilo Conventional Commits em português
(`feat:`, `fix(gui):`, `test:`, `docs:`, `ci:`, `build:`). Para uma versão nova, atualize
`src/ddbot/__init__.py`, `packaging/version_info.txt`, `docs/RELEASE_NOTES.md` e `PROGRESS.md`; a tag dispara a
Release na CI.

Ao terminar uma mudança relevante, registre em `PROGRESS.md` o que foi feito e o que **ainda não** foi validado
no jogo real.
