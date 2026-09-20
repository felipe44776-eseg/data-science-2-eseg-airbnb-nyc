"""Validacao temporal: o mercado de 2019 ainda explica o de hoje?

Pergunta (docs/01, O5). Um modelo treinado em julho de 2019 (em dolar constante)
e aplicado aos anuncios de junho de 2026, com as MESMAS features — so as que os
dois snapshots tem (o Kaggle traz 16 colunas) mais a localizacao, cada snapshot
com a safra das suas fontes externas.

Tres numeros contam a historia:
  - o erro do modelo de 2019 em 2026 (generalizacao no tempo);
  - o erro de um modelo de 2026 com as mesmas features, sob CV espacial
    (o teto: o quanto essas features explicam o mercado atual);
  - a diferenca entre os dois = deriva de conceito.

O residuo "real de 2026 - previsto pela estrutura de 2019", agregado por celula
r8, e a valorizacao AJUSTADA: quanto a area ficou mais cara do que o mix de
anuncios e a localizacao dela fariam esperar em 2019 (ADR 0005).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

from airbnb import schema as S
from airbnb.config import PROCESSED
from airbnb.models import especificacao as E
from airbnb.models.validacao import folds_espaciais, metricas_preco, treinar_cv, treinar_final

SAIDA = PROCESSED / "_deriva.json"
SAIDA_R8 = PROCESSED / "deriva_r8.parquet"


def features() -> list[str]:
    return E.COMUNS_2019_2026 + E.LOCAL_BASE + E.externas()


def carregar(snapshot: str) -> pd.DataFrame:
    df = pd.read_parquet(PROCESSED / f"modelagem_{snapshot}.parquet")
    df = df[df[E.PRECO_VALIDO]].reset_index(drop=True)
    df["y"] = np.log(df[E.PRECO_REAL].to_numpy(dtype=float))
    return df


def psi(a: np.ndarray, b: np.ndarray, n_faixas: int = 10) -> float:
    """Population Stability Index de b em relacao a a (faixas pelos quantis de a).

    Convencao de mercado: < 0,1 estavel; 0,1–0,25 mudanca moderada; > 0,25 forte.
    """
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    cortes = np.unique(np.quantile(a, np.linspace(0, 1, n_faixas + 1)))
    if len(cortes) < 3:
        return float("nan")
    cortes[0], cortes[-1] = -np.inf, np.inf
    pa = np.histogram(a, cortes)[0] / len(a)
    pb = np.histogram(b, cortes)[0] / len(b)
    pa, pb = np.clip(pa, 1e-4, None), np.clip(pb, 1e-4, None)
    return float(np.sum((pb - pa) * np.log(pb / pa)))


def main() -> None:
    d19, d26 = carregar("2019"), carregar("2026")
    cols = features()

    # referencia: 2026 explicado por ele mesmo, com as mesmas features
    blocos26 = d26[E.BLOCO_CV].to_numpy()
    fold26 = folds_espaciais(blocos26)
    ref = treinar_cv(d26[cols], d26["y"].to_numpy(), fold26, blocos26)
    m_ref = metricas_preco(d26["y"], ref.oof)

    # 2019 -> 2026
    blocos19 = d19[E.BLOCO_CV].to_numpy()
    cv19 = treinar_cv(d19[cols], d19["y"].to_numpy(), folds_espaciais(blocos19), blocos19)
    m19 = treinar_final(d19[cols], d19["y"].to_numpy(), cv19.n_arvores)
    p = m19.predict(d26[cols])
    m_tempo = metricas_preco(d26["y"], p)
    m_19_em_19 = metricas_preco(d19["y"], cv19.oof)

    # 2026 -> 2019 (o caminho inverso: o mercado de hoje explica o de antes?)
    m26 = treinar_final(d26[cols], d26["y"].to_numpy(), ref.n_arvores)
    m_inverso = metricas_preco(d19["y"], m26.predict(d19[cols]))

    por_estrato = {}
    for (m30, tipo), g in d26.assign(_p=p).groupby([E.MIN30, E.TIPO_QUARTO]):
        if len(g) >= 100:
            chave = f"{'30+' if m30 else '<30'} | {tipo}"
            por_estrato[chave] = {
                **metricas_preco(g["y"], g["_p"]),
                # vies: >0 = em 2026 o estrato cobra MAIS do que a estrutura de 2019 previa
                "vies_log_medio": float((g["y"] - g["_p"]).mean()),
            }

    # A valorizacao ajustada era calculada sobre TODOS os anuncios da celula. Isso
    # violava a invariante 8 do projeto: o vies do modelo de 2019 e de +0,07 em log
    # na estadia de 30+ noites e de +0,63 a +1,29 na curta (ver `por_estrato` acima),
    # entao a media por celula media, em primeira ordem, ONDE A ESTADIA CURTA
    # SOBREVIVEU — nao valorizacao. Medido: rho(metrica antiga, fracao de curta na
    # celula) = 0,57. Agora o residuo e calculado DENTRO do estrato de 30+ noites,
    # que e 82% do mercado atual e o unico regime comparavel entre as duas safras.
    d26["residuo_2019"] = d26["y"] - p
    m30 = d26[E.MIN30].astype(bool)
    r8 = (d26.groupby(S.COL_H3_R8)["residuo_2019"].agg(["mean", "size"])
              .rename(columns={"mean": "residuo_log_todos", "size": "n"}).reset_index())
    longa = (d26[m30].groupby(S.COL_H3_R8)["residuo_2019"].agg(["mean", "size"])
                     .rename(columns={"mean": "residuo_log", "size": "n_30mais"}).reset_index())
    r8 = r8.merge(longa, on=S.COL_H3_R8, how="left")
    r8["valorizacao_ajustada_pct"] = np.where(
        r8["n_30mais"] >= 5, 100 * (np.exp(r8["residuo_log"]) - 1), np.nan)
    # a correlacao que motivou a mudanca, gravada no resultado e nao so no comentario
    pct_curta = (~m30).groupby(d26[S.COL_H3_R8]).mean().rename("pct_curta")
    diag = r8.join(pct_curta, on=S.COL_H3_R8).dropna(subset=["residuo_log_todos", "pct_curta"])
    rho_antigo = float(stats.spearmanr(diag["residuo_log_todos"], diag["pct_curta"]).statistic)
    rho_novo = float(stats.spearmanr(*diag.dropna(subset=["residuo_log"])[
        ["residuo_log", "pct_curta"]].to_numpy().T).statistic)
    r8.to_parquet(SAIDA_R8, index=False)
    # mesmo motivo da metrica do mapa: o ranking sai DENTRO do estrato de 30+ noites,
    # senao ele ordena bairros por quanta estadia curta sobreviveu neles
    bairros = (d26[m30].groupby(E.BAIRRO)["residuo_2019"].agg(["mean", "size"])
                  .query("size >= 30").sort_values("mean"))

    res = {
        "features": cols,
        "n_2019": int(len(d19)), "n_2026": int(len(d26)),
        "modelo_2019_cv_espacial_em_2019": m_19_em_19,
        "modelo_2026_cv_espacial_em_2026": m_ref,
        "modelo_2019_aplicado_a_2026": m_tempo,
        "valorizacao_ajustada": {
            "definicao": ("residuo medio de log(preco) contra a previsao do modelo de 2019, "
                          "DENTRO do estrato de 30+ noites (82% do mercado atual)"),
            "celulas_publicadas": int((r8["n_30mais"] >= 5).sum()),
            "rho_com_fracao_de_curta_antes": round(rho_antigo, 3),
            "rho_com_fracao_de_curta_depois": round(rho_novo, 3),
            "por_que": ("sem estratificar, a metrica media onde a estadia curta sobreviveu "
                        "em vez de valorizacao — invariante 8 do projeto"),
        },
        "modelo_2026_aplicado_a_2019": m_inverso,
        "deriva_mdape_pp": round(100 * (m_tempo["mdape"] - m_ref["mdape"]), 2),
        "vies_log_medio_2026": float(d26["residuo_2019"].mean()),
        "por_estrato": por_estrato,
        "psi": {c: round(psi(d19[c].to_numpy(dtype=float), d26[c].to_numpy(dtype=float)), 4)
                for c in cols},
        "bairros_mais_valorizados": {k: 100 * (np.exp(v) - 1)
                                     for k, v in bairros["mean"].tail(10)[::-1].items()},
        "bairros_menos_valorizados": {k: 100 * (np.exp(v) - 1)
                                      for k, v in bairros["mean"].head(10).items()},
    }
    SAIDA.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    print(f"2019 em 2019 (CV): MdAPE {m_19_em_19['mdape']:.3f} | 2026 em 2026 (CV): "
          f"{m_ref['mdape']:.3f} | 2019 -> 2026: {m_tempo['mdape']:.3f} | 2026 -> 2019: "
          f"{m_inverso['mdape']:.3f}")
    print(f"gravado {SAIDA.name} e {SAIDA_R8.name}")


if __name__ == "__main__":
    main()
