"""Ocupacao e receita: o que a v0 tentou medir com `1 - availability_365/365`.

Pergunta (docs/01, O3): quantas noites por ano um anuncio como este, neste
lugar, fica ocupado — e quanto isso fatura?

O alvo e `estimated_occupancy_l365d`, a estimativa do proprio Inside Airbnb.
Verificado no dado (docs/07): ela e funcao deterministica das avaliacoes dos
ultimos 12 meses — zero se e somente se nao houve avaliacao; para anuncios de
30+ noites, 60 noites por avaliacao (30 noites / taxa de avaliacao de 50%); teto
de 255 noites (70% do ano). E um modelo de outro modelo, e dizemos isso.

Por isso o problema se parte em dois:
  1. o anuncio esta ATIVO (teve hospede no ano)? — 55% dos anuncios com preco
     nao tiveram nenhuma avaliacao em 12 meses: estao listados, nao operados;
  2. se ativo, quantas noites? — e este o numero que o simulador mostra, porque
     quem pergunta "quanto fatura" pretende operar o imovel.

Receita = preco x noites. Alem disso: quanto cobrar ACIMA do previsto pelo
modelo de preco custa em ocupacao (a "penalidade de sobrepreco").
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score

from airbnb import schema as S
from airbnb.config import PROCESSED
from airbnb.models import especificacao as E
from airbnb.models.validacao import folds_espaciais, treinar_cv

SAIDA = PROCESSED / "_ocupacao.json"
ATIVO = "ativo"
TETO_NOITES = 255

PARAMS_ATIVO = {"objective": "binary", "num_leaves": 31, "min_data_in_leaf": 50}
PARAMS_NOITES = {"num_leaves": 31, "min_data_in_leaf": 40, "learning_rate": 0.05}


def carregar() -> pd.DataFrame:
    df = pd.read_parquet(PROCESSED / "modelagem_2026.parquet")
    df = df[df[E.PRECO_VALIDO]].reset_index(drop=True)
    df[ATIVO] = (df[S.COL_N_AVALIACOES_LTM] > 0).astype(float)
    return df


def metricas_noites(y: np.ndarray, p: np.ndarray) -> dict:
    erro = np.abs(p - y)
    return {"n": int(len(y)), "mae_noites": float(erro.mean()),
            "mdae_noites": float(np.median(erro)),
            "spearman": float(stats.spearmanr(y, p).statistic),
            "media_observada": float(y.mean()), "media_prevista": float(p.mean())}


def baseline_grupo(df: pd.DataFrame, y: np.ndarray, fold: np.ndarray) -> np.ndarray:
    """Mediana do treino por bairro x tipo x minimo de noites, com recuo para tipo x min30."""
    oof = np.empty(len(y))
    chaves = [E.BAIRRO, E.TIPO_QUARTO, E.MIN30]
    for k in np.unique(fold):
        tr, te = fold != k, fold == k
        d_tr = df.loc[tr, chaves].assign(y=y[tr])
        fina = d_tr.groupby(chaves)["y"].median().rename("a")
        grossa = d_tr.groupby(chaves[1:])["y"].median().rename("b")
        t = df.loc[te, chaves].join(fina, on=chaves).join(grossa, on=chaves[1:])
        oof[te] = t["a"].fillna(t["b"]).fillna(np.median(y[tr])).to_numpy()
    return oof


def penalidade_sobrepreco(df: pd.DataFrame) -> dict | None:
    """Ocupacao dos ativos por faixa de 'preco acima do previsto' (residuo fora do fold)."""
    oof = PROCESSED / "preco_oof.parquet"
    if not oof.exists():
        return None
    r = pd.read_parquet(oof)[[E.ID, "y_log", "oof_M5"]]
    d = df[df[ATIVO] == 1].merge(r, on=E.ID, how="inner")
    d["acima_pct"] = 100 * (np.exp(d["y_log"] - d["oof_M5"]) - 1)
    faixas = [-np.inf, -20, -5, 5, 20, np.inf]
    rotulos = ["≥ 20% abaixo", "5–20% abaixo", "±5%", "5–20% acima", "≥ 20% acima"]
    d["faixa"] = pd.cut(d["acima_pct"], faixas, labels=rotulos)
    saida = {}
    for m30, g in d.groupby(E.MIN30):
        t = g.groupby("faixa", observed=True)[E.OCUPACAO].agg(["median", "mean", "size"])
        saida["30+ noites" if m30 else "< 30 noites"] = {
            str(k): {"mediana_noites": float(v["median"]), "media_noites": float(v["mean"]),
                     "n": int(v["size"])} for k, v in t.iterrows()}
    rho = stats.spearmanr(d["acima_pct"], d[E.OCUPACAO]).statistic
    return {"por_estrato": saida, "spearman_sobrepreco_ocupacao": float(rho), "n": int(len(d))}


def receita_vs_aluguel(df: pd.DataFrame) -> dict:
    """O Airbnb fatura mais que um ano de aluguel de longo prazo no mesmo lugar?

    So apartamento/casa inteira ativo (quarto privativo nao compete com o aluguel
    do imovel inteiro). Aluguel = ZORI do CEP da celula x 12, em dolar de 2026-06.
    Receita = estimated_revenue_l365d (preco x noites estimadas) — bruta: sem
    taxa da plataforma, limpeza, mobilia, vacancia entre estadias.
    """
    at = df[(df[ATIVO] == 1) & (df[E.TIPO_QUARTO_COD] == 0) & df[E.ZORI].notna()]
    razao = at[S.COL_RECEITA_L365D] / (12 * at[E.ZORI])
    saida = {
        "n": int(len(at)),
        "razao_mediana": float(razao.median()),
        "pct_receita_acima_de_um_ano_de_aluguel": float((razao > 1).mean()),
        "por_min30": {("30+ noites" if k else "< 30 noites"):
                      {"n": int(len(g)), "razao_mediana": float(g.median()),
                       "pct_acima": float((g > 1).mean())}
                      for k, g in razao.groupby(at[E.MIN30])},
        "por_distrito": {str(k): {"n": int(len(g)), "razao_mediana": float(g.median()),
                                  "pct_acima": float((g > 1).mean())}
                         for k, g in razao.groupby(at[E.DISTRITO]) if len(g) >= 30},
    }
    return saida


def main() -> None:
    df = carregar()
    cols = E.produto()
    blocos = df[E.BLOCO_CV].to_numpy()
    fold = folds_espaciais(blocos)

    # parte 1 — atividade
    ya = df[ATIVO].to_numpy()
    ra = treinar_cv(df[cols], ya, fold, blocos, params=PARAMS_ATIVO)
    auc = float(roc_auc_score(ya, ra.oof))

    # parte 2 — noites, entre os ativos (alvo em log: erro relativo, como no preco)
    at = df[df[ATIVO] == 1].reset_index(drop=True)
    fold_at = folds_espaciais(at[E.BLOCO_CV].to_numpy())
    yn = at[E.OCUPACAO].to_numpy(dtype=float)
    rn = treinar_cv(at[cols], np.log(yn), fold_at, at[E.BLOCO_CV].to_numpy(),
                    params=PARAMS_NOITES)
    pn = np.minimum(np.exp(rn.oof), TETO_NOITES)
    base = baseline_grupo(at, yn, fold_at)
    receita_obs = at[E.PRECO].to_numpy() * yn
    receita_prev = np.exp(pd.read_parquet(PROCESSED / "preco_oof.parquet")
                            .set_index(E.ID).loc[at[E.ID], "oof_M5"].to_numpy()) * pn \
        if (PROCESSED / "preco_oof.parquet").exists() else None

    res = {
        "alvo": "estimated_occupancy_l365d (Inside Airbnb)",
        "n_com_preco": int(len(df)),
        "pct_ativos": float(ya.mean()),
        "pct_ativos_por_min30": {("30+ noites" if k else "< 30 noites"): float(v)
                                 for k, v in df.groupby(E.MIN30)[ATIVO].mean().items()},
        "atividade": {"auc": auc, "arvores": ra.melhores_iteracoes},
        "noites_se_ativo": {
            "modelo": metricas_noites(yn, pn),
            "baseline_bairro_tipo_min30": metricas_noites(yn, base),
            "arvores": rn.melhores_iteracoes,
            "n_arvores_final": rn.n_arvores,
            "pct_no_teto": float((yn >= TETO_NOITES).mean()),
        },
        "receita_se_ativo": None if receita_prev is None else {
            "mediana_observada": float(np.median(receita_obs)),
            "mediana_prevista": float(np.median(receita_prev)),
            "spearman": float(stats.spearmanr(receita_obs, receita_prev).statistic),
        },
        "penalidade_sobrepreco": penalidade_sobrepreco(df),
        "receita_vs_aluguel": receita_vs_aluguel(df),
        "features": cols,
    }
    SAIDA.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    nm, nb = res["noites_se_ativo"]["modelo"], res["noites_se_ativo"]["baseline_bairro_tipo_min30"]
    print(f"ativos: {ya.mean():.1%} (AUC atividade {auc:.3f}) | noites se ativo: MAE "
          f"{nm['mae_noites']:.1f} (baseline {nb['mae_noites']:.1f}), Spearman {nm['spearman']:.3f}")
    print(f"gravado {SAIDA.name}")


if __name__ == "__main__":
    main()
