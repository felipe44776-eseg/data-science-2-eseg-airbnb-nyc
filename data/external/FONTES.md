# Fontes externas — proveniência e integridade

Os arquivos baixados **não são versionados** (invariante 5). O que vai para o git é o
**manifesto** `data/external/_manifesto_externos.json`, com URL, parâmetros da consulta,
data de acesso, bytes e SHA-256 de cada artefato, e o resultado `data/processed/_celulas.json`.
Este documento é a versão para ler; o manifesto é a prova.

A leitura analítica das fontes (a pergunta de negócio de cada uma, os vieses, a cobertura
nas células e a linha do tempo regulatória) está em `docs/03-fontes-externas.md`.

## Um comando baixa tudo

```powershell
.\tasks.ps1 externos                      # todas as fontes; pula o que já existe
.\tasks.ps1 externos --apenas acs nypd    # só algumas
.\tasks.ps1 externos --forcar             # rebaixa tudo
.\tasks.ps1 celulas                       # células H3 r9 com as features
```

Equivale a `python -m airbnb.external.coletar [--apenas FONTE ...] [--forcar]` e
`python -m airbnb.features.celulas`, com `PYTHONPATH=src`.

Regras de convivência aplicadas a todas as fontes (`src/airbnb/external/_http.py`):
User-Agent `data-science-2-eseg-airbnb-nyc (projeto academico)`, uma requisição por vez,
retry com backoff exponencial em 429/5xx (honra `Retry-After`), timeout curto (≤ 90 s),
download via arquivo `.parcial` renomeado só no fim. Um arquivo que é pulado mantém no
manifesto a data e os parâmetros da coleta que o baixou (`verificado_em` registra a
conferência); se o hash tiver mudado, o manifesto marca a divergência.

Uma fonte fora do ar **não derruba as outras**: ela entra no manifesto como
`"estado": "falhou"`, com o erro, e as features dela saem nulas nas células — a
cobertura em `_celulas.json` mostra o buraco.

## Resumo

Coleta de referência: **2026-09-19 (UTC)**, 40,3 MB no total.

| # | fonte | órgão | granularidade | safra 2019 | safra atual | licença |
|---|---|---|---|---|---|---|
| E1 | ACS 5 anos, Summary File por tabela | U.S. Census Bureau | tract | 2015–2019 (tracts 2010) | 2020–2024 (tracts 2020) | domínio público |
| E2 | Cartographic Boundary, tracts 1:500k | U.S. Census Bureau | tract | `cb_2019` | `cb_2024` | domínio público |
| E3 | NYPD Complaint Data (Historic + YTD) | NYPD | delegacia (agregado no servidor) | 2018-07-08 a 2019-07-07 | 2025-06-14 a 2026-06-13 | NYC Open Data |
| E4 | MTA Subway Stations | MTA | estação | a atual (sem estação nova desde 2017) | 2026 | Open NY |
| E5 | 311 Service Requests, `Noise%` | NYC 311 | ZIP → MODZCTA (agregado no servidor) | 2018-07-08 a 2019-07-07 | 2025-06-14 a 2026-06-13 | NYC Open Data |
| E6 | Zillow Observed Rent Index (ZORI) | Zillow Research | ZIP → MODZCTA | 2019-07 | 2026-06 | uso livre com atribuição |
| E7 | CPI-U NY-Newark-Jersey City | BLS | mensal | 2019-07 | 2026-06 | domínio público |
| E8 | OpenStreetMap via Overpass | colaboradores do OSM | ponto | a atual (anacronismo) | 2026-09 | ODbL 1.0 |
| E9 | marcos da cidade | curadoria + Wikipedia | ponto | fixo | fixo | fato; CC BY-SA (texto) |
| E10 | relatórios anuais da LL18 | NYC OSE | distrito do Conselho | não existia | FY26 | nyc.gov |
| — | MODZCTA | NYC DOHMH | ZIP modificado (178) | ponte ZIP → área | idem | NYC Open Data |

---

## E1 · American Community Survey (ACS), estimativas de 5 anos — `acs/`

| | |
|---|---|
| **Arquivos** | `acs5_2015-2019_tracts_nyc.csv` (191.292 bytes, SHA-256 `fcbb5f4c54186740…`) · `acs5_2020-2024_tracts_nyc.csv` (202.868 bytes, `19291c2738caf4bf…`) |
| **Origem** | `https://www2.census.gov/programs-surveys/acs/summary_file/2019/prototype/5YRData/acsdt5y2019-<tabela>.dat` e `…/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-<tabela>.dat` |
| **Tabelas** | B01003 (população), B19013 (renda domiciliar mediana), B25064 (aluguel bruto mediano), B25077 (valor mediano do imóvel), B25003 (posse: ocupados/alugados), B25002 (ocupação: total/vagos) — estimativa e margem de erro |
| **Tracts de NYC** | 2.167 (2015–2019) · 2.327 (2020–2024) |
| **Licença** | domínio público. Crédito: *"Fonte: U.S. Census Bureau, American Community Survey 5-year estimates"* |

**Por que não a API.** O briefing previa `api.census.gov` sem chave. Em 2026-09-18 a API
respondia a página *Missing Key* ("A valid key must be included with each data API
request") a qualquer requisição. A alternativa oficial e sem chave é o **ACS Summary File
no formato por tabela**: um arquivo por tabela com estimativa e margem de erro de todas as
geografias do país. Para 2018–2020 o Census publica esse formato na pasta `prototype/`
(página oficial do Summary File: *"2018-2020: Select the Prototype folder to select the
table-based format"*).

**Como baixamos só NYC.** Cada arquivo tem 15–27 MB, mas é **ordenado por `GEO_ID`** e o
servidor aceita `Range`. Uma busca binária por bytes acha o bloco `1400000US36…` (tracts do
estado de NY) e baixa ~0,5 MB por tabela, não o arquivo inteiro. O código confere que o
bloco saiu ordenado e sem repetição; o SHA-256 de cada bloco está no manifesto.

**Tratamento.** Código-sentinela (`-666666666`, `-999999999`, `-888888888`, `-222222222`,
`-333333333`, `-555555555`) → nulo. Mediana com teto é censura, não valor: tracts no teto
em 2015–2019 / 2020–2024: renda (250.001) 5 / 13, valor do imóvel (2.000.001) 33 / 57,
aluguel (3.501) 8 / 94. Coeficiente de variação mediano da renda do tract (MOE/1,645/estimativa):
**0,128** (2015–2019) e **0,174** (2020–2024).

## E2 · Geometria dos tracts — `tracts/`

| arquivo | bytes | SHA-256 | tracts de NYC |
|---|---:|---|---:|
| `cb_2019_36_tract_500k.zip` | 1.761.483 | `e4ed39cd98bc0336…` | 2.166 (tracts 2010) |
| `cb_2024_36_tract_500k.zip` | 1.925.268 | `ab7f72cb4a66079f…` | 2.324 (tracts 2020) |

Origem: `https://www2.census.gov/geo/tiger/GENZ{ano}/shp/cb_{ano}_36_tract_500k.zip`.
Cada safra do ACS casa com a geometria da **mesma década** de tracts. `ALAND` (m² de
terra) é o denominador da densidade. Domínio público.

## E3 · Queixas criminais do NYPD — `nypd/`

| | |
|---|---|
| **Datasets** | `qgea-i56i` NYPD Complaint Data Historic (em 2026-09: `rpt_dt` de 2006-01-01 a 2025-12-31, 10.071.507 linhas) · `5uac-w243` NYPD Complaint Data Current (Year To Date) (2026-01-01 a 2026-06-30) · `y76i-bdw7` Police Precincts (78 polígonos, NYC DCP) |
| **Consulta** | `$select=addr_pct_cd, law_cat_cd, count(*) AS n` · `$where=rpt_dt between '<início>T00:00:00' and '<fim>T23:59:59'` · `$group=addr_pct_cd, law_cat_cd` |
| **Janelas** | 2019: 2018-07-08..2019-07-07 (Historic) · atual: 2025-06-14..2025-12-31 (Historic) + 2026-01-01..2026-06-13 (Current) |
| **Resultado** | `queixas_por_delegacia.csv` (23.889 bytes, `1246521bbea6c219…`) · `delegacias.geojson` (3.842.851 bytes, `7181d42d8384a4a0…`) |
| **Volume** | 2019: **458.158** queixas (FELONY 140.916 · MISDEMEANOR 245.465 · VIOLATION 71.777) · atual: **570.820** (184.147 · 294.837 · 91.836) · 0 sem delegacia válida |
| **Licença** | NYC Open Data Terms of Use: uso livre, sem garantia; a Prefeitura pode exigir que a republicação identifique fonte, versão e modificações |

**Por que agregado por delegacia.** A primeira tentativa (paginar as ~500 mil linhas da
janela no Historic, 10 milhões de linhas, filtrando por `rpt_dt`) levou mais de 100 s por
página e estourou o timeout. Agregado no servidor, cada janela responde em segundos com
poucas centenas de linhas. O preço é a granularidade: **77 polígonos em 2019 e 78 no
atual**, não o anel r9. Se a janela inteira não responder em 90 s, o código a divide em
meses e soma (a soma de meses disjuntos é a contagem da janela; há teste).

**O corte é por `rpt_dt`** (data do registro), que é como os dois datasets se particionam:
cortar pela data do fato deixaria buraco ou contagem dupla na emenda Historic/Current.

**A 116ª delegacia** (sudeste do Queens) foi desmembrada da 105ª em dezembro de 2023. Na
safra 2019, as duas são tratadas como uma só (área somada); no atual, separadas.

## E4 · Estações do metrô — `mta/`

`estacoes_metro.csv` (48.490 bytes, `c7c8e21325113e8d…`), de
`https://data.ny.gov/resource/39hk-dx4f.csv`: **496 estações-plataforma, 445 complexos,
24 linhas** (inclui a Staten Island Railway). Licença: Open NY Terms of Use; atribuição à
Metropolitan Transportation Authority (mta.info/open-data).

## E5 · Barulho no 311 — `nyc311/`

| | |
|---|---|
| **Datasets** | `76ig-c548` 311 Service Requests from 2010 to 2019 (janela 2019) · `erm2-nwe9` 311 Service Requests from 2020 to Present (janela atual) |
| **Consulta** | `$select=incident_zip, count(*) AS n` · `$where=created_date between … AND complaint_type like 'Noise%'` · `$group=incident_zip` |
| **Resultado** | `barulho_por_zip.csv` (11.877 bytes, `db00a7420d3c0705…`) |
| **Volume** | 2019: **460.880** chamados (4.356 em ZIP fora de qualquer MODZCTA) · atual: **803.259** (4.916 fora) |
| **Licença** | NYC Open Data Terms of Use |

**Escolha da granularidade (documentada).** Por ponto seriam ~0,5–0,8 milhão de linhas por
janela num dataset de dezenas de milhões — o mesmo problema do NYPD. Por ZIP, agregado no
servidor, são ~200 linhas por janela. O ZIP é traduzido para o MODZCTA pela lista de ZCTAs
de cada MODZCTA e dividido pela área dele (km²).

## E6 · Zillow Observed Rent Index — `zillow/`

| | |
|---|---|
| **Arquivo** | `Zip_zori_uc_sfrcondomfr_sm_month.csv` (10.023.480 bytes, `a60963f429dbacf9…`), série de 2015-01 a 2026-08 |
| **Origem** | `https://files.zillowstatic.com/research/public_csvs/zori/Zip_zori_uc_sfrcondomfr_sm_month.csv` |
| **Derivado** | `zori_nyc.csv`: 149 ZIPs dos cinco condados; **81** com valor em 2019-07 e **140** em 2026-06 |
| **Licença** | *"free for public use … Proper and clear attribution of all data to Zillow is required"* (página Zillow Research Data). Crédito: *"Zillow Observed Rent Index (ZORI), Zillow Research"* |

## E7 · CPI-U New York-Newark-Jersey City — `cpi/`

| | |
|---|---|
| **Série** | BLS `CUURS12ASA0` (mensal, sem ajuste sazonal, base 1982–84 = 100) |
| **Arquivo** | `CUURS12ASA0_bls.json` (API pública v2 do BLS, sem chave, 2017–2026) |
| **Conferência** | `CUURA101SA0_fred.csv` — a **mesma série** no FRED, que manteve o código de área anterior à revisão de 2018 (`fredgraph.csv?id=CUURS12ASA0` responde 404). Os 115 meses em comum são **idênticos** |
| **Saída** | `data/processed/cpi_ny.parquet` (`mes`, `indice`) e `fator_cpi()` em `src/airbnb/external/cpi.py` |
| **Fator** | 2019-07 → 2026-06 = **1,293067** (278,817 → 360,529) |
| **Lacuna** | **2025-10 não existe**: o BLS não coletou preços durante a paralisação do governo federal. Não é interpolado |
| **Licença** | domínio público. Crédito: *"U.S. Bureau of Labor Statistics, CPI-U, New York-Newark-Jersey City"* |

Em 2026-09-18, clientes que não são navegador tinham a conexão com o FRED segurada até o
timeout; por isso o BLS é a fonte primária e o FRED, a conferência.

## E8 · OpenStreetMap — `osm/`

Uma consulta Overpass por grupo (`https://overpass-api.de/api/interpreter`; espelho
`overpass.kumi.systems`), no envelope de NYC alargado em 0,01° (~1 km), com `out center`:

| grupo | chave OSM | elementos | arquivo | bytes | SHA-256 |
|---|---|---:|---|---:|---|
| restaurantes | `amenity=restaurant\|fast_food` | 15.540 | `restaurantes.json` | 7.059.351 | `367445817e6787bb…` |
| cafés | `amenity=cafe` | 2.958 | `cafes.json` | 1.372.629 | `97bc7d02760650bf…` |
| bares | `amenity=bar\|pub\|nightclub` | 2.137 | `bares.json` | 898.242 | `d93987747197d40f…` |
| atrações | `tourism=attraction\|museum\|gallery\|viewpoint` | 1.103 | `atracoes.json` | 515.737 | `3fe76d1314699da1…` |
| hotéis | `tourism=hotel\|hostel\|guest_house` | 859 | `hoteis.json` | 618.018 | `90a95dc2643b5166…` |
| parques | `leisure=park` | 3.134 | `parques.json` | 1.912.140 | `ca60e4408181fdde…` |

Base OSM (`timestamp_osm_base`) de todos os grupos: **2026-09-19**, servidor principal.
O espelho `overpass.kumi.systems` servia, no mesmo dia, a base de **2026-06-01**: um grupo
que caísse nele ficaria três meses defasado dos outros. A coleta registra a base de cada
grupo e marca `bases_coerentes: false` se elas divergirem mais de um dia.

Licença **ODbL 1.0**: atribuição obrigatória — *"© OpenStreetMap contributors"*, com link
para `openstreetmap.org/copyright`. O `timestamp_osm_base` de cada consulta está no
manifesto.

## E9 · Marcos da cidade — `marcos/`

Sete pontos fixados em `src/airbnb/external/marcos.py` (Times Square, Empire State
Building, Central Park, One World Trade Center, Brooklyn Bridge, JFK, LGA) com as
coordenadas da infobox da Wikipedia em inglês. A coleta **confere** cada uma na API da
Wikipedia (`prop=coordinates`) e grava o desvio em metros em `marcos.json`.

## E10 · Local Law 18 — `ll18/`

| | |
|---|---|
| **Dado aberto?** | **Não há dataset** da OSE no NYC Open Data (busca no catálogo por *short-term rental*, *Office of Special Enforcement*, *Local Law 18*, em 2026-09-18) |
| **O que existe** | os relatórios anuais que a própria LL18 obriga a OSE a publicar, em XLSX: `https://www.nyc.gov/site/specialenforcement/about/data-reports.page` |
| **Coletados** | LL18 FY23, FY24, FY25, FY26 (ano fiscal de 1/jul a 30/jun) e, só registrados, os relatórios de fiscalização LL87 de 2018, 2019, 2024 e 2025 |
| **Extraído** | Figura 1: registros **ativos por distrito do Conselho Municipal** (51) → `registros_ll18_por_distrito.csv` |
| **Limites** | `distritos_conselho.geojson`, NYC Open Data `872g-cjhh` (NYC DCP) |
| **Leitura** | XLSX lido com `zipfile` + XML (`src/airbnb/external/_xlsx.py`), sem dependência nova |

Registros ativos no fim de cada ano fiscal: **FY23 105 · FY24 2.290 · FY25 2.952 ·
FY26 3.338** (3.522 ativos em algum momento do FY26).

## MODZCTA — `modzcta/`

`modzcta.geojson` (3.150.358 bytes, `bad811df00484f72…`), NYC Open Data `pri4-ifjk`
(NYC DOHMH): 178 polígonos, 771,2 km². Ponte entre a célula e tudo que vem por ZIP (311,
ZORI).

---

## Incidentes da coleta de 2026-09-18/19

| fonte | o que aconteceu | o que foi feito |
|---|---|---|
| Census API | exige chave em toda requisição | Summary File por tabela (oficial, sem chave) com HTTP Range |
| FRED | `CUURS12ASA0` responde 404; o código lá é `CUURA101SA0` | BLS primário, FRED como conferência (idênticos) |
| FRED | conexão de cliente não-navegador segurada até o timeout | idem |
| NYPD Historic | paginar linhas: > 100 s por página | agregação por delegacia no servidor |
| Overpass | HTTP 429 e 504 intermitentes | backoff de 15–60 s, 5 s entre consultas, espelho de reserva |
| 311 | o dataset `erm2-nwe9` só cobre 2020 em diante | janela 2019 no `76ig-c548` |
