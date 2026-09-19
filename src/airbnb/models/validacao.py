"""Validacao espacial, metricas e intervalo conformal — comum a todos os modelos.

Por que espacial (ADR 0002): anuncios vizinhos compartilham o que o modelo nao
ve — a rua, o predio, o mesmo anfitriao com trinta unidades no quarteirao.
KFold aleatorio poe o vizinho no treino e o anuncio no teste; o erro medido vira
erro de *interpolacao*. O simulador do site faz outra coisa: preve para um ponto
que o usuario escolhe, possivelmente longe de qualquer anuncio. O erro que
interessa e o de *generalizar para um lugar novo*, e so o bloco espacial mede
isso. Bloco = celula H3 r6 (~36 km2).

O KFold aleatorio continua existindo aqui, mas so para medir o otimismo que ele
produziria (`docs/07`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, KFold

from airbnb.config import N_FOLDS, SEMENTE

# --- particao -----------------------------------------------------------------


def folds_espaciais(blocos: pd.Series | np.ndarray, n_folds: int = N_FOLDS,
                    semente: int = SEMENTE) -> np.ndarray:
    """Fold de cada linha, com todos os anuncios de um mesmo bloco no mesmo fold.

    `shuffle=True` embaralha a atribuicao de blocos: sem isso o GroupKFold
    ordena por tamanho e os folds viram faixas geograficas previsiveis.
    """
    blocos = np.asarray(blocos)
    fold = np.full(len(blocos), -1, dtype=np.int8)
    gkf = GroupKFold(n_splits=n_folds, shuffle=True, random_state=semente)
    for k, (_, teste) in enumerate(gkf.split(np.zeros(len(blocos)), groups=blocos)):
        fold[teste] = k
    return fold


def folds_aleatorios(n: int, n_folds: int = N_FOLDS, semente: int = SEMENTE) -> np.ndarray:
    """KFold ingenuo — existe so para medir o otimismo que ele produziria."""
    fold = np.full(n, -1, dtype=np.int8)
    for k, (_, teste) in enumerate(KFold(n_folds, shuffle=True, random_state=semente)
                                    .split(np.zeros(n))):
        fold[teste] = k
    return fold


def blocos_compartilhados(blocos: np.ndarray, fold: np.ndarray) -> int:
    """Quantos blocos aparecem em mais de um fold. Tem de ser zero no espacial."""
    df = pd.DataFrame({"b": blocos, "f": fold})
    return int((df.groupby("b")["f"].nunique() > 1).sum())


# --- metricas -----------------------------------------------------------------


def metricas_preco(y_log: np.ndarray, p_log: np.ndarray) -> dict[str, float]:
    """Metricas de preco a partir de alvo e previsao em log natural.

    Reportamos em dolar (MAE, erro absoluto mediano) porque e a unidade que o
    anfitriao entende, e MdAPE porque o erro relativo e comparavel entre um
    quarto de US$ 60 e uma cobertura de US$ 900. O R2 e no log, onde o modelo
    foi ajustado — R2 em dolar e dominado por meia duzia de anuncios de luxo.
    """
    y_log = np.asarray(y_log, dtype=float)
    p_log = np.asarray(p_log, dtype=float)
    y, p = np.exp(y_log), np.exp(p_log)
    erro = np.abs(p - y)
    ss_res = float(np.sum((y_log - p_log) ** 2))
    ss_tot = float(np.sum((y_log - y_log.mean()) ** 2))
    return {
        "n": int(len(y)),
        "mae_usd": float(erro.mean()),
        "mdae_usd": float(np.median(erro)),
        "mdape": float(np.median(erro / y)),
        "rmse_log": float(math.sqrt(ss_res / len(y))),
        "r2_log": float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan"),
    }


# --- conformal ----------------------------------------------------------------


def quantis_conformal(residuos: np.ndarray, nivel: float) -> tuple[float, float]:
    """Quantis do residuo (alvo - previsao) para um intervalo de nivel `nivel`.

    Correcao de amostra finita do conformal split: o quantil e tomado na
    posicao ceil((n+1)(1-a))/n, o que garante cobertura >= nivel sob
    permutabilidade. Intervalo assimetrico de proposito — no log, o erro
    de preco nao e simetrico (anuncio subprecificado erra mais para baixo).
    """
    r = np.sort(np.asarray(residuos, dtype=float))
    r = r[np.isfinite(r)]
    n = len(r)
    a = (1 - nivel) / 2
    k_sup = min(n - 1, math.ceil((n + 1) * (1 - a)) - 1)
    k_inf = max(0, math.floor((n + 1) * a) - 1)
    return float(r[k_inf]), float(r[k_sup])


def cobertura_honesta(residuos: np.ndarray, fold: np.ndarray, nivel: float,
                      grupos: np.ndarray | None = None) -> dict:
    """Cobertura medida fora da amostra que calibrou o intervalo.

    Para cada fold j, os quantis vem dos residuos dos OUTROS folds e a
    cobertura e medida em j. Calibrar e medir no mesmo residuo daria a
    cobertura nominal por construcao — seria um numero sem informacao.
    """
    residuos = np.asarray(residuos, dtype=float)
    dentro = np.zeros(len(residuos), dtype=bool)
    largura = np.zeros(len(residuos))
    for j in np.unique(fold):
        cal, tst = fold != j, fold == j
        q_inf, q_sup = quantis_conformal(residuos[cal], nivel)
        dentro[tst] = (residuos[tst] >= q_inf) & (residuos[tst] <= q_sup)
        largura[tst] = q_sup - q_inf
    saida = {
        "nivel": nivel,
        "cobertura": float(dentro.mean()),
        "largura_log_media": float(largura.mean()),
        # largura em fator multiplicativo: o intervalo vai de p*e^q_inf a p*e^q_sup
        "razao_sup_inf_media": float(np.exp(largura).mean()),
    }
    if grupos is not None:
        grupos = np.asarray(grupos)
        saida["por_grupo"] = {
            str(g): {"n": int((grupos == g).sum()), "cobertura": float(dentro[grupos == g].mean())}
            for g in pd.unique(grupos)
        }
    return saida


# --- LightGBM com validacao cruzada -------------------------------------------

PARAMS_BASE: dict = {
    "objective": "regression",
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 30,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "verbose": -1,
    "seed": SEMENTE,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 0,
}


@dataclass
class ResultadoCV:
    """Previsoes fora do fold e o numero de arvores que cada fold escolheu."""

    oof: np.ndarray
    melhores_iteracoes: list[int]
    importancia_ganho: pd.Series
    modelos: list[lgb.Booster] = field(default_factory=list, repr=False)

    @property
    def n_arvores(self) -> int:
        """Numero de arvores do modelo final: mediana do que a CV escolheu."""
        return int(np.median(self.melhores_iteracoes))


def treinar_cv(X: pd.DataFrame, y: np.ndarray, fold: np.ndarray, blocos: np.ndarray,
               params: dict | None = None, max_arvores: int = 3000,
               categoricas: list[str] | None = None, guardar_modelos: bool = False,
               semente: int = SEMENTE) -> ResultadoCV:
    """LightGBM com parada antecipada honesta.

    A parada antecipada precisa de um conjunto de validacao. Usar o fold de
    teste para isso vazaria o teste para a escolha do numero de arvores — o
    erro publicado seria otimista. Aqui a validacao sai do TREINO, por bloco
    espacial (15% dos blocos de treino), e o fold de teste so e tocado para
    prever.
    """
    params = {**PARAMS_BASE, **(params or {})}
    y = np.asarray(y, dtype=float)
    oof = np.full(len(y), np.nan)
    melhores, ganhos, modelos = [], [], []
    rng = np.random.default_rng(semente)
    for k in np.unique(fold):
        treino_idx = np.flatnonzero(fold != k)
        teste_idx = np.flatnonzero(fold == k)
        blocos_treino = pd.unique(blocos[treino_idx])
        n_val = max(1, int(round(0.15 * len(blocos_treino))))
        val_blocos = set(rng.choice(blocos_treino, size=n_val, replace=False))
        e_val = np.isin(blocos[treino_idx], list(val_blocos))
        tr, va = treino_idx[~e_val], treino_idx[e_val]

        d_tr = lgb.Dataset(X.iloc[tr], y[tr], categorical_feature=categoricas or "auto",
                           free_raw_data=False)
        d_va = lgb.Dataset(X.iloc[va], y[va], reference=d_tr,
                           categorical_feature=categoricas or "auto")
        m = lgb.train(params, d_tr, num_boost_round=max_arvores, valid_sets=[d_va],
                      callbacks=[lgb.early_stopping(100, verbose=False)])
        melhores.append(int(m.best_iteration or max_arvores))
        oof[teste_idx] = m.predict(X.iloc[teste_idx], num_iteration=m.best_iteration)
        ganhos.append(pd.Series(m.feature_importance("gain"), index=X.columns))
        if guardar_modelos:
            modelos.append(m)
    imp = pd.concat(ganhos, axis=1).mean(axis=1).sort_values(ascending=False)
    return ResultadoCV(oof=oof, melhores_iteracoes=melhores, importancia_ganho=imp,
                       modelos=modelos)


def treinar_final(X: pd.DataFrame, y: np.ndarray, n_arvores: int, params: dict | None = None,
                  categoricas: list[str] | None = None) -> lgb.Booster:
    """Modelo final no dado inteiro, com o numero de arvores que a CV escolheu."""
    params = {**PARAMS_BASE, **(params or {})}
    d = lgb.Dataset(X, np.asarray(y, dtype=float), categorical_feature=categoricas or "auto")
    return lgb.train(params, d, num_boost_round=n_arvores)
