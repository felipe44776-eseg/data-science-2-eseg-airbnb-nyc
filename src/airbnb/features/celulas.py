"""Celulas H3 r9 de NYC com as features de localizacao (ADR 0001, invariante 4).

Localizacao e a celula, nao o ponto: o Airbnb desloca a coordenada publicada em
ate ~150 m, da ordem da aresta da r9 (~174 m). Toda feature externa e calculada
UMA vez por celula e o anuncio a herda pela celula em que cai — assim o ruido da
coordenada nao vira ruido de feature, e o simulador do site consulta a mesma
tabela que o modelo usou.

Cobertura: todas as celulas r9 que tocam a NYC terrestre (contencao "overlap"
sobre a uniao dos 233 bairros do Inside Airbnb). Com contencao por centro, a
celula costeira cujo centro cai na agua ficaria de fora — e anuncio na orla
ficaria sem feature.

Unidade de agregacao por fonte (declarada em FEATURES["..."]["transformacao"]):
  * ACS              -> tract que contem o centroide da celula
  * NYPD             -> delegacia que contem o centroide (contagem agregada no
                        servidor por `addr_pct_cd`: 77/78 poligonos, nao anel r9)
  * 311 barulho      -> MODZCTA do centroide (agregado no servidor por ZIP)
  * Zillow ZORI      -> MODZCTA do centroide
  * MTA, marcos      -> distancia metrica a partir do centroide
  * OSM              -> contagem no anel k=1 (a celula + 6 vizinhas, ~0,74 km2)
  * OSE (LL18)       -> distrito do Conselho do centroide (so safra atual; contexto)

Contrato com a modelagem:
  * `FEATURES_LOCAL_NEUTRAS`: nomes sem sufixo de safra, ordem estavel (com lat, lon);
  * `features_da_safra(df, "2019" | "atual")`: DataFrame indexado por `h3_r9`
    com exatamente essas colunas;
  * `fonte_da_feature(nome_neutro)`: rotulo curto da fonte.
`zori_var_pct` e `ll18_registros_km2_atual` ficam na tabela mas FORA das listas
de modelo: uma e informacao do futuro para 2019; a outra so existe em 2026.

Uso:
    python -m airbnb.features.celulas
"""

from __future__ import annotations

import json
from collections.abc import Iterable

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely import get_parts
from shapely.geometry import MultiPolygon, Polygon
from shapely.validation import make_valid

from airbnb import config

RES = config.H3_RES_FEATURES
SAIDA = config.PROCESSED / "celulas_r9.parquet"
RESUMO = config.PROCESSED / "_celulas.json"
BAIRROS = config.RAW_INSIDE / "neighbourhoods.geojson"

SAFRAS = ("2019", "atual")
RAIO_METRO_M = 800  # ~10 min a pe: a distancia que o anuncio costuma chamar de "perto do metro"
ANEL_K = 1

_PARA_METRICO = Transformer.from_crs(config.CRS_GEO, config.CRS_METRICO, always_xy=True)

# --------------------------------------------------------------------------
# dicionario de features
# --------------------------------------------------------------------------

#: rotulo curto da fonte (o site e o SHAP agrupam por ele)
FONTES_ROTULO = ("H3", "ACS", "NYPD", "311", "Zillow", "MTA", "OSM", "marcos")

_SAFRA_DESC = {
    "ACS": {"2019": "ACS 5 anos 2015-2019 (tracts 2010)",
            "atual": "ACS 5 anos 2020-2024 (tracts 2020)"},
    "NYPD": {"2019": "12 meses: 2018-07-08 a 2019-07-07",
             "atual": "12 meses: 2025-06-14 a 2026-06-13"},
    "311": {"2019": "12 meses: 2018-07-08 a 2019-07-07",
            "atual": "12 meses: 2025-06-14 a 2026-06-13"},
    "Zillow": {"2019": "2019-07", "atual": "2026-06"},
}

_ACS_TRANSF = ("tract (GEOID) que contem o centroide da celula; codigos-sentinela "
               "negativos do Census -> NaN")

#: (nome neutro, fonte, tem safra?, unidade, descricao, transformacao)
_DEFINICOES: list[tuple[str, str, bool, str, str, str]] = [
    ("lat", "H3", False, "graus (WGS84)", "latitude do centroide da celula r9",
     "h3.cell_to_latlng"),
    ("lon", "H3", False, "graus (WGS84)", "longitude do centroide da celula r9",
     "h3.cell_to_latlng"),
    ("acs_renda_mediana", "ACS", True, "USD nominais do ultimo ano do ACS (2019 | 2024)",
     "renda domiciliar mediana do tract (B19013_001)",
     _ACS_TRANSF + "; teto do Census 250.001 = '250.000 ou mais'"),
    ("acs_aluguel_mediano", "ACS", True, "USD/mes nominais do ultimo ano do ACS",
     "aluguel bruto mediano do tract (B25064_001)",
     _ACS_TRANSF + "; teto 3.501 (2019) / 3.501+ (2024) e censura"),
    ("acs_pop_densidade", "ACS", True, "hab/km2 de terra",
     "populacao do tract (B01003_001) / area de terra do tract (ALAND)",
     _ACS_TRANSF + "; ALAND do cartographic boundary da mesma safra"),
    ("acs_pct_alugado", "ACS", True, "%",
     "domicilios ocupados de aluguel / domicilios ocupados (B25003_003 / B25003_001)",
     _ACS_TRANSF + "; denominador 0 -> NaN"),
    ("acs_pct_vago", "ACS", True, "%",
     "unidades habitacionais vagas / total (B25002_003 / B25002_001)",
     _ACS_TRANSF + "; inclui unidade vaga por uso sazonal/ocasional — onde mora o Airbnb"),
    ("acs_valor_imovel", "ACS", True, "USD nominais do ultimo ano do ACS",
     "valor mediano do imovel ocupado pelo proprietario (B25077_001)",
     _ACS_TRANSF + "; teto 2.000.001 = '2.000.000 ou mais'"),
    ("crime_graves_km2", "NYPD", True, "queixas/km2 em 12 meses",
     "queixas criminais de natureza FELONY registradas (rpt_dt) nos 12 meses antes do "
     "snapshot, por km2 de terra da delegacia",
     "contagem agregada no servidor por delegacia (addr_pct_cd); a celula herda a "
     "densidade da delegacia que contem o centroide"),
    ("crime_total_km2", "NYPD", True, "queixas/km2 em 12 meses",
     "queixas criminais de qualquer natureza (FELONY + MISDEMEANOR + VIOLATION) nos 12 "
     "meses antes do snapshot, por km2 de terra da delegacia",
     "idem crime_graves_km2"),
    ("ruido_311_km2", "311", True, "chamados/km2 em 12 meses",
     "chamados ao 311 com complaint_type iniciado por 'Noise' nos 12 meses antes do "
     "snapshot, por km2 do MODZCTA",
     "contagem agregada no servidor por incident_zip -> MODZCTA; a celula herda a "
     "densidade do MODZCTA que contem o centroide"),
    ("zori", "Zillow", True, "USD/mes nominais do mes de referencia",
     "Zillow Observed Rent Index (suavizado, todas as tipologias) do ZIP",
     "MODZCTA do centroide; valor do ZIP do MODZCTA ou, na falta, media dos ZCTAs "
     "membros com valor"),
    ("metro_dist_m", "MTA", False, "m",
     "distancia do centroide a estacao de metro mais proxima (inclui SIR)",
     "KD-tree em UTM 18N (EPSG:32618)"),
    ("metro_n_800m", "MTA", False, "complexos",
     "complexos de estacao distintos (complex_id) a ate 800 m do centroide",
     "KD-tree em UTM 18N; conta complexo, nao plataforma"),
    ("metro_linhas_800m", "MTA", False, "linhas",
     "linhas distintas (daytime_routes) servidas pelas estacoes a ate 800 m",
     "uniao das linhas diurnas das estacoes no raio"),
    ("poi_restaurantes_k1", "OSM", False, "POIs no anel k=1",
     "restaurantes e fast-food (amenity=restaurant|fast_food) na celula e nas 6 vizinhas",
     "ponto (no) ou centro (way/relation) -> celula r9 -> soma no anel k=1"),
    ("poi_bares_k1", "OSM", False, "POIs no anel k=1",
     "bares, pubs e casas noturnas (amenity=bar|pub|nightclub) no anel k=1", "idem"),
    ("poi_cafes_k1", "OSM", False, "POIs no anel k=1", "cafes (amenity=cafe) no anel k=1",
     "idem"),
    ("poi_atracoes_k1", "OSM", False, "POIs no anel k=1",
     "atracoes, museus, galerias e mirantes (tourism=attraction|museum|gallery|viewpoint) "
     "no anel k=1", "idem"),
    ("poi_hoteis_k1", "OSM", False, "POIs no anel k=1",
     "hoteis, hostels e pousadas (tourism=hotel|hostel|guest_house) no anel k=1 — a "
     "concorrencia formal do Airbnb", "idem"),
    ("poi_parques_k1", "OSM", False, "POIs no anel k=1",
     "parques (leisure=park) cujo centro cai no anel k=1",
     "idem; parque grande conta 1 (limitacao declarada)"),
    ("dist_centro_km", "marcos", False, "km", "distancia do centroide a Times Square",
     "euclidiana em UTM 18N"),
    ("dist_aeroporto_km", "marcos", False, "km",
     "distancia ao aeroporto mais proximo (min de JFK e LGA)", "euclidiana em UTM 18N"),
    ("dist_marco_km", "marcos", False, "km",
     "distancia ao marco turistico mais proximo (Times Square, Empire State, Central "
     "Park, One WTC, Brooklyn Bridge)", "euclidiana em UTM 18N"),
]

#: nomes neutros, na ordem estavel usada pela modelagem (inclui lat e lon)
FEATURES_LOCAL_NEUTRAS: list[str] = [d[0] for d in _DEFINICOES]
_TEM_SAFRA = {d[0]: d[2] for d in _DEFINICOES}
_FONTE = {d[0]: d[1] for d in _DEFINICOES}


def nome_na_safra(neutro: str, safra: str) -> str:
    """'acs_renda_mediana', '2019' -> 'acs_renda_mediana_2019'; sem safra fica igual."""
    return f"{neutro}_{safra}" if _TEM_SAFRA[neutro] else neutro


FEATURES_LOCAL_2019: list[str] = [nome_na_safra(n, "2019") for n in FEATURES_LOCAL_NEUTRAS]
FEATURES_LOCAL_ATUAL: list[str] = [nome_na_safra(n, "atual") for n in FEATURES_LOCAL_NEUTRAS]

#: nome da coluna no parquet -> metadados
FEATURES: dict[str, dict] = {}
for _n, _f, _s, _u, _d, _t in _DEFINICOES:
    for _safra in (SAFRAS if _s else (None,)):
        FEATURES[nome_na_safra(_n, _safra) if _safra else _n] = {
            "fonte": _f, "neutro": _n,
            "safra": _SAFRA_DESC[_f][_safra] if _safra else "unica (aplicada as duas safras)",
            "unidade": _u, "descricao": _d, "transformacao": _t,
        }
FEATURES["zori_var_pct"] = {
    "fonte": "Zillow", "neutro": None, "safra": "2019-07 -> 2026-06", "unidade": "%",
    "descricao": "variacao nominal do ZORI do ZIP entre os dois snapshots",
    "transformacao": "(zori_atual / zori_2019 - 1) * 100. NAO usar como feature de modelo "
                     "de 2019: e informacao do futuro. Serve a analise de deriva e ao mapa.",
}
FEATURES["ll18_registros_km2_atual"] = {
    "fonte": "OSE", "neutro": None, "safra": "FY26 (registros ativos em 2026-06-30)",
    "unidade": "registros/km2",
    "descricao": "registros de curta temporada ATIVOS (Local Law 18) no distrito do Conselho "
                 "Municipal que contem o centroide, por km2 de terra do distrito",
    "transformacao": "Figura 1 do relatorio anual FY26 da OSE; 51 distritos. So existe na safra "
                     "atual (a lei nao existia em 2019): contexto e mapa, nao feature de modelo.",
}

#: features monetarias -> referencia do dolar por safra (periodo aceito por fator_cpi)
MONETARIAS: dict[str, dict[str, str]] = {
    "acs_renda_mediana": {"2019": "2019", "atual": "2024"},
    "acs_aluguel_mediano": {"2019": "2019", "atual": "2024"},
    "acs_valor_imovel": {"2019": "2019", "atual": "2024"},
    "zori": {"2019": "2019-07", "atual": "2026-06"},
}


def fonte_da_feature(nome_neutro: str) -> str:
    """Rotulo curto da fonte: 'ACS', 'NYPD', '311', 'MTA', 'OSM', 'Zillow', 'marcos', 'H3'."""
    if nome_neutro in _FONTE:
        return _FONTE[nome_neutro]
    if nome_neutro in FEATURES:
        return FEATURES[nome_neutro]["fonte"]
    raise KeyError(f"feature desconhecida: {nome_neutro}")


def features_da_safra(df: pd.DataFrame, safra: str, *, dolar: str | None = None,
                      cpi: pd.DataFrame | None = None) -> pd.DataFrame:
    """Colunas da safra com nome NEUTRO, indexadas por `h3_r9`.

    `acs_renda_mediana_2019` e `acs_renda_mediana_atual` viram `acs_renda_mediana`:
    o modelo treinado numa safra le a outra sem renomear nada.

    `dolar` (opcional, ex. "2019-07"): converte as features monetarias para dolares
    desse mes pelo CPI-U NY (invariante 8). Sem ele, os valores ficam nominais da
    safra — renda do ACS 2020-2024 em dolares de 2024, ZORI atual em dolares de 2026-06.
    """
    if safra not in SAFRAS:
        raise ValueError(f"safra deve ser uma de {SAFRAS}, nao {safra!r}")
    base = df.set_index("h3_r9") if "h3_r9" in df.columns else df
    colunas = FEATURES_LOCAL_2019 if safra == "2019" else FEATURES_LOCAL_ATUAL
    out = base.reindex(columns=colunas).copy()
    out.columns = FEATURES_LOCAL_NEUTRAS
    out.index.name = "h3_r9"
    if dolar is not None:
        from airbnb.external.cpi import fator_cpi

        for neutro, refs in MONETARIAS.items():
            fator, _ = fator_cpi(refs[safra], dolar, cpi)
            out[neutro] = out[neutro] * fator
    return out


# --------------------------------------------------------------------------
# geometria das celulas
# --------------------------------------------------------------------------

def so_poligonos(g) -> MultiPolygon:
    """Partes poligonais de uma geometria. `make_valid` pode devolver uma
    GeometryCollection com linhas soltas, que o H3 nao aceita."""
    polys: list[Polygon] = []
    for p in get_parts(g):
        if p.geom_type == "Polygon":
            polys.append(p)
        elif p.geom_type in ("MultiPolygon", "GeometryCollection"):
            polys.extend(so_poligonos(p).geoms)
    return MultiPolygon(polys)


def uniao_terrestre(bairros: gpd.GeoDataFrame) -> MultiPolygon:
    """Uniao dos poligonos de bairro, com as geometrias invalidas corrigidas."""
    geoms = bairros.geometry.map(lambda g: g if g.is_valid else make_valid(g))
    return so_poligonos(gpd.GeoSeries(geoms, crs=bairros.crs).union_all())


def gerar_celulas(poligono, res: int = RES) -> list[str]:
    """Celulas H3 que TOCAM o poligono (WGS84), unicas e em ordem estavel.

    O `set` nao e enfeite: para MultiPolygon o H3 devolve as celulas de cada parte
    concatenadas, e a celula que toca duas partes (ilha e continente separados por
    um canal estreito — City Island, Inwood/Kingsbridge) vinha repetida. A primeira
    versao da tabela saiu com 38 celulas em dobro por isso.
    """
    shape = h3.geo_to_h3shape(poligono.__geo_interface__)
    return sorted(set(h3.polygon_to_cells_experimental(shape, res, contain="overlap")))


def celula_poligono(c: str) -> Polygon:
    return Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)])


def para_metrico(lon: Iterable[float], lat: Iterable[float]) -> np.ndarray:
    x, y = _PARA_METRICO.transform(np.asarray(lon, dtype=float), np.asarray(lat, dtype=float))
    return np.column_stack([x, y])


def distancia_m(lon1, lat1, lon2, lat2) -> np.ndarray:
    """Distancia euclidiana em UTM 18N (m). Em NYC difere da geodesica em < 0,1%."""
    a, b = para_metrico(lon1, lat1), para_metrico(lon2, lat2)
    return np.hypot(a[:, 0] - b[:, 0], a[:, 1] - b[:, 1])


def anel(c: str, k: int = ANEL_K) -> list[str]:
    return list(h3.grid_disk(c, k))


def area_anel_km2(celulas: Iterable[str], k: int = ANEL_K) -> np.ndarray:
    return np.array([sum(h3.cell_area(n, unit="km^2") for n in anel(c, k)) for c in celulas])


def pontos_para_celulas(lat: Iterable[float], lon: Iterable[float], res: int = RES) -> list[str]:
    return [h3.latlng_to_cell(a, b, res) for a, b in zip(lat, lon, strict=True)]


def contar_no_anel(celulas: Iterable[str], contagem: pd.Series, k: int = ANEL_K) -> np.ndarray:
    """Soma, para cada celula, a contagem da propria celula e das vizinhas ate k.

    `contagem` e indexada por celula (inclusive celulas FORA da tabela — ponto em
    pier ou na divisa conta para o anel da celula terrestre vizinha).
    """
    d = contagem.to_dict()
    return np.array([sum(d.get(n, 0) for n in anel(c, k)) for c in celulas], dtype=float)


def atribuir_por_centroide(pontos: gpd.GeoDataFrame, poligonos: gpd.GeoDataFrame,
                           colunas: list[str], *, candidatos_proximo=None) -> pd.DataFrame:
    """Atributos do poligono que contem cada ponto; sem poligono, o mais proximo.

    O "mais proximo" e calculado em CRS metrico. `candidatos_proximo` (mascara
    booleana sobre `poligonos`) restringe o fallback — ex.: so tracts com terra, para
    a celula costeira nao herdar um tract so de agua.
    """
    pts = pontos[["geometry"]].to_crs(config.CRS_METRICO)
    pol = poligonos[colunas + ["geometry"]].reset_index(drop=True).to_crs(config.CRS_METRICO)
    dentro = gpd.sjoin(pts, pol, how="left", predicate="within")
    # ponto dentro de dois poligonos (bairros sobrepostos no geojson): fica o de
    # menor posicao na tabela de poligonos — deterministico, e a contagem e declarada
    multiplos = int(dentro.index[dentro.index.duplicated()].nunique())
    dentro = (dentro.assign(_ordem=dentro["index_right"].fillna(-1))
              .sort_values("_ordem", kind="stable"))
    dentro = dentro[~dentro.index.duplicated(keep="first")].reindex(pts.index)
    out = dentro[colunas].copy()
    out.attrs["pontos_em_mais_de_um_poligono"] = multiplos
    out["_atribuicao"] = np.where(dentro["index_right"].notna(), "contem", "proximo")
    faltam = out.index[dentro["index_right"].isna()]
    if len(faltam):
        alvo = pol if candidatos_proximo is None else pol[np.asarray(candidatos_proximo)]
        prox = gpd.sjoin_nearest(pts.loc[faltam], alvo, how="left")
        prox = prox[~prox.index.duplicated(keep="first")]
        out.loc[faltam, colunas] = prox[colunas].to_numpy()
    return out


# --------------------------------------------------------------------------
# features por fonte (cada uma devolve colunas alinhadas a `cel`)
# --------------------------------------------------------------------------

def _pontos_celulas(cel: pd.DataFrame) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(index=cel.index,
                            geometry=gpd.points_from_xy(cel["lon"], cel["lat"]),
                            crs=config.CRS_GEO)


def feat_marcos(cel: pd.DataFrame) -> pd.DataFrame:
    from airbnb.external.marcos import AEROPORTOS, CENTRO, MARCOS, TURISTICOS

    def ate(nome: str) -> np.ndarray:
        lat, lon = MARCOS[nome][0], MARCOS[nome][1]
        n = len(cel)
        return distancia_m(cel["lon"], cel["lat"], np.full(n, lon), np.full(n, lat)) / 1000

    return pd.DataFrame({
        "dist_centro_km": ate(CENTRO),
        "dist_aeroporto_km": np.minimum.reduce([ate(a) for a in AEROPORTOS]),
        "dist_marco_km": np.minimum.reduce([ate(m) for m in TURISTICOS]),
    }, index=cel.index)


def feat_metro(cel: pd.DataFrame, estacoes: pd.DataFrame) -> pd.DataFrame:
    from airbnb.external.metro import linhas_de

    xy_est = para_metrico(estacoes["lon"], estacoes["lat"])
    xy_cel = para_metrico(cel["lon"], cel["lat"])
    arvore = cKDTree(xy_est)
    dist, _ = arvore.query(xy_cel)
    vizinhos = arvore.query_ball_point(xy_cel, r=RAIO_METRO_M)
    complexos = estacoes["complex_id"].to_numpy()
    rotas = estacoes["daytime_routes"].reset_index(drop=True)
    return pd.DataFrame({
        "metro_dist_m": dist,
        "metro_n_800m": [len({complexos[j] for j in v}) for v in vizinhos],
        "metro_linhas_800m": [len(linhas_de(rotas.iloc[v])) if v else 0 for v in vizinhos],
    }, index=cel.index).astype({"metro_n_800m": "int64", "metro_linhas_800m": "int64"})


def feat_acs(cel: pd.DataFrame, safra: str, acs: pd.DataFrame,
             tracts: gpd.GeoDataFrame) -> pd.DataFrame:
    """Valores do tract da celula. `acs` indexado por GEOID de 11 digitos."""
    col_geoid = "geoid_2010" if safra == "2019" else "geoid_2020"
    t = tracts.set_index("geoid")
    a = acs.reindex(cel[col_geoid])
    area = t["aland_km2"].reindex(cel[col_geoid]).to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        dens = np.where(area > 0, a["populacao"].to_numpy() / area, np.nan)
        pct_alug = np.where(a["ocupados"] > 0, a["alugados"] / a["ocupados"] * 100, np.nan)
        pct_vago = np.where(a["unidades"] > 0, a["vagos"] / a["unidades"] * 100, np.nan)
    s = f"_{safra}"
    return pd.DataFrame({
        "acs_renda_mediana" + s: a["renda_mediana"].to_numpy(),
        "acs_aluguel_mediano" + s: a["aluguel_mediano"].to_numpy(),
        "acs_pop_densidade" + s: dens,
        "acs_pct_alugado" + s: pct_alug,
        "acs_pct_vago" + s: pct_vago,
        "acs_valor_imovel" + s: a["valor_imovel"].to_numpy(),
    }, index=cel.index)


def feat_poi(cel: pd.DataFrame, pois: pd.DataFrame) -> pd.DataFrame:
    """`pois`: colunas grupo, lat, lon. Contagem no anel k=1 por grupo."""
    pois = pois.copy()
    pois["h3"] = pontos_para_celulas(pois["lat"], pois["lon"])
    out = {}
    for grupo in ("restaurantes", "bares", "cafes", "atracoes", "hoteis", "parques"):
        cont = pois.loc[pois["grupo"] == grupo, "h3"].value_counts()
        out[f"poi_{grupo}_k1"] = contar_no_anel(cel["h3_r9"], cont).astype("int64")
    return pd.DataFrame(out, index=cel.index)


def feat_densidade_por_area(cel: pd.DataFrame, chave_celula: pd.Series,
                            densidade: pd.Series) -> np.ndarray:
    """Densidade da area (delegacia, MODZCTA) que contem a celula."""
    return densidade.reindex(chave_celula.to_numpy()).to_numpy(dtype=float)


# --------------------------------------------------------------------------
# montagem
# --------------------------------------------------------------------------

def base_celulas(bairros: gpd.GeoDataFrame, diag: dict | None = None) -> pd.DataFrame:
    """Uma linha por celula: indices H3, centroide, area, fracao de terra, bairro."""
    uniao = uniao_terrestre(bairros)
    celulas = gerar_celulas(uniao)
    lat, lon = zip(*(h3.cell_to_latlng(c) for c in celulas), strict=True)
    cel = pd.DataFrame({
        "h3_r9": celulas, "lat": lat, "lon": lon,
        "h3_r8": [h3.cell_to_parent(c, config.H3_RES_MAPA) for c in celulas],
        "h3_r6": [h3.cell_to_parent(c, config.H3_RES_CV) for c in celulas],
        "area_km2": [h3.cell_area(c, unit="km^2") for c in celulas],
    })
    # fracao de terra: celula de orla com 5% de terra nao e comparavel a uma interna
    polys = gpd.GeoSeries([celula_poligono(c) for c in celulas], crs=config.CRS_GEO)
    polys_m = polys.to_crs(config.CRS_METRICO)
    uniao_m = gpd.GeoSeries([uniao], crs=config.CRS_GEO).to_crs(config.CRS_METRICO).iloc[0]
    cel["frac_terra"] = np.clip(polys_m.intersection(uniao_m).area.to_numpy()
                                / polys_m.area.to_numpy(), 0, 1)

    b = bairros.copy()
    b["geometry"] = b.geometry.map(lambda g: g if g.is_valid else make_valid(g))
    attr = atribuir_por_centroide(_pontos_celulas(cel), b,
                                  ["neighbourhood", "neighbourhood_group"])
    cel["bairro"] = attr["neighbourhood"].to_numpy()
    cel["distrito"] = attr["neighbourhood_group"].to_numpy()
    cel["bairro_por"] = attr["_atribuicao"].to_numpy()
    if diag is not None:
        diag["centroide_em_mais_de_um_bairro"] = attr.attrs["pontos_em_mais_de_um_poligono"]
        diag["bairro_por_proximidade"] = int((attr["_atribuicao"] == "proximo").sum())
    return cel


def montar() -> tuple[pd.DataFrame, dict, dict]:
    """Constroi a tabela de celulas com todas as fontes disponiveis.

    Devolve (tabela, estado de cada fonte, diagnostico das atribuicoes).
    """
    from airbnb.external import acs, ll18, metro, modzcta, nypd, osm, ruido311, tracts, zillow

    presentes: dict[str, str] = {}
    diag: dict = {}
    bairros = gpd.read_file(BAIRROS)
    cel = base_celulas(bairros, diag)
    pts = _pontos_celulas(cel)
    print(f"    {len(cel):,} celulas r{RES}", flush=True)

    # --- chaves geograficas: tract de cada safra e MODZCTA --------------------
    for safra, col in (("2019", "geoid_2010"), ("atual", "geoid_2020")):
        t = tracts.carregar(safra)
        if t is None:
            cel[col] = pd.NA
            presentes[f"tracts_{safra}"] = "ausente"
            continue
        attr = atribuir_por_centroide(pts, t, ["geoid"], candidatos_proximo=t["ALAND"] > 0)
        cel[col] = attr["geoid"].astype("string").to_numpy()
        presentes[f"tracts_{safra}"] = "ok"
        diag[f"{col}_por_proximidade"] = int((attr["_atribuicao"] == "proximo").sum())
    mz = modzcta.carregar()
    if mz is not None:
        attr = atribuir_por_centroide(pts, mz, ["zip"])
        cel["zip"] = attr["zip"].astype("string").to_numpy()
        presentes["modzcta"] = "ok"
        diag["zip_por_proximidade"] = int((attr["_atribuicao"] == "proximo").sum())
    else:
        cel["zip"] = pd.NA
        presentes["modzcta"] = "ausente"

    # --- ACS ------------------------------------------------------------------
    for safra in SAFRAS:
        a, t = acs.carregar(safra), tracts.carregar(safra)
        if a is not None and t is not None:
            cel = cel.join(feat_acs(cel, safra, a, t))
            presentes[f"acs_{safra}"] = "ok"
        else:
            presentes[f"acs_{safra}"] = "ausente"

    # --- NYPD por delegacia ---------------------------------------------------
    crime = nypd.carregar()
    if crime is not None:
        precintos, dens = crime  # dens: DataFrame (safra, precinto) -> graves_km2, total_km2
        attr = atribuir_por_centroide(pts, precintos, ["precinto"])
        cel["precinto"] = attr["precinto"].to_numpy()
        diag["precinto_por_proximidade"] = int((attr["_atribuicao"] == "proximo").sum())
        for safra in SAFRAS:
            d = dens[dens["safra"] == safra].set_index("precinto")
            if d.empty:
                presentes[f"nypd_{safra}"] = "ausente"
                continue
            # 2019: a 116a delegacia (2023) ainda era parte da 105a -> dens mapeia 116 -> 105
            chave = cel["precinto"].map(lambda p, s=safra: nypd.precinto_na_safra(p, s))
            cel[f"crime_graves_km2_{safra}"] = feat_densidade_por_area(cel, chave, d["graves_km2"])
            cel[f"crime_total_km2_{safra}"] = feat_densidade_por_area(cel, chave, d["total_km2"])
            presentes[f"nypd_{safra}"] = "ok"
    else:
        presentes["nypd"] = "ausente"

    # --- 311 barulho por MODZCTA ---------------------------------------------
    ruido = ruido311.carregar()
    if ruido is not None and mz is not None:
        for safra in SAFRAS:
            d = ruido[ruido["safra"] == safra].set_index("zip")
            if d.empty:
                presentes[f"ruido311_{safra}"] = "ausente"
                continue
            cel[f"ruido_311_km2_{safra}"] = feat_densidade_por_area(cel, cel["zip"], d["por_km2"])
            presentes[f"ruido311_{safra}"] = "ok"
    else:
        presentes["ruido311"] = "ausente"

    # --- Zillow ZORI por MODZCTA ---------------------------------------------
    zori = zillow.carregar()
    if zori is not None and mz is not None:
        z = zillow.por_modzcta(zori, mz).set_index("zip")
        cel["zori_2019"] = z["zori_2019"].reindex(cel["zip"].to_numpy()).to_numpy(dtype=float)
        cel["zori_atual"] = z["zori_atual"].reindex(cel["zip"].to_numpy()).to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            cel["zori_var_pct"] = (cel["zori_atual"] / cel["zori_2019"] - 1) * 100
        presentes["zillow"] = "ok"
    else:
        presentes["zillow"] = "ausente"

    # --- MTA, OSM, marcos -----------------------------------------------------
    est = metro.carregar()
    if est is not None:
        cel = cel.join(feat_metro(cel, est))
        presentes["metro"] = "ok"
    else:
        presentes["metro"] = "ausente"
    pois = osm.carregar()
    if pois is not None:
        cel = cel.join(feat_poi(cel, pois))
        presentes["osm"] = "ok"
    else:
        presentes["osm"] = "ausente"
    cel = cel.join(feat_marcos(cel))
    presentes["marcos"] = "ok"

    # --- LL18: registros ativos por distrito do Conselho (so safra atual) ------
    reg = ll18.carregar()
    if reg is not None:
        distritos, fy = reg
        attr = atribuir_por_centroide(pts, distritos, ["distrito_conselho"])
        cel["distrito_conselho"] = pd.to_numeric(attr["distrito_conselho"]).astype("Int64")
        dens = (fy.set_index("distrito")["ativos_fim"]
                / distritos.set_index("distrito_conselho")["area_km2"])
        cel["ll18_registros_km2_atual"] = dens.reindex(
            cel["distrito_conselho"].astype("float").to_numpy()).to_numpy(dtype=float)
        presentes["ll18"] = "ok"
    else:
        presentes["ll18"] = "ausente"

    # toda coluna do contrato existe, mesmo com a fonte ausente (NaN declarado)
    for nome in FEATURES:
        if nome not in cel.columns:
            cel[nome] = np.nan
    ordem = (["h3_r9", "lat", "lon", "h3_r8", "h3_r6", "area_km2", "frac_terra", "bairro",
              "distrito", "bairro_por", "geoid_2010", "geoid_2020", "zip", "precinto",
              "distrito_conselho"]
             + [c for c in FEATURES if c not in ("lat", "lon")])
    cel = cel.reindex(columns=[c for c in ordem if c in cel.columns])
    for c in ("h3_r9", "h3_r8", "h3_r6", "bairro", "distrito", "bairro_por",
              "geoid_2010", "geoid_2020", "zip"):
        cel[c] = cel[c].astype("string")
    if "precinto" in cel.columns:
        cel["precinto"] = pd.to_numeric(cel["precinto"], errors="coerce").astype("Int64")
    # uma linha por celula: a juncao anuncio x celula e o simulador dependem disso
    repetidas = int(cel["h3_r9"].duplicated().sum())
    if repetidas:
        raise RuntimeError(f"{repetidas} celulas repetidas em h3_r9 — tabela invalida")
    diag["h3_r9_repetidas"] = repetidas
    return cel, presentes, diag


# --------------------------------------------------------------------------
# resumo
# --------------------------------------------------------------------------

def cobertura_anuncios(cel: pd.DataFrame) -> dict:
    """Fracao dos anuncios de cada snapshot cuja celula r9 esta na tabela.

    E o teste que importa: celula que falta e anuncio sem feature.
    """
    celulas = set(cel["h3_r9"])
    fontes = {"2019": config.RAW_KAGGLE, "atual": config.RAW_INSIDE / "listings_resumo.csv"}
    out = {}
    for safra, caminho in fontes.items():
        if not caminho.exists():
            out[safra] = "arquivo ausente"
            continue
        d = pd.read_csv(caminho, usecols=["latitude", "longitude"]).dropna()
        c = pontos_para_celulas(d["latitude"], d["longitude"])
        dentro = np.array([x in celulas for x in c])
        out[safra] = {"anuncios": int(len(d)), "na_tabela": int(dentro.sum()),
                      "pct_na_tabela": round(float(dentro.mean() * 100), 3),
                      "celulas_com_anuncio": int(len(set(np.array(c)[dentro])))}
    return out


def resumo(cel: pd.DataFrame, presentes: dict, diag: dict | None = None) -> dict:
    from airbnb.external.cpi import fator_cpi

    cobertura = {c: round(float(cel[c].notna().mean() * 100), 2) for c in FEATURES}
    estat = {}
    for c in FEATURES:
        s = pd.to_numeric(cel[c], errors="coerce").dropna()
        if s.empty:
            estat[c] = None
            continue
        q = s.quantile([0.0, 0.25, 0.5, 0.75, 1.0]).round(4).tolist()
        estat[c] = {"n": int(len(s)), "media": round(float(s.mean()), 4),
                    "min": q[0], "p25": q[1], "mediana": q[2], "p75": q[3], "max": q[4]}
    try:
        fator, mes_para = fator_cpi(config.SNAPSHOT_2019[:7])
        cpi = {"fator": round(fator, 6), "de": config.SNAPSHOT_2019[:7], "para": mes_para,
               "serie": "CUURS12ASA0 (BLS)", "arquivo": "data/processed/cpi_ny.parquet"}
    except FileNotFoundError:
        cpi = "cpi_ny.parquet ausente"
    return {
        "gerado_por": "python -m airbnb.features.celulas",
        "resolucao_h3": RES,
        "n_celulas": int(len(cel)),
        "h3_r9_unicas": int(cel["h3_r9"].nunique()),
        "area_total_celulas_km2": round(float(cel["area_km2"].sum()), 1),
        "area_terra_km2": round(float((cel["area_km2"] * cel["frac_terra"]).sum()), 1),
        "celulas_por_distrito": cel["distrito"].value_counts().to_dict(),
        "diagnostico_atribuicao": diag or {},
        "fontes": presentes,
        "cpi": cpi,
        "cobertura_anuncios": cobertura_anuncios(cel),
        "cobertura_pct_nao_nulo": cobertura,
        "estatisticas": estat,
        "features": FEATURES,
        "features_local_neutras": FEATURES_LOCAL_NEUTRAS,
    }


def main() -> None:
    print("==> celulas H3 r9", flush=True)
    cel, presentes, diag = montar()
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    cel.to_parquet(SAIDA, index=False)
    r = resumo(cel, presentes, diag)
    RESUMO.write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str) + "\n",
                      encoding="utf-8")
    print(f"    {len(cel):,} celulas -> {SAIDA.relative_to(config.RAIZ).as_posix()}")
    print(f"    fontes: {presentes}")
    for k, v in r["cobertura_anuncios"].items():
        print(f"    anuncios {k}: {v}")
    baixa = {k: v for k, v in r["cobertura_pct_nao_nulo"].items() if v < 90}
    if baixa:
        print(f"    cobertura < 90%: {baixa}")


if __name__ == "__main__":
    main()
