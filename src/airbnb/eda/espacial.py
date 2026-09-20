"""Testes de localizacao aplicados ao Airbnb de NYC.

"A localizacao importa" deixa de ser opiniao e vira hipotese testada (docs/06):

1. Autocorrelacao espacial global (I de Moran) do preco por celula r8 — em 2019
   e hoje. H0: o preco de uma celula nao se parece com o das vizinhas.
2. Mesma coisa para o PREMIO DE LOCALIZACAO: o residuo de um modelo que so ve o
   imovel (M2, fora do fold), medio por celula. O preco bruto mistura "onde" com
   "o que" (Manhattan tem mais apartamento inteiro); o residuo isola o "onde".
3. LISA (Moran local) com FDR: onde estao os aglomerados caros e baratos.
4. Diferenca entre distritos (Kruskal-Wallis + epsilon2 + pares com Holm) e a
   fracao da variancia do preco explicada por distrito, bairro e celula — contra
   a fracao explicada pelo proprio imovel.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from airbnb import schema as S
from airbnb.config import PROCESSED
from airbnb.eda.estatistica_espacial import (
    eta2,
    kruskal_com_efeito,
    lisa,
    moran_global,
    pares_mann_whitney,
)
from airbnb.models import especificacao as E
from airbnb.models.validacao import metricas_preco

SAIDA = PROCESSED / "_espacial.json"
SAIDA_R8 = PROCESSED / "espacial_r8.parquet"
MIN_ANUNCIOS = 5


def _por_celula(df: pd.DataFrame, coluna: str, estat: str = "median") -> pd.Series:
    g = df.groupby(S.COL_H3_R8)[coluna]
    v = g.agg(estat)
    return v[g.size() >= MIN_ANUNCIOS]


def main() -> None:
    d26 = pd.read_parquet(PROCESSED / "modelagem_2026.parquet")
    d26 = d26[d26[E.PRECO_VALIDO]].copy()
    d26["lp"] = np.log(d26[E.PRECO])
    d19 = pd.read_parquet(PROCESSED / "modelagem_2019.parquet")
    d19 = d19[d19[E.PRECO_VALIDO]].copy()
    d19["lp"] = np.log(d19[E.PRECO_REAL])

    oof = pd.read_parquet(PROCESSED / "preco_oof.parquet")[[E.ID, "oof_M2", "oof_M4"]]
    d26 = d26.merge(oof, on=E.ID, how="left")
    d26["premio_local"] = d26["lp"] - d26["oof_M2"]

    preco26 = _por_celula(d26, "lp")
    preco19 = _por_celula(d19, "lp")
    premio = _por_celula(d26, "premio_local", "mean")

    res = {
        "moran": {
            "preco_2026": moran_global(preco26),
            "preco_real_2019": moran_global(preco19),
            "premio_local_2026": moran_global(premio),
        }
    }
    cl = lisa(premio)
    cl_preco = lisa(preco26)
    res["lisa_premio_local"] = {
        "contagem": cl["cluster"].value_counts().to_dict(),
        "celulas": int(len(cl)),
    }
    res["lisa_preco_2026"] = {"contagem": cl_preco["cluster"].value_counts().to_dict()}

    # distritos, dentro do tipo de quarto (comparar tipos diferentes seria composicao)
    res["distritos"] = {}
    for tipo in S.ROOM_TYPES[:2]:
        g = d26[d26[E.TIPO_QUARTO] == tipo]
        res["distritos"][tipo] = {
            "kruskal": kruskal_com_efeito(g["lp"], g[E.DISTRITO]),
            "pares": pares_mann_whitney(np.exp(g["lp"]), g[E.DISTRITO]),
        }

    # quanto da variancia do log-preco cada nivel de localizacao explica, sozinho,
    # contra o que o imovel explica sozinho (R2 fora do fold do M2)
    res["variancia_explicada"] = {
        "distrito_eta2": eta2(d26["lp"], d26[E.DISTRITO]),
        "bairro_eta2": eta2(d26["lp"], d26[E.BAIRRO]),
        "celula_r8_eta2": eta2(d26["lp"], d26[S.COL_H3_R8]),
        "imovel_M2_r2_fora_do_fold": metricas_preco(d26["lp"], d26["oof_M2"])["r2_log"],
        "imovel_mais_local_M4_r2_fora_do_fold": metricas_preco(d26["lp"], d26["oof_M4"])["r2_log"],
        "nota": "eta2 de grupos pequenos e otimista (cada celula usa a propria media); "
                "os R2 dos modelos sao fora do fold e nao tem esse vies",
    }

    # Por que as fontes externas nao melhoram o preco (criterio C4): elas sao,
    # em quase toda a sua variancia, a propria celula com outro nome. Um modelo
    # que ja tem a localizacao nao ganha informacao ao receber de novo.
    res["redundancia_das_externas"] = {
        "definicao": "eta2 de cada feature externa explicado pela celula H3 r8",
        "por_feature": {c: eta2(d26[c].dropna(), d26.loc[d26[c].notna(), S.COL_H3_R8])
                        for c in E.externas() if c in d26.columns and d26[c].notna().sum() > 100},
        "nota": "eta2 alto = a feature nao carrega informacao alem de onde o anuncio esta",
    }
    pf = res["redundancia_das_externas"]["por_feature"]
    if pf:
        res["redundancia_das_externas"]["mediana_eta2"] = float(np.median(list(pf.values())))

    r8 = pd.DataFrame({
        "premio_local_pct": 100 * (np.exp(premio) - 1),
        "preco_mediano_2026": np.exp(preco26),
    })
    r8["lisa_premio"] = cl["cluster"]
    r8["lisa_preco"] = cl_preco["cluster"]
    r8.index.name = S.COL_H3_R8
    r8.reset_index().to_parquet(SAIDA_R8, index=False)
    SAIDA.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    m = res["moran"]
    print(f"Moran preco 2026 I={m['preco_2026']['I']:.3f} (p={m['preco_2026']['p_bilateral']:.3f}) | "
          f"2019 I={m['preco_real_2019']['I']:.3f} | premio local I={m['premio_local_2026']['I']:.3f}")
    print(f"LISA premio: {res['lisa_premio_local']['contagem']}")
    print(f"gravado {SAIDA.name} e {SAIDA_R8.name}")


if __name__ == "__main__":
    main()
