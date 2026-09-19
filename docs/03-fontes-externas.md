# 2 · Fontes externas

> Números apurados por `python -m airbnb.external.coletar` e `python -m airbnb.features.celulas`
> e gravados em `data/external/_manifesto_externos.json` (URL, parâmetros, data de acesso,
> bytes e SHA-256 de cada artefato) e `data/processed/_celulas.json` (cobertura e
> estatísticas por feature). Coleta de referência: **2026-09-19 (UTC)**. Proveniência
> byte a byte em
> [`data/external/FONTES.md`](https://github.com/felipe44776-eseg/data-science-2-eseg-airbnb-nyc/blob/main/data/external/FONTES.md).

A base do Kaggle sabe **onde** está o anúncio — um ponto deslocado em até ~150 m e o nome
do bairro — mas não sabe **o que há** ali. A v0 parou em "Manhattan é mais caro". Para
perguntar *o que, no entorno, explica o preço, a ocupação e a saída do mercado*, é preciso
medir o entorno com dados que não vêm do Airbnb. Cada fonte abaixo responde a uma pergunta
de negócio, tem safra declarada e entra no modelo pela célula H3 r9
([ADR 0001](adr/0001-unidade-espacial-h3.md)).

## 1. Mapa das fontes

| fonte | pergunta de negócio | vira | chega à célula por | safra 2019 | safra atual |
|---|---|---|---|---|---|
| **ACS** (Census) | o anúncio caro está onde o morador é rico, ou onde o aluguel é caro? onde há imóvel vago? | renda, aluguel, valor do imóvel, densidade, % alugado, % vago | tract do centroide | 2015–2019 | 2020–2024 |
| **NYPD** | a segurança percebida do entorno pesa no preço e na permanência? | queixas graves e totais por km² | delegacia do centroide | 12 meses até 2019-07-07 | 12 meses até 2026-06-13 |
| **311** | vida noturna atrai hóspede e irrita vizinho — quanto? | chamados de barulho por km² | MODZCTA do centroide | 12 meses até 2019-07-07 | 12 meses até 2026-06-13 |
| **Zillow ZORI** | o Airbnb acompanha o aluguel de longo prazo do entorno? onde o aluguel mais subiu, a oferta encolheu mais? | aluguel anunciado típico | MODZCTA do centroide | 2019-07 | 2026-06 |
| **MTA** | quanto vale estar perto do metrô? | distância, estações e linhas a 800 m | distância do centroide | a atual | a atual |
| **OpenStreetMap** | o que há a pé: restaurante, bar, café, atração, hotel, parque? | contagens no anel k = 1 | anel de 7 células | a atual ⚠ | a atual |
| **Marcos** | quanto pesa a distância ao centro turístico e ao aeroporto? | distâncias em km | distância do centroide | fixo | fixo |
| **CPI-U NY** (BLS) | quanto vale, em dólar de hoje, o preço de 2019? | deflator | — | 2019-07 | 2026-06 |
| **OSE / LL18** | quantos registros legais existem, e onde? | registros ativos por km² (contexto) | distrito do Conselho do centroide | não existia | FY26 |

⚠ = anacronismo declarado (§6).

## 2. Como a fonte vira feature: a célula H3 r9

A tabela `data/processed/celulas_r9.parquet` tem **7.219 células r9, uma linha por
célula**: todas as que **tocam** a NYC terrestre (contenção *overlap* sobre a união dos 233
polígonos de bairro do Inside Airbnb). Com contenção por centro, a célula costeira cujo
centro cai na água ficaria de fora, e o anúncio na orla ficaria sem feature. Área das
células: 763,6 km², dos quais 666,3 km² de terra (a coluna `frac_terra` diz quanto de cada
célula é terra).

| | 2019 | 2026 |
|---|---:|---:|
| anúncios | 48.895 | 30.555 |
| anúncios cuja célula está na tabela | 48.888 (**99,986%**) | 30.555 (**100%**) |
| células com anúncio | 3.508 | 3.434 |

Cada fonte chega à célula pela unidade em que é publicada — e a unidade está declarada em
`FEATURES[nome]["transformacao"]`, no código:

| unidade de agregação | fontes | por quê |
|---|---|---|
| **tract** que contém o centroide | ACS | é a menor unidade com margem de erro publicada |
| **delegacia** que contém o centroide | NYPD | agregação no servidor (ver o aviso abaixo) |
| **MODZCTA** que contém o centroide | 311, ZORI | as duas são publicadas por ZIP |
| **anel k = 1** (a célula + 6 vizinhas, ~0,74 km²) | OSM | suaviza o deslocamento de ~150 m do ponto do Airbnb |
| **distância métrica** do centroide (UTM 18N) | MTA, marcos | — |

Centroide que não cai em nenhum polígono (orla, píer) herda o **polígono mais próximo**;
para os tracts, só entre os que têm terra (`ALAND > 0`), para a célula costeira não herdar
um tract só de água. Quantas células foram atribuídas por proximidade: bairro 897 · tract
2010 270 · tract 2020 360 · MODZCTA 620 · delegacia 608 (`_celulas.json` →
`diagnostico_atribuicao`). Nenhum centroide caiu em dois bairros ao mesmo tempo.

!!! warning "Crime e barulho não estão no anel r9"
    O briefing previa contar queixas e chamados no anel k = 1 de cada célula. Paginar as
    ~500 mil queixas de uma janela no dataset histórico do NYPD (10 milhões de linhas)
    levou mais de 100 s por página e estourou o timeout. A decisão foi **agregar no
    servidor**: queixas por **delegacia** (77 polígonos em 2019, 78 no atual) e chamados
    311 por **ZIP**, convertidos em densidade por km² da delegacia ou do MODZCTA. É uma
    feature mais grossa — todas as células de uma delegacia recebem o mesmo valor — e o
    [teste de localização](06-testes-de-localizacao.md) e o SHAP têm de ser lidos com isso
    em mente.

**Contrato com a modelagem** (`src/airbnb/features/celulas.py`):

- `FEATURES_LOCAL_NEUTRAS` — 24 nomes sem sufixo de safra, em ordem estável, incluindo
  `lat` e `lon` (centroide da célula);
- `features_da_safra(df, "2019" | "atual")` — DataFrame indexado por `h3_r9` com
  exatamente essas colunas: `acs_renda_mediana_2019` e `acs_renda_mediana_atual` viram
  `acs_renda_mediana`. Com `dolar="2019-07"`, as monetárias (ACS e ZORI) são convertidas
  pelo CPI (§3.8);
- `fonte_da_feature(nome)` — rótulo curto (`ACS`, `NYPD`, `311`, `Zillow`, `MTA`, `OSM`,
  `marcos`, `H3`), usado para agrupar o SHAP e o site;
- `zori_var_pct` e `ll18_registros_km2_atual` estão na tabela, mas **fora** das listas de
  modelo: a primeira é informação do futuro para um modelo de 2019; a segunda só existe
  em 2026.

## 3. Fonte a fonte

### 3.1 ACS — American Community Survey, estimativas de 5 anos

| | |
|---|---|
| **Pergunta** | preço alto acompanha renda alta, aluguel alto ou imóvel caro? onde há vacância (inclusive de uso sazonal)? |
| **Órgão** | U.S. Census Bureau |
| **Granularidade** | tract (setor censitário): 2.167 em 2015–2019 (tracts de 2010), 2.327 em 2020–2024 (tracts de 2020) |
| **Safra** | 2015–2019 para o snapshot de 2019 · 2020–2024 (a mais recente publicada; 2021–2025 sai em dez/2026) para o atual |
| **Licença** | domínio público |
| **Features** | `acs_renda_mediana` (B19013), `acs_aluguel_mediano` (B25064), `acs_valor_imovel` (B25077), `acs_pop_densidade` (B01003 ÷ área de terra), `acs_pct_alugado` (B25003_003 ÷ B25003_001), `acs_pct_vago` (B25002_003 ÷ B25002_001) |

Os dados vêm do **Summary File por tabela** (www2.census.gov), não da API: em 2026-09-18
a API do Census passou a exigir chave em toda requisição. O arquivo nacional de cada tabela
é ordenado por `GEO_ID`; uma busca binária com HTTP `Range` baixa só o bloco dos tracts de
NY. Cada safra do ACS é juntada à geometria da **mesma década** de tracts — os GEOIDs de
2010 e 2020 não designam o mesmo território.

!!! note "Limitações do ACS"
    - **É estimativa amostral, com margem de erro.** O coeficiente de variação mediano da
      renda do tract é **0,128** em 2015–2019 e **0,174** em 2020–2024 — a renda de um
      tract típico tem incerteza de ±13–17% (1 desvio-padrão). A MOE está guardada em
      `data/external/acs/`, não nas features.
    - **Mediana com teto é censura:** renda 250.001 ("250 mil ou mais"), valor do imóvel
      2.000.001, aluguel 3.501. Tracts no teto em 2015–2019 / 2020–2024: renda 5 / 13,
      valor 33 / 57, aluguel 8 / 94 — e 59 desses 94 tetos de aluguel são de Manhattan.
    - **Tract sem morador não tem mediana:** parques, cemitérios, aeroportos. Os tracts de
      2020 isolaram mais dessas áreas — 84 tracts de NYC com população zero, contra 43
      nos de 2010 —, por isso a cobertura de 2020–2024 é menor (§4).
    - **2020–2024 inclui a pandemia**, com o êxodo e o retorno a Manhattan dentro da
      janela.
    - **Dólares nominais do último ano** (2019 ou 2024). Use `features_da_safra(...,
      dolar=...)` para comparar safras.

### 3.2 NYPD — queixas criminais

| | |
|---|---|
| **Pergunta** | a segurança percebida do entorno pesa no preço, na ocupação e na saída do mercado? |
| **Órgão** | NYPD, via NYC Open Data (`qgea-i56i` Historic, `5uac-w243` Current YTD); delegacias `y76i-bdw7` (NYC DCP) |
| **Granularidade** | delegacia (agregado no servidor por `addr_pct_cd` × `law_cat_cd`) |
| **Safra** | 12 meses antes de cada snapshot, pela data do registro (`rpt_dt`): 2018-07-08..2019-07-07 e 2025-06-14..2026-06-13 |
| **Volume** | **458.158** queixas na janela de 2019 (140.916 FELONY) · **570.820** na atual (184.147 FELONY) |
| **Licença** | NYC Open Data Terms of Use |
| **Features** | `crime_graves_km2` (FELONY por km² da delegacia) · `crime_total_km2` (FELONY + MISDEMEANOR + VIOLATION por km²) |

A janela atual emenda dois datasets: o histórico vai até 2025-12-31 e o do ano corrente
cobre 2026 até o fim do 2º trimestre. O corte é pela data do **registro** porque é assim
que os dois se particionam. A **116ª delegacia**, criada em dez/2023 a partir da 105ª, é
fundida à 105ª na safra 2019 (queixas e área somadas).

!!! warning "Crime registrado ≠ crime ocorrido"
    A queixa depende de a vítima procurar a polícia e de a polícia registrar. As duas
    coisas variam por bairro, por tipo de crime e por relação da comunidade com a polícia.
    Densidade por km² também favorece áreas de muito fluxo e pouca moradia: a maior
    densidade da cidade, nas duas safras e nas duas features, é a da 14ª delegacia
    (Midtown South — Times Square, Penn Station). A feature mede **registro**; o texto do
    site diz isso ([Ética e LGPD](10-etica-e-lgpd.md)).

### 3.3 311 — chamados de barulho

| | |
|---|---|
| **Pergunta** | onde há vida noturna — que atrai hóspede — e onde há vizinho disposto a reclamar, inclusive do Airbnb ao lado? |
| **Órgão** | NYC 311, via NYC Open Data (`76ig-c548` 2010–2019; `erm2-nwe9` 2020 em diante) |
| **Granularidade** | ZIP do chamado → MODZCTA (agregado no servidor por `incident_zip`) |
| **Safra** | mesmas janelas do NYPD, por `created_date` |
| **Filtro** | `complaint_type like 'Noise%'` (residencial, rua/calçada, comercial, veículo, helicóptero, parque, templo e o "Noise" do DEP) |
| **Volume** | **460.880** chamados em 2019 · **803.259** no atual (+74%); ~1% cai em ZIP fora de qualquer MODZCTA e fica de fora (contado no manifesto) |
| **Licença** | NYC Open Data Terms of Use |
| **Feature** | `ruido_311_km2` — chamados por km² do MODZCTA |

!!! note "Chamado mede disposição a reclamar"
    Um bairro que reclama pouco não é necessariamente silencioso. O aumento de 74% entre
    as janelas pode vir de mais barulho, de mais uso do 311 ou de mudança na forma de
    registrar — este dado não separa as três coisas. Comparações entre safras devem usar
    posição relativa (ranking), não o nível.

### 3.4 Zillow — ZORI (Zillow Observed Rent Index)

| | |
|---|---|
| **Pergunta** | o preço do Airbnb acompanha o aluguel de longo prazo? onde o aluguel mais subiu, a conversão para aluguel tradicional ficou mais atraente? |
| **Órgão** | Zillow Research |
| **Granularidade** | ZIP → MODZCTA (o do próprio código ou, na falta, a média dos ZCTAs membros) |
| **Safra** | 2019-07 e 2026-06 (série de 2015-01 a 2026-08) |
| **Licença** | uso público gratuito com atribuição clara ao Zillow |
| **Features** | `zori` (aluguel anunciado típico, US$/mês nominais) · `zori_var_pct` (variação 2019→2026, só contexto) |

É um índice de aluguel repetido, ponderado pelo estoque de imóveis de aluguel, calculado
sobre os aluguéis **anunciados** entre os percentis 35 e 65 e suavizado. Não é aluguel pago
(o ACS B25064 mede isso, com defasagem).

!!! warning "O ZORI não cobre a cidade inteira — sobretudo em 2019"
    Dos 149 ZIPs de NYC no arquivo, só **81 têm valor em 2019-07** e 140 em 2026-06. Nas
    células, a cobertura é de **30,9% em 2019** e 77,4% no atual. Por distrito, em 2019:
    Manhattan 88,5%, Brooklyn 60,6%, Bronx 20,3%, Queens 18,4%, **Staten Island 0%**. A
    ausência não é aleatória: faltam as áreas com pouco anúncio de aluguel no Zillow.

### 3.5 MTA — estações do metrô

| | |
|---|---|
| **Pergunta** | quanto vale, dentro de um mesmo bairro, estar perto do metrô? |
| **Órgão** | Metropolitan Transportation Authority, via data.ny.gov (`39hk-dx4f`) |
| **Granularidade** | estação: 496 plataformas, 445 complexos, 24 linhas (inclui a Staten Island Railway) |
| **Safra** | a de 2026, aplicada às duas |
| **Licença** | Open NY Terms of Use, com atribuição à MTA |
| **Features** | `metro_dist_m` (estação mais próxima) · `metro_n_800m` (complexos distintos a até 800 m, ~10 min a pé) · `metro_linhas_800m` (linhas diurnas distintas a até 800 m) |

Conta **complexos** e **linhas**, não linhas da tabela: Times Square tem várias
plataformas, e contar registro inflaria os grandes entroncamentos. A tabela é a de 2026,
aplicada também a 2019; a leva mais recente de estações novas que conhecemos é a da
Second Avenue, aberta em 2017, então o efeito esperado sobre as distâncias é nulo ou
desprezível — mas a tabela não traz data de inauguração para provar isso.

### 3.6 OpenStreetMap — pontos de interesse

| | |
|---|---|
| **Pergunta** | o que há a pé do anúncio — e quanta hotelaria formal compete com ele? |
| **Órgão** | colaboradores do OpenStreetMap, via Overpass API |
| **Granularidade** | ponto (nó) ou centro de área (way/relation) |
| **Safra** | a de 2026-09 — **aplicada também a 2019** (anacronismo, §6) |
| **Licença** | ODbL 1.0 — atribuição obrigatória |
| **Features** | contagem no anel k = 1: `poi_restaurantes_k1` (restaurant + fast_food) · `poi_bares_k1` (bar + pub + nightclub) · `poi_cafes_k1` · `poi_atracoes_k1` (attraction + museum + gallery + viewpoint) · `poi_hoteis_k1` (hotel + hostel + guest_house) · `poi_parques_k1` (leisure=park) |

Uma consulta por grupo, no envelope de NYC alargado em ~1 km — sem a folga, a célula da
divisa com Nassau e Westchester perderia os POIs do outro lado.

| grupo | elementos | composição |
|---|---:|---|
| restaurantes | 15.540 | restaurant 9.858 · fast_food 5.682 |
| cafés | 2.958 | cafe |
| bares | 2.137 | bar 1.586 · pub 430 · nightclub 121 |
| atrações | 1.103 | gallery 362 · attraction 285 · viewpoint 250 · museum 206 |
| hotéis | 859 | hotel 814 · guest_house 24 · hostel 21 |
| parques | 3.134 | park (2.745 como área, 230 como ponto, 159 como relação) |

Base OSM de todos os grupos: **2026-09-19** (servidor principal). Numa primeira coleta, o
grupo "bares" caiu no espelho, que servia a base de 2026-06-01 (43 bares a menos); ele foi
rebuscado no servidor principal, e agora a coleta registra a base de cada grupo e acusa
quando elas divergem (`bases_coerentes` no manifesto).

!!! note "Limitações do OSM"
    - **Colaborativo e desigual:** a completude do mapeamento varia de bairro para
      bairro, e com este dado não há como separar "mais comércio" de "mais mapeamento".
      Densidade de POI mede também densidade de mapeador.
    - **Parque grande conta 1:** o Central Park vale o mesmo que uma praça. A feature
      responde "há parque perto", não "quanto parque".
    - **Duplicidade rara:** um restaurante mapeado como nó e como prédio conta duas vezes.

### 3.7 Marcos da cidade

| | |
|---|---|
| **Pergunta** | quanto pesa a distância ao centro turístico e ao aeroporto? |
| **Fonte** | curadoria em `src/airbnb/external/marcos.py`, com as coordenadas da infobox da Wikipedia, conferidas na API dela a cada coleta (o desvio em metros vai para `marcos.json`) |
| **Features** | `dist_centro_km` (Times Square) · `dist_aeroporto_km` (o mais próximo entre JFK e LGA) · `dist_marco_km` (o mais próximo entre Times Square, Empire State, Central Park, One WTC e Brooklyn Bridge) |

Distâncias em linha reta no plano UTM 18N (EPSG:32618), que difere da geodésica em menos
de 0,1% em NYC (há teste). Linha reta não é tempo de viagem: um anúncio em Long Island City
está "longe" de Times Square em km e perto em minutos de metrô — a feature do metrô cobre
essa parte.

### 3.8 CPI-U New York-Newark-Jersey City — o deflator

| | |
|---|---|
| **Pergunta** | quanto vale, em dólar de junho de 2026, um preço de julho de 2019? (invariante 8, [ADR 0005](adr/0005-comparabilidade-2019-2026.md)) |
| **Órgão** | U.S. Bureau of Labor Statistics, série `CUURS12ASA0` (mensal, sem ajuste sazonal) |
| **Safra** | 2017-01 a 2026-08 (115 meses) |
| **Licença** | domínio público |
| **Saída** | `data/processed/cpi_ny.parquet` (`mes`, `indice`) e `fator_cpi(de, para)` |

**Fator 2019-07 → 2026-06 = 1,293067** (índice 278,817 → 360,529): o preço de 2019
multiplicado por 1,293 está em dólar do mês do snapshot atual. A série foi baixada da API
do BLS e **conferida** contra a mesma série no FRED (onde o código é `CUURA101SA0`, o de
antes da revisão de áreas de 2018): os 115 meses são idênticos.

!!! note "Um mês que não existe"
    **Outubro de 2025 não tem índice**: o BLS não coletou preços durante a paralisação do
    governo federal. `fator_cpi` recusa esse mês em vez de interpolar. Para os valores do
    ACS, publicados "em dólares de 2019/2024", o fator usa a **média anual** do índice
    (`fator_cpi("2024", "2019-07")`).

### 3.9 Office of Special Enforcement — registros da Local Law 18

| | |
|---|---|
| **Pergunta** | quantos anfitriões estão registrados e, portanto, podem legalmente oferecer menos de 30 noites? onde? |
| **Órgão** | NYC Mayor's Office of Special Enforcement (OSE) |
| **O que existe** | **nenhum dataset no NYC Open Data**. Existem os relatórios anuais que a LL18 obriga a OSE a publicar, em XLSX, na página *Data & Reports* da OSE (FY23 a FY26; o ano fiscal vai de 1/jul a 30/jun) |
| **Granularidade** | distrito do Conselho Municipal (51) |
| **Licença** | publicação oficial da Prefeitura; limites dos distritos: NYC DCP via NYC Open Data (`872g-cjhh`) |
| **Coluna** | `ll18_registros_km2_atual` — registros ativos em 2026-06-30 por km² do distrito. **Contexto e mapa, não feature de modelo** |

Registros ativos no fim de cada ano fiscal: **105** (FY23, jun/2023) · **2.290** (FY24) ·
**2.952** (FY25) · **3.338** (FY26, jun/2026); **3.522** estiveram ativos em algum momento
do FY26. Para comparação, o snapshot de 2026 tem 30.555 anúncios. Também foram baixados,
e só registrados no manifesto, os relatórios de fiscalização da Local Law 87 (2018, 2019,
2024, 2025), com queixas e inspeções de *illegal hotel* por distrito — o candidato natural
para medir a pressão de fiscalização **antes** da LL18.

## 4. Cobertura nas células

Percentual das 7.219 células com valor não nulo (`_celulas.json` →
`cobertura_pct_nao_nulo`). Distâncias e contagens (metrô, OSM, marcos) cobrem 100% por
construção.

| feature | fonte | 2019 | atual | por que falta |
|---|---|---:|---:|---|
| `acs_renda_mediana` | ACS | 92,0% | 86,3% | tract sem moradores ou com amostra insuficiente |
| `acs_aluguel_mediano` | ACS | 91,9% | 84,9% | idem; poucos domicílios alugados |
| `acs_valor_imovel` | ACS | 86,5% | 80,4% | tract com poucos imóveis ocupados pelo dono — no Bronx, 39% dos tracts de 2020–2024 não têm valor |
| `acs_pop_densidade` | ACS | 100% | 100% | — |
| `acs_pct_alugado` | ACS | 94,2% | 89,3% | tract sem domicílio ocupado |
| `acs_pct_vago` | ACS | 94,3% | 89,6% | tract sem unidade habitacional |
| `crime_graves_km2`, `crime_total_km2` | NYPD | 100% | 100% | — |
| `ruido_311_km2` | 311 | 99,1% | 99,1% | célula em MODZCTA sem chamado registrado |
| `zori` | Zillow | **30,9%** | 77,4% | ZIP sem ZORI (§3.4) |
| `zori_var_pct` | Zillow | 30,9% (2019→2026) | | exige as duas pontas |
| `metro_*`, `poi_*`, `dist_*` | MTA, OSM, marcos | 100% | 100% | — |
| `ll18_registros_km2_atual` | OSE | — | 100% | — |

A falta **não é aleatória**: concentra-se em parques, aeroportos, cemitérios e, no ZORI, nas
áreas de mercado de aluguel menos ativo. O LightGBM trata o ausente como informação, e o
[dicionário](dicionario-dados.md) registra cada feature.

## 5. Linha do tempo regulatória

| data | evento | fonte |
|---|---|---|
| 2010 | lei estadual (Laws of New York 2010, cap. 225) altera a Multiple Dwelling Law: locação por menos de 30 dias em prédio residencial classe A, sem o morador permanente, passa a ser ilegal | [texto da lei (nyc.gov)](https://www.nyc.gov/assets/buildings/local_laws/NYS_chapter_225.pdf) |
| 2019 | a OSE recebe 3.871 queixas de aluguel ilegal de curta temporada (*illegal hotel*), em mais de 2.500 endereços | relatório LL87 de 2019 |
| **2019-07-08** | **scrape do snapshot de 2019** (Kaggle) | `config.SNAPSHOT_2019` |
| 2022-01-09 | Local Law 18 de 2022 adotada (*Short-Term Rental Registration Law*) | relatório FY26 da OSE, seção *History* |
| 2023-03-06 | a OSE começa a aceitar pedidos de registro | idem |
| 2023-06-30 | 105 registros ativos (fim do FY23) | relatório FY23 |
| **2023-09-05** | as plataformas passam a ter de verificar o registro antes de processar a reserva — início da fiscalização | relatório FY26; `config.LL18_VIGENCIA` |
| 2024-06-30 | 2.290 registros ativos | relatório FY24 |
| 2025 | 2.036 queixas de aluguel ilegal de curta temporada, em mais de 1.537 endereços | relatório LL87 de 2025 |
| 2025-06-30 | 2.952 registros ativos | relatório FY25 |
| **2026-06-14** | **scrape do snapshot atual** (Inside Airbnb) — dentro do FY26 | `config.SNAPSHOT_ATUAL` |
| 2026-06-30 | 3.338 registros ativos; primeiras revogações (17 revogados e 15 em processo no FY26) | relatório FY26 |

Relatórios: [OSE — Data & Reports](https://www.nyc.gov/site/specialenforcement/about/data-reports.page).

## 6. Anacronismos e vieses declarados

| feature | o que está sendo assumido | consequência |
|---|---|---|
| POIs do OSM em 2019 | que o comércio de 2026 descreve o de 2019 | restaurantes que fecharam na pandemia só contam em 2019 se ainda estiverem mapeados; o efeito dos POIs em 2019 tende a ser subestimado |
| metrô em 2019 | a rede de 2026 | sem efeito nas distâncias (nenhuma estação nova no período) |
| ACS 2015–2019 para jul/2019 | o meio do período (2017) descreve 2019 | defasagem de ~2 anos; o mesmo vale para 2020–2024 em 2026 |
| crime e 311 | registro mede ocorrência | mede também propensão a registrar e a reclamar |
| crime por delegacia | homogeneidade dentro da delegacia | 77/78 polígonos: a feature não distingue quarteirões |
| ZORI | aluguel anunciado mede aluguel de mercado | cobre mal as áreas com pouco anúncio; 2019 cobre 30,9% das células |
| OSM | mapeamento uniforme | mais POIs onde há mais mapeadores |

## 7. Atribuições

Texto de crédito exigido ou recomendado por cada licença. O site reproduz este bloco no
rodapé.

| fonte | crédito |
|---|---|
| OpenStreetMap | **© colaboradores do OpenStreetMap** (*© OpenStreetMap contributors*), dados sob a Open Database License — [openstreetmap.org/copyright](https://www.openstreetmap.org/copyright). Obrigatório (ODbL 1.0) |
| Zillow | **Zillow Observed Rent Index (ZORI), Zillow Research** — [zillow.com/research/data](https://www.zillow.com/research/data/). Atribuição clara exigida pelos termos |
| Census | Fonte: U.S. Census Bureau, American Community Survey 5-year estimates (2015–2019 e 2020–2024) e Cartographic Boundary Files. Este produto usa dados do Census Bureau, mas não é endossado nem certificado por ele |
| BLS | U.S. Bureau of Labor Statistics, Consumer Price Index for All Urban Consumers (CPI-U), New York-Newark-Jersey City, série CUURS12ASA0 |
| NYPD | NYPD Complaint Data Historic e Current (Year To Date), via NYC Open Data. Agregado por delegacia pelo projeto |
| 311 | NYC 311 Service Requests (2010–2019 e 2020–presente), via NYC Open Data. Filtrado (barulho) e agregado por ZIP pelo projeto |
| NYC DCP / DOHMH | limites de delegacias e de distritos do Conselho (NYC Department of City Planning) e MODZCTA (NYC Department of Health and Mental Hygiene), via NYC Open Data |
| MTA | Estações: Metropolitan Transportation Authority, via data.ny.gov |
| OSE | NYC Mayor's Office of Special Enforcement, relatórios anuais da Local Law 18 |
| Wikipedia | coordenadas dos marcos conferidas na Wikipedia (CC BY-SA 4.0) |

Os termos do NYC Open Data não restringem o uso, mas permitem à Prefeitura exigir que a
republicação identifique **fonte, versão e modificações** — por isso cada crédito acima diz
como o dado foi agregado, e o manifesto guarda a data de acesso.

## 8. Reproduzir

```powershell
.\tasks.ps1 externos     # baixa o que falta e grava o manifesto (~5 min na primeira vez)
.\tasks.ps1 celulas      # 7.219 células -> data/processed/celulas_r9.parquet
```

As fontes são **dado vivo**: o NYPD e o 311 recebem correções retroativas, o ZORI é
revisado todo mês e o OSM muda a cada minuto. Uma nova coleta pode dar hashes diferentes
dos do manifesto — o que o manifesto garante é saber **qual** versão gerou cada número
publicado. A segunda coleta de 2026-09-19 reproduziu byte a byte o ACS, o NYPD e o 311.
