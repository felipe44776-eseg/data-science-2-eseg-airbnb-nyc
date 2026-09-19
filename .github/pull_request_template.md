## O que muda

<!-- uma ou duas frases: o quê e por quê -->

Fecha #

## Fase do CRISP-DM

- [ ] 1 · negócio  - [ ] 2 · dados  - [ ] 3 · preparação  - [ ] 4 · modelagem  - [ ] 5 · avaliação  - [ ] 6 · implantação

## Checklist

- [ ] `.\tasks.ps1 test` passa localmente (ruff + pytest)
- [ ] números citados em docs vêm de `_*.json` gerado pelo pipeline (nenhum número à mão)
- [ ] nenhuma coluna nova fora de `src/airbnb/schema.py`
- [ ] se mudou o modelo do site: `.\tasks.ps1 site` rodou e a paridade JS passou
- [ ] se mudou uma decisão de método: ADR criado/atualizado em `docs/adr/`
- [ ] nenhum dado pessoal (nome de anfitrião, foto, URL de perfil, id de anúncio) em `site/` ou `reports/`
