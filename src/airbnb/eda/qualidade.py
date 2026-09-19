"""Perguntas da equipe e correcoes da v0 — respondidas com numero, nao com opiniao.

Duas saidas versionadas (resultado, nao dado):

* `data/processed/_perguntas_equipe.json` — Q1 a Q6, as perguntas anotadas em
  `reports/v0/Análise.txt` (id unico? campos vazios? host_id x host_name?
  coordenada dentro do bairro? price e por noite? reviews_per_month e do
  anuncio ou do anfitriao?).
* `data/processed/_correcoes_v0.json` — o que a v0 mediu e o que de fato mede:
  (a) "taxa de ocupacao" = 1 - availability_365/365; (b) drop do id antes do
  drop_duplicates; (c) dropna por `name`; (d) Pearson em variavel de cauda pesada.

Nenhum nome de anfitriao, id de anuncio ou texto livre sai daqui — so contagens
e estatisticas (invariante 9: os JSON sao publicos no repositorio).

Uso:
    python -m airbnb.eda.qualidade        # (tambem roda ao fim de clean.pipeline)
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy import stats

from airbnb import config
from airbnb.clean import derivadas as dv
from airbnb.clean import pipeline as pl
from airbnb.schema import (
    COL_AVALIACOES_MES,
    COL_DIAS_ULTIMA_AVALIACAO,
    COL_DISPONIBILIDADE_365,
    COL_DISTRITO,
    COL_HOST_ID,
    COL_ID,
    COL_MIN30,
    COL_MIN_NOITES,
    COL_N_AVALIACOES,
    COL_OCUPACAO_L365D,
    COL_OCUPACAO_MODELO,
    COL_PRECO,
    COL_PRECO_VALIDO,
)

SAIDA_PERGUNTAS = config.PROCESSED / "_perguntas_equipe.json"
SAIDA_CORRECOES = config.PROCESSED / "_correcoes_v0.json"
ARQ_GEOJSON = config.RAW_INSIDE / "neighbourhoods.geojson"
ARQ_REVIEWS = config.RAW_INSIDE / "reviews_resumo.csv"

R19, R26 = config.ROTULO_2019, config.ROTULO_ATUAL

#: Numeros publicados pela v0 (reports/v0/airbnb-nyc-dashboard-slide.html, constante STATS).
V0 = {
    "linhas_brutas": 48_895, "linhas_limpas": 48_868, "ocupacao_geral": 0.691,
    "ocupacao_por_distrito": {"Bronx": 0.546, "Brooklyn": 0.725, "Manhattan": 0.693,
                              "Queens": 0.604, "Staten Island": 0.453},
    "rendimento_por_distrito": {"Brooklyn": 86.3, "Manhattan": 124.0, "Queens": 57.7,
                                "Staten Island": 48.2, "Bronx": 45.2},
    "pct_anuncios_host_multiplo": 33.9, "corr_preco_avaliacoes_pearson": -0.05,
}
V0_NUMERICAS = ["price", "minimum_nights", "number_of_reviews", "reviews_per_month",
                "calculated_host_listings_count", "availability_365"]
#: Deslocamento de privacidade declarado pelo Inside Airbnb: 0–450 pes (~150 m).
DESLOCAMENTO_M = 150


def _r(x, n: int = 4):
    """Arredonda para JSON; NaN/None viram None."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    if isinstance(x, (np.integer,)):
        return int(x)
    return round(float(x), n)


def _pct(parte, todo, n: int = 4):
    return None if not todo else round(float(parte) / float(todo), n)


# --- Q1: id unico e duplicados ------------------------------------------------------------------


def q1_duplicados(bruto: pd.DataFrame, snapshot: str) -> dict:
    ids = bruto[COL_ID]
    sem_id = bruto.drop(columns=[c for c in (COL_ID, "listing_url") if c in bruto.columns])
    lat, lon = bruto["latitude"], bruto["longitude"]
    chave_geo = [COL_HOST_ID, "latitude", "longitude"]
    mesmo_ponto = bruto.duplicated(subset=chave_geo, keep=False)
    grupos_ponto = bruto[mesmo_ponto].groupby(chave_geo).size()
    preco = dv.parse_preco(bruto["price"])
    b = bruto.assign(_preco=preco)
    mesmo_ponto_preco = b.duplicated(subset=[*chave_geo, "_preco"], keep=False)
    mesmo_ponto_nome = b.duplicated(subset=[*chave_geo, "name"], keep=False) & b["name"].notna()
    mesmo_host_nome = b.duplicated(subset=[COL_HOST_ID, "name"], keep=False) & b["name"].notna()
    # mesmo host no mesmo PONTO e o esperado para hotel (localizacao publica, sem
    # deslocamento); para residencia o Airbnb desloca cada anuncio de forma independente
    rt = bruto.loc[mesmo_ponto, "room_type"].value_counts().to_dict()
    return {
        "linhas": len(bruto),
        "ids_distintos": int(ids.nunique()),
        "id_unico": bool(ids.is_unique),
        "ids_repetidos": int(ids.duplicated().sum()),
        "duplicatas_perfeitas_todas_colunas": int(bruto.duplicated().sum()),
        "duplicatas_perfeitas_sem_id": int(sem_id.duplicated().sum()),
        "semanticas": {
            "anuncios_mesmo_host_mesma_coordenada": int(mesmo_ponto.sum()),
            "grupos_mesmo_host_mesma_coordenada": int(len(grupos_ponto)),
            "maior_grupo": int(grupos_ponto.max()) if len(grupos_ponto) else 0,
            "room_type_desses_anuncios": rt,
            "anuncios_mesmo_host_coordenada_e_preco": int(mesmo_ponto_preco.sum()),
            "anuncios_mesmo_host_coordenada_e_nome": int(mesmo_ponto_nome.sum()),
            "anuncios_mesmo_host_e_nome": int(mesmo_host_nome.sum()),
            "coordenadas_distintas": int(pd.MultiIndex.from_arrays([lat, lon]).nunique()),
        },
    }


# --- Q2: campos vazios -----------------------------------------------------------------------------


def _equivalencia(nulo: pd.Series, sem_avaliacao: pd.Series) -> dict:
    return {
        "nulos": int(nulo.sum()),
        "nulo_e_sem_avaliacao": int((nulo & sem_avaliacao).sum()),
        "nulo_com_avaliacao": int((nulo & ~sem_avaliacao).sum()),
        "preenchido_sem_avaliacao": int((~nulo & sem_avaliacao).sum()),
        "estrutural": bool(((nulo & ~sem_avaliacao).sum() == 0) and ((~nulo & sem_avaliacao).sum() == 0)),
    }


def q2_vazios(bruto: pd.DataFrame, snapshot: str) -> dict:
    n = bruto.isna().sum()
    com_nulo = {c: int(v) for c, v in n[n > 0].sort_values(ascending=False).items()}
    sem_av = bruto[COL_N_AVALIACOES].eq(0)
    estr = {c: _equivalencia(bruto[c].isna(), sem_av)
            for c in ("last_review", "reviews_per_month", "first_review", "review_scores_rating",
                      "review_scores_accuracy", "review_scores_value")
            if c in bruto.columns}
    out = {
        "colunas_com_nulo": com_nulo,
        "colunas_100pct_nulas": [c for c, v in n.items() if v == len(bruto)],
        "sem_avaliacao": int(sem_av.sum()),
        "nulos_estruturais_de_avaliacao": estr,
    }
    if snapshot == R19:
        nome_nulo = bruto["name"].isna()
        preco = bruto["price"]
        out["name_nulo"] = {
            "linhas": int(nome_nulo.sum()),
            "com_preco_positivo": int((nome_nulo & preco.gt(0)).sum()),
            "com_coordenada": int((nome_nulo & bruto["latitude"].notna()).sum()),
            "host_name_nulo_tambem": int((nome_nulo & bruto["host_name"].isna()).sum()),
        }
        out["host_name_nulo"] = int(bruto["host_name"].isna().sum())
    else:
        sem_host = bruto["host_name"].isna()
        out["sem_perfil_de_anfitriao"] = {
            "linhas": int(sem_host.sum()),
            "has_availability_f": int((sem_host & bruto["has_availability"].eq("f")).sum()),
            "preco_nulo": int((sem_host & bruto["price"].isna()).sum()),
        }
    return out


# --- Q3: host_id x host_name ----------------------------------------------------------------------


def q3_host(bruto: pd.DataFrame) -> dict:
    h = bruto[[COL_HOST_ID, "host_name"]].dropna()
    nomes_por_id = h.groupby(COL_HOST_ID)["host_name"].nunique()
    ids_por_nome = h.drop_duplicates().groupby("host_name")[COL_HOST_ID].nunique()
    anuncios_nome_compartilhado = bruto["host_name"].map(ids_por_nome).gt(1)
    return {
        "host_id_distintos": int(bruto[COL_HOST_ID].nunique()),
        "host_name_distintos": int(bruto["host_name"].nunique()),
        "host_name_nulo": int(bruto["host_name"].isna().sum()),
        "host_id_com_mais_de_um_nome": int((nomes_por_id > 1).sum()),
        "nomes_usados_por_mais_de_um_host_id": int((ids_por_nome > 1).sum()),
        "fracao_nomes_compartilhados": _pct((ids_por_nome > 1).sum(), len(ids_por_nome)),
        "anuncios_cujo_nome_e_compartilhado": int(anuncios_nome_compartilhado.sum()),
        "fracao_anuncios_nome_compartilhado": _pct(anuncios_nome_compartilhado.sum(), len(bruto)),
        # so a contagem: o nome em si e dado pessoal e nao sai (invariante 9)
        "host_ids_do_nome_mais_comum": int(ids_por_nome.max()),
        "host_ids_por_nome_mediana": _r(ids_por_nome.median(), 1),
    }


# --- Q4: coordenada x poligono do bairro ----------------------------------------------------------


def _poligonos() -> gpd.GeoDataFrame:
    g = gpd.read_file(ARQ_GEOJSON)
    invalidas = int((~g.is_valid).sum())
    # make_valid pode devolver GeometryCollection (poligono + sobra de linha), cuja
    # fronteira nao e definida; buffer(0) fica so com a parte poligonal
    g["geometry"] = shapely.buffer(shapely.make_valid(g.geometry.values), 0)
    # 3 bairros vem em 2 feicoes cada (Bayswater, City Island, Howard Beach)
    g = g.dissolve(by=["neighbourhood", "neighbourhood_group"], as_index=False)
    assert g.geom_type.isin(["Polygon", "MultiPolygon"]).all(), "poligono de bairro nao poligonal"
    g.attrs["invalidas_originais"] = invalidas
    return g


def q4_coordenadas(silver: pd.DataFrame, col_bairro: str, poli: gpd.GeoDataFrame) -> dict:
    lon_min, lat_min, lon_max, lat_max = config.NYC_BBOX
    dentro_bbox = silver["latitude"].between(lat_min, lat_max) & silver["longitude"].between(lon_min, lon_max)
    pts = gpd.GeoDataFrame({"bairro": silver[col_bairro].to_numpy()},
                           geometry=gpd.points_from_xy(silver["longitude"], silver["latitude"]),
                           crs=config.CRS_GEO)
    j = gpd.sjoin(pts, poli[["neighbourhood", "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated(keep="first")]
    no_declarado = j["neighbourhood"].eq(j["bairro"])
    fora_de_todos = j["neighbourhood"].isna()
    outro = ~no_declarado & ~fora_de_todos
    # distancia (m) do ponto ao poligono DECLARADO, para os que caem fora dele
    divergentes = ~no_declarado
    met = poli.to_crs(config.CRS_METRICO).set_index("neighbourhood").geometry
    pts_m = pts.to_crs(config.CRS_METRICO)
    alvo = met.reindex(pts_m.loc[divergentes, "bairro"]).to_numpy()
    dist = pd.Series(shapely.distance(pts_m.loc[divergentes].geometry.to_numpy(), alvo), dtype="float64")
    # O bairro declarado foi atribuido a partir do PROPRIO ponto deslocado, entao
    # "cair em outro bairro" e ~0 por construcao. O efeito do deslocamento e sobre
    # o endereco VERDADEIRO, inobservavel; o mensuravel e quantos pontos estao a
    # menos de 150 m de uma fronteira — para esses o bairro real pode ser o vizinho.
    fronteira = met.boundary.reindex(pts_m.loc[no_declarado, "bairro"]).to_numpy()
    d_front = pd.Series(shapely.distance(pts_m.loc[no_declarado].geometry.to_numpy(), fronteira),
                        dtype="float64")
    return {
        "anuncios": len(silver),
        "dentro_do_envelope_nyc": int(dentro_bbox.sum()),
        "dentro_do_poligono_declarado": int(no_declarado.sum()),
        "fracao_no_declarado": _pct(no_declarado.sum(), len(silver)),
        "em_outro_bairro": int(outro.sum()),
        "fora_de_todos_os_poligonos": int(fora_de_todos.sum()),
        "distancia_ao_declarado_m": {
            "mediana": _r(dist.median(), 1), "p90": _r(dist.quantile(0.9), 1),
            "max": _r(dist.max(), 1),
            "ate_150m": int((dist <= DESLOCAMENTO_M).sum()),
            "fracao_ate_150m": _pct((dist <= DESLOCAMENTO_M).sum(), dist.notna().sum()),
        },
        "distancia_a_fronteira_do_proprio_bairro_m": {
            "mediana": _r(d_front.median(), 1),
            "ate_150m": int((d_front <= DESLOCAMENTO_M).sum()),
            "fracao_ate_150m": _pct((d_front <= DESLOCAMENTO_M).sum(), d_front.notna().sum()),
        },
    }


# --- Q5: price --------------------------------------------------------------------------------------


def _descr(s: pd.Series) -> dict:
    s = s.dropna()
    q = s.quantile([0.01, 0.25, 0.5, 0.75, 0.99]).to_dict()
    return {"n": int(len(s)), "media": _r(s.mean(), 2), "min": _r(s.min(), 2),
            "p01": _r(q[0.01], 2), "p25": _r(q[0.25], 2), "mediana": _r(q[0.5], 2),
            "p75": _r(q[0.75], 2), "p99": _r(q[0.99], 2), "max": _r(s.max(), 2),
            "assimetria": _r(stats.skew(s), 2)}


def _mediana_por_min30(s: pd.DataFrame) -> dict:
    ok = s[s[COL_PRECO_VALIDO]]
    return {"min_lt30": {"n": int((~ok[COL_MIN30]).sum()), "mediana": _r(ok.loc[~ok[COL_MIN30], COL_PRECO].median(), 2)},
            "min30": {"n": int(ok[COL_MIN30].sum()), "mediana": _r(ok.loc[ok[COL_MIN30], COL_PRECO].median(), 2)}}


def _media_mensal(bruto: object) -> float:
    if not isinstance(bruto, str):
        return np.nan
    try:
        for it in json.loads(bruto)["quote"].get("raw_price_line_items") or []:
            if it.get("description") == "Average monthly price":
                return float(it["amount"])
    except (ValueError, KeyError, TypeError, AttributeError):
        return np.nan
    return np.nan


def q5_preco(k: pd.DataFrame, d: pd.DataFrame, s19: pd.DataFrame, s26: pd.DataFrame) -> dict:
    p19 = k["price"].astype("float64")
    p26 = dv.parse_preco(d["price"])
    ci = pd.to_datetime(d["price_quote_checkin_date"])
    co = pd.to_datetime(d["price_quote_checkout_date"])
    n = (co - ci).dt.days
    tem_cot = d["price_quote_raw"].notna()
    ppn = d["price_quote_price_per_night"]
    ambos = p26.notna() & ppn.notna()
    total = d["price_quote_total_price"]
    ok_tot = p26.notna() & n.gt(0) & total.notna()
    faixa = pd.cut(n, [0, 27, 31, 60, 120, 366], labels=["1-27", "28-31", "32-60", "61-120", "121-365"])
    por_faixa = (pd.DataFrame({"p": p26, "faixa": faixa, "total": total}).dropna()
                 .groupby("faixa", observed=True)
                 .agg(n=("p", "size"), preco_mediano=("p", "median"), total_mediano=("total", "median")))
    media_mensal = d["price_quote_raw"].map(_media_mensal)
    cot = dv.cotacao(d["price_quote_raw"], d["price_quote_checkin_date"], d["price_quote_checkout_date"])
    bruto_periodo = cot["preco_cheio"] * cot["preco_cotacao_noites"].astype("float64")
    tem_mm = media_mensal.notna() & bruto_periodo.notna()
    disp0 = d[COL_DISPONIBILIDADE_365].eq(0)
    desc = s26.loc[s26["desconto_pct"].notna()]
    return {
        "2019": {
            "semantica": "diária anunciada pelo anfitrião (inteiro, US$)",
            "distribuicao": _descr(p19),
            "zeros": int(p19.eq(0).sum()),
            "entre_1_e_9": int(p19.between(1, 9).sum()),
            "igual_10000": int(p19.eq(10_000).sum()),
            "igual_9999": int(p19.eq(9_999).sum()),
            "acima_1000": int(p19.gt(1_000).sum()),
            "mediana_por_minimo_de_noites": _mediana_por_min30(s19),
            "fracao_min30": _pct(s19[COL_MIN30].sum(), len(s19)),
        },
        "2026": {
            "semantica": ("cotação de uma estadia de N noites a partir da primeira data livre, "
                          "dividida por N, já com desconto de estadia longa"),
            "distribuicao": _descr(p26),
            "preco_nulo": int(p26.isna().sum()),
            "preco_nulo_sem_cotacao": int((p26.isna() & ~tem_cot).sum()),
            "preco_nulo_com_cotacao_sem_valor": int((p26.isna() & tem_cot).sum()),
            "preco_nulo_se_availability_365_zero": _pct((p26.isna() & disp0).sum(), disp0.sum()),
            "availability_365_zero": int(disp0.sum()),
            "preco_nulo_se_availability_365_positivo": _pct((p26.isna() & ~disp0).sum(), (~disp0).sum()),
            "price_igual_price_per_night": {"linhas_com_ambos": int(ambos.sum()),
                                            "iguais": int(np.isclose(p26[ambos], ppn[ambos]).sum())},
            "total_igual_price_vezes_noites": _pct(
                np.isclose(total[ok_tot], p26[ok_tot] * n[ok_tot], rtol=0.01).sum(), ok_tot.sum()),
            "cotacoes": int(tem_cot.sum()),
            "noites_cotacao": _descr(n),
            "noites_igual_minimo": {"cotacoes": int(n.notna().sum()),
                                    "iguais": int((n == d[COL_MIN_NOITES]).sum()),
                                    "fracao": _pct((n == d[COL_MIN_NOITES]).sum(), n.notna().sum())},
            "dias_do_scrape_ao_checkin": _descr((ci - pd.to_datetime(d["last_scraped"])).dt.days),
            "preco_mediano_por_noites_cotadas": {
                str(i): {"n": int(r.n), "preco_mediano": _r(r.preco_mediano, 2),
                         "total_mediano": _r(r.total_mediano, 2)} for i, r in por_faixa.iterrows()},
            "cheio_do_periodo_igual_average_monthly_price": {
                "cotacoes_com_o_item": int(tem_mm.sum()),
                "iguais_ate_2_centavos": int(((bruto_periodo - media_mensal).abs() <= 0.02)[tem_mm].sum()),
                "iguais_ate_1_dolar": int(((bruto_periodo - media_mensal).abs() <= 1)[tem_mm].sum()),
                "nota": ("total_price às vezes vem arredondado ao dólar; as cotações que diferem mais "
                         "de US$ 1 têm impostos embutidos no total (itens 'Taxes' + 'Total')"),
                "cotacoes_com_imposto": int(d["price_quote_raw"].str.contains('"Taxes"', na=False).sum())},
            "desconto": {
                "cotacoes_com_valor": int(len(desc)),
                "com_desconto": int(desc["desconto_pct"].gt(0).sum()),
                "fracao_com_desconto": _pct(desc["desconto_pct"].gt(0).sum(), len(desc)),
                "mediana_min_lt30": _r(desc.loc[~desc[COL_MIN30], "desconto_pct"].median()),
                "mediana_min30": _r(desc.loc[desc[COL_MIN30], "desconto_pct"].median()),
                "p90_min30": _r(desc.loc[desc[COL_MIN30], "desconto_pct"].quantile(0.9)),
                "max": _r(desc["desconto_pct"].max()),
            },
            "mediana_por_minimo_de_noites": _mediana_por_min30(s26),
            "mediana_preco_cheio_por_minimo_de_noites": {
                "min_lt30": _r(s26.loc[s26[COL_PRECO_VALIDO] & ~s26[COL_MIN30], "preco_cheio"].median(), 2),
                "min30": _r(s26.loc[s26[COL_PRECO_VALIDO] & s26[COL_MIN30], "preco_cheio"].median(), 2)},
            "fracao_min30": _pct(s26[COL_MIN30].sum(), len(s26)),
            "acima_10000": int(p26.gt(10_000).sum()),
            "abaixo_10": int(p26.lt(10).sum()),
        },
    }


# --- Q6: reviews_per_month ----------------------------------------------------------------------------


def _variacao_no_host(s: pd.DataFrame) -> dict:
    """Se reviews_per_month fosse do anfitriao, seria constante entre os anuncios dele."""
    com = s[s[COL_AVALIACOES_MES].notna()]
    g = com.groupby(COL_HOST_ID)[COL_AVALIACOES_MES]
    n = g.size()
    multi = n[n >= 2].index
    nuniq = g.nunique().loc[multi]
    return {
        "hosts_com_2_ou_mais_anuncios_avaliados": int(len(multi)),
        "hosts_com_valor_constante": int((nuniq == 1).sum()),
        "hosts_com_valor_variando": int((nuniq > 1).sum()),
        "fracao_variando": _pct((nuniq > 1).sum(), len(multi)),
        "amplitude_mediana_no_host": _r((g.max() - g.min()).loc[multi].median(), 3),
    }


def q6_avaliacoes(k: pd.DataFrame, d: pd.DataFrame, s19: pd.DataFrame, s26: pd.DataFrame) -> dict:
    fr = pd.to_datetime(d["first_review"])
    ls = pd.to_datetime(d["last_scraped"])
    dias = (ls - fr).dt.days
    rpm = d[COL_AVALIACOES_MES]
    ok = rpm.notna()
    ingenuo = d[COL_N_AVALIACOES] / (dias / dv.DIAS_POR_MES)
    formula = d[COL_N_AVALIACOES] / np.maximum(1.0, (dias + 1) / 30)
    ok_i = ok & np.isfinite(ingenuo)
    teste1 = {
        "anuncios_com_avaliacao": int(ok.sum()),
        "ingenuo_total_div_meses": {
            "pearson": _r(np.corrcoef(ingenuo[ok_i], rpm[ok_i])[0, 1]),
            "spearman": _r(stats.spearmanr(ingenuo[ok_i], rpm[ok_i]).statistic),
            "erro_abs_medio": _r((ingenuo[ok_i] - rpm[ok_i]).abs().mean()),
        },
        "formula_inside_airbnb": {
            "definicao": "number_of_reviews / max(1, (last_scraped - first_review + 1 dia) / 30)",
            "pearson": _r(np.corrcoef(formula[ok], rpm[ok])[0, 1], 6),
            "igual_em_2_casas": int((formula[ok].round(2) == rpm[ok]).sum()),
            "diferenca_ate_0_01": int(((formula[ok] - rpm[ok]).abs() <= 0.0101).sum()),
            "fracao_ate_0_01": _pct(((formula[ok] - rpm[ok]).abs() <= 0.0101).sum(), ok.sum()),
        },
    }
    # 2019 nao tem first_review: meses implicitos = total / taxa
    impl = (k[COL_N_AVALIACOES] / k[COL_AVALIACOES_MES]).dropna()
    return {
        "teste1_recalculo_2026": teste1,
        "teste2_variacao_entre_anuncios_do_mesmo_host": {R19: _variacao_no_host(s19),
                                                         R26: _variacao_no_host(s26)},
        "teste3_reviews_per_month_maior_que_total": {
            R19: int((k[COL_AVALIACOES_MES] > k[COL_N_AVALIACOES]).sum()),
            R26: int((rpm > d[COL_N_AVALIACOES]).sum()),
            "rpm_igual_total_piso_de_1_mes": {
                R19: int((k[COL_AVALIACOES_MES] == k[COL_N_AVALIACOES]).sum()),
                R26: int((rpm == d[COL_N_AVALIACOES]).sum())},
            "meses_implicitos_2019_min": _r(impl.min(), 3),
        },
        "acima_de_30_por_mes": {
            R19: int((k[COL_AVALIACOES_MES] > 30).sum()),
            R26: int((rpm > 30).sum()),
            "tipo_de_imovel_2026": d.loc[rpm > 30, "property_type"].value_counts().to_dict(),
            "maximo": {R19: _r(k[COL_AVALIACOES_MES].max(), 2), R26: _r(rpm.max(), 2)},
        },
    }


# --- correcoes da v0 ----------------------------------------------------------------------------------


def _v0_limpeza(k: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Reproduz, passo a passo, o script da v0 (constante PY_CODE do dashboard)."""
    passos = {"entrada": len(k)}
    df = k.drop(columns=["id", "host_name", "last_review"])
    passos["duplicatas_removidas_sem_id"] = int(df.duplicated().sum())
    df = df.drop_duplicates()
    df["reviews_per_month"] = df["reviews_per_month"].fillna(0)
    passos["price_zero_removidos"] = int((df["price"] <= 0).sum())
    df = df[df["price"] > 0]
    passos["dropna_removidos"] = int(df.isna().any(axis=1).sum())
    passos["dropna_por_coluna"] = {c: int(v) for c, v in df.isna().sum().items() if v}
    df = df.dropna()
    passos["saida"] = len(df)
    return df, passos


def _corr(df: pd.DataFrame, cols: list[str]) -> dict:
    p = df[cols].corr(method="pearson")
    s = df[cols].corr(method="spearman")
    pares = []
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            pares.append({"par": f"{a} × {b}", "pearson": _r(p.loc[a, b], 3),
                          "spearman": _r(s.loc[a, b], 3),
                          "diferenca": _r(s.loc[a, b] - p.loc[a, b], 3)})
    pares.sort(key=lambda x: -abs(x["diferenca"]))
    return {"pares_ordenados_pela_diferenca": pares,
            "assimetria": {c: _r(stats.skew(df[c].astype(float)), 2) for c in cols}}


def _ocupacao_ltm_sobreviventes(s19: pd.DataFrame) -> dict:
    """Para os anuncios de 2019 que ainda existem em 2026, o arquivo de avaliacoes
    de 2026 permite contar as avaliacoes dos 12 meses ANTES de 2019-07-08 — o
    mesmo insumo do `estimated_occupancy_l365d` — e testar o modelo por
    reviews_per_month no proprio 2019 (com vies de sobrevivencia declarado)."""
    ref = dv.snapshot_2019_ts()
    rv = pd.read_csv(ARQ_REVIEWS, usecols=["listing_id", "date"])
    rv["date"] = pd.to_datetime(rv["date"])
    janela = rv[(rv["date"] > ref - pd.Timedelta(days=365)) & (rv["date"] <= ref)]
    ltm = janela.groupby("listing_id").size()
    sv = s19[s19["presente_2026"]].copy()
    sv["ltm"] = sv[COL_ID].map(ltm).fillna(0)
    noites = np.maximum(dv.ESTADIA_MEDIA_NYC, sv[COL_MIN_NOITES].astype(float))
    sv["occ_ltm"] = (sv["ltm"] / dv.TAXA_AVALIACAO * noites / 365).clip(upper=dv.TETO_OCUPACAO)
    return {
        "anuncios": len(sv),
        "ocupacao_media_modelo_rpm": _r(sv[COL_OCUPACAO_MODELO].mean()),
        "ocupacao_media_ltm_reconstruida": _r(sv["occ_ltm"].mean()),
        "spearman": _r(stats.spearmanr(sv[COL_OCUPACAO_MODELO], sv["occ_ltm"]).statistic, 3),
        "pearson": _r(np.corrcoef(sv[COL_OCUPACAO_MODELO], sv["occ_ltm"])[0, 1], 3),
        "erro_abs_medio": _r((sv[COL_OCUPACAO_MODELO] - sv["occ_ltm"]).abs().mean()),
        "nota": "sobreviventes são um subconjunto enviesado (mais ativos); serve para validar o proxy, não para estimar 2019",
    }


def correcoes_v0(k: pd.DataFrame, d: pd.DataFrame, s19: pd.DataFrame, s26: pd.DataFrame) -> dict:
    v0df, passos = _v0_limpeza(k)
    occ_v0 = 1 - v0df["availability_365"] / 365
    disp0_19 = s19[COL_DISPONIBILIDADE_365].eq(0)
    disp0_26 = s26[COL_DISPONIBILIDADE_365].eq(0)
    occ_real_26 = s26[COL_OCUPACAO_L365D] / 365
    occ_disp_26 = 1 - s26[COL_DISPONIBILIDADE_365] / 365

    def _sens(s: pd.DataFrame, estadia: float, janela: int | None) -> float:
        return float(dv.ocupacao_modelo(s[COL_AVALIACOES_MES], s[COL_MIN_NOITES],
                                        s[COL_DIAS_ULTIMA_AVALIACAO], estadia, janela).mean())

    por_distrito = s19.groupby(COL_DISTRITO, observed=True)[COL_OCUPACAO_MODELO].mean()
    ok19 = s19[s19[COL_PRECO_VALIDO]]
    rend = (ok19[COL_PRECO] * ok19[COL_OCUPACAO_MODELO]).groupby(ok19[COL_DISTRITO], observed=True).mean()
    val26 = {}
    for estadia in (dv.ESTADIA_MEDIA_PADRAO, dv.ESTADIA_MEDIA_NYC):
        for janela in (None, dv.JANELA_ATIVIDADE_DIAS):
            x = dv.ocupacao_modelo(s26[COL_AVALIACOES_MES], s26[COL_MIN_NOITES],
                                   s26[COL_DIAS_ULTIMA_AVALIACAO], estadia, janela)
            val26[f"estadia_{estadia:g}_{'com' if janela else 'sem'}_janela"] = {
                "media": _r(x.mean()), "spearman": _r(stats.spearmanr(x, occ_real_26).statistic, 3),
                "pearson": _r(np.corrcoef(x, occ_real_26)[0, 1], 3),
                "erro_abs_medio": _r((x - occ_real_26).abs().mean())}
    # a formula do estimated_occupancy_l365d, reconstruida a partir do proprio arquivo
    reproducao = np.minimum(np.round(d["number_of_reviews_ltm"] / dv.TAXA_AVALIACAO
                                     * np.maximum(dv.ESTADIA_MEDIA_NYC, d[COL_MIN_NOITES])), 255)
    ok_rep = reproducao.notna()
    v0_num = v0df[V0_NUMERICAS]
    # mesmo tratamento da v0 (reviews_per_month nulo = 0), para a comparacao ser justa
    s26_num = (s26[s26[COL_PRECO_VALIDO]].rename(columns={COL_PRECO: "price"})[V0_NUMERICAS]
               .fillna({"reviews_per_month": 0}))
    return {
        "a_ocupacao": {
            "o_que_a_v0_mediu": "1 − availability_365/365: fração do calendário INDISPONÍVEL, "
                                "que soma noite reservada e noite bloqueada pelo anfitrião",
            "v0_publicado": {"geral": V0["ocupacao_geral"], "por_distrito": V0["ocupacao_por_distrito"]},
            "v0_reproduzido": {"geral": _r(occ_v0.mean()),
                               "por_distrito": {g: _r(v) for g, v in occ_v0.groupby(v0df["neighbourhood_group"]).mean().items()}},
            "availability_365_zero": {R19: {"anuncios": int(disp0_19.sum()), "fracao": _pct(disp0_19.sum(), len(s19))},
                                      R26: {"anuncios": int(disp0_26.sum()), "fracao": _pct(disp0_26.sum(), len(s26))}},
            "2026_indisponibilidade_vs_ocupacao_estimada": {
                "pearson": _r(np.corrcoef(occ_disp_26, occ_real_26)[0, 1], 3),
                "spearman": _r(stats.spearmanr(occ_disp_26, occ_real_26).statistic, 3),
                "media_1_menos_disp": _r(occ_disp_26.mean()),
                "media_ocupacao_estimada": _r(occ_real_26.mean()),
                "anuncios_disp_zero": int(disp0_26.sum()),
                "disp_zero_com_ocupacao_estimada_zero": int((disp0_26 & s26[COL_OCUPACAO_L365D].eq(0)).sum()),
                "disp_zero_fracao_ocupacao_zero": _pct((disp0_26 & s26[COL_OCUPACAO_L365D].eq(0)).sum(), disp0_26.sum()),
                "disp_zero_ocupacao_estimada_media": _r(occ_real_26[disp0_26].mean()),
                "disp_zero_sem_avaliacao_12m": int((disp0_26 & s26["number_of_reviews_ltm"].eq(0)).sum()),
            },
            "reproducao_estimated_occupancy_l365d": {
                "formula": "min(round(number_of_reviews_ltm / 0,5 × max(6,4; minimum_nights)); 255)",
                "anuncios": int(ok_rep.sum()),
                "iguais": int((reproducao[ok_rep] == d.loc[ok_rep, COL_OCUPACAO_L365D]).sum()),
            },
            "modelo_avaliacoes": {
                "fonte": "https://insideairbnb.com/data-assumptions/ (consultado em 2026-09-18)",
                "parametros": {"taxa_avaliacao": dv.TAXA_AVALIACAO, "estadia_media_nyc": dv.ESTADIA_MEDIA_NYC,
                               "estadia_media_padrao_da_pagina": dv.ESTADIA_MEDIA_PADRAO,
                               "teto": dv.TETO_OCUPACAO, "janela_atividade_dias": dv.JANELA_ATIVIDADE_DIAS},
                "validacao_2026_contra_estimated_occupancy_l365d": val26,
                "validacao_2019_sobreviventes_ltm": _ocupacao_ltm_sobreviventes(s19),
            },
            "ocupacao_2019_modelo": {
                "geral": _r(s19[COL_OCUPACAO_MODELO].mean()),
                "por_distrito": {g: _r(v) for g, v in por_distrito.items()},
                "mediana": _r(s19[COL_OCUPACAO_MODELO].median()),
                "fracao_zero": _pct(s19[COL_OCUPACAO_MODELO].eq(0).sum(), len(s19)),
                "sensibilidade": {
                    "estadia_3_com_janela": _r(_sens(s19, dv.ESTADIA_MEDIA_PADRAO, dv.JANELA_ATIVIDADE_DIAS)),
                    "estadia_6.4_sem_janela": _r(_sens(s19, dv.ESTADIA_MEDIA_NYC, None)),
                    "estadia_3_sem_janela": _r(_sens(s19, dv.ESTADIA_MEDIA_PADRAO, None)),
                },
            },
            "ocupacao_2026": {"estimated_occupancy_l365d_media": _r(occ_real_26.mean()),
                              "modelo_rpm_media": _r(s26[COL_OCUPACAO_MODELO].mean())},
            "rendimento_por_distrito": {
                "v0_publicado": V0["rendimento_por_distrito"],
                "preco_vezes_ocupacao_modelo_2019": {g: _r(v, 1) for g, v in rend.items()},
            },
        },
        "b_drop_id_antes_do_drop_duplicates": {
            "o_que_a_v0_fez": "removeu id, host_name e last_review e SÓ ENTÃO procurou duplicatas",
            "problema": ("sem a chave, dois anúncios distintos com os mesmos atributos seriam fundidos; "
                         "a verificação certa é por id (chave) e, à parte, por todas as colunas exceto o id"),
            "duplicatas_v0": passos["duplicatas_removidas_sem_id"],
            "ids_repetidos_2019": int(k[COL_ID].duplicated().sum()),
            "duplicatas_sem_id_2019": int(k.drop(columns=[COL_ID]).duplicated().sum()),
            "efeito_nesta_base": "nenhum — 0 duplicatas por qualquer critério; o erro é de método, não de número",
        },
        "c_dropna_por_name": {
            "o_que_a_v0_fez": "dropna() depois de preencher reviews_per_month — só `name` ainda tinha nulo",
            "linhas_removidas": passos["dropna_removidos"],
            "colunas_responsaveis": passos["dropna_por_coluna"],
            "necessario": False,
            "por_que": ("nenhuma análise da v0 usa `name`; os 16 anúncios têm preço, coordenada e bairro "
                        "válidos. A limpeza desta versão os mantém (name é só para análise)"),
            "limpeza_v0_reproduzida": passos,
        },
        "d_pearson_vs_spearman": {
            "o_que_a_v0_fez": "df.corr() — Pearson — em variáveis de cauda pesada",
            "v0_publicado_preco_x_avaliacoes": V0["corr_preco_avaliacoes_pearson"],
            "2019_base_da_v0": _corr(v0_num, V0_NUMERICAS),
            "2026_preco_valido": _corr(s26_num, V0_NUMERICAS),
        },
        "host_multiplo": {
            "v0_publicado_pct_anuncios": V0["pct_anuncios_host_multiplo"],
            "pct_anuncios_2019": _r(100 * s19["host_multi"].mean(), 1),
            "pct_anfitrioes_2019": _r(100 * (s19.groupby(COL_HOST_ID)[COL_ID].size() > 1).mean(), 1),
            "pct_anuncios_2026": _r(100 * s26["host_multi"].mean(), 1),
            "pct_anfitrioes_2026": _r(100 * (s26.groupby(COL_HOST_ID)[COL_ID].size() > 1).mean(), 1),
            "nota": "a v0 está certa: é fração de ANÚNCIOS; a fração de ANFITRIÕES é outra grandeza",
        },
    }


# --- orquestracao ------------------------------------------------------------------------------------


def executar() -> tuple[dict, dict]:
    print("  qualidade: perguntas da equipe e correcoes da v0…", flush=True)
    k, d = pl.ler_kaggle(), pl.ler_detalhado()
    s19 = pd.read_parquet(pl.SAIDA_2019)
    s26 = pd.read_parquet(pl.SAIDA_2026)
    poli = _poligonos()
    perguntas = {
        "descricao": ("Perguntas da equipe (reports/v0/Análise.txt) respondidas com contagem sobre os dados. "
                      "Q1–Q3 no bruto (antes da limpeza); Q4–Q6 na silver. Sem nome, id ou texto livre."),
        "Q1_id_unico_e_duplicatas": {R19: q1_duplicados(k, R19), R26: q1_duplicados(d, R26)},
        "Q2_campos_vazios": {R19: q2_vazios(k, R19), R26: q2_vazios(d, R26)},
        "Q3_host_id_x_host_name": {R19: q3_host(k), R26: q3_host(d)},
        "Q4_coordenadas": {"poligonos": {"feicoes_geojson": 233, "bairros": int(len(poli)),
                                         "geometrias_invalidas_corrigidas": poli.attrs.get("invalidas_originais")},
                           R19: q4_coordenadas(s19, "neighbourhood", poli),
                           R26: q4_coordenadas(s26, "neighbourhood_cleansed", poli)},
        "Q5_preco": q5_preco(k, d, s19, s26),
        "Q6_reviews_per_month": q6_avaliacoes(k, d, s19, s26),
    }
    correcoes = {
        "descricao": ("Correções da v0 (reports/v0/airbnb-nyc-dashboard-slide.html): o que a v0 mediu e o "
                      "que de fato mede. Números da v0 reproduzidos com o script dela antes de comparar."),
        **correcoes_v0(k, d, s19, s26),
    }
    for caminho, obj in ((SAIDA_PERGUNTAS, perguntas), (SAIDA_CORRECOES, correcoes)):
        caminho.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=_json_default) + "\n",
                           encoding="utf-8")
        print(f"  {caminho.name}")
    return perguntas, correcoes


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, Path):
        return o.as_posix()
    return str(o)


def main() -> None:
    executar()


if __name__ == "__main__":
    main()
