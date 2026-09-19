"""Validacao espacial, metricas e conformal — sem dado real.

O que se protege aqui e a honestidade da avaliacao: nenhum bloco espacial pode
cruzar folds (ADR 0002), a cobertura do intervalo tem de ser medida fora da
amostra que o calibrou, e a parada antecipada nao pode enxergar o fold de teste.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from airbnb.models.validacao import (
    blocos_compartilhados,
    cobertura_honesta,
    folds_aleatorios,
    folds_espaciais,
    metricas_preco,
    quantis_conformal,
    treinar_cv,
)


@pytest.fixture
def blocos() -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.choice([f"b{i}" for i in range(40)], size=2000)


def test_folds_espaciais_nao_cruzam_blocos(blocos):
    fold = folds_espaciais(blocos, n_folds=5, semente=1)
    assert (fold >= 0).all()
    assert set(np.unique(fold)) == set(range(5))
    assert blocos_compartilhados(blocos, fold) == 0


def test_folds_aleatorios_cruzam_blocos(blocos):
    # e exatamente por isso que o KFold aleatorio so aparece como comparacao
    fold = folds_aleatorios(len(blocos), n_folds=5, semente=1)
    assert blocos_compartilhados(blocos, fold) > 0


def test_folds_espaciais_deterministicos(blocos):
    assert (folds_espaciais(blocos, semente=7) == folds_espaciais(blocos, semente=7)).all()


def test_metricas_preco_perfeitas():
    y = np.log(np.array([50.0, 100.0, 200.0, 400.0]))
    m = metricas_preco(y, y)
    assert m["mae_usd"] == pytest.approx(0)
    assert m["mdape"] == pytest.approx(0)
    assert m["r2_log"] == pytest.approx(1)


def test_metricas_preco_em_dolar():
    y = np.log(np.array([100.0, 100.0]))
    p = np.log(np.array([110.0, 90.0]))
    m = metricas_preco(y, p)
    assert m["mae_usd"] == pytest.approx(10)
    assert m["mdape"] == pytest.approx(0.10)


def test_quantis_conformal_cobrem_nivel():
    rng = np.random.default_rng(3)
    r = rng.normal(0, 1, 5000)
    q_inf, q_sup = quantis_conformal(r, 0.8)
    assert q_inf == pytest.approx(-1.2816, abs=0.08)
    assert q_sup == pytest.approx(1.2816, abs=0.08)
    novo = rng.normal(0, 1, 20000)
    assert ((novo >= q_inf) & (novo <= q_sup)).mean() == pytest.approx(0.8, abs=0.02)


def test_cobertura_honesta_perto_do_nominal(blocos):
    rng = np.random.default_rng(4)
    r = rng.standard_t(df=5, size=len(blocos))
    fold = folds_espaciais(blocos, semente=2)
    c = cobertura_honesta(r, fold, 0.8, grupos=(blocos < "b2"))
    assert c["cobertura"] == pytest.approx(0.8, abs=0.03)
    assert set(c["por_grupo"]) == {"True", "False"}


def test_treinar_cv_preve_so_fora_do_fold(blocos):
    rng = np.random.default_rng(5)
    n = len(blocos)
    X = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n)})
    y = 2 * X["a"].to_numpy() + rng.normal(0, 0.1, n)
    fold = folds_espaciais(blocos, semente=3)
    res = treinar_cv(X, y, fold, blocos, params={"num_leaves": 7}, max_arvores=300,
                     guardar_modelos=True)
    assert not np.isnan(res.oof).any()
    assert len(res.melhores_iteracoes) == 5
    assert res.importancia_ganho.index[0] == "a"
    # o modelo de cada fold nao viu o fold: a previsao OOF difere da in-sample
    k0 = fold == 0
    in_sample = res.modelos[1].predict(X[k0])
    assert not np.allclose(in_sample, res.oof[k0])
    assert np.corrcoef(res.oof, y)[0, 1] > 0.95
