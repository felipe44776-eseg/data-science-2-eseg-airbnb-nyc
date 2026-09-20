# Como contribuir

Guia de trabalho da equipe. Vale para qualquer mudança — código, documento ou dado
publicado no site.

--8<-- "_snippets/equipe.md"

## Fluxo

1. **Abra (ou pegue) uma issue.** Cada issue tem um rótulo de fase do CRISP-DM
   (`fase-1-negocio` … `fase-6-implantacao`). Trabalho sem issue vira trabalho invisível.
2. **Crie um branch a partir de `main`:** `git switch -c <fase>/<assunto-curto>`,
   por exemplo `fase-4/modelo-ocupacao` ou `docs/etica`.
3. **Commits pequenos, mensagem no imperativo, em português:** "Adiciona feature de
   distância ao metrô", não "mudanças".
4. **Antes do push:** `.\tasks.ps1 test` (ruff + pytest). O CI roda o mesmo e bloqueia
   o que falhar.
5. **Pull request para `main`**, com o template preenchido, e **revisão de outro
   integrante** antes do merge.

## Regras que o CI não consegue verificar sozinho

- **Tabela de resultado não se escreve à mão.** As tabelas dos documentos são geradas
  dos `_*.json` (`.\tasks.ps1 figuras` → `docs/_snippets/`). O texto corrido cita poucos
  números — e cada um tem de bater com o `_*.json`: se o pipeline mudou o número,
  atualize o texto no mesmo PR.
- **Nome de coluna só em `src/airbnb/schema.py`**; caminho e constante só em
  `src/airbnb/config.py`; nome de integrante só em `src/airbnb/produto/autoria.py`.
- **Notebook não contém lógica.** Função nova vai para `src/airbnb/`; o notebook importa.
- **Dado não entra no git** (`.gitignore` já barra `data/**`). Resultado entra:
  `data/**/_*.json` e `site/data/`.
- **Nada pessoal no site**: sem nome de anfitrião, foto, URL de perfil ou id de anúncio.
- **Mudou uma decisão de método?** Escreva ou atualize um ADR em `docs/adr/`.

## Onde cada coisa mora

| quero… | vou em |
|---|---|
| rodar o projeto do zero | [Como reproduzir](como-reproduzir.md) |
| entender uma coluna | `src/airbnb/schema.py` e o [dicionário](dicionario-dados.md) |
| adicionar uma fonte externa | um módulo em `src/airbnb/external/`, entrada no manifesto, `data/external/FONTES.md`, [docs/03](03-fontes-externas.md) e um teste com fixture |
| mudar o modelo do site | `src/airbnb/models/preco.py` → `.\tasks.ps1 preco` → `.\tasks.ps1 site` (a paridade JS roda junto) |
| mudar o visual do site | `site/index.html` (portal), `site/mapa/index.html` (mapa), `site/assets/` — e `.\tasks.ps1 servir` para ver |
| ver o que está desatualizado | `.\tasks.ps1 status` |

## Adicionando uma fonte externa (checklist)

- [ ] URL oficial, licença e texto de atribuição exigido
- [ ] download idempotente, com hash no manifesto (`data/external/_manifesto_externos.json`)
- [ ] feature calculada **por célula H3 r9** (ADR 0001), com safra declarada
- [ ] teste sem rede, com fixture mínima
- [ ] linha na tabela de fontes e de limitações em [docs/03](03-fontes-externas.md)
- [ ] ablação: a feature entra no modelo? a ablação mostra ganho? (se não, documente)
