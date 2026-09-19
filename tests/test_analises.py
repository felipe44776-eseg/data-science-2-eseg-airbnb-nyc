"""Analises e produto sobre dado sintetico: decomposicao, PSI, baseline, realocacao, site.

O que se protege: a decomposicao shift-share tem de separar composicao de preco
(o argumento central do ADR 0005); o baseline tem de recuar quando o bairro
inteiro esta no fold de teste; o anuncio fora da cobertura herda a celula mais
proxima, nunca some; e o site nao publica nada pessoal.
"""

from __future__ import annotations

import json

import h3
import numpy as np
import pandas as pd
import pytest

from airbnb import schema as S
from airbnb.config import ROTULO_2019, ROTULO_ATUAL, SITE_DADOS
from airbnb.eda.comparativo import COL_PRECO_REAL, ESTRATO, decomposicao
from airbnb.features.anuncios import realocar
from airbnb.models.deriva import psi
from airbnb.models.preco import baseline_mediana


def _mercado(n19: int, n26: int, frac30_19: float, frac30_26: float,
             preco30: float, preco_curto: float, inflacao: float = 1.0) -> pd.DataFrame:
    """Dois estratos com preco fixo; so a composicao muda entre os snapshots."""
    linhas = []
    for snap, n, f30 in ((ROTULO_2019, n19, frac30_19), (ROTULO_ATUAL, n26, frac30_26)):
        k30 = int(round(n * f30))
        mult = inflacao if snap == ROTULO_ATUAL else 1.0
        for i in range(n):
            longo = i < k30
            linhas.append({S.COL_SNAPSHOT: snap, S.COL_PRECO_VALIDO: True,
                           ESTRATO: "30+ noites" if longo else "< 30 noites",
                           S.COL_ROOM_TYPE: S.ROOM_TYPES[0],
                           COL_PRECO_REAL: (preco30 if longo else preco_curto) * mult})
    return pd.DataFrame(linhas)


def test_decomposicao_so_composicao():
    # mesmo preco em cada estrato; o mercado so migrou para 30+ noites (mais barato)
    d = decomposicao(_mercado(1000, 1000, 0.1, 0.8, preco30=100, preco_curto=200))
    assert d["dentro_do_estrato_log"] == pytest.approx(0, abs=1e-12)
    assert d["composicao_log"] < 0
    assert d["delta_log_total"] == pytest.approx(d["composicao_log"])


def test_decomposicao_so_preco():
    d = decomposicao(_mercado(1000, 1000, 0.3, 0.3, 100, 200, inflacao=1.25))
    assert d["composicao_log"] == pytest.approx(0, abs=1e-12)
    assert d["variacao_geometrica_pct"] == pytest.approx(25.0)


def test_psi_estavel_e_deslocado():
    rng = np.random.default_rng(0)
    a = rng.normal(0, 1, 20000)
    assert psi(a, rng.normal(0, 1, 20000)) < 0.01
    assert psi(a, rng.normal(1, 1, 20000)) > 0.25


def test_baseline_recua_para_o_tipo_quando_o_bairro_nao_esta_no_treino():
    y = np.log(np.array([100.0, 100, 300, 300, 50, 50]))
    bairro = np.array(["A", "A", "B", "B", "C", "C"])
    tipo = np.array(["x", "x", "x", "x", "y", "y"])
    fold = np.array([0, 0, 1, 1, 2, 2])
    oof = baseline_mediana(y, fold, [bairro, tipo])
    # bairro A so aparece no fold de teste 0: recua para a mediana do tipo x no treino (B)
    assert np.exp(oof[0]) == pytest.approx(300)
    # tipo y so no fold 2: recua para a mediana global do treino
    assert np.exp(oof[4]) == pytest.approx(np.exp(np.median(y[fold != 2])))


def test_realocar_herda_a_celula_coberta_mais_proxima():
    centro = h3.latlng_to_cell(40.75, -73.98, 9)
    cobertas = set(h3.grid_disk(centro, 1))
    fora = [c for c in h3.grid_ring(centro, 2)][0]
    longe = h3.latlng_to_cell(40.60, -73.80, 9)
    serie, info = realocar(pd.Series([centro, fora, longe]), cobertas)
    assert serie.iloc[0] == centro
    assert serie.iloc[1] in cobertas and h3.grid_distance(fora, serie.iloc[1]) == 1
    assert pd.isna(serie.iloc[2])
    assert info["sem_celula_coberta"] == 1
    assert info["realocados_por_anel"]["1"] == 1


# --- o site publicado ----------------------------------------------------------------

PROIBIDAS = {"id", "host_id", "host_name", "name", "listing_url", "host_url", "picture_url"}


def _site(nome: str) -> dict | None:
    p = SITE_DADOS / nome
    if not p.exists():
        return None
    dado = json.loads(p.read_text(encoding="utf-8"))
    return None if dado.get("provisorio") else dado


@pytest.mark.dados
def test_site_sem_dado_pessoal():
    pts = _site("anuncios_2026.json")
    if pts is None:
        pytest.skip("site/data ainda nao exportado")
    assert not (PROIBIDAS & set(pts["colunas"]))
    i_lat = pts["colunas"].index("lat")
    casas = {len(str(linha[i_lat]).split(".")[-1]) for linha in pts["linhas"][:2000]
             if linha[i_lat] is not None}
    assert max(casas) <= 4


@pytest.mark.dados
def test_site_json_estrito_e_coerente():
    resumo, r9 = _site("resumo.json"), _site("celulas_r9.json")
    modelo = _site("modelo_preco.json")
    if not (resumo and r9 and modelo):
        pytest.skip("site/data ainda nao exportado")
    def rejeita(token):
        raise AssertionError(f"token {token} no JSON — o JSON.parse do navegador falharia")
    for nome in ("resumo.json", "celulas_r8.json", "celulas_r9.json", "modelo_preco.json",
                 "anuncios_2026.json"):
        # "NaN" pode aparecer como TEXTO (o codigo de missing_type do LightGBM); o que
        # nao pode e o literal NaN/Infinity, que o Python aceita e o navegador nao
        json.loads((SITE_DADOS / nome).read_text(encoding="utf-8"), parse_constant=rejeita)
    assert r9["colunas"] == modelo["features_local"]
    assert r9["referencia"] in r9["celulas"]
    chaves = [m["chave"] for m in resumo["metricas_celula"]]
    assert len(chaves) == len(set(chaves))
    r8 = _site("celulas_r8.json")
    assert r8["colunas"][3:] == chaves
