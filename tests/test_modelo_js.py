"""Testes do avaliador LightGBM em JavaScript (invariante 10).

O teste central treina LightGBMs pequenos em dado sintetico que exercita toda a
semantica de arvore — numerica sem ausente (missing_type None), com NaN
(missing_type NaN), com zero tratado como ausente (missing_type Zero) e
categorica nativa com split de varias categorias ("a||b||c") — exporta, gera os
casos com as saidas do PROPRIO LightGBM e roda `tests/paridade_js.mjs`, que
importa o MESMO `site/assets/modelo.js` da pagina.

Objetivos cobertos: regressao em log1p (expm1), poisson e tweedie (exp) e
binario com escala de sigmoide != 1.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

lgb = pytest.importorskip("lightgbm")

from airbnb.produto.modelo_js import (  # noqa: E402 - depois do importorskip
    FORMATO,
    TOLERANCIA_BRUTO,
    exportar_modelo,
    gerar_casos_paridade,
    prever_bruto_json,
    verificar_export,
)

RAIZ = Path(__file__).resolve().parents[1]
PARIDADE = RAIZ / "tests" / "paridade_js.mjs"
NODE = shutil.which("node")

CATEGORIAS = ["casa", "quarto", "compartilhado", "hotel", "loft", "estudio"]


def _dados(n: int = 2500, semente: int = 7) -> tuple[pd.DataFrame, np.ndarray]:
    """Dado sintetico com NaN, zeros, categorica nativa e numerica sem ausente."""
    rng = np.random.default_rng(semente)
    tipo = rng.choice(CATEGORIAS, size=n, p=[0.35, 0.3, 0.1, 0.1, 0.1, 0.05]).astype(object)
    tipo[rng.random(n) < 0.03] = None  # categoria ausente
    X = pd.DataFrame({
        "tipo": pd.Categorical(tipo, categories=CATEGORIAS),
        "hospedes": rng.integers(1, 9, size=n).astype(float),
        "nota": np.where(rng.random(n) < 0.25, np.nan, rng.normal(4.6, 0.3, n)),
        "avaliacoes": np.where(rng.random(n) < 0.4, 0.0, rng.gamma(2.0, 20.0, n)),
        "dist_metro": rng.gamma(2.0, 0.4, n),
    })
    efeito = {"casa": 0.8, "quarto": 0.0, "compartilhado": -0.6, "hotel": 0.5,
              "loft": 0.9, "estudio": 0.3}
    log_preco = (4.0 + X["tipo"].map(efeito).astype(float).fillna(0.2).to_numpy()
                 + 0.09 * X["hospedes"].to_numpy()
                 + 0.3 * np.nan_to_num(X["nota"].to_numpy() - 4.6)
                 - 0.2 * X["dist_metro"].to_numpy()
                 + 0.002 * X["avaliacoes"].to_numpy()
                 + rng.normal(0, 0.25, n))
    return X, log_preco


BASE = {"verbose": -1, "num_leaves": 15, "min_data_in_leaf": 10, "learning_rate": 0.1,
        "max_cat_to_onehot": 2, "cat_smooth": 1.0, "min_data_per_group": 10, "seed": 42}


def _treinar(caso: str):
    """(booster, X, transformacao) para cada objetivo coberto."""
    X, log_preco = _dados()
    if caso == "regressao_log1p":
        y, params, t = log_preco, {"objective": "regression"}, "expm1"
    elif caso == "poisson_zero":
        # zero_as_missing: gera nos com missing_type "Zero"
        y = np.random.default_rng(1).poisson(np.exp(log_preco - 3.0))
        params, t = {"objective": "poisson", "zero_as_missing": True}, "exp"
    elif caso == "tweedie":
        y, params, t = np.expm1(log_preco), {"objective": "tweedie"}, "exp"
    elif caso == "binario":
        y = (log_preco > np.median(log_preco)).astype(int)
        params, t = {"objective": "binary", "sigmoid": 1.7}, "sigmoide"
    else:
        raise ValueError(caso)
    booster = lgb.train({**BASE, **params}, lgb.Dataset(X, y), num_boost_round=60)
    return booster, X, t


CASOS = ["regressao_log1p", "poisson_zero", "tweedie", "binario"]


@pytest.fixture(scope="module")
def modelos(tmp_path_factory) -> dict[str, tuple]:
    base = tmp_path_factory.mktemp("modelos")
    saida = {}
    for caso in CASOS:
        booster, X, t = _treinar(caso)
        caminho = base / f"{caso}.json"
        modelo = exportar_modelo(booster, caminho, features=list(X.columns), transformacao=t)
        saida[caso] = (booster, X, modelo, caminho)
    return saida


def _codigos(modelo: dict, chave: str) -> set:
    return {v for a in modelo["arvores"] for v in a[chave]}


# --- o export em si -------------------------------------------------------

def test_formato_e_estrutura(modelos):
    _, X, modelo, caminho = modelos["regressao_log1p"]
    assert modelo["formato"] == FORMATO
    assert modelo["features"] == list(X.columns)
    assert modelo["n_arvores"] == len(modelo["arvores"]) == 60
    for a in modelo["arvores"]:
        n_nos = len(a["feature"])
        assert all(len(a[k]) == n_nos for k in (
            "limiar", "esquerda", "direita", "padrao_esquerda", "ausente", "decisao"))
        assert len(a["folhas"]) == n_nos + 1
    # o arquivo e JSON estrito: o navegador rejeita NaN/Infinity
    texto = caminho.read_text(encoding="utf-8")
    assert "NaN" not in texto.replace('"NaN"', "") and "Infinity" not in texto


def test_dado_sintetico_exercita_toda_a_semantica(modelos):
    """Sem isto, a paridade poderia passar sem nunca visitar um caminho de ausente."""
    m1 = modelos["regressao_log1p"][2]
    assert {0, 2} <= _codigos(m1, "ausente")          # None e NaN
    assert 1 in _codigos(m1, "decisao")                # categorica
    limiares = [lim for a in m1["arvores"] for lim, d in zip(a["limiar"], a["decisao"], strict=True)
                if d == 1]
    assert any("||" in lim for lim in limiares)        # split com varias categorias
    assert 1 in _codigos(modelos["poisson_zero"][2], "ausente")  # Zero


@pytest.mark.parametrize("caso", CASOS)
def test_export_reproduz_o_lightgbm_em_python(modelos, caso):
    booster, X, modelo, _ = modelos[caso]
    r = verificar_export(booster, modelo, X, n=800)
    assert r["aprovado"], r
    assert r["erro_max"] <= TOLERANCIA_BRUTO


def test_objeto_e_array_dao_o_mesmo(modelos):
    _, X, modelo, _ = modelos["regressao_log1p"]
    linha = [2.0, 3.0, None, 0.0, 1.2]
    obj = dict(zip(modelo["features"], linha, strict=True))
    assert prever_bruto_json(modelo, linha) == prever_bruto_json(modelo, obj)
    with pytest.raises(KeyError):
        prever_bruto_json(modelo, {"nao_existe": 1.0})


def test_arvore_de_uma_folha(tmp_path):
    X, y = _dados(n=200)
    booster = lgb.train({**BASE, "objective": "regression", "min_data_in_leaf": 10_000},
                        lgb.Dataset(X, y), num_boost_round=3)
    modelo = exportar_modelo(booster, tmp_path / "m.json", features=list(X.columns),
                             transformacao="identidade")
    assert all(a["feature"] == [] and len(a["folhas"]) == 1 for a in modelo["arvores"])
    assert verificar_export(booster, modelo, X)["aprovado"]


def test_init_score_explicito(tmp_path):
    X, y = _dados(n=600)
    c = 4.0
    booster = lgb.train({**BASE, "objective": "regression"},
                        lgb.Dataset(X, y, init_score=np.full(len(y), c)), num_boost_round=20)
    modelo = exportar_modelo(booster, tmp_path / "m.json", features=list(X.columns),
                             transformacao="expm1", init_score=c)
    assert modelo["init_score"] == c
    assert verificar_export(booster, modelo, X)["aprovado"]


# --- o export recusa o que daria numero errado ----------------------------

def test_recusa_features_fora_de_ordem(modelos, tmp_path):
    booster, X, _, _ = modelos["regressao_log1p"]
    with pytest.raises(ValueError, match="ordem"):
        exportar_modelo(booster, tmp_path / "m.json", features=list(X.columns)[::-1],
                        transformacao="expm1")


def test_recusa_transformacao_incoerente(modelos, tmp_path):
    booster, X, _, _ = modelos["poisson_zero"]
    with pytest.raises(ValueError, match="incoerente"):
        exportar_modelo(booster, tmp_path / "m.json", features=list(X.columns),
                        transformacao="expm1")


def test_recusa_multiclasse(tmp_path):
    X, y = _dados(n=300)
    classes = np.digitize(y, np.quantile(y, [0.33, 0.66]))
    booster = lgb.train({**BASE, "objective": "multiclass", "num_class": 3},
                        lgb.Dataset(X, classes), num_boost_round=2)
    with pytest.raises(NotImplementedError):
        exportar_modelo(booster, tmp_path / "m.json", features=list(X.columns),
                        transformacao="identidade")


def test_extras_mesclados_e_contrato_do_simulador(modelos, tmp_path):
    booster, X, _, _ = modelos["regressao_log1p"]
    extras = {
        "entradas_usuario": [
            {"chave": "tipo", "rotulo": "Tipo", "tipo": "categoria", "padrao": 0,
             "opcoes": [{"valor": 0, "rotulo": "Casa"}]},
            {"chave": "hospedes", "rotulo": "Hóspedes", "tipo": "inteiro", "padrao": 2},
        ],
        "features_local": ["dist_metro"],
        "features_fixas": {"nota": None, "avaliacoes": 0},
        "intervalo": {"nivel": 0.8, "q_inf": -0.3, "q_sup": 0.35},
    }
    modelo = exportar_modelo(booster, tmp_path / "m.json", features=list(X.columns),
                             transformacao="expm1", extras=extras)
    assert modelo["intervalo"]["q_sup"] == 0.35 and modelo["features_local"] == ["dist_metro"]

    sem_origem = {**extras, "features_fixas": {"nota": None}}  # "avaliacoes" sem origem
    with pytest.raises(ValueError, match="sem origem"):
        exportar_modelo(booster, tmp_path / "m2.json", features=list(X.columns),
                        transformacao="expm1", extras=sem_origem)
    with pytest.raises(ValueError, match="sobrescrever"):
        exportar_modelo(booster, tmp_path / "m3.json", features=list(X.columns),
                        transformacao="expm1", extras={"arvores": []})
    with pytest.raises(ValueError):  # NaN nao vira JSON valido para o navegador
        exportar_modelo(booster, tmp_path / "m4.json", features=list(X.columns),
                        transformacao="expm1", extras={"metricas": {"mae": float("nan")}})


def test_casos_incluem_nan_zero_e_extremos(modelos, tmp_path):
    booster, X, modelo, _ = modelos["regressao_log1p"]
    r = gerar_casos_paridade(booster, X, tmp_path / "c.json", modelo=modelo, n=300)
    assert r["n"] == 300 and r["com_nan"] > 0 and r["com_zero"] > 0
    casos = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    xs = [c["x"] for c in casos["casos"]]
    assert any(all(v is None for v in x) for x in xs)          # linha toda ausente
    assert any(x[0] is not None and x[0] < 0 for x in xs)      # categoria negativa


# --- paridade no Node: o MESMO modelo.js da pagina ------------------------

def _node(tmp_path: Path, modelo: Path, casos: Path) -> subprocess.CompletedProcess:
    return subprocess.run([NODE, str(PARIDADE), str(modelo), str(casos)], cwd=tmp_path,
                          capture_output=True, text=True, encoding="utf-8", timeout=120)


@pytest.mark.parametrize("caso", CASOS)
@pytest.mark.node
@pytest.mark.skipif(NODE is None, reason="node ausente")
def test_paridade_python_javascript(modelos, caso, tmp_path):
    booster, X, modelo, caminho = modelos[caso]
    gerar_casos_paridade(booster, X, tmp_path / "casos.json", modelo=modelo, n=500)
    r = _node(tmp_path, caminho, tmp_path / "casos.json")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "APROVADO" in r.stdout


@pytest.mark.node
@pytest.mark.skipif(NODE is None, reason="node ausente")
def test_paridade_confere_intervalo_por_grupo_e_teto(tmp_path):
    """O simulador usa o par do grupo da entrada; sem grupo, o global; e o teto."""
    X, y = _dados(n=1500)
    X = X.assign(tipo_cod=X["tipo"].cat.codes.astype(float)).drop(columns="tipo")
    X.loc[X["tipo_cod"] < 0, "tipo_cod"] = np.nan
    booster = lgb.train({**BASE, "objective": "tweedie"}, lgb.Dataset(X, np.expm1(y)),
                        num_boost_round=30)
    extras = {
        "intervalo": {"nivel": 0.8, "q_inf": -0.3, "q_sup": 0.3},
        "intervalo_por_grupo": {"chave": "tipo_cod", "grupos": {
            "0": {"q_inf": -0.2, "q_sup": 0.25}, "3": {"q_inf": 0.05, "q_sup": 0.9}}},
        "teto": 200.0,
    }
    modelo = exportar_modelo(booster, tmp_path / "m.json", features=list(X.columns),
                             transformacao="exp", extras=extras)
    gerar_casos_paridade(booster, X, tmp_path / "c.json", modelo=modelo, n=300)
    r = _node(tmp_path, tmp_path / "m.json", tmp_path / "c.json")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "casos com intervalo do grupo" in r.stdout

    # grupo que nao casa com nenhum valor ("0.0" nunca e o texto de um codigo inteiro)
    with pytest.raises(ValueError, match="inteiro em texto"):
        exportar_modelo(booster, tmp_path / "m2.json", features=list(X.columns),
                        transformacao="exp", extras={"intervalo_por_grupo": {
                            "chave": "tipo_cod", "grupos": {"0.0": {"q_inf": -1, "q_sup": 1}}}})


@pytest.mark.node
@pytest.mark.skipif(NODE is None, reason="node ausente")
def test_paridade_reprova_modelo_adulterado(modelos, tmp_path):
    """O teste tem de ser capaz de falhar: folhas alteradas em 1e-6 reprovam."""
    booster, X, modelo, _ = modelos["regressao_log1p"]
    gerar_casos_paridade(booster, X, tmp_path / "casos.json", modelo=modelo, n=200)
    adulterado = json.loads(json.dumps(modelo))
    adulterado["arvores"][0]["folhas"] = [v + 1e-6 for v in adulterado["arvores"][0]["folhas"]]
    (tmp_path / "adulterado.json").write_text(json.dumps(adulterado), encoding="utf-8")
    r = _node(tmp_path, tmp_path / "adulterado.json", tmp_path / "casos.json")
    assert r.returncode != 0 and "REPROVADO" in r.stderr


@pytest.mark.node
@pytest.mark.skipif(NODE is None, reason="node ausente")
def test_paridade_reprova_sem_caso_com_nan(modelos, tmp_path):
    booster, X, modelo, caminho = modelos["regressao_log1p"]
    gerar_casos_paridade(booster, X, tmp_path / "casos.json", modelo=modelo, n=200)
    casos = json.loads((tmp_path / "casos.json").read_text(encoding="utf-8"))
    casos["casos"] = [c for c in casos["casos"] if None not in c["x"]]
    (tmp_path / "sem_nan.json").write_text(json.dumps(casos), encoding="utf-8")
    r = _node(tmp_path, caminho, tmp_path / "sem_nan.json")
    assert r.returncode != 0 and "NaN" in r.stderr


@pytest.mark.node
@pytest.mark.skipif(NODE is None, reason="node ausente")
def test_paridade_reprova_transformacao_trocada(modelos, tmp_path):
    booster, X, modelo, caminho = modelos["tweedie"]
    gerar_casos_paridade(booster, X, tmp_path / "casos.json", modelo=modelo, n=100)
    casos = json.loads((tmp_path / "casos.json").read_text(encoding="utf-8"))
    casos["transformacao"] = "expm1"
    (tmp_path / "trocada.json").write_text(json.dumps(casos), encoding="utf-8")
    r = _node(tmp_path, caminho, tmp_path / "trocada.json")
    assert r.returncode != 0
