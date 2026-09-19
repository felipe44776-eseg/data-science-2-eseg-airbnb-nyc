"""MODZCTA — ZIPs "modificados" do Departamento de Saude de NYC (`pri4-ifjk`).

Para que serve: e a ponte entre a celula H3 e tudo que vem por ZIP (ZORI do
Zillow, 311 agregado por `incident_zip`). ZIP postal nao e area — e rota de
carteiro; o ZCTA do Census e a aproximacao em area, e o MODZCTA junta os ZCTAs
minusculos (um predio, uma estacao) ao vizinho, para ter populacao estavel. Sao
178 poligonos; a coluna `zcta` lista os ZCTAs contidos em cada um, o que permite
traduzir qualquer ZIP para o seu MODZCTA.
"""

from __future__ import annotations

import geopandas as gpd

from airbnb import config
from airbnb.external._http import artefato, obter

DOMINIO = "data.cityofnewyork.us"
DATASET = "pri4-ifjk"
URL = f"https://{DOMINIO}/resource/{DATASET}.geojson"
PASTA = config.EXTERNAL / "modzcta"
ARQUIVO = PASTA / "modzcta.geojson"

META = {
    "titulo": "Modified Zip Code Tabulation Areas (MODZCTA)",
    "orgao": "NYC Department of Health and Mental Hygiene (via NYC Open Data)",
    "licenca": "NYC Open Data Terms of Use (uso livre, sem garantia)",
    "atribuicao": "MODZCTA: NYC Department of Health and Mental Hygiene, via NYC Open Data.",
}


def coletar(forcar: bool = False) -> dict:
    PASTA.mkdir(parents=True, exist_ok=True)
    params = {"$limit": 1000}
    if ARQUIVO.exists() and not forcar:
        art = artefato(ARQUIVO, url=URL, parametros=params, nota="ja existia — nao rebaixado")
    else:
        r = obter(URL, params=params, timeout=90)
        ARQUIVO.write_bytes(r.content)
        art = artefato(ARQUIVO, url=URL, parametros=params)
    g = carregar()
    return {**META, "estado": "ok", "artefatos": [art],
            "resumo": {"poligonos": int(len(g)), "area_km2": round(float(g["area_km2"].sum()), 1)}}


def carregar() -> gpd.GeoDataFrame | None:
    """MODZCTA com `zip` (codigo do MODZCTA), `zctas` (lista) e `area_km2` (metrica)."""
    if not ARQUIVO.exists():
        return None
    g = gpd.read_file(ARQUIVO)
    g = g[g["modzcta"].astype(str).str.fullmatch(r"\d{5}")].copy()
    g["zip"] = g["modzcta"].astype(str)
    g["zctas"] = g["zcta"].fillna("").map(lambda s: [z.strip() for z in s.split(",") if z.strip()])
    g["area_km2"] = g.to_crs(config.CRS_METRICO).area / 1e6
    return g[["zip", "zctas", "area_km2", "geometry"]].set_crs(config.CRS_GEO, allow_override=True)


def zip_para_modzcta(g: gpd.GeoDataFrame) -> dict[str, str]:
    """Qualquer ZIP/ZCTA listado -> codigo do MODZCTA que o contem."""
    mapa = {}
    for z, membros in zip(g["zip"], g["zctas"], strict=True):
        for m in [z, *membros]:
            mapa.setdefault(m, z)
    return mapa
