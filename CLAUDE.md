# CLAUDE.md — Data Science 2 · Airbnb em Nova York (2019 → 2026)

Contexto de projeto. Herda de `~/CLAUDE.md` tudo que não estiver aqui.

## Tenant

**ESEG (acadêmico)** — nunca tocar em recurso de cliente a partir deste diretório.

| | |
|---|---|
| Identidade git | `felipe_44776@aluno.eseg.edu.br` (via `includeIf` de `Eseg/`) |
| Conta gh | `felipe44776-eseg` (`GH_CONFIG_DIR=~/.config/gh-esg`) |
| Repo | `felipe44776-eseg/data-science-2-eseg-airbnb-nyc` (público) |
| gcloud config | `eseg` (não utilizada — projeto é local-first + GitHub Pages) |

Subagente que rode `git`/`gh` aqui deve receber o tenant declarado no prompt.

## Equipe

Fonte única: `src/airbnb/produto/autoria.py`. Nome de integrante **não se escreve
à mão em nenhum outro lugar**.

| integrante | RA | GitHub |
|---|---|---|
| Felipe Marins | 44776 | `felipe44776-eseg` |
| Otavio Bonfochi | 44585 | `otaviobonfochisilva1-rgb` |
| Phelipe Torres Pamponet da França | 46643 | `phelipe-061` |
| Tadeu Radovan Graça | 46305 | `tadeu46305-prog` |

## O problema

Base de partida: Kaggle `dgomonov/new-york-city-airbnb-open-data` (`AB_NYC_2019.csv`,
48.895 anúncios, 16 colunas, scrape de 2019-07-08). A v0 do grupo
(`reports/v0/`) é descritiva. Esta versão é **preditiva, enriquecida com fontes
externas e comparada com o mercado atual** (Inside Airbnb, 2026-06-14).

Entre os dois snapshots há a **Local Law 18** (fiscalização desde 2023-09-05):
estadia < 30 noites exige registro. Em 2026, 81,7% dos anúncios têm mínimo ≥ 30
noites. Toda comparação 2019 × 2026 tem de levar isso em conta.

## Comandos

```powershell
.\tasks.ps1 dados      # fontes primárias, hash conferido
.\tasks.ps1 all        # fontes -> limpeza -> externos -> modelos -> site -> docs
.\tasks.ps1 test       # ruff + pytest
.\tasks.ps1 servir     # site + docs em http://localhost:8000
```

`tasks.ps1` usa `.venv\Scripts\python.exe` quando existe. `PYTHONPATH` aponta para `src/`.

## Invariantes — não violar

1. **`src/airbnb/schema.py` é a única fonte de verdade** de nome, tipo, domínio e
   semântica de coluna das bases do Airbnb. Coluna de origem mantém o nome da origem
   (rastreável ao dicionário do Inside Airbnb); coluna derivada é pt-BR snake_case.
2. **Nenhuma linha é descartada em silêncio.** Toda remoção vai para a quarentena com
   motivo, e toda regra emite contagem em `_qualidade.json`. Excluir da análise de
   preço (flag) é diferente de excluir da base (quarentena).
3. **Nunca validação aleatória em modelo com localização.** CV espacial por bloco
   H3 r6 (ADR 0002). KFold aleatório aparece só como comparação, para medir o otimismo.
4. **Localização é a célula H3 r9, não o ponto** (ADR 0001). O Airbnb desloca a
   coordenada publicada em até ~150 m; features no ponto exato seriam ruído.
5. **Dado não é versionado; manifesto com hash é.** Resultado (`_*.json`) e dados do
   site (`site/data/`) são.
6. **Notebook não contém lógica** — importa de `src/` e mostra resultado.
7. **`availability_365` não é ocupação** (erro da v0). Dia indisponível inclui dia
   bloqueado pelo anfitrião. Ocupação vem de `estimated_occupancy_l365d` (atual) ou
   do modelo de avaliações do Inside Airbnb (2019).
8. **Preço de 2019 só se compara com o atual em dólar constante** (CPI-U NY,
   `CUURS12ASA0`) **e estratificado por mínimo de noites** (< 30 / ≥ 30): pós-LL18, o
   `price` de estadia longa é cotação com desconto mensal (ADR 0005). Em 2026 a diária
   comparável é o **`preco_cheio`** (sem desconto) — a mesma definição do `price` de
   2019; o preço descontado fica só como transparência (`preco_real_cotado`).
9. **Nenhum dado pessoal nas superfícies publicadas**: sem `host_name`, `host_about`,
   fotos, URLs de perfil, nem id de anúncio no site.
10. **O site calcula com o mesmo modelo validado.** Paridade Python ↔ JavaScript
    conferida por `tests/paridade_js.mjs` a cada `.\tasks.ps1 site`.

## Onde cada coisa mora

| quero… | vou em |
|---|---|
| nome/tipo/domínio de coluna da silver | `src/airbnb/schema.py` |
| quais colunas entram em cada modelo | `src/airbnb/models/especificacao.py` |
| features de localização por célula (e a API de safra) | `src/airbnb/features/celulas.py` |
| caminhos, snapshots, resoluções H3 | `src/airbnb/config.py` |
| o grafo de etapas e o status | `src/airbnb/pipeline/estado.py` (`.\tasks.ps1 status`) |
| o modelo que o site roda | `site/data/modelo_preco.json` — **é** o modelo |
| tabelas e figuras dos docs | geradas: `docs/_snippets/`, `docs/assets/figuras/` (`.\tasks.ps1 figuras`) |
| decisões travadas | `docs/adr/` |
| as páginas publicadas | `site/`: `index.html` (portal), `mapa/`, `apresentacao/`, `executiva/`, `executiva-maior/` |
| se uma página diverge do pipeline | `tests/test_superficies.py` |
| se um deck quebrou o layout | `node tests/geometria_decks.mjs <url>` — manual, precisa de Chrome (cabeçalho do arquivo) |

## Estado

**Em 2026-09-22: pipeline 13/13 etapas ok**, 185 testes, ruff limpo, paridade
Python ↔ JS com erro 0 nos dois modelos do site (preço e ocupação). Critérios
pré-registrados (docs/01 §5): C1, C2, C3 atendidos; **C4 (externas melhoram o preço) e C5
(sobrevivência AUC ≥ 0,70) não** — reportados como resultado, não escondidos (docs/07,
docs/08). C4 e C5 são o mesmo achado: dado o ponto no mapa, o resto da geografia é
redundante (η² mediano de 0,85 das externas explicado pela célula r8).

`.\tasks.ps1 status` compara **data de modificação**. Como os `_*.json` são versionados,
trocar de branch reescreve código e resultado no mesmo segundo e pode marcar etapa como
"obsoleto" sem nada ter mudado. Rodar a etapa de novo e conferir `git status` limpo tira
a dúvida (feito em 2026-09-22: as seis etapas marcadas reproduziram resultado idêntico).

### Superfícies publicadas

GitHub Pages, deploy a cada merge em `main` que toque `site/**`.

| URL | o que é |
|---|---|
| `/` | portal do projeto (identidade ESEG: `#08223D`, `#00A1B8`, Public Sans) |
| `/mapa/` | mapa + simulador (modelo de preço e de ocupação no navegador) |
| `/apresentacao/` | deck técnico, 20 slides, paleta Airbnb (sem logo, com a linha de não afiliação) |
| `/executiva/` | deck executivo, 20 slides, tom leve |
| `/executiva-maior/` | a executiva com a letra ~15% maior; 21 slides ("De onde vem a conta" vira dois) |
| `/docs/` | MkDocs, uma página por fase do CRISP-DM |

- **Os decks escrevem os números no HTML.** Resultado mudou → atualizar o portal e os três
  decks no mesmo commit. `test_superficies.py` amarra os números do portal e do deck
  técnico ao pipeline; as executivas não têm essa amarra.
- **`executiva-maior/` é cópia editada à mão de `executiva/`.** Mudança de texto ou número
  numa vai para a outra, e a maior usa a captura `../executiva/mapa-simulador.jpg`.
- Nomes da equipe nos decks vêm de `site/assets/equipe.js`, que lê `site/data/resumo.json`.

### Números revisados — não reintroduzir

Cada um destes já foi publicado errado e corrigido:

- preço 2019 × 2026 do apartamento inteiro de 30+ noites: **+4,0%** com `preco_cheio`
  (o −6,4% era o preço descontado);
- cumprimento do registro: **86%** dentro da base (2.268 de 2.635 que precisam de
  registro); o "60%" dividia registros da cidade por anúncios da base e foi retirado;
- o mercado **encolheu** (−38% de anúncios, −59,3% de noites ocupadas) **e foi trocado**
  (57,5% dos anúncios de 2026 são de anfitriões que não existiam em 2019) — nunca "não
  encolheu";
- leis até a fiscalização funcionar: **13 anos** (2010 → 2023);
- prêmio da localização: de −15% ao dobro **em 95% da cidade** (nos 5% mais caros passa
  disso, até +445%);
- saídas atribuíveis à LL18 pelo controle de 30+ noites: **6,8%, ordem de grandeza** —
  nem piso nem teto;
- cobertura do intervalo de 80%: **79,6%**, nunca "80%".

### Pendências conhecidas

- Deck técnico: no slide 3 o "US$ 313" quebra em duas linhas; no slide 19 os dois cartões
  de baixo invadem o rodapé (~34 px). Acusados por `tests/geometria_decks.mjs`.
- `pipeline/estado.py` não enxerga dependência em `regras.py`, `relatorio.py` e nos
  snippets, e trata entrada ausente como ok.
- Falha de fonte externa vira NaN em silêncio.
- `site/data/anuncios_2026.json` publica coordenada com 4 casas (~11 m). O Airbnb já
  desloca ~150 m, mas arredondar para 3 casas reduz o risco de reidentificação.

Falhas conhecidas de ambiente:
- **A API do Census exige chave** desde 2026: o ACS vem do Summary File oficial por HTTP
  Range (`external/acs.py`). Não "consertar" voltando para a API.
- **Overpass**: o espelho `overpass.kumi.systems` pode servir dado defasado; o manifesto
  marca quando as datas divergem.
- O snapshot de 2019 do Inside Airbnb responde **403** — 2019 só vem do Kaggle.
- No FRED, a série do CPI-U NY é `CUURA101SA0`; no BLS, `CUURS12ASA0` (idênticas).

Frentes abertas (docs/08 §5): painel de snapshots trimestrais para diferenças-em-diferenças
da LL18; relatórios LL87 (queixas de aluguel ilegal por distrito do Conselho) como feature
de fiscalização em 2019; recalibração trimestral automática (gatilho do ADR 0003).
