# Fontes primárias — proveniência e integridade

Os arquivos de dados não são versionados (invariante 5). Este documento é a versão
humana do **manifesto** `data/raw/_manifesto.json`: de onde cada arquivo veio, quando,
sob que licença e como provar que é o mesmo arquivo que gerou os números publicados.

## Um comando obtém tudo e confere o hash

```powershell
.\tasks.ps1 dados                        # baixa o que falta e CONFERE o SHA-256 de tudo
.\tasks.ps1 dados --verificar            # só confere; não baixa
.\tasks.ps1 dados --kaggle <CSV|pasta|zip>   # copia o Kaggle baixado à mão
```

(`python -m airbnb.ingest.baixar` com os mesmos argumentos.)

A primeira execução **registrou** bytes e SHA-256 de cada arquivo; as seguintes
**conferem** e **abortam** se um hash divergir — sem reescrever o manifesto, que é a
prova do que era esperado. Download vai para `.parcial` e só ganha o nome final
inteiro. Troca deliberada de versão exige `--aceitar-fonte-nova` e reprocessamento de
tudo a jusante.

## Resumo

| arquivo em `data/raw/` | bytes | SHA-256 | origem | licença |
|---|---:|---|---|---|
| `kaggle/AB_NYC_2019.csv` | 7.077.973 | `e420db40ff10fcb40efc1b5b1648ee0b18a48f4e4537155cecc59fe95d18783a` | Kaggle | CC0 1.0 |
| `insideairbnb/2026-06-14/listings.csv.gz` | 15.694.632 | `10eb56b21ec71a838b30ef47b836f3d375269baeed5ff9e5c35ff3c6a98d3ca7` | Inside Airbnb | CC BY 4.0 |
| `insideairbnb/2026-06-14/listings_resumo.csv` | 5.540.939 | `e42f8f897a4ed89d489e703dc462d314f5aa98912cca6637c988c99f5490caba` | Inside Airbnb | CC BY 4.0 |
| `insideairbnb/2026-06-14/reviews_resumo.csv` | 22.506.716 | `dca796445924529428d6ab7f13f161b56114ef9bf7209ea1c2255ca45866e647` | Inside Airbnb | CC BY 4.0 |
| `insideairbnb/2026-06-14/neighbourhoods.geojson` | 634.167 | `c0d3f80e341a4a95c40f37fc54c4af890c834bb30b5b27308e04033b05e9c3e7` | Inside Airbnb | CC BY 4.0 |
| `insideairbnb/2026-06-14/neighbourhoods.csv` | 4.962 | `0085b86dc498478df3024483fe5d4ddcf3f848802e280b1b6171145aed8edeff` | Inside Airbnb | CC BY 4.0 |
| `insideairbnb/2026-06-14/calendar.csv.gz` | 25.904.041 | `1023688159497ffccdfabe81e163d31ca4fae7af4b4e87bed119168531e4648d` | Inside Airbnb | CC BY 4.0 |

Data de acesso de todos: **2026-09-18**. Os seis primeiros hashes foram conferidos
contra os registrados no momento do download, antes de o manifesto existir.

---

## 2019 — Kaggle `dgomonov/new-york-city-airbnb-open-data`

| | |
|---|---|
| **Página** | <https://www.kaggle.com/datasets/dgomonov/new-york-city-airbnb-open-data> (versão 3) |
| **Licença** | CC0 1.0 — domínio público |
| **Conteúdo** | 48.895 anúncios × 16 colunas (formato do *resumo* do Inside Airbnb) |
| **Data do scrape** | 2019-07-08 — conferida no dado: `max(last_review)` |
| **Download** | exige conta Kaggle: botão *Download* → `archive.zip`. O módulo aceita o CSV, a pasta que o contém ou o zip (`--kaggle`), ou baixa pela API se houver `KAGGLE_USERNAME`/`KAGGLE_KEY` ou `~/.kaggle/kaggle.json` |

### Por que 2019 vem do Kaggle, e não do Inside Airbnb

O Inside Airbnb publica para download só os snapshots dos últimos 12 meses ("generally
quarterly data for the last 12 months"); dado mais antigo é acessível por *data request*
(<https://insideairbnb.com/get-the-data/>, consultado em 2026-09-18). A URL do snapshot
de 2019, no mesmo padrão das atuais, responde **HTTP 403**. O dataset do Kaggle é a
republicação, em CC0, do *resumo*
(`visualisations/listings.csv`) do scrape de julho de 2019 — as 16 colunas, com os
mesmos nomes e na mesma ordem, estão no resumo atual, que acrescentou
`host_profile_id`, `number_of_reviews_ltm` e `license`.

**O que ele NÃO tem**, e que limita a comparação: descrição do imóvel (quartos,
banheiros, amenidades), notas de avaliação, avaliações dos últimos 12 meses, data da
primeira avaliação, cotação de preço, licença. Tudo que o projeto compara entre os
anos usa só as colunas comuns (`anuncios_resumo.parquet`).

## 2026 — Inside Airbnb, snapshot `2026-06-14`

| | |
|---|---|
| **Origem** | <https://insideairbnb.com/get-the-data/> — base `https://data.insideairbnb.com/united-states/ny/new-york-city/2026-06-14/` |
| **Licença** | **CC BY 4.0** — atribuição obrigatória: *"Inside Airbnb, insideairbnb.com"* em toda superfície publicada (site, relatório, figuras) |
| **Coleta** | scrape da cidade em 14–15/06/2026 e recoleta dos anúncios do scrape anterior em 22–23/06/2026 (`source = previous scrape`) |
| **User-Agent** | o download se identifica como `airbnb-nyc-eseg/0.1 (projeto acadêmico ESEG; <repositório>)` |

| arquivo local | URL (relativa à base) | conteúdo | no pipeline |
|---|---|---|---|
| `listings.csv.gz` | `data/listings.csv.gz` | **detalhado**: 30.259 × 90 — a base de 2026 | sim |
| `listings_resumo.csv` | `visualisations/listings.csv` | resumo: 30.555 × 19 | só conferência |
| `reviews_resumo.csv` | `visualisations/reviews.csv` | 990.170 avaliações (`listing_id`, `date`) de 21.939 anúncios, 2009-05-25 a 2026-06-22 | validação da ocupação de 2019 |
| `neighbourhoods.geojson` | `visualisations/neighbourhoods.geojson` | 233 polígonos (230 bairros; 3 bairros em 2 partes; 7 geometrias inválidas, corrigidas com `make_valid`) | Q4 |
| `neighbourhoods.csv` | `visualisations/neighbourhoods.csv` | 230 pares bairro → distrito | regra B05 |
| `calendar.csv.gz` | `data/calendar.csv.gz` | calendário de 365 dias por anúncio | **não** |

### Detalhado × resumo: por que o detalhado

O detalhado cobre **30.259 dos 30.555** ids do resumo, com valores **idênticos** em todas
as colunas comuns (coordenada, bairro, tipo, mínimo de noites, avaliações, licença...);
o preço do resumo é o do detalhado arredondado ao dólar. Os **296 ids que só o resumo
tem** são todos: sem `host_id`, `room_type = Private room`, mínimo de 1 noite, sem
licença, 268 com nome de hotel — inventário de hotel distribuído sem perfil de
anfitrião, que o detalhado não traz. Detalhe em
[Preparação dos dados §1](../../docs/04-preparacao-dos-dados.md).

### O que o detalhado tem e o que não tem

- **Tem, e é novo em relação a 2019:** cotação de preço (`price_quote_*`, com o JSON bruto
  dos itens da cotação), `estimated_occupancy_l365d` e `estimated_revenue_l365d`,
  `number_of_reviews_ltm`, `first_review`, notas de avaliação, amenidades, banheiros,
  licença da OSE (Local Law 18), tempo de conta do anfitrião (`hosts_time_as_*`).
- **Veio 100% vazio neste snapshot** (12 colunas): `host_since`, `host_response_time`,
  `host_response_rate`, `host_acceptance_rate`, `host_thumbnail_url`,
  `host_neighbourhood`, `host_total_listings_count`, `host_verifications`,
  `neighbourhood`, `neighborhood_overview`, `calendar_updated`, `instant_bookable`.
  As taxas de resposta e aceitação, portanto, **não existem** para 2026.
- **`price` mudou de significado:** é a cotação de uma estadia de N noites (em 96,6% das
  cotações, N = mínimo de noites) dividida por N, já com desconto semanal/mensal —
  ver [Entendimento dos dados, Q5](../../docs/02-entendimento-dos-dados.md).

### Por que o calendário está fora

`calendar.csv.gz` tem só `listing_id, date, available, minimum_nights, maximum_nights`.
O Inside Airbnb **retirou a coluna de preço** do calendário: ele não dá preço por data
nem ocupação (dia indisponível mistura reserva e bloqueio — o mesmo problema do
`availability_365`, invariante 7). É baixado e tem o hash conferido para que a
reprodução seja completa, mas nenhuma etapa o lê.

---

## Modelo de ocupação — premissas consultadas

<https://insideairbnb.com/data-assumptions/> (consultado em 2026-09-18): taxa de
avaliação de **50%**; estadia média configurada por cidade (**3 noites** onde não há
dado público); mínimo de noites quando maior que a estadia média; teto de **70%**;
coordenada publicada a **0–450 pés (~150 m)** do endereço real. O valor de NYC (**6,4
noites**) não está na página: foi obtido reproduzindo `estimated_occupancy_l365d` do
próprio detalhado (acerto em 30.257 de 30.257 anúncios).
