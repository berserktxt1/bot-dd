# bot-dd

## Fluxo de trabalho (Git Flow)

- `main` — código em produção; recebe apenas merges de `release/*` e `hotfix/*` (com tag de versão).
- `develop` — branch de integração; base para novas features.
- `feature/<nome>` — sai de `develop`, volta para `develop` via PR.
- `release/<versão>` — sai de `develop`, vai para `main` (com tag) e `develop`.
- `hotfix/<versão>` — sai de `main`, vai para `main` (com tag) e `develop`.
