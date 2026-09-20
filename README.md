# Airbnb em Nova York, 2019 → 2026

**Data Science 2 · ESEG** — CRISP-DM completo sobre os anúncios do Airbnb em Nova
York: da base do Kaggle (2019) ao mercado atual (Inside Airbnb, junho de 2026),
enriquecido com fontes públicas externas, com **modelos preditivos validados
espacialmente** e um **site público com mapa e teste de localização**.

| | |
|---|---|
| 🧭 **O projeto inteiro** | <https://felipe44776-eseg.github.io/data-science-2-eseg-airbnb-nyc/> |
| 🗺️ **Mapa e teste de localização** | <https://felipe44776-eseg.github.io/data-science-2-eseg-airbnb-nyc/mapa/> |
| 🎞️ **Apresentação (20 slides)** | <https://felipe44776-eseg.github.io/data-science-2-eseg-airbnb-nyc/apresentacao/> |
| 📚 **Documentação (CRISP-DM)** | <https://felipe44776-eseg.github.io/data-science-2-eseg-airbnb-nyc/docs/> |
| 🧾 **Versão anterior (v0, descritiva)** | [`reports/v0/`](reports/v0/) |

## A pergunta

A v0 do grupo descreveu 48.895 anúncios de 2019. Esta versão responde o que a
descrição não alcança:

- **Quanto deveria custar** um imóvel com estas características, **neste ponto** da
  cidade — e com que margem de erro? *(modelo hedônico + intervalo conformal)*
- **Quanto ele fatura**, com ocupação medida de verdade — não `1 − disponibilidade`.
- **O que mudou desde 2019**, em dólar constante, depois da pandemia e da
  **Local Law 18** — e **quem sobreviveu** a ela?
- **A localização importa?** Como hipótese testada (I de Moran, LISA), não como opinião.

## O que encontramos

| | |
|---|---|
| **O mercado encolheu e se profissionalizou** | −38% de anúncios e −56% de anfitriões entre 2019 e 2026; o 1% maior de anfitriões passou de 10% para 25% da oferta |
| **A Local Law 18 mudou o que é um anúncio** | mínimo de 30 noites passou de 9% para 82% dos anúncios; em dólar constante, a estadia de 30+ noites custa o mesmo que em 2019 e a estadia curta, 2 a 3 vezes mais |
| **A "ocupação de 69%" da v0 era calendário fechado** | ocupação estimada pelas avaliações: 29% em 2019; a métrica da v0 tem correlação −0,11 com ela |
| **O simulador erra 25% na mediana** | sob validação cruzada **espacial** (lugar novo), com intervalo de 80% calibrado em cada tipo de acomodação; no modelo completo, o KFold aleatório teria prometido 18% de erro onde o real é 22% |
| **O lugar importa, mesmo descontado o imóvel** | I de Moran 0,44 no resíduo de um modelo que só vê o imóvel; o mesmo apartamento vale do −15% ao dobro da mediana conforme a célula |
| **Fontes externas: interpretação, não acurácia** | não superam as coordenadas no preço (resultado nulo, publicado), mas explicam o lugar: aluguel do entorno (Zillow) é a 3ª feature do modelo |
| **Airbnb × aluguel tradicional** | só 28% dos apartamentos ativos faturam mais que um ano de aluguel; na estadia curta legal, 75% |

Critérios de sucesso registrados antes da modelagem e o resultado de cada um:
[`docs/08-avaliacao.md`](docs/08-avaliacao.md).

## Fontes

| fonte | o que traz | licença |
|---|---|---|
| Kaggle — *New York City Airbnb Open Data* | 48.895 anúncios, julho/2019 | CC0 |
| Inside Airbnb — NYC, 2026-06-14 | 30 mil anúncios, 90 colunas | CC BY 4.0 |
| US Census — ACS 5 anos | renda, aluguel, densidade por setor censitário | domínio público |
| NYC Open Data — NYPD e 311 | crimes e reclamações de barulho georreferenciados | termos NYC Open Data |
| MTA (data.ny.gov) | estações de metrô | termos NY Open Data |
| Zillow — ZORI | aluguel de longo prazo por CEP | uso com atribuição |
| BLS / FRED — CPI-U NY | inflação regional (deflator) | domínio público |
| OpenStreetMap (Overpass) | restaurantes, bares, atrações, hotéis, parques | ODbL |

Detalhes, safras e limitações: [`docs/03-fontes-externas.md`](docs/03-fontes-externas.md).

## Como rodar

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# coloque AB_NYC_2019.csv (Kaggle) em data/raw/kaggle/
.\tasks.ps1 all      # fontes -> limpeza -> externos -> modelos -> site -> docs
.\tasks.ps1 test     # ruff + pytest
.\tasks.ps1 servir   # http://localhost:8000
```

Passo a passo completo: [`docs/como-reproduzir.md`](docs/como-reproduzir.md).

## Estrutura

```
src/airbnb/
  schema.py        única fonte de verdade das colunas
  config.py        caminhos, snapshots, resoluções H3, CRS
  ingest/          fontes primárias, com hash conferido
  clean/           bronze -> silver, quarentena com motivo
  external/        fontes externas (ACS, NYPD, MTA, 311, Zillow, CPI, OSM)
  features/        células H3 r9 e tabelas de modelagem
  eda/             qualidade, comparativo 2019 -> 2026, testes espaciais
  models/          preço, ocupação, sobrevivência, deriva — validação espacial
  produto/         exportação para o site, figuras, autoria
site/              mapa + teste de localização (HTML/JS puro, MapLibre, h3-js)
docs/              documentação CRISP-DM (MkDocs) + ADRs
tests/             pytest + paridade Python <-> JavaScript do modelo
```

## Equipe

<!-- equipe:inicio -->
| integrante | RA | GitHub |
|---|---|---|
| Felipe Marins | **44776** | [@felipe44776-eseg](https://github.com/felipe44776-eseg) |
| Otavio Bonfochi | *a confirmar* | [@otaviobonfochisilva1-rgb](https://github.com/otaviobonfochisilva1-rgb) |
| Phelipe Torres Pamponet da França | **46643** | [@phelipe-061](https://github.com/phelipe-061) |
| Tadeu Radovan Graça | **46305** | [@tadeu46305-prog](https://github.com/tadeu46305-prog) |
<!-- equipe:fim -->

<sub>Tabela gerada de `src/airbnb/produto/autoria.py` — a única fonte dos nomes.</sub>

Como contribuir: [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Licença

Código sob [MIT](LICENSE). Os dados pertencem às suas fontes e seguem as licenças
listadas acima — ver [`docs/10-etica-e-lgpd.md`](docs/10-etica-e-lgpd.md) §Atribuição.
