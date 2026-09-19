"""Modelo hedonico de preco: escada de modelos, ablacao por fonte, conformal e SHAP.

Pergunta (docs/01, O1/O2): quanto um imovel com estas caracteristicas, neste
ponto da cidade, deveria cobrar por noite — e com que margem de erro?

A escada existe para que cada degrau justifique o seguinte com numero:

  B0  mediana global                      — o que se sabe sem olhar nada
  B1  mediana por bairro x tipo de quarto — o que a analise descritiva (v0) sabe
  M1  regressao linear hedonica           — o classico da literatura
  M2  LightGBM, so atributos do anuncio   — o imovel sem a localizacao
  M3  M2 + coordenadas e distrito         — a localizacao como latitude/longitude
  M4  M3 + fontes externas                — a localizacao como o que ha nela
  M5  produto: entradas do simulador + localizacao, compacto para o navegador

Tudo sob CV espacial por bloco H3 r6 (ADR 0002). A ablacao retira uma fonte
externa por vez do M4 e mede o quanto o erro piora: e o numero que diz se buscar
dado fora do Kaggle valeu a pena (criterio C4).
"""

from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
import shap
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from airbnb.config import COBERTURA_ALVO, PROCESSED, SEMENTE
from airbnb.models import especificacao as E
from airbnb.models.validacao import (
    cobertura_honesta,
    folds_aleatorios,
    folds_espaciais,
    metricas_preco,
    quantis_conformal,
    treinar_cv,
    treinar_final,
)

SAIDA = PROCESSED / "_preco.json"
OOF = PROCESSED / "preco_oof.parquet"

#: Modelo do produto: menor e mais raso, para caber no navegador (ADR 0004).
#: O custo em erro frente ao M4 e medido e publicado.
PARAMS_PRODUTO = {"num_leaves": 31, "learning_rate": 0.08, "min_data_in_leaf": 40}
MAX_ARVORES_PRODUTO = 600
MIN_GRUPO_CONFORMAL = 100


def carregar() -> pd.DataFrame:
    df = pd.read_parquet(PROCESSED / "modelagem_2026.parquet")
    return df[df[E.PRECO_VALIDO]].reset_index(drop=True)


# --- baselines ----------------------------------------------------------------


def baseline_mediana(y: np.ndarray, fold: np.ndarray, chaves: list[np.ndarray] | None) -> np.ndarray:
    """Mediana do treino por combinacao de chaves, com recuo para chaves mais grossas.

    Sem chaves: mediana global. Com [bairro, tipo]: bairro x tipo; se a
    combinacao nao existe no treino (bairro inteiro no fold de teste — o caso
    normal na CV espacial), recua para tipo; se nem isso, global. As chaves vao
    da mais fina para a mais grossa: o recuo descarta pela esquerda.
    """
    oof = np.empty(len(y))
    for k in np.unique(fold):
        tr, te = fold != k, fold == k
        global_ = np.median(y[tr])
        if not chaves:
            oof[te] = global_
            continue
        df_tr = pd.DataFrame({f"c{i}": c[tr] for i, c in enumerate(chaves)} | {"y": y[tr]})
        df_te = pd.DataFrame({f"c{i}": c[te] for i, c in enumerate(chaves)})
        pred = pd.Series(np.nan, index=df_te.index)
        for n in range(len(chaves), 0, -1):
            cols = [f"c{i}" for i in range(len(chaves) - n, len(chaves))]
            med = df_tr.groupby(cols)["y"].median().rename("m").reset_index()
            falta = pred.isna()
            achado = df_te.loc[falta, cols].merge(med, on=cols, how="left")["m"].to_numpy()
            pred.loc[falta] = achado
        oof[te] = pred.fillna(global_).to_numpy()
    return oof


def linear_hedonico(X: pd.DataFrame, y: np.ndarray, fold: np.ndarray,
                    categoricas: list[str]) -> np.ndarray:
    """Regressao linear regularizada no log do preco (M1)."""
    numericas = [c for c in X.columns if c not in categoricas]
    prep = ColumnTransformer([
        ("num", make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                              StandardScaler()), numericas),
        ("cat", make_pipeline(SimpleImputer(strategy="most_frequent"),
                              OneHotEncoder(handle_unknown="ignore")), categoricas),
    ])
    oof = np.empty(len(y))
    for k in np.unique(fold):
        tr, te = fold != k, fold == k
        m = make_pipeline(prep, RidgeCV(alphas=np.logspace(-2, 3, 12)))
        m.fit(X[tr], y[tr])
        oof[te] = m.predict(X[te])
    return oof


# --- escada, ablacao, conformal -----------------------------------------------


def _resumo_folds(y: np.ndarray, oof: np.ndarray, fold: np.ndarray) -> dict:
    """Metricas globais + dispersao entre folds (a ablacao precisa da dispersao)."""
    geral = metricas_preco(y, oof)
    por_fold = [metricas_preco(y[fold == k], oof[fold == k]) for k in np.unique(fold)]
    geral["mdape_folds"] = [round(f["mdape"], 4) for f in por_fold]
    geral["mae_usd_folds"] = [round(f["mae_usd"], 2) for f in por_fold]
    return geral


def escada(df: pd.DataFrame, fold: np.ndarray, blocos: np.ndarray) -> tuple[dict, dict]:
    y = np.log(df[E.PRECO].to_numpy(dtype=float))
    res, oofs = {}, {}

    oofs["B0"] = baseline_mediana(y, fold, None)
    oofs["B1"] = baseline_mediana(y, fold, [df[E.BAIRRO].to_numpy(), df[E.TIPO_QUARTO].to_numpy()])

    cols_m1 = E.ANUNCIO + E.LOCAL_BASE
    oofs["M1"] = linear_hedonico(df[cols_m1], y, fold, categoricas=E.CATEGORICAS_LINEAR)

    for nome, cols in (("M2", E.ANUNCIO), ("M3", E.ANUNCIO + E.LOCAL_BASE),
                       ("M4", E.ANUNCIO + E.LOCAL_BASE + E.externas())):
        r = treinar_cv(df[cols], y, fold, blocos)
        oofs[nome] = r.oof
        res[nome + "_arvores"] = r.melhores_iteracoes
        if nome == "M4":
            res["M4_importancia_ganho"] = (r.importancia_ganho / r.importancia_ganho.sum()
                                           ).round(5).head(40).to_dict()

    # sem coordenadas, so fontes externas: as externas SUBSTITUEM a lat/lon?
    cols = E.ANUNCIO + [E.DISTRITO_COD] + E.externas()
    oofs["M4_sem_coordenadas"] = treinar_cv(df[cols], y, fold, blocos).oof

    r5 = treinar_cv(df[E.produto()], y, fold, blocos, params=PARAMS_PRODUTO,
                    max_arvores=MAX_ARVORES_PRODUTO)
    oofs["M5"] = r5.oof
    res["M5_arvores"] = r5.melhores_iteracoes
    res["M5_n_arvores_final"] = r5.n_arvores

    res["metricas"] = {k: _resumo_folds(y, v, fold) for k, v in oofs.items()}
    return res, oofs


def ablacao(df: pd.DataFrame, fold: np.ndarray, blocos: np.ndarray, base_oof: np.ndarray) -> dict:
    """Retira UMA fonte externa por vez do M4. Positivo = a fonte ajudava."""
    y = np.log(df[E.PRECO].to_numpy(dtype=float))
    base = metricas_preco(y, base_oof)
    base_folds = np.array([metricas_preco(y[fold == k], base_oof[fold == k])["mdape"]
                           for k in np.unique(fold)])
    saida = {}
    for grupo, cols_grupo in E.grupos_externos().items():
        cols = [c for c in E.ANUNCIO + E.LOCAL_BASE + E.externas() if c not in cols_grupo]
        oof = treinar_cv(df[cols], y, fold, blocos).oof
        m = metricas_preco(y, oof)
        folds = np.array([metricas_preco(y[fold == k], oof[fold == k])["mdape"]
                          for k in np.unique(fold)])
        delta = folds - base_folds
        saida[grupo] = {
            "features": cols_grupo,
            "delta_mdape_pp": round(100 * (m["mdape"] - base["mdape"]), 3),
            "delta_mae_usd": round(m["mae_usd"] - base["mae_usd"], 2),
            # quantos folds pioram sem a fonte: 5/5 e evidencia consistente
            "folds_que_pioram": int((delta > 0).sum()),
            "delta_mdape_pp_folds": [round(100 * d, 3) for d in delta],
        }
    return dict(sorted(saida.items(), key=lambda kv: -kv[1]["delta_mdape_pp"]))


def conformal_produto(y: np.ndarray, oof: np.ndarray, fold: np.ndarray,
                      grupos: np.ndarray) -> dict:
    """Intervalo de 80% do produto: global e por tipo de quarto (Mondrian).

    O global cobre ~80% na media, mas os grupos pequenos (quarto de hotel,
    compartilhado) erram mais e ficam descobertos. O Mondrian calibra um par de
    quantis por grupo — cobertura condicional, que e a que o usuario do
    simulador experimenta. Grupo com menos de MIN_GRUPO_CONFORMAL residuos usa o
    global: com 100, cada cauda de 10% ainda tem 10 residuos.
    """
    r = y - oof
    global_ = quantis_conformal(r, COBERTURA_ALVO)
    honesta_global = cobertura_honesta(r, fold, COBERTURA_ALVO, grupos=grupos)
    por_grupo, dentro = {}, np.zeros(len(r), dtype=bool)
    for g in pd.unique(grupos):
        m = grupos == g
        q = quantis_conformal(r[m], COBERTURA_ALVO) if m.sum() >= MIN_GRUPO_CONFORMAL else global_
        por_grupo[str(g)] = {"n": int(m.sum()), "q_inf": q[0], "q_sup": q[1]}
    # cobertura honesta do Mondrian: calibra fora do fold, mede no fold
    for k in np.unique(fold):
        cal, tst = fold != k, fold == k
        for g in pd.unique(grupos):
            mc, mt = cal & (grupos == g), tst & (grupos == g)
            q = quantis_conformal(r[mc], COBERTURA_ALVO) if mc.sum() >= MIN_GRUPO_CONFORMAL else \
                quantis_conformal(r[cal], COBERTURA_ALVO)
            dentro[mt] = (r[mt] >= q[0]) & (r[mt] <= q[1])
    return {
        "nivel": COBERTURA_ALVO,
        "global": {"q_inf": global_[0], "q_sup": global_[1], "honesta": honesta_global},
        "mondrian": {
            "por_grupo": por_grupo,
            "cobertura_honesta": float(dentro.mean()),
            "cobertura_honesta_por_grupo": {
                str(g): float(dentro[grupos == g].mean()) for g in pd.unique(grupos)},
        },
    }


def otimismo_aleatorio(df: pd.DataFrame, blocos: np.ndarray) -> dict:
    """O mesmo M4 sob KFold aleatorio: quanto a validacao ingenua infla o resultado."""
    y = np.log(df[E.PRECO].to_numpy(dtype=float))
    fold = folds_aleatorios(len(df))
    r = treinar_cv(df[E.ANUNCIO + E.LOCAL_BASE + E.externas()], y, fold, blocos)
    return metricas_preco(y, r.oof)


def shap_m4(df: pd.DataFrame, n_arvores: int, n_amostra: int = 4000) -> dict:
    """Contribuicao media absoluta (SHAP) por feature e por fonte, no M4 final.

    Importancia por ganho mede o uso da feature nas divisoes; SHAP mede o quanto
    ela move a previsao — e soma certinho por grupo, o que responde "quanto do
    preco a localizacao explica" sem dupla contagem.
    """
    cols = E.ANUNCIO + E.LOCAL_BASE + E.externas()
    y = np.log(df[E.PRECO].to_numpy(dtype=float))
    modelo = treinar_final(df[cols], y, n_arvores)
    amostra = df[cols].sample(min(n_amostra, len(df)), random_state=SEMENTE)
    valores = shap.TreeExplainer(modelo).shap_values(amostra)
    media_abs = pd.Series(np.abs(valores).mean(axis=0), index=cols).sort_values(ascending=False)
    grupos = E.grupo_de_cada_feature(cols)
    por_grupo = media_abs.groupby(grupos).sum().sort_values(ascending=False)
    # dependencia das principais features de localizacao: media do SHAP por faixa
    dependencia = {}
    for f in [c for c in media_abs.index if grupos[c] != "anúncio"][:6]:
        x = amostra[f]
        faixas = pd.qcut(x.rank(method="first"), q=min(12, x.nunique()), labels=False)
        tab = pd.DataFrame({"x": x, "s": valores[:, cols.index(f)], "b": faixas}).groupby("b")
        dependencia[f] = {"x": tab["x"].median().round(4).tolist(),
                          "shap": tab["s"].mean().round(4).tolist()}
    return {
        "n_amostra": int(len(amostra)),
        "media_abs_por_feature": media_abs.round(5).head(30).to_dict(),
        "media_abs_por_grupo": por_grupo.round(5).to_dict(),
        "fracao_por_grupo": (por_grupo / por_grupo.sum()).round(4).to_dict(),
        "dependencia": dependencia,
    }


def main() -> None:
    t0 = time.time()
    df = carregar()
    blocos = df[E.BLOCO_CV].to_numpy()
    fold = folds_espaciais(blocos)
    y = np.log(df[E.PRECO].to_numpy(dtype=float))
    print(f"anuncios com preco valido: {len(df):,} | blocos r6: {len(set(blocos))}")

    res, oofs = escada(df, fold, blocos)
    for k, m in res["metricas"].items():
        print(f"  {k:<20} MdAPE {m['mdape']:.3f}  MAE US$ {m['mae_usd']:7.1f}  R2(log) {m['r2_log']:.3f}")

    print("ablacao por fonte externa...")
    res["ablacao"] = ablacao(df, fold, blocos, oofs["M4"])
    res["otimismo_kfold_aleatorio"] = otimismo_aleatorio(df, blocos)
    res["conformal_produto"] = conformal_produto(y, oofs["M5"], fold,
                                                 df[E.TIPO_QUARTO].to_numpy())
    res["shap_m4"] = shap_m4(df, int(np.median(res["M4_arvores"])))

    # desempenho do produto por estrato — o que o usuario do simulador experimenta
    res["produto_por_estrato"] = {
        col: {str(g): metricas_preco(y[m], oofs["M5"][m])
              for g in pd.unique(df[col]) if (m := (df[col] == g).to_numpy()).sum() >= 100}
        for col in (E.TIPO_QUARTO, E.DISTRITO, E.MIN30)
    }
    b1, m5 = res["metricas"]["B1"], res["metricas"]["M5"]
    m3, m4 = res["metricas"]["M3"], res["metricas"]["M4"]
    res["criterios"] = {
        "C1_mae_vs_b1_pct": round(100 * (1 - m5["mae_usd"] / b1["mae_usd"]), 2),
        "C2_mdape_produto": round(m5["mdape"], 4),
        "C3_cobertura_mondrian": round(
            res["conformal_produto"]["mondrian"]["cobertura_honesta"], 4),
        # C4 como registrado em docs/01: com as fontes externas (M4) o erro cai frente ao
        # mesmo modelo so com coordenadas (M3), de forma consistente entre folds
        "C4_folds_em_que_externas_melhoram": int(sum(
            a < b for a, b in zip(m4["mdape_folds"], m3["mdape_folds"], strict=True))),
        "C4_delta_mdape_pp": round(100 * (m4["mdape"] - m3["mdape"]), 3),
    }
    res["n"] = int(len(df))
    res["n_blocos"] = int(len(set(blocos)))
    res["features"] = {"M4": E.ANUNCIO + E.LOCAL_BASE + E.externas(), "M5": E.produto()}
    res["segundos"] = round(time.time() - t0, 1)

    pd.DataFrame({E.ID: df[E.ID], "fold": fold, "y_log": y,
                  **{f"oof_{k}": v for k, v in oofs.items()}}).to_parquet(OOF, index=False)
    SAIDA.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float),
                     encoding="utf-8")
    print(f"criterios: {res['criterios']}")
    print(f"gravado {SAIDA.relative_to(PROCESSED.parents[1])} em {res['segundos']}s")


if __name__ == "__main__":
    main()
