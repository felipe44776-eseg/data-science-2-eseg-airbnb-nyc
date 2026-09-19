"""E2 — Geometria dos setores censitarios (tracts): cartographic boundary do Census.

Duas safras porque o Census redesenhou os tracts em 2020:
  * `cb_2019_36_tract_500k` -> tracts de 2010, os do ACS 2015-2019;
  * `cb_2024_36_tract_500k` -> tracts de 2020, os do ACS 2020-2024.
Juntar o ACS de uma safra com a geometria da outra casaria GEOIDs que nao
designam mais o mesmo territorio.

Arquivo "500k" (generalizado, recortado na linha da costa): e o adequado para
atribuir centroide de celula a tract; o TIGER completo inclui agua e pesa 20x.
`ALAND` (m2 de terra) e o denominador da densidade populacional — area total
inflaria a densidade de tract costeiro com agua.
"""

from __future__ import annotations

import geopandas as gpd

from airbnb import config
from airbnb.external._http import artefato, baixar_arquivo

URL = "https://www2.census.gov/geo/tiger/GENZ{ano}/shp/cb_{ano}_36_tract_500k.zip"
PASTA = config.EXTERNAL / "tracts"

#: safra do projeto -> ano do arquivo de geometria
SAFRAS = {"2019": 2019, "atual": 2024}

META = {
    "titulo": "Cartographic Boundary Files — Census Tracts, New York (1:500.000)",
    "orgao": "U.S. Census Bureau, Geography Division",
    "licenca": "dominio publico (obra do governo federal dos EUA)",
    "atribuicao": "Limites de setores censitarios: U.S. Census Bureau, Cartographic Boundary Files.",
}


def arquivo(safra: str):
    ano = SAFRAS[safra]
    return PASTA / f"cb_{ano}_36_tract_500k.zip"


def coletar(forcar: bool = False) -> dict:
    artefatos, resumo = [], {}
    for safra, ano in SAFRAS.items():
        destino = arquivo(safra)
        url = URL.format(ano=ano)
        if destino.exists() and not forcar:
            artefatos.append(artefato(destino, url=url, nota="ja existia — nao rebaixado"))
        else:
            artefatos.append(baixar_arquivo(url, destino))
        g = carregar(safra)
        resumo[safra] = {"arquivo_ano": ano, "tracts_nyc": int(len(g)),
                         "tracts_sem_terra": int((g["ALAND"] == 0).sum())}
    return {**META, "estado": "ok", "artefatos": artefatos, "resumo": resumo}


def carregar(safra: str) -> gpd.GeoDataFrame | None:
    """Tracts dos 5 condados de NYC, com `geoid` (11 digitos) e `aland_km2`."""
    p = arquivo(safra)
    if not p.exists():
        return None
    g = gpd.read_file(f"zip://{p.as_posix()}")
    g = g[g["COUNTYFP"].isin(config.CONDADO_FIPS.values())].copy()
    g["geoid"] = g["GEOID"].astype(str)
    g["aland_km2"] = g["ALAND"].astype(float) / 1e6
    return g[["geoid", "COUNTYFP", "ALAND", "aland_km2", "geometry"]].to_crs(config.CRS_GEO)
