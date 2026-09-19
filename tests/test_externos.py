"""Testes das fontes externas — sem rede e sem dado real.

O que se protege aqui e o que produziria numero errado SEM erro visivel:
  * codigo-sentinela do Census virando renda de -666 milhoes de dolares;
  * janela de 12 meses com buraco ou dia repetido na emenda Historic/Current;
  * contagem mensal (fallback) que nao soma o mesmo que a janela inteira;
  * a 116a delegacia de 2023 contando em 2019 com a area atual da 105a;
  * ZIP do 311 que nao chega ao MODZCTA certo;
  * POI de way/relation sem coordenada, ou envelope do Overpass na ordem errada;
  * deflator que cai no mes errado sem avisar.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from airbnb import config
from airbnb.external import acs, cpi, janelas, ll18, marcos, nypd, osm, ruido311, socrata, zillow
from airbnb.external._xlsx import ler_abas

# --- ACS ------------------------------------------------------------------


def test_sentinelas_do_acs_viram_nan():
    s = pd.Series(["-666666666", "52000", "", "-222222222", "0", "-999999999", "250001"])
    r = acs.limpar_sentinelas(s)
    assert r.isna().tolist() == [True, False, True, True, False, True, False]
    assert r.iloc[1] == 52000 and r.iloc[4] == 0


def test_bloco_de_tracts_descarta_pontas_partidas():
    """O trecho vem de um Range: primeira e ultima linha podem estar cortadas."""
    texto = ("0000US3500501|1|2\n"                      # ponta partida
             "1400000US35001000100|10|1\n"
             "1400000US36005000100|20|2\n"
             "1400000US36061000200|30|3\n"
             "1400000US37001000100|40|4\n"
             "1400000US3700")                           # ponta partida
    linhas = acs.extrair_bloco(texto, "1400000US36")
    assert [x.split("|")[0] for x in linhas] == ["1400000US36005000100", "1400000US36061000200"]


def test_parse_tabela_renomeia_e_tira_prefixo_do_geoid():
    cab = "GEO_ID|B25003_E001|B25003_M001|B25003_E002|B25003_M002|B25003_E003|B25003_M003"
    linhas = ["1400000US36061000100|100|5|40|3|60|4",
              "1400000US36061000200|-666666666|-222222222|0|0|0|0"]
    t = acs.parse_tabela(cab, linhas, acs.TABELAS["b25003"])
    assert t["geoid"].tolist() == ["36061000100", "36061000200"]
    assert t["ocupados"].iloc[0] == 100 and t["alugados"].iloc[0] == 60
    assert np.isnan(t["ocupados"].iloc[1])


def test_limites_da_busca_binaria_do_acs():
    assert acs.PREFIXO == "1400000US36" and acs.LIMITE == "1400000US37"
    assert acs.PREFIXO < acs.LIMITE


# --- janelas e Socrata ------------------------------------------------------


def test_janelas_de_12_meses_terminam_na_vespera_do_snapshot():
    assert janelas.JANELAS == {"2019": ("2018-07-08", "2019-07-07"),
                               "atual": ("2025-06-14", "2026-06-13")}


def test_meses_particionam_a_janela_sem_buraco_nem_sobreposicao():
    partes = socrata.meses("2018-07-08", "2019-07-07")
    assert partes[0][0] == "2018-07-08" and partes[-1][1] == "2019-07-07"
    dias = pd.DatetimeIndex([])
    for a, b in partes:
        dias = dias.append(pd.date_range(a, b, freq="D"))
    assert dias.is_unique and len(dias) == 365


class _Resp:
    def __init__(self, texto: str):
        self.content = texto.encode()


def test_contagem_mensal_soma_o_mesmo_que_a_janela(monkeypatch):
    """Se a janela inteira nao responde, a soma dos meses tem de ser a contagem."""
    chamadas = []

    def falso_obter(url, params=None, **kw):
        chamadas.append(params["$where"])
        if len(chamadas) == 1:  # janela inteira: o servidor nao responde
            raise RuntimeError("timeout")
        return _Resp('"addr_pct_cd","law_cat_cd","n"\n"1","FELONY","2"\n"1","VIOLATION","1"\n'
                     '"5","FELONY","3"\n')

    monkeypatch.setattr(socrata, "obter", falso_obter)
    df, meta = socrata.contar_agrupado("x", "y", campo_data="rpt_dt", ini="2019-01-01",
                                       fim="2019-03-31", grupo=["addr_pct_cd", "law_cat_cd"])
    assert meta["consultas"] == 3  # jan, fev, mar
    felony_1 = df[(df.addr_pct_cd == "1") & (df.law_cat_cd == "FELONY")]["n"].item()
    assert felony_1 == 6 and meta["total"] == 18


def test_where_soql_fecha_o_ultimo_dia():
    w = janelas.where_soql("rpt_dt", "2025-06-14", "2025-12-31")
    assert w == "rpt_dt between '2025-06-14T00:00:00' and '2025-12-31T23:59:59'"


# --- NYPD -------------------------------------------------------------------


def test_janela_atual_emenda_historic_e_current_sem_buraco():
    t = nypd.trechos("atual")
    assert [x[0] for x in t] == [nypd.HISTORIC, nypd.CURRENT]
    assert t[0][2] == nypd.FIM_HISTORIC and t[1][1] == "2026-01-01"
    assert nypd.trechos("2019") == [(nypd.HISTORIC, "2018-07-08", "2019-07-07")]


def test_delegacia_116_era_parte_da_105_em_2019():
    assert nypd.precinto_na_safra(116, "2019") == 105
    assert nypd.precinto_na_safra(116, "atual") == 116
    assert nypd.precinto_na_safra(14, "2019") == 14


def test_densidade_2019_soma_a_area_da_116_na_105():
    prec = gpd.GeoDataFrame({"precinto": [105, 116], "area_km2": [30.0, 10.0]},
                            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs=config.CRS_GEO)
    tab = pd.DataFrame({"addr_pct_cd": ["105", "105", "105", "116"],
                        "law_cat_cd": ["FELONY", "VIOLATION", "FELONY", "FELONY"],
                        "n": [40, 40, 10, 5], "safra": ["2019", "2019", "atual", "atual"]})
    d = nypd.densidades(tab, prec).set_index(["safra", "precinto"])
    assert d.loc[("2019", 105), "area_km2"] == 40.0
    assert d.loc[("2019", 105), "total_km2"] == pytest.approx(80 / 40)
    assert ("2019", 116) not in d.index
    assert d.loc[("atual", 116), "graves_km2"] == pytest.approx(5 / 10)


# --- 311 e MODZCTA ------------------------------------------------------------


def _modzcta_sintetico() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"zip": ["10001", "10002"],
                             "zctas": [["10001", "10118", "10119"], ["10002"]],
                             "area_km2": [2.0, 4.0]},
                            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs=config.CRS_GEO)


@pytest.mark.parametrize("entrada,esperado", [
    ("10001", "10001"), ("10001-1234", "10001"), ("10001.0", "10001"), (" 10002", "10002"),
    ("N/A", None), ("1000", None), (None, None)])
def test_normaliza_zip_do_311(entrada, esperado):
    assert ruido311.normalizar_zip(entrada) == esperado


def test_zip_membro_do_modzcta_soma_no_modzcta():
    tab = pd.DataFrame({"incident_zip": ["10001", "10118", "10002", "99999"],
                        "n": [10, 6, 8, 100], "safra": ["2019"] * 4})
    d = ruido311.por_modzcta(tab, _modzcta_sintetico()).set_index("zip")
    assert d.loc["10001", "n"] == 16 and d.loc["10001", "por_km2"] == 8.0
    assert d.loc["10002", "por_km2"] == 2.0
    assert d["n"].sum() == 24  # o 99999 fica fora (e e contado no manifesto)


# --- Overpass ---------------------------------------------------------------


def test_parse_overpass_usa_centro_de_way_e_descarta_sem_coordenada():
    dados = {"elements": [
        {"type": "node", "id": 1, "lat": 40.7, "lon": -74.0, "tags": {"amenity": "cafe"}},
        {"type": "way", "id": 2, "center": {"lat": 40.8, "lon": -73.9},
         "tags": {"amenity": "cafe"}},
        {"type": "relation", "id": 3, "tags": {"amenity": "cafe"}},
    ]}
    df = osm.parse(dados, "cafes", "amenity")
    assert df["id"].tolist() == [1, 2]
    assert df.loc[1, ["lat", "lon"]].tolist() == [40.8, -73.9]


def test_consulta_overpass_usa_envelope_sul_oeste_norte_leste():
    s, w, n, e = osm.envelope()
    assert s < n and w < e
    lon0, lat0, lon1, lat1 = config.NYC_BBOX
    assert s < lat0 and n > lat1 and w < lon0 and e > lon1  # com folga
    q = osm.consulta("amenity", ("bar", "pub"))
    assert f"({s},{w},{n},{e})" in q and '"^(bar|pub)$"' in q and "out center" in q


# --- CPI --------------------------------------------------------------------


def _serie(meses: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({"mes": list(meses), "indice": list(meses.values())})


def test_parse_fred_descarta_mes_sem_valor():
    df = cpi.parse_fred("observation_date,CUURA101SA0\n2025-09-01,340.0\n"
                        "2025-10-01,.\n2025-11-01,341.5\n")
    assert df["mes"].tolist() == ["2025-09", "2025-11"]


def test_parse_bls_ignora_media_anual():
    dados = {"Results": {"series": [{"data": [
        {"year": "2019", "period": "M13", "value": "273.6"},
        {"year": "2019", "period": "M07", "value": "278.817"},
        {"year": "2019", "period": "M08", "value": "-"}]}]}}
    df = cpi.parse_bls(dados)
    assert df.to_dict("records") == [{"mes": "2019-07", "indice": 278.817}]


def test_fator_cpi_e_razao_dos_indices():
    s = _serie({"2019-07": 200.0, "2026-06": 260.0, "2026-07": 262.0})
    fator, mes = cpi.fator_cpi("2019-07", None, s)
    assert mes == "2026-06" and fator == pytest.approx(1.3)
    assert cpi.fator_cpi("2026-06", "2019-07", s)[0] == pytest.approx(1 / 1.3)


def test_fator_cpi_cai_no_ultimo_mes_e_declara_qual():
    s = _serie({"2019-07": 200.0, "2026-04": 250.0})
    fator, mes = cpi.fator_cpi("2019-07", None, s)
    assert mes == "2026-04" and fator == pytest.approx(1.25)


def test_fator_cpi_media_anual_exige_doze_meses():
    s = _serie({f"2019-{m:02d}": 100.0 + m for m in range(1, 13)} | {"2026-06": 150.0})
    fator, _ = cpi.fator_cpi("2019", "2026-06", s)
    assert fator == pytest.approx(150.0 / 106.5)
    with pytest.raises(ValueError, match="12 meses"):
        cpi.fator_cpi("2019", "2026-06", s[s["mes"] != "2019-05"])


def test_fator_cpi_falha_alto_em_mes_ausente():
    s = _serie({"2019-07": 200.0, "2025-09": 250.0, "2025-11": 251.0})
    with pytest.raises(KeyError, match="2025-10"):
        cpi.fator_cpi("2019-07", "2025-10", s)


# --- Zillow ---------------------------------------------------------------------


def test_coluna_do_mes_exata_ou_mais_proxima():
    cols = ["RegionName", "2019-06-30", "2019-07-31", "2026-04-30"]
    assert zillow.coluna_do_mes(cols, "2019-07") == "2019-07-31"
    assert zillow.coluna_do_mes(cols, "2026-06") == "2026-04-30"


def test_zori_do_modzcta_cai_na_media_dos_membros():
    zori = pd.DataFrame({"zip": ["10118", "10119", "10002"],
                         "zori_2019": [3000.0, 3200.0, 2500.0],
                         "zori_atual": [4000.0, np.nan, 3100.0]})
    z = zillow.por_modzcta(zori, _modzcta_sintetico()).set_index("zip")
    assert z.loc["10001", "zori_2019"] == 3100.0 and z.loc["10001", "origem"] == "membros"
    assert z.loc["10001", "zori_atual"] == 4000.0
    assert z.loc["10002", "origem"] == "proprio"


# --- LL18 e leitor de XLSX -----------------------------------------------------------


def _xlsx(linhas: list[list[str]]) -> bytes:
    """XLSX minimo (uma aba, textos inline) montado em memoria."""
    def cel(v):
        return f'<c t="inlineStr"><is><t>{v}</t></is></c>'
    corpo = "".join(f"<row>{''.join(cel(v) for v in lin)}</row>" for lin in linhas)
    m = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{m}" xmlns:r="{r}"><sheets>'
                   '<sheet name="1. Active Registrations" sheetId="1" r:id="rId1"/>'
                   "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                   'relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
                   "</Relationships>")
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{m}"><sheetData>{corpo}'
                   "</sheetData></worksheet>")
    return buf.getvalue()


def test_tabela_de_registros_ativos_por_distrito():
    conteudo = _xlsx([["Figure 1: Short-Term Rental Registrations Active"],
                      ["Council district", "Number of active registrations as of June 30",
                       "Number active at any time"],
                      ["1", "37", "42"], ["2", "51", "57"], ["Total", "88", "99"]])
    t = ll18.tabela_ativos(ler_abas(conteudo))
    assert t.to_dict("records") == [{"distrito": 1, "ativos_fim": 37, "ativos_periodo": 42},
                                    {"distrito": 2, "ativos_fim": 51, "ativos_periodo": 57}]


def test_linha_do_tempo_da_ll18_bate_com_config():
    datas = [d for d, _ in ll18.LINHA_DO_TEMPO]
    assert datas == sorted(datas) and config.LL18_VIGENCIA in datas


# --- manifesto ----------------------------------------------------------------


def test_arquivo_pulado_preserva_a_proveniencia_original():
    from airbnb.external.coletar import preservar

    anterior = {"artefatos": [{"arquivo": "a.csv", "sha256": "x" * 64, "bytes": 10,
                               "acessado_em": "2026-09-18T10:00:00Z", "consultas": [1]},
                              {"arquivo": "b.csv", "sha256": "y" * 64, "bytes": 5,
                               "acessado_em": "2026-09-18T10:00:00Z"}]}
    novo = {"artefatos": [{"arquivo": "a.csv", "sha256": "x" * 64, "bytes": 10,
                           "acessado_em": "2026-09-19T00:00:00Z", "nota": "ja existia"},
                          {"arquivo": "b.csv", "sha256": "z" * 64, "bytes": 6,
                           "acessado_em": "2026-09-19T00:00:00Z", "nota": "ja existia"}]}
    a, b = preservar(anterior, novo)["artefatos"]
    assert a["acessado_em"] == "2026-09-18T10:00:00Z" and a["consultas"] == [1]
    assert a["verificado_em"] == "2026-09-19T00:00:00Z"
    assert b["sha256"] == "z" * 64 and b["hash_diverge_do_registro_anterior"] == "y" * 64


# --- marcos -------------------------------------------------------------------


def test_marcos_dentro_de_nyc_e_haversine_conhecida():
    lon0, lat0, lon1, lat1 = config.NYC_BBOX
    for nome, (lat, lon, _, _) in marcos.MARCOS.items():
        assert lat0 <= lat <= lat1 and lon0 <= lon <= lon1, nome
    # 1 grau de latitude ~ 111,2 km na esfera de raio medio
    assert marcos.haversine_m(40.0, -74.0, 41.0, -74.0) == pytest.approx(111_195, rel=1e-3)


# --- resultados reais (pulados quando ausentes, como no CI) ------------------------

MANIFESTO = config.EXTERNAL / "_manifesto_externos.json"


@pytest.mark.dados
@pytest.mark.skipif(not MANIFESTO.exists(), reason="coleta externa nao executada")
def test_manifesto_tem_hash_de_todo_artefato():
    m = json.loads(MANIFESTO.read_text(encoding="utf-8"))
    for chave, f in m["fontes"].items():
        if f.get("estado") != "ok":
            continue
        for a in f["artefatos"]:
            assert len(a["sha256"]) == 64 and a["bytes"] > 0, (chave, a["arquivo"])
            assert (config.RAIZ / Path(a["arquivo"])).exists(), a["arquivo"]


@pytest.mark.dados
@pytest.mark.skipif(not cpi.SAIDA.exists(), reason="cpi_ny.parquet ausente")
def test_cpi_real_tem_os_meses_dos_snapshots():
    fator, mes = cpi.fator_cpi()
    assert mes == "2026-06" and 1.2 < fator < 1.4
