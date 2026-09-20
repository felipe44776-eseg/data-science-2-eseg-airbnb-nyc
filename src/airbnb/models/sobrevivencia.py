"""Quem sobreviveu de 2019 ate hoje? — classificacao e razoes de chance.

Pergunta (docs/01, O4): dos 48 mil anuncios de julho de 2019, quais ainda estao
no ar em junho de 2026 — atravessando a pandemia e a Local Law 18 — e o que os
distinguia ja em 2019?

"Sobreviver" aqui e o MESMO id de anuncio aparecer no snapshot atual. Nao e o
mesmo que o imovel continuar alugado: o anfitriao pode ter recriado o anuncio
com outro id, e o scrape do Inside Airbnb pode nao capturar um anuncio ativo.
As duas coisas contam como "nao sobreviveu" — limite declarado em docs/07.

Dois modelos, dois papeis:
  - logistica com erro-padrao agrupado por anfitriao: razoes de chance
    interpretaveis (anuncios do mesmo anfitriao saem juntos — sem agrupar, o IC
    fingiria ter mais informacao independente do que ha);
  - LightGBM sob CV espacial: quanto do destino e previsivel (AUC, PR-AUC,
    Brier) e o mapa de sobrevivencia prevista.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import shap
import statsmodels.api as sm
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from airbnb import schema as S
from airbnb.config import PROCESSED, SEMENTE
from airbnb.models import especificacao as E
from airbnb.models.validacao import folds_espaciais, treinar_cv, treinar_final

SAIDA = PROCESSED / "_sobrevivencia.json"
SAIDA_R8 = PROCESSED / "sobrevivencia_r8.parquet"
PARAMS = {"objective": "binary", "num_leaves": 31, "min_data_in_leaf": 50,
          "learning_rate": 0.05}

LOG_PRECO = "log_preco_real"
SEM_AVALIACAO = "sem_avaliacao"
DISP_ZERO = "disponibilidade_zero"


def carregar() -> pd.DataFrame:
    df = pd.read_parquet(PROCESSED / "modelagem_2019.parquet")
    df[LOG_PRECO] = np.log(df[E.PRECO_REAL].where(df[E.PRECO_VALIDO]))
    df[SEM_AVALIACAO] = (df[S.COL_N_AVALIACOES] == 0).astype(float)
    df[DISP_ZERO] = (df[S.COL_DISPONIBILIDADE_365] == 0).astype(float)
    df[E.SOBREVIVEU] = df[E.SOBREVIVEU].astype(float)
    return df


def features() -> list[str]:
    return (E.COMUNS_2019_2026 + [LOG_PRECO, S.COL_DIAS_ULTIMA_AVALIACAO, S.COL_HOST_MULTI,
                                  S.COL_OCUPACAO_MODELO, DISP_ZERO]
            + E.LOCAL_BASE + E.externas())


def metricas_classificacao(y: np.ndarray, p: np.ndarray) -> dict:
    prev = float(y.mean())
    return {
        "n": int(len(y)), "prevalencia": prev,
        "auc": float(roc_auc_score(y, p)),
        "pr_auc": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        # Brier de quem chuta a prevalencia para todos: o piso a bater
        "brier_baseline": float(prev * (1 - prev)),
    }


def calibracao(y: np.ndarray, p: np.ndarray, n_faixas: int = 10) -> list[dict]:
    faixa = pd.qcut(p, n_faixas, labels=False, duplicates="drop")
    t = pd.DataFrame({"y": y, "p": p, "f": faixa}).groupby("f")
    return [{"previsto": float(g.p.mean()), "observado": float(g.y.mean()), "n": int(len(g))}
            for _, g in t]


def logistica(df: pd.DataFrame) -> dict:
    """Razoes de chance com IC 95% agrupado por anfitriao."""
    d = df.copy()
    d["log1p_avaliacoes"] = np.log1p(d[S.COL_N_AVALIACOES])
    d["log_anuncios_host"] = np.log(d[S.COL_ANUNCIOS_HOST].clip(lower=1))
    d["avaliacao_recente_90d"] = (d[S.COL_DIAS_ULTIMA_AVALIACAO] <= 90).astype(float)
    X = pd.concat([
        d[[LOG_PRECO, S.COL_MIN30, "log1p_avaliacoes", "avaliacao_recente_90d",
           "log_anuncios_host", DISP_ZERO]].astype(float),
        # astype(str): o dtype categorico traz "Hotel room", que nao existe em 2019 —
        # a coluna de zeros tornaria a matriz singular
        pd.get_dummies(d[S.COL_ROOM_TYPE].astype(str), prefix="tipo", drop_first=True,
                       dtype=float),
        pd.get_dummies(d[E.DISTRITO].astype(str), prefix="distrito", drop_first=True,
                       dtype=float),
    ], axis=1)
    ok = X.notna().all(axis=1)
    X, y, grupos = sm.add_constant(X[ok]), d.loc[ok, E.SOBREVIVEU], d.loc[ok, S.COL_HOST_ID]
    m = sm.Logit(y, X).fit(disp=0, cov_type="cluster", cov_kwds={"groups": grupos})
    ic = m.conf_int()
    return {
        "n": int(ok.sum()), "n_anfitrioes": int(grupos.nunique()),
        "pseudo_r2": float(m.prsquared),
        "referencias": {"tipo": sorted(d[S.COL_ROOM_TYPE].astype(str).unique())[0],
                        "distrito": sorted(d[E.DISTRITO].astype(str).unique())[0]},
        "razoes_de_chance": {
            v: {"or": float(np.exp(m.params[v])), "ic95": [float(np.exp(ic.loc[v, 0])),
                                                          float(np.exp(ic.loc[v, 1]))],
                "p": float(m.pvalues[v])}
            for v in X.columns if v != "const"},
    }


def taxas(df: pd.DataFrame) -> dict:
    """Taxa observada de sobrevivencia por recorte — o descritivo que o modelo explica."""
    d = df.assign(faixa_host=pd.cut(df[S.COL_ANUNCIOS_HOST], [0, 1, 2, 5, 10, np.inf],
                                    labels=["1", "2", "3–5", "6–10", "11+"]),
                  recencia=pd.cut(df[S.COL_DIAS_ULTIMA_AVALIACAO], [-1, 90, 365, 1e6],
                                  labels=["≤ 90 dias", "91–365 dias", "> 1 ano"]))
    d["recencia"] = d["recencia"].cat.add_categories("sem avaliação").fillna("sem avaliação")
    saida = {}
    for col in (E.DISTRITO, S.COL_ROOM_TYPE, S.COL_MIN30, "faixa_host", "recencia"):
        t = d.groupby(col, observed=True)[E.SOBREVIVEU].agg(["mean", "size"])
        saida[col] = {str(k): {"taxa": float(r["mean"]), "n": int(r["size"])}
                      for k, r in t.iterrows()}
    return saida


def fracao_atribuivel_ll18(df: pd.DataFrame) -> dict:
    """Quanto do encolhimento a Local Law 18 explica — diferencas-em-diferencas ingenuo.

    O grupo de CONTROLE ja esta na base e ninguem tinha usado: um anuncio que em
    2019 ja exigia 30+ noites nunca esteve no alcance do registro. O EXPOSTO e o
    resto. Se os expostos tivessem morrido a taxa dos controles, quantos a mais
    teriam sobrevivido? Essa diferenca, sobre o total de mortes, e a fracao
    atribuivel.

    LIMITE, que vai publicado junto com o numero: em 2019 o grupo de 30+ noites
    era 9,2% do mercado e atipico — estadia longa mobiliada, outro publico, outra
    sazonalidade. Tendencias paralelas nao e testavel com dois pontos no tempo.
    O resultado e um PISO sob um desenho contestavel, nao um efeito causal
    estimado. Serve para dizer o que NAO se sustenta: que a lei explica "quase
    tudo" do encolhimento.
    """
    m30 = df[S.COL_MIN30].astype(bool)
    exp, ctl = df.loc[~m30, E.SOBREVIVEU], df.loc[m30, E.SOBREVIVEU]
    s_e, s_c = float(exp.mean()), float(ctl.mean())
    n_e, n_c = len(exp), len(ctl)
    mortes = n_e * (1 - s_e) + n_c * (1 - s_c)
    salvos = n_e * max(0.0, s_c - s_e)
    return {
        "exposto_min30_falso": {"n": n_e, "sobrevivencia": round(s_e, 6)},
        "controle_min30_verdadeiro": {"n": n_c, "sobrevivencia": round(s_c, 6)},
        "diferenca_pp": round(100 * (s_c - s_e), 2),
        "mortes_observadas": round(mortes, 0),
        "sobreviventes_no_contrafactual": round(salvos, 0),
        "fracao_atribuivel_pct": round(100 * salvos / mortes, 2),
        "limite": ("controle atipico (9,2% do mercado de 2019) e tendencias paralelas "
                   "nao testaveis com dois snapshots: e um piso, nao um efeito causal"),
    }


def main() -> None:
    df = carregar()
    cols = features()
    y = df[E.SOBREVIVEU].to_numpy()
    blocos = df[E.BLOCO_CV].to_numpy()
    fold = folds_espaciais(blocos)
    print(f"anuncios 2019: {len(df):,} | sobreviventes: {int(y.sum()):,} ({y.mean():.1%})")

    r = treinar_cv(df[cols], y, fold, blocos, params=PARAMS)
    met = metricas_classificacao(y, r.oof)
    so_anuncio = treinar_cv(df[E.COMUNS_2019_2026 + [LOG_PRECO, S.COL_DIAS_ULTIMA_AVALIACAO]],
                            y, fold, blocos, params=PARAMS)
    print(f"LightGBM CV espacial: AUC {met['auc']:.3f} | PR-AUC {met['pr_auc']:.3f} | "
          f"Brier {met['brier']:.4f} (baseline {met['brier_baseline']:.4f})")

    final = treinar_final(df[cols], y, r.n_arvores, params=PARAMS)
    amostra = df[cols].sample(min(5000, len(df)), random_state=SEMENTE)
    sv = shap.TreeExplainer(final).shap_values(amostra)
    sv = sv[1] if isinstance(sv, list) else sv
    shap_abs = pd.Series(np.abs(sv).mean(axis=0), index=cols).sort_values(ascending=False)

    df["p_sobrevivencia"] = r.oof
    r8 = (df.groupby(S.COL_H3_R8)
            .agg(n_2019=(E.SOBREVIVEU, "size"), sobrevivencia=(E.SOBREVIVEU, "mean"),
                 sobrevivencia_prevista=("p_sobrevivencia", "mean"))
            .reset_index())
    r8.loc[r8["n_2019"] < 5, ["sobrevivencia", "sobrevivencia_prevista"]] = np.nan
    r8.to_parquet(SAIDA_R8, index=False)

    res = {
        "definicao": "mesmo id de anúncio presente no snapshot atual",
        "lightgbm": {**met, "arvores": r.melhores_iteracoes,
                     "calibracao": calibracao(y, r.oof)},
        "lightgbm_sem_localizacao": metricas_classificacao(y, so_anuncio.oof),
        "shap_media_abs": shap_abs.round(5).head(20).to_dict(),
        "shap_por_grupo": shap_abs.groupby(E.grupo_de_cada_feature(cols)).sum()
                                  .sort_values(ascending=False).round(5).to_dict(),
        "logistica": logistica(df),
        "taxas": taxas(df),
        "fracao_atribuivel_ll18": fracao_atribuivel_ll18(df),
        "criterio_C5": {"auc_minimo": 0.70, "auc": met["auc"],
                        "atende": bool(met["auc"] >= 0.70 and met["brier"] < met["brier_baseline"])},
    }
    SAIDA.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print(f"gravado {SAIDA.name} e {SAIDA_R8.name}")


if __name__ == "__main__":
    main()
