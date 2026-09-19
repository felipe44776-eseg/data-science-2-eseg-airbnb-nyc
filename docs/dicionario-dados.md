# Dicionário de dados

!!! note "Gerado, não editado"
    Este arquivo é a saída de `python -m airbnb.schema --escrever`. A fonte é
    `src/airbnb/schema.py` (invariante 1). Editar aqui é perder a edição na próxima geração.

**Pessoal** = nunca sai para site nem relatório (invariante 9). Colunas pessoais que a
análise precisa (ids, título) ficam na silver com a flag; as demais são descartadas na limpeza.

## 1. Contrato da silver (`data/processed/`)

| parquet | linhas | conteúdo |
|---|---|---|
| `anuncios_2019.parquet` | Kaggle limpo | 2019, sem `host_name` |
| `anuncios_2026.parquet` | detalhado limpo | 2026, sem colunas pessoais/texto livre (exceto `name`) |
| `anuncios_resumo.parquet` | os dois empilhados | colunas comuns + `snapshot` |

| coluna | dtype | em | domínio | pessoal | descrição | origem |
|---|---|---|---|---|---|---|
| `snapshot` | category | 2019, 2026, resumo | `2019`, `2026`; sem nulo |  | Snapshot de origem da linha: "2019" (Kaggle, scrape de 2019-07-08) ou "2026" (Inside Airbnb, 2026-06-14). | derivada (constante por arquivo; config.ROTULO_*) |
| `id` | int64 | 2019, 2026, resumo | [1, ]; sem nulo | **sim** | Identificador do anúncio no Airbnb. Único por snapshot (conferido). Nunca publicado. | origem: `id` |
| `last_scraped` | datetime64[ns] | 2026 | sem nulo |  | Data em que o anúncio foi coletado. Quatro datas entre 14 e 23/06/2026: o scrape da cidade (14–15) e a recoleta dos anúncios vistos no scrape anterior (22–23). | origem: `last_scraped` (detalhado) |
| `source` | category | 2026 | `city scrape`, `previous scrape`; sem nulo |  | Como o anúncio entrou no scrape: `city scrape` (achado na busca da cidade) ou `previous scrape` (existia no scrape anterior e foi recoletado pelo id). | origem: `source` (detalhado) |
| `name` | str | 2019, 2026 | — | **sim** | Título do anúncio, escrito pelo anfitrião. Texto livre: usado só em análise (ex.: duplicatas), nunca publicado. | origem: `name` |
| `host_id` | int64 | 2019, 2026, resumo | [1, ]; sem nulo | **sim** | Identificador do anfitrião. Único identificador confiável do anfitrião (o nome não é — ver Q3). Nunca publicado. | origem: `host_id` |
| `hosts_time_as_user_years` | float64 | 2026 | [0, ] |  | Anos completos desde que o anfitrião criou a conta no Airbnb (campo novo do Inside Airbnb; substitui `host_since`, que veio 100% vazio). | origem: detalhado |
| `hosts_time_as_user_months` | float64 | 2026 | [0, 11] |  | Meses restantes (0–11) além de `hosts_time_as_user_years`. | origem: detalhado |
| `hosts_time_as_host_years` | float64 | 2026 | [0, ] |  | Anos completos desde que a conta passou a anunciar. | origem: detalhado |
| `hosts_time_as_host_months` | float64 | 2026 | [0, 11] |  | Meses restantes (0–11) além de `hosts_time_as_host_years`. | origem: detalhado |
| `host_is_superhost` | boolean | 2026 | — |  | Selo de Superhost (t/f da origem convertido em booleano; nulo nos 349 anúncios sem perfil de anfitrião). | origem: `host_is_superhost` |
| `host_listings_count` | Int64 | 2026 | [0, ] |  | Anúncios do anfitrião segundo o perfil no Airbnb (inclui outras cidades). Difere de `calculated_host_listings_count` em 33% dos anúncios. | origem: detalhado |
| `host_has_profile_pic` | boolean | 2026 | — |  | Anfitrião tem foto de perfil (só o indicador; a foto em si é descartada). | origem: detalhado |
| `host_identity_verified` | boolean | 2026 | — |  | Anfitrião com identidade verificada pelo Airbnb. | origem: detalhado |
| `neighbourhood_group` | category | 2019, resumo | `Manhattan`, `Brooklyn`, `Queens`, `Bronx`, `Staten Island`; sem nulo |  | Distrito (borough) de Nova York. Em 2026 vem de `neighbourhood_group_cleansed` (atribuído pelo Inside Airbnb a partir da coordenada). | origem: `neighbourhood_group` (Kaggle); `neighbourhood_group_cleansed` (2026) |
| `neighbourhood` | str | 2019, resumo | sem nulo |  | Bairro (Neighbourhood Tabulation Area do Inside Airbnb). Os 221 bairros de 2019 existem todos no neighbourhoods.geojson de 2026. | origem: `neighbourhood` (Kaggle); `neighbourhood_cleansed` (2026) |
| `neighbourhood_group_cleansed` | category | 2026 | `Manhattan`, `Brooklyn`, `Queens`, `Bronx`, `Staten Island`; sem nulo |  | Distrito (borough) atribuído pelo Inside Airbnb pela coordenada. Vira `neighbourhood_group` em anuncios_resumo. | origem: detalhado |
| `neighbourhood_cleansed` | str | 2026 | sem nulo |  | Bairro atribuído pelo Inside Airbnb pela coordenada (o campo `neighbourhood` do detalhado veio 100% vazio). Vira `neighbourhood` em anuncios_resumo. | origem: detalhado |
| `latitude` | float64 | 2019, 2026, resumo | [40.4774, 40.9176]; sem nulo |  | Latitude publicada. O Airbnb desloca o ponto em até ~150 m (0–450 pés) para proteger o endereço: a unidade de análise é a célula H3, não o ponto (ADR 0001). | origem: `latitude` |
| `longitude` | float64 | 2019, 2026, resumo | [-74.2591, -73.7004]; sem nulo |  | Longitude publicada (mesmo deslocamento da latitude). | origem: `longitude` |
| `property_type` | str | 2026 | sem nulo |  | Tipo de imóvel como o anfitrião declarou (69 valores em 2026). Agrupado em `tipo_imovel_grupo`. | origem: detalhado |
| `room_type` | category | 2019, 2026, resumo | `Entire home/apt`, `Private room`, `Shared room`, `Hotel room`; sem nulo |  | Tipo de acomodação. `Hotel room` só existe em 2026 (520 anúncios); em 2019 havia três categorias. | origem: `room_type` |
| `accommodates` | int64 | 2026 | [1, ]; sem nulo |  | Número máximo de hóspedes. | origem: detalhado |
| `bathrooms` | float64 | 2026 | [0, ] |  | Número de banheiros como o Inside Airbnb extraiu (33% nulo). Ver `banheiros`, que completa pelo texto. | origem: detalhado |
| `bathrooms_text` | str | 2026 | — |  | Banheiros em texto ("1.5 shared baths", "Half-bath"...). Fonte de `banheiros` e `banheiro_compartilhado`. | origem: detalhado |
| `bedrooms` | float64 | 2026 | [0, ] |  | Número de quartos (36% nulo). | origem: detalhado |
| `beds` | float64 | 2026 | [0, ] |  | Número de camas (31% nulo). | origem: detalhado |
| `amenities` | str | 2026 | sem nulo |  | Lista JSON de comodidades, grafia livre do Airbnb (6.179 itens distintos). Fonte de `n_amenidades` e das flags `amen_*`. | origem: detalhado |
| `preco` | float64 | 2019, 2026, resumo | [0, ] |  | Preço por noite em US$. 2019: diária anunciada. 2026: cotação de uma estadia de N noites (N = `preco_cotacao_noites`, em regra o mínimo do anúncio) dividida por N, JÁ COM desconto semanal/mensal — não é a mesma grandeza de 2019 (ADR 0005). Nulo quando não houve cotação. | origem: `price` (Kaggle: inteiro; 2026: texto "$1,234.00") |
| `preco_valido` | bool | 2019, 2026, resumo | sem nulo |  | True quando o preço entra nas análises de preço: não caiu em nenhuma regra de escopo `preco` da quarentena (ausente, zero, cotação > 31 noites, < US$ 10, > US$ 10.000). | derivada: regras P01–P05 da limpeza |
| `preco_cotacao_noites` | Int64 | 2026 | [1, ] |  | Noites da estadia cotada (checkout − checkin da cotação). Igual ao mínimo de noites em 96,6% das cotações; mediana 30. | derivada: `price_quote_checkout_date` − `price_quote_checkin_date` |
| `preco_cheio` | float64 | 2026 | [0, ] |  | Diária SEM desconto: preço cheio do período cotado (total + \|descontos\|; coincide até US$ 1 com o item "Average monthly price" em 99,8% das cotações que o têm) ÷ noites da cotação. Alternativa de robustez a `preco` na comparação com 2019. Mesma ressalva de `preco` para cotações > 31 noites. | derivada: `price_quote_raw` (JSON) e `price_quote_total_price` |
| `desconto_pct` | float64 | 2026 | [0, 1] |  | Fração do preço cheio do período abatida por descontos (mensal, semanal, oferta especial, antecipação): Σ\|itens negativos\| ÷ preço cheio. 0 quando a cotação não tem desconto; nulo sem cotação. | derivada: `price_quote_raw` (JSON) |
| `price_quote_checkin_date` | datetime64[ns] | 2026 | — |  | Início da estadia cotada pelo Inside Airbnb (primeira data livre; mediana 18 dias após o scrape). | origem: detalhado |
| `price_quote_checkout_date` | datetime64[ns] | 2026 | — |  | Fim da estadia cotada. | origem: detalhado |
| `price_quote_total_price` | float64 | 2026 | [0, ] |  | Total cotado após descontos (sem taxa de limpeza e de serviço; inclui resort fee quando houver). Em cotações > 31 noites é um total MENSAL, não do período. | origem: detalhado |
| `minimum_nights` | int64 | 2019, 2026, resumo | [1, ]; sem nulo |  | Mínimo de noites por reserva. ≥ 30 é o limiar da Local Law 18 (ver `min30`). | origem: `minimum_nights` |
| `min30` | bool | 2019, 2026, resumo | sem nulo |  | Mínimo de noites ≥ 30 (config.NOITES_CURTA_TEMPORADA): fora do alcance do registro da Local Law 18. 9,2% em 2019, 81,7% em 2026. | derivada: `minimum_nights` ≥ 30 |
| `maximum_nights` | Int64 | 2026 | [1, ] |  | Máximo de noites por reserva. 2.147.483.647 (2³¹−1) é sentinela de "sem máximo". | origem: detalhado |
| `minimum_minimum_nights` | float64 | 2026 | [0, ] |  | Menor mínimo de noites no calendário dos próximos 365 dias. | origem: detalhado |
| `maximum_minimum_nights` | float64 | 2026 | [0, ] |  | Maior mínimo de noites no calendário dos próximos 365 dias. | origem: detalhado |
| `minimum_maximum_nights` | float64 | 2026 | [0, ] |  | Menor máximo de noites no calendário. | origem: detalhado |
| `maximum_maximum_nights` | float64 | 2026 | [0, ] |  | Maior máximo de noites no calendário. | origem: detalhado |
| `minimum_nights_avg_ntm` | float64 | 2026 | [0, ] |  | Média do mínimo de noites nos próximos 365 dias. | origem: detalhado |
| `maximum_nights_avg_ntm` | float64 | 2026 | [0, ] |  | Média do máximo de noites nos próximos 365 dias. | origem: detalhado |
| `has_availability` | boolean | 2026 | — |  | Anúncio aceita reservas (t/f convertido; `f` em 349 anúncios, 348 deles sem perfil de anfitrião). | origem: detalhado |
| `availability_30` | int64 | 2026 | [0, 30]; sem nulo |  | Dias livres nos próximos 30. | origem: detalhado |
| `availability_60` | int64 | 2026 | [0, 60]; sem nulo |  | Dias livres nos próximos 60. | origem: detalhado |
| `availability_90` | int64 | 2026 | [0, 90]; sem nulo |  | Dias livres nos próximos 90. | origem: detalhado |
| `availability_365` | int64 | 2019, 2026, resumo | [0, 365]; sem nulo |  | Dias livres nos próximos 365. NÃO é ocupação: dia indisponível inclui dia bloqueado pelo anfitrião (invariante 7). | origem: `availability_365` |
| `availability_eoy` | int64 | 2026 | [0, 366]; sem nulo |  | Dias livres até o fim do ano corrente. | origem: detalhado |
| `calendar_last_scraped` | datetime64[ns] | 2026 | sem nulo |  | Data da coleta do calendário. | origem: detalhado |
| `number_of_reviews` | int64 | 2019, 2026, resumo | [0, ]; sem nulo |  | Total de avaliações do anúncio desde a criação. | origem: `number_of_reviews` |
| `number_of_reviews_ltm` | int64 | 2026 | [0, ]; sem nulo |  | Avaliações nos últimos 12 meses (base da ocupação estimada do Inside Airbnb). | origem: detalhado |
| `number_of_reviews_l30d` | int64 | 2026 | [0, ]; sem nulo |  | Avaliações nos últimos 30 dias. | origem: detalhado |
| `number_of_reviews_ly` | int64 | 2026 | [0, ]; sem nulo |  | Avaliações no ano-calendário anterior. | origem: detalhado |
| `first_review` | datetime64[ns] | 2026 | — |  | Data da primeira avaliação (nula ⟺ sem avaliação). | origem: detalhado |
| `last_review` | datetime64[ns] | 2019, 2026, resumo | — |  | Data da avaliação mais recente (nula ⟺ sem avaliação). | origem: `last_review` |
| `reviews_per_month` | float64 | 2019, 2026, resumo | [0, ] |  | Avaliações por mês do ANÚNCIO: total ÷ meses desde a primeira avaliação, com piso de 1 mês (por isso nunca excede `number_of_reviews`). Nula ⟺ sem avaliação. Ver Q6. | origem: `reviews_per_month` |
| `review_scores_rating` | float64 | 2026 | [0, 5] |  | Nota média (geral), escala 0–5. | origem: detalhado |
| `review_scores_accuracy` | float64 | 2026 | [0, 5] |  | Nota média (exatidão do anúncio), escala 0–5. | origem: detalhado |
| `review_scores_cleanliness` | float64 | 2026 | [0, 5] |  | Nota média (limpeza), escala 0–5. | origem: detalhado |
| `review_scores_checkin` | float64 | 2026 | [0, 5] |  | Nota média (check-in), escala 0–5. | origem: detalhado |
| `review_scores_communication` | float64 | 2026 | [0, 5] |  | Nota média (comunicação), escala 0–5. | origem: detalhado |
| `review_scores_location` | float64 | 2026 | [0, 5] |  | Nota média (localização), escala 0–5. | origem: detalhado |
| `review_scores_value` | float64 | 2026 | [0, 5] |  | Nota média (custo-benefício), escala 0–5. | origem: detalhado |
| `estimated_occupancy_l365d` | int64 | 2026 | [0, 365]; sem nulo |  | Noites ocupadas estimadas pelo Inside Airbnb nos últimos 365 dias: min(avaliações_ltm ÷ 0,5 × max(6,4; mínimo de noites); 255). Reproduzida em 99,99% dos anúncios (docs/02). | origem: detalhado |
| `estimated_revenue_l365d` | float64 | 2026 | [0, ] |  | Receita estimada = `estimated_occupancy_l365d` × `price` (idêntica em 100% dos anúncios com preço). Herda o problema das cotações > 31 noites. | origem: detalhado |
| `ocupacao_modelo` | float64 | 2019, 2026, resumo | [0, 0.7]; sem nulo |  | Fração do ano ocupada pelo modelo de avaliações do Inside Airbnb aplicado IGUAL aos dois snapshots: avaliações/mês × 12 ÷ 0,5 × max(6,4; mínimo de noites) ÷ 365, teto 0,70; zero se a última avaliação tem mais de 365 dias (ou não existe). É a ocupação comparável 2019 × 2026 (invariante 7). | derivada: `reviews_per_month`, `minimum_nights`, `last_review` |
| `calculated_host_listings_count` | int64 | 2019, 2026, resumo | [1, ]; sem nulo |  | Anúncios do mesmo anfitrião NESTE scrape de NYC. | origem: `calculated_host_listings_count` |
| `calculated_host_listings_count_entire_homes` | int64 | 2026 | [0, ]; sem nulo |  | Idem, só imóveis inteiros. | origem: detalhado |
| `calculated_host_listings_count_private_rooms` | int64 | 2026 | [0, ]; sem nulo |  | Idem, só quartos privativos. | origem: detalhado |
| `calculated_host_listings_count_shared_rooms` | int64 | 2026 | [0, ]; sem nulo |  | Idem, só quartos compartilhados. | origem: detalhado |
| `host_multi` | bool | 2019, 2026, resumo | sem nulo |  | Anfitrião com mais de um anúncio no scrape (`calculated_host_listings_count` > 1). | derivada |
| `license` | str | 2026 | — |  | Registro na OSE (Local Law 18) como declarado: "OSE-STRREG-…", "Exempt" ou vazio. Grafia de caixa variável. | origem: `license` (detalhado) |
| `licenca_status` | category | 2026 | `registrada`, `isenta`, `ausente`, `outra`; sem nulo |  | `registrada` (começa com OSE-STRREG, sem distinguir caixa), `isenta` (Exempt), `ausente` (vazio) ou `outra`. | derivada: `license` |
| `h3_r9` | str | 2019, 2026, resumo | sem nulo |  | Célula H3 resolução 9 (~0,105 km², aresta ~174 m) — unidade das features de localização (ADR 0001). | derivada: h3.latlng_to_cell(lat, lon, 9) |
| `h3_r8` | str | 2019, 2026, resumo | sem nulo |  | Célula H3 resolução 8 (~0,74 km²) — unidade dos mapas. | derivada: h3.latlng_to_cell(lat, lon, 8) |
| `h3_r6` | str | 2019, 2026, resumo | sem nulo |  | Célula H3 resolução 6 (~36 km²) — blocos da validação cruzada espacial (ADR 0002). | derivada: h3.latlng_to_cell(lat, lon, 6) |
| `dias_desde_ultima_avaliacao` | Int64 | 2019, 2026, resumo | [0, ] |  | Dias entre a última avaliação e a data do scrape (2019: config.SNAPSHOT_2019; 2026: `last_scraped`). Nulo sem avaliação. | derivada |
| `meses_desde_primeira_avaliacao` | float64 | 2026 | [0, ] |  | Meses (dias ÷ 30,4375) entre a primeira avaliação e `last_scraped`. Nulo sem avaliação. | derivada: `first_review`, `last_scraped` |
| `presente_2026` | bool | 2019 | sem nulo |  | O id de 2019 ainda aparece no snapshot de 2026 (resumo ou detalhado). Base da análise de sobrevivência. | derivada: cruzamento de ids |
| `banheiros` | float64 | 2026 | [0, ] |  | Número de banheiros: `bathrooms` quando existe; senão o número em `bathrooms_text`; "half-bath" = 0,5. | derivada: `bathrooms`, `bathrooms_text` |
| `banheiro_compartilhado` | boolean | 2026 | — |  | Banheiro compartilhado ("shared" no texto). Nulo quando não há texto. | derivada: `bathrooms_text` |
| `n_amenidades` | int64 | 2026 | [0, ]; sem nulo |  | Quantidade de itens na lista de comodidades. | derivada: `amenities` |
| `amen_wifi` | bool | 2026 | sem nulo |  | Comodidade: Wi-Fi (inclui 'Fast wifi – N Mbps' e 'Pocket wifi'). Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_cozinha` | bool | 2026 | sem nulo |  | Comodidade: cozinha ou kitchenette (não conta cozinha externa nem eletrodoméstico KitchenAid). Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_ar_condicionado` | bool | 2026 | sem nulo |  | Comodidade: ar-condicionado: central, de janela, split ou portátil. Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_aquecimento` | bool | 2026 | sem nulo |  | Comodidade: aquecimento: central, radiante, split ou aquecedor portátil. Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_lavadora` | bool | 2026 | sem nulo |  | Comodidade: lavadora de roupa, na unidade ou no prédio (não conta lava-louças). Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_secadora` | bool | 2026 | sem nulo |  | Comodidade: secadora de roupa (não conta secador de cabelo). Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_lava_loucas` | bool | 2026 | sem nulo |  | Comodidade: lava-louças. Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_elevador` | bool | 2026 | sem nulo |  | Comodidade: elevador. Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_academia` | bool | 2026 | sem nulo |  | Comodidade: academia no prédio ou equipamento de ginástica (não conta 'nearby'). Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_estacionamento` | bool | 2026 | sem nulo |  | Comodidade: estacionamento no imóvel, pago ou gratuito (não conta vaga na rua). Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_piscina` | bool | 2026 | sem nulo |  | Comodidade: piscina (não conta mesa de sinuca nem vista para piscina). Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_porteiro` | bool | 2026 | sem nulo |  | Comodidade: equipe no prédio / porteiro. Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_self_checkin` | bool | 2026 | sem nulo |  | Comodidade: self check-in. Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_espaco_trabalho` | bool | 2026 | sem nulo |  | Comodidade: espaço de trabalho dedicado. Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_tv` | bool | 2026 | sem nulo |  | Comodidade: TV. Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_varanda_patio` | bool | 2026 | sem nulo |  | Comodidade: varanda, pátio, quintal ou terraço. Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `amen_permite_pets` | bool | 2026 | sem nulo |  | Comodidade: aceita animais de estimação. Expressão regular sobre cada item da lista em `schema.AMENIDADES`. | derivada: `amenities` |
| `host_superhost` | bool | 2026 | sem nulo |  | Superhost, com nulo tratado como False (os 349 anúncios sem perfil não podem ter o selo verificado). | derivada: `host_is_superhost` |
| `host_anos` | float64 | 2026 | [0, ] |  | Anos como anfitrião: `hosts_time_as_host_years` + meses/12. (`host_since` veio 100% vazio neste snapshot.) | derivada |
| `tipo_imovel_grupo` | category | 2026 | `apartamento_inteiro`, `casa_inteira`, `quarto_em_apartamento`, `quarto_em_casa`, `hotel_pousada`, `quarto_compartilhado`, `atipico`; sem nulo |  | `property_type` em 7 grupos: apartamento/casa inteira, quarto em apartamento/casa, hotel ou pousada, quarto compartilhado, atípico (barco, trailer, torre...). Regra em clean/derivadas.py. | derivada: `property_type` |

## 2. Colunas de origem e o que a limpeza faz com cada uma

### Kaggle 2019 — `AB_NYC_2019.csv`

| coluna | tipo bruto | descrição | tratamento | pessoal | motivo |
|---|---|---|---|---|---|
| `id` | int64 | Id do anúncio. | mantida | **sim** |  |
| `name` | texto | Título do anúncio (16 nulos). | mantida | **sim** |  |
| `host_id` | int64 | Id do anfitrião. | mantida | **sim** |  |
| `host_name` | texto | Primeiro nome do anfitrião (21 nulos). | descartada | **sim** | dado pessoal (invariante 9) e inútil como chave: homônimos entre anfitriões (Q3) |
| `neighbourhood_group` | texto | Distrito. | mantida |  |  |
| `neighbourhood` | texto | Bairro. | mantida |  |  |
| `latitude` | float64 | Latitude. | mantida |  |  |
| `longitude` | float64 | Longitude. | mantida |  |  |
| `room_type` | texto | Tipo de acomodação (3 valores). | mantida |  |  |
| `price` | int64 | Diária em US$ (inteiro). | renomeada → `preco` |  |  |
| `minimum_nights` | int64 | Mínimo de noites. | mantida |  |  |
| `number_of_reviews` | int64 | Total de avaliações. | mantida |  |  |
| `last_review` | texto (data) | Última avaliação (10.052 nulos). | mantida |  |  |
| `reviews_per_month` | float64 | Avaliações por mês (10.052 nulos). | mantida |  |  |
| `calculated_host_listings_count` | int64 | Anúncios do anfitrião no scrape. | mantida |  |  |
| `availability_365` | int64 | Dias livres nos próximos 365. | mantida |  |  |

### Inside Airbnb 2026-06-14 — detalhado (`data/listings.csv.gz`)

| coluna | tipo bruto | descrição | tratamento | pessoal | motivo |
|---|---|---|---|---|---|
| `id` | int64 | Id do anúncio. | mantida | **sim** |  |
| `listing_url` | texto | URL do anúncio. | descartada | **sim** | URL leva ao anúncio e ao anfitrião (invariante 9) |
| `scrape_id` | int64 | Id da coleta. | descartada |  | constante (20260614073253) |
| `last_scraped` | texto (data) | Data da coleta. | mantida |  |  |
| `source` | texto | Origem no scrape. | mantida |  |  |
| `name` | texto | Título. | mantida | **sim** |  |
| `description` | texto | Descrição livre do anúncio. | descartada | **sim** | texto livre do anfitrião (pode conter nome, telefone, endereço) |
| `neighborhood_overview` | texto | Texto do anfitrião sobre o bairro. | descartada | **sim** | 100% nula neste snapshot |
| `picture_url` | texto | Foto do anúncio. | descartada | **sim** | foto (invariante 9) |
| `host_id` | int64 | Id do anfitrião. | mantida | **sim** |  |
| `host_url` | texto | URL do perfil. | descartada | **sim** | URL de perfil (invariante 9) |
| `host_profile_id` | float64 | Id do perfil novo do anfitrião. | descartada | **sim** | identificador pessoal redundante com host_id |
| `host_profile_url` | texto | URL do perfil novo. | descartada | **sim** | URL de perfil (invariante 9) |
| `host_name` | texto | Nome do anfitrião. | descartada | **sim** | dado pessoal (invariante 9); homônimos (Q3) |
| `host_since` | texto (data) | Data de início como anfitrião. | descartada |  | 100% nula neste snapshot; substituída por hosts_time_as_host_* |
| `hosts_time_as_user_years` | float64 | Anos de conta. | mantida |  |  |
| `hosts_time_as_user_months` | float64 | Meses além dos anos de conta. | mantida |  |  |
| `hosts_time_as_host_years` | float64 | Anos como anfitrião. | mantida |  |  |
| `hosts_time_as_host_months` | float64 | Meses além dos anos como anfitrião. | mantida |  |  |
| `host_location` | texto | Onde o anfitrião diz morar. | descartada | **sim** | localização pessoal do anfitrião, texto livre |
| `host_about` | texto | Texto do anfitrião sobre si. | descartada | **sim** | texto pessoal (invariante 9) |
| `host_response_time` | texto | Tempo de resposta. | descartada |  | 100% nula neste snapshot |
| `host_response_rate` | texto (%) | Taxa de resposta. | descartada |  | 100% nula neste snapshot — a taxa numérica pedida não pode ser derivada |
| `host_acceptance_rate` | texto (%) | Taxa de aceitação. | descartada |  | 100% nula neste snapshot — idem |
| `host_is_superhost` | t/f | Superhost. | mantida |  | tipada como booleana; alimenta host_superhost |
| `host_thumbnail_url` | texto | Miniatura da foto do anfitrião. | descartada | **sim** | foto; 100% nula neste snapshot |
| `host_picture_url` | texto | Foto do anfitrião. | descartada | **sim** | foto (invariante 9) |
| `host_neighbourhood` | texto | Bairro do anfitrião. | descartada | **sim** | 100% nula neste snapshot |
| `host_listings_count` | float64 | Anúncios do perfil. | mantida |  |  |
| `host_total_listings_count` | float64 | Anúncios totais do perfil. | descartada |  | 100% nula neste snapshot |
| `host_verifications` | texto | Meios de verificação. | descartada |  | 100% nula neste snapshot |
| `host_has_profile_pic` | t/f | Tem foto de perfil. | mantida |  |  |
| `host_identity_verified` | t/f | Identidade verificada. | mantida |  |  |
| `neighbourhood` | texto | Bairro em texto livre. | descartada |  | 100% nula neste snapshot; usar neighbourhood_cleansed |
| `neighbourhood_cleansed` | texto | Bairro pela coordenada. | mantida |  |  |
| `neighbourhood_group_cleansed` | texto | Distrito pela coordenada. | mantida |  |  |
| `latitude` | float64 | Latitude. | mantida |  |  |
| `longitude` | float64 | Longitude. | mantida |  |  |
| `property_type` | texto | Tipo de imóvel. | mantida |  |  |
| `room_type` | texto | Tipo de acomodação (4 valores). | mantida |  |  |
| `accommodates` | int64 | Hóspedes. | mantida |  |  |
| `bathrooms` | float64 | Banheiros. | mantida |  |  |
| `bathrooms_text` | texto | Banheiros em texto. | mantida |  |  |
| `bedrooms` | float64 | Quartos. | mantida |  |  |
| `beds` | float64 | Camas. | mantida |  |  |
| `amenities` | texto (JSON) | Comodidades. | mantida |  |  |
| `price` | texto | Preço "$1,234.00" (28,9% nulo). | renomeada → `preco` |  |  |
| `price_quote_checkin_date` | texto (data) | Check-in da cotação. | mantida |  |  |
| `price_quote_checkout_date` | texto (data) | Check-out da cotação. | mantida |  |  |
| `price_quote_total_price` | float64 | Total da cotação. | mantida |  |  |
| `price_quote_price_per_night` | float64 | Total ÷ noites. | descartada |  | idêntica a price em 100% das linhas com ambos (21.514); preco já a representa |
| `price_quote_raw` | texto (JSON) | Resposta bruta da cotação. | derivada → `preco_cheio, desconto_pct` |  | JSON bruto; os campos úteis viram derivadas |
| `minimum_nights` | float64 | Mínimo de noites (2 nulos). | mantida |  |  |
| `maximum_nights` | float64 | Máximo de noites. | mantida |  |  |
| `minimum_minimum_nights` | float64 | Menor mínimo. | mantida |  |  |
| `maximum_minimum_nights` | float64 | Maior mínimo. | mantida |  |  |
| `minimum_maximum_nights` | float64 | Menor máximo. | mantida |  |  |
| `maximum_maximum_nights` | float64 | Maior máximo. | mantida |  |  |
| `minimum_nights_avg_ntm` | float64 | Mínimo médio. | mantida |  |  |
| `maximum_nights_avg_ntm` | float64 | Máximo médio. | mantida |  |  |
| `calendar_updated` | texto | Última atualização do calendário. | descartada |  | 100% nula neste snapshot |
| `has_availability` | t/f | Aceita reservas. | mantida |  |  |
| `availability_30` | int64 | Dias livres em 30. | mantida |  |  |
| `availability_60` | int64 | Dias livres em 60. | mantida |  |  |
| `availability_90` | int64 | Dias livres em 90. | mantida |  |  |
| `availability_365` | int64 | Dias livres em 365. | mantida |  |  |
| `calendar_last_scraped` | texto (data) | Coleta do calendário. | mantida |  |  |
| `number_of_reviews` | int64 | Total de avaliações. | mantida |  |  |
| `number_of_reviews_ltm` | int64 | Avaliações em 12 meses. | mantida |  |  |
| `number_of_reviews_l30d` | int64 | Avaliações em 30 dias. | mantida |  |  |
| `availability_eoy` | int64 | Dias livres até o fim do ano. | mantida |  |  |
| `number_of_reviews_ly` | int64 | Avaliações no ano anterior. | mantida |  |  |
| `estimated_occupancy_l365d` | int64 | Ocupação estimada (noites). | mantida |  |  |
| `estimated_revenue_l365d` | float64 | Receita estimada. | mantida |  |  |
| `first_review` | texto (data) | Primeira avaliação. | mantida |  |  |
| `last_review` | texto (data) | Última avaliação. | mantida |  |  |
| `review_scores_rating` | float64 | Nota média 0–5. | mantida |  |  |
| `review_scores_accuracy` | float64 | Nota média 0–5. | mantida |  |  |
| `review_scores_cleanliness` | float64 | Nota média 0–5. | mantida |  |  |
| `review_scores_checkin` | float64 | Nota média 0–5. | mantida |  |  |
| `review_scores_communication` | float64 | Nota média 0–5. | mantida |  |  |
| `review_scores_location` | float64 | Nota média 0–5. | mantida |  |  |
| `review_scores_value` | float64 | Nota média 0–5. | mantida |  |  |
| `license` | texto | Registro OSE. | mantida |  |  |
| `instant_bookable` | t/f | Reserva instantânea. | descartada |  | 100% nula neste snapshot |
| `calculated_host_listings_count` | int64 | Contagem de anúncios do anfitrião no scrape. | mantida |  |  |
| `calculated_host_listings_count_entire_homes` | int64 | Contagem de anúncios do anfitrião no scrape. | mantida |  |  |
| `calculated_host_listings_count_private_rooms` | int64 | Contagem de anúncios do anfitrião no scrape. | mantida |  |  |
| `calculated_host_listings_count_shared_rooms` | int64 | Contagem de anúncios do anfitrião no scrape. | mantida |  |  |
| `reviews_per_month` | float64 | Avaliações por mês. | mantida |  |  |

### Inside Airbnb 2026-06-14 — resumo (`visualisations/listings.csv`)

| coluna | tipo bruto | descrição | tratamento | pessoal | motivo |
|---|---|---|---|---|---|
| `id` | int64 | Id do anúncio. | referencia | **sim** | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `name` | texto | Título (quebras de linha preservadas, ao contrário do detalhado). | referencia | **sim** | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `host_id` | float64 | Id do anfitrião (296 nulos). | referencia | **sim** | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `host_profile_id` | float64 | Id do perfil do anfitrião. | referencia | **sim** | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `host_name` | texto | Nome do anfitrião. | referencia | **sim** | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `neighbourhood_group` | texto | Distrito. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `neighbourhood` | texto | Bairro. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `latitude` | float64 | Latitude. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `longitude` | float64 | Longitude. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `room_type` | texto | Tipo de acomodação. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `price` | float64 | Preço arredondado ao dólar. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `minimum_nights` | float64 | Mínimo de noites. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `number_of_reviews` | int64 | Total de avaliações. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `last_review` | texto (data) | Última avaliação. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `reviews_per_month` | float64 | Avaliações por mês. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `calculated_host_listings_count` | float64 | Anúncios do anfitrião. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `availability_365` | int64 | Dias livres nos próximos 365. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `number_of_reviews_ltm` | int64 | Avaliações nos últimos 12 meses. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |
| `license` | texto | Registro OSE. | referencia |  | conferência apenas: o detalhado traz 30.259 dos 30.555 ids com valores idênticos (preço lá tem centavos); os 296 restantes não têm anfitrião — docs/04 §1 |

## 3. Quarentena (`data/processed/quarentena.parquet`)

| coluna | descrição |
|---|---|
| `snapshot` | "2019" ou "2026" |
| `id` | id do anúncio (pessoal — não publicar) |
| `regra` | código da regra (B01…, P01…) |
| `motivo` | texto da regra |
| `escopo` | `base` (a linha sai de tudo) ou `preco` (a linha fica, mas sai das análises de preço) |

Regras, contagens e cascata em `data/processed/_qualidade.json` e em
[Preparação dos dados](04-preparacao-dos-dados.md).
