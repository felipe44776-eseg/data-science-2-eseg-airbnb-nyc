"""Testes de localizacao sobre celulas H3 sinteticas — sem dado real."""

from __future__ import annotations

import h3
import numpy as np
import pandas as pd
import pytest

from airbnb.eda.estatistica_espacial import (
    NAO_SIGNIFICATIVO,
    _fdr_bh,
    eta2,
    kruskal_com_efeito,
    lisa,
    moran_global,
    pares_mann_whitney,
    pesos_h3,
)

CENTRO = h3.latlng_to_cell(40.75, -73.98, 8)


@pytest.fixture
def disco() -> list[str]:
    return sorted(h3.grid_disk(CENTRO, 8))  # 217 celulas contiguas


def test_pesos_sem_ilhas_e_padronizados(disco):
    isolada = h3.latlng_to_cell(40.55, -74.15, 8)  # longe do disco: ilha
    w, mantidas = pesos_h3(disco + [isolada])
    assert isolada not in mantidas
    assert len(mantidas) == len(disco)
    assert all(abs(sum(p) - 1) < 1e-12 for p in w.weights.values())


def test_moran_detecta_gradiente(disco):
    # valor = distancia ao centro: autocorrelacao positiva forte
    v = pd.Series({c: h3.grid_distance(CENTRO, c) for c in disco}, dtype=float)
    r = moran_global(v, permutacoes=199)
    assert r["I"] > 0.5
    assert r["p_bilateral"] <= 0.01


def test_moran_ruido_nao_e_significativo(disco):
    rng = np.random.default_rng(0)
    v = pd.Series(rng.normal(size=len(disco)), index=disco)
    r = moran_global(v, permutacoes=199)
    assert abs(r["I"]) < 0.15
    assert r["p_bilateral"] > 0.05


def test_lisa_marca_o_nucleo_quente(disco):
    v = pd.Series({c: 10.0 if h3.grid_distance(CENTRO, c) <= 2 else 0.0 for c in disco})
    rng = np.random.default_rng(1)
    v = v + rng.normal(0, 0.1, len(v))
    # com FDR sobre 217 celulas, 199 permutacoes nao bastam: o menor p possivel
    # (0,01 bilateral) so seria rejeitado com >= 44 celulas nesse patamar
    res = lisa(v, permutacoes=999)
    assert res.loc[CENTRO, "cluster"] == "Alto-Alto"
    longe = [c for c in disco if h3.grid_distance(CENTRO, c) == 8][0]
    assert res.loc[longe, "cluster"] in {"Baixo-Baixo", NAO_SIGNIFICATIVO}


def test_fdr_benjamini_hochberg():
    p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216])
    assert _fdr_bh(p, 0.05).sum() == 2


def test_kruskal_e_pares():
    rng = np.random.default_rng(2)
    v = pd.Series(np.r_[rng.normal(0, 1, 300), rng.normal(1, 1, 300), rng.normal(1, 1, 300)])
    g = pd.Series(["a"] * 300 + ["b"] * 300 + ["c"] * 300)
    k = kruskal_com_efeito(v, g)
    assert k["k"] == 3 and k["p"] < 1e-10 and 0.05 < k["epsilon2"] < 0.5
    pares = {(x["a"], x["b"]): x for x in pares_mann_whitney(v, g)}
    assert pares[("a", "b")]["p_holm"] < 1e-6
    assert pares[("a", "b")]["rank_biserial"] < 0  # `a` tende a ser menor que `b`
    assert pares[("b", "c")]["p_holm"] > 0.01


def test_eta2_limites():
    v = pd.Series([1.0, 1.0, 5.0, 5.0])
    assert eta2(v, pd.Series(["x", "x", "y", "y"])) == pytest.approx(1.0)
    assert eta2(v, pd.Series(["x", "y", "x", "y"])) == pytest.approx(0.0)
