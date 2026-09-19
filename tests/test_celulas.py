"""Testes das celulas H3 r9 — sem rede e sem dado real (salvo os marcados `dados`).

Invariantes protegidas:
  * uma linha por h3_r9 (a juncao anuncio x celula e o simulador dependem disso);
  * cobertura por "overlap": celula que so toca o poligono entra;
  * anel k=1 = a celula + 6 vizinhas, somando contagem de celula fora da tabela;
  * distancia metrica certa (UTM 18N contra a geodesica);
  * atribuicao por centroide deterministica, com fallback ao mais proximo;
  * `features_da_safra` devolve as MESMAS colunas neutras nas duas safras.
"""

from __future__ import annotations

import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import pytest
from pyproj import Geod
from shapely.geometry import MultiPolygon, box

from airbnb import config
from airbnb.features import celulas as C

# quadrado de ~1,1 km x 0,85 km em Midtown
QUADRADO = box(-73.990, 40.750, -73.980, 40.760)


def test_celulas_de_poligono_pequeno():
    cel = C.gerar_celulas(QUADRADO)
    assert len(cel) == len(set(cel)) > 0
    assert all(h3.get_resolution(c) == config.H3_RES_FEATURES for c in cel)
    # overlap: toda celula toca o poligono, e a celula de cada canto interno esta la
    assert all(C.celula_poligono(c).intersects(QUADRADO) for c in cel)
    for lon, lat in [(-73.9899, 40.7501), (-73.9801, 40.7599), (-73.985, 40.755)]:
        assert h3.latlng_to_cell(lat, lon, config.H3_RES_FEATURES) in cel


def test_multipoligono_nao_repete_celula():
    """Regressao: duas partes separadas por um canal estreito tocam a mesma
    celula; o H3 a devolvia uma vez por parte (38 celulas em dobro na v1)."""
    ilha = box(-73.9850, 40.7500, -73.9800, 40.7550)
    continente = box(-73.97995, 40.7500, -73.9750, 40.7550)  # canal de ~4 m
    cel = C.gerar_celulas(MultiPolygon([ilha, continente]))
    assert len(cel) == len(set(cel))


def test_anel_k1_tem_sete_celulas_e_area_de_sete_hexagonos():
    c = h3.latlng_to_cell(40.755, -73.985, config.H3_RES_FEATURES)
    anel = C.anel(c)
    assert len(anel) == 7 and c in anel
    area = C.area_anel_km2([c])[0]
    assert area == pytest.approx(7 * h3.cell_area(c, unit="km^2"), rel=0.01)
    assert 0.6 < area < 0.9  # ~0,74 km2 em NYC


def test_contagem_no_anel_inclui_vizinha_fora_da_tabela():
    c = h3.latlng_to_cell(40.755, -73.985, config.H3_RES_FEATURES)
    viz = [n for n in h3.grid_disk(c, 1) if n != c]
    longe = h3.latlng_to_cell(40.60, -74.10, config.H3_RES_FEATURES)
    cont = pd.Series({c: 2, viz[0]: 3, viz[5]: 1, longe: 50})
    assert C.contar_no_anel([c], cont)[0] == 6
    assert C.contar_no_anel([viz[0]], cont)[0] >= 5  # c e viz[0] sao vizinhas


def test_pontos_para_celulas_bate_com_h3():
    lat, lon = [40.7580, 40.6413], [-73.9855, -73.7781]
    assert C.pontos_para_celulas(lat, lon) == [h3.latlng_to_cell(a, b, 9)
                                                for a, b in zip(lat, lon, strict=True)]


def test_distancia_metrica_contra_geodesica():
    """Times Square -> JFK: UTM 18N tem de bater com a geodesica WGS84 em 0,1%."""
    geod = Geod(ellps="WGS84")
    _, _, ref = geod.inv(-73.9858, 40.7575, -73.778889, 40.639722)
    d = C.distancia_m([-73.9858], [40.7575], [-73.778889], [40.639722])[0]
    assert d == pytest.approx(ref, rel=1e-3)
    assert 21_000 < d < 22_500


def _quadrados() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"nome": ["A", "B", "C"]},
        geometry=[box(-74.00, 40.70, -73.99, 40.71),      # A
                  box(-73.99, 40.70, -73.98, 40.71),      # B
                  box(-73.995, 40.70, -73.985, 40.705)],  # C sobrepoe A e B
        crs=config.CRS_GEO)


def test_atribuicao_por_centroide_com_fallback_e_desempate():
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy(
        [-73.997, -73.982, -73.993, -73.950], [40.708, 40.708, 40.702, 40.708]),
        crs=config.CRS_GEO)
    r = C.atribuir_por_centroide(pts, _quadrados(), ["nome"])
    assert r["nome"].tolist()[:2] == ["A", "B"]
    # ponto dentro de A e de C: fica o de menor posicao (A), de forma deterministica
    assert r["nome"].iloc[2] == "A" and r.attrs["pontos_em_mais_de_um_poligono"] == 1
    # ponto fora de tudo: o poligono mais proximo (B, a leste)
    assert r["nome"].iloc[3] == "B" and r["_atribuicao"].iloc[3] == "proximo"
    assert len(r) == len(pts) and r.index.equals(pts.index)


def _tabela_sintetica() -> pd.DataFrame:
    celulas = C.gerar_celulas(QUADRADO)[:3]
    df = pd.DataFrame({"h3_r9": celulas})
    for i, nome in enumerate(C.FEATURES):
        df[nome] = np.arange(len(df), dtype=float) + i * 10
        if nome.endswith("_atual"):
            df[nome] += 1000  # valor da safra atual distinguivel do de 2019
    return df


def test_features_da_safra_tem_colunas_neutras_identicas():
    df = _tabela_sintetica()
    f19, fat = C.features_da_safra(df, "2019"), C.features_da_safra(df, "atual")
    assert list(f19.columns) == list(fat.columns) == C.FEATURES_LOCAL_NEUTRAS
    assert f19.index.name == fat.index.name == "h3_r9"
    assert f19.index.tolist() == df["h3_r9"].tolist()
    assert {"lat", "lon"} <= set(C.FEATURES_LOCAL_NEUTRAS)
    # a coluna neutra vem da safra pedida
    assert (fat["acs_renda_mediana"] - f19["acs_renda_mediana"] >= 1000 - 1e-9).all()
    assert (fat["metro_dist_m"] == f19["metro_dist_m"]).all()  # feature sem safra
    with pytest.raises(ValueError):
        C.features_da_safra(df, "2026")


def test_features_da_safra_deflaciona_so_as_monetarias():
    df = _tabela_sintetica()
    serie = pd.DataFrame({"mes": [f"2024-{m:02d}" for m in range(1, 13)] + ["2026-06", "2019-07"],
                          "indice": [120.0] * 12 + [130.0, 100.0]})
    nominal = C.features_da_safra(df, "atual")
    real = C.features_da_safra(df, "atual", dolar="2019-07", cpi=serie)
    assert real["acs_renda_mediana"].tolist() == pytest.approx(
        (nominal["acs_renda_mediana"] * 100 / 120).tolist())
    assert real["zori"].tolist() == pytest.approx((nominal["zori"] * 100 / 130).tolist())
    assert real["metro_dist_m"].equals(nominal["metro_dist_m"])


def test_listas_por_safra_mapeiam_para_a_mesma_lista_neutra():
    assert len(C.FEATURES_LOCAL_2019) == len(C.FEATURES_LOCAL_ATUAL) == len(
        C.FEATURES_LOCAL_NEUTRAS)
    for n, a, b in zip(C.FEATURES_LOCAL_NEUTRAS, C.FEATURES_LOCAL_2019,
                       C.FEATURES_LOCAL_ATUAL, strict=True):
        assert a in (n, f"{n}_2019") and b in (n, f"{n}_atual")
        assert a in C.FEATURES and b in C.FEATURES


def test_informacao_do_futuro_fica_fora_das_listas_de_modelo():
    for proibida in ("zori_var_pct", "ll18_registros_km2_atual"):
        assert proibida in C.FEATURES
        assert proibida not in C.FEATURES_LOCAL_2019 + C.FEATURES_LOCAL_ATUAL


def test_fonte_da_feature_usa_os_rotulos_curtos():
    for n in C.FEATURES_LOCAL_NEUTRAS:
        assert C.fonte_da_feature(n) in C.FONTES_ROTULO
    assert C.fonte_da_feature("acs_renda_mediana") == "ACS"
    assert C.fonte_da_feature("crime_graves_km2") == "NYPD"
    assert C.fonte_da_feature("ruido_311_km2") == "311"
    assert C.fonte_da_feature("zori") == "Zillow"
    assert C.fonte_da_feature("metro_dist_m") == "MTA"
    assert C.fonte_da_feature("poi_bares_k1") == "OSM"
    assert C.fonte_da_feature("dist_centro_km") == "marcos"
    with pytest.raises(KeyError):
        C.fonte_da_feature("nao_existe")


def test_todo_metadado_de_feature_esta_completo():
    for nome, meta in C.FEATURES.items():
        for k in ("fonte", "safra", "unidade", "descricao", "transformacao"):
            assert meta.get(k), (nome, k)


# --- tabela real (pulada quando ausente, como no CI) -------------------------------


@pytest.mark.dados
@pytest.mark.skipif(not C.SAIDA.exists(), reason="celulas_r9.parquet ausente")
def test_tabela_real_tem_uma_linha_por_celula():
    df = pd.read_parquet(C.SAIDA)
    assert df["h3_r9"].is_unique
    assert 6_500 < len(df) < 9_500
    assert set(C.FEATURES) <= set(df.columns)
    assert df["distrito"].isin(config.DISTRITOS).all()
    for safra in C.SAFRAS:
        f = C.features_da_safra(df, safra)
        assert f.index.is_unique and list(f.columns) == C.FEATURES_LOCAL_NEUTRAS
