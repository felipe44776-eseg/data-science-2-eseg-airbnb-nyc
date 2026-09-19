"""Caminhos e constantes compartilhadas — fonte unica.

Nome de coluna NAO mora aqui: mora em `schema.py`. Aqui fica o que e de
ambiente (onde cada artefato vive) e o que e decisao de projeto que mais de um
modulo precisa ler (datas de snapshot, resolucoes H3, sistema de coordenadas).

Mudar um valor daqui muda o resultado publicado — cada um cita o ADR ou o
documento que o justifica.
"""

from __future__ import annotations

from pathlib import Path

# --- caminhos ---------------------------------------------------------------

RAIZ = Path(__file__).resolve().parents[2]

DADOS = RAIZ / "data"
RAW = DADOS / "raw"
EXTERNAL = DADOS / "external"
INTERIM = DADOS / "interim"
PROCESSED = DADOS / "processed"

REPORTS = RAIZ / "reports"
FIGURAS = REPORTS / "figures"
DOCS = RAIZ / "docs"
SITE = RAIZ / "site"
SITE_DADOS = SITE / "data"

# --- snapshots --------------------------------------------------------------

#: Data do scrape do Inside Airbnb que deu origem ao dataset do Kaggle
#: (dgomonov/new-york-city-airbnb-open-data). Conferida no dado: max(last_review).
SNAPSHOT_2019 = "2019-07-08"

#: Snapshot mais recente publicado pelo Inside Airbnb para NYC no momento da coleta.
SNAPSHOT_ATUAL = "2026-06-14"

#: Rotulos curtos usados em coluna `snapshot` e em chave de JSON.
ROTULO_2019 = "2019"
ROTULO_ATUAL = "2026"

INSIDE_AIRBNB_BASE = "https://data.insideairbnb.com/united-states/ny/new-york-city"
KAGGLE_DATASET = "dgomonov/new-york-city-airbnb-open-data"

RAW_KAGGLE = RAW / "kaggle" / "AB_NYC_2019.csv"
RAW_INSIDE = RAW / "insideairbnb" / SNAPSHOT_ATUAL

#: Local Law 18 (Short-Term Rental Registration Law): fiscalizacao desde esta data.
#: Estadia < 30 noites passa a exigir registro na OSE. Quebra estrutural entre os
#: dois snapshots — ver docs/01 e ADR 0005.
LL18_VIGENCIA = "2023-09-05"
NOITES_CURTA_TEMPORADA = 30

# --- espaco -----------------------------------------------------------------

CRS_GEO = "EPSG:4326"
#: UTM 18N: distancia e area em metros sem distorcao relevante em NYC.
CRS_METRICO = "EPSG:32618"

#: Unidade espacial das features de localizacao e da busca do simulador (ADR 0001).
#: r9 ~ 0,105 km2, aresta ~ 174 m: da ordem do ruido que o Airbnb injeta na
#: coordenada publicada (ate ~150 m). Precisao abaixo disso e ficcao.
H3_RES_FEATURES = 9
#: Unidade dos mapas coropleticos: r8 ~ 0,74 km2, anuncios suficientes por celula.
H3_RES_MAPA = 8
#: Blocos da validacao cruzada espacial (ADR 0002): r6 ~ 36 km2.
H3_RES_CV = 6

#: (lon_min, lat_min, lon_max, lat_max) — envelope dos 5 distritos.
NYC_BBOX = (-74.2591, 40.4774, -73.7004, 40.9176)

DISTRITOS = ("Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island")
ESTADO_FIPS = "36"
CONDADO_FIPS = {
    "Bronx": "005",
    "Brooklyn": "047",
    "Manhattan": "061",
    "Queens": "081",
    "Staten Island": "085",
}

# --- modelagem --------------------------------------------------------------

SEMENTE = 42
N_FOLDS = 5
#: Nivel nominal dos intervalos de previsao publicados (conformal).
COBERTURA_ALVO = 0.80
