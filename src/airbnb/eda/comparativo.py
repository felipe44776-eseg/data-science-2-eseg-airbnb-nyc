"""Comparativo 2019 -> atual: o que mudou no Airbnb de Nova York.

Duas regras do ADR 0005 governam tudo aqui:

1. Preco de 2019 so se compara em DOLAR CONSTANTE (CPI-U NY, `CUURS12ASA0`).
2. Toda comparacao de preco e ESTRATIFICADA por minimo de noites (< 30 / >= 30)
   e tipo de quarto. Pos-Local Law 18 a maioria dos anuncios exige 30+ noites e
   o `price` virou cotacao de estadia longa com desconto — a mediana agregada
   mede mudanca de COMPOSICAO, nao de preco. A decomposicao shift-share separa
   as duas coisas com numero.

Saidas: data/processed/_comparativo.json e comparativo_r8.parquet (metricas por
celula H3 r8, lidas pela exportacao do site).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from airbnb import schema as S
from airbnb.config import PROCESSED, ROTULO_2019, ROTULO_ATUAL, SEMENTE, SNAPSHOT_2019
from airbnb.external.cpi import fator_cpi

SAIDA = PROCESSED / "_comparativo.json"
SAIDA_R8 = PROCESSED / "comparativo_r8.parquet"
COL_PRECO_REAL = "preco_real"
ESTRATO = "estrato"

#: celula r8 com menos anuncios que isto nao publica mediana de preco
MIN_ANUNCIOS_CELULA = 5


def carregar() -> tuple[pd.DataFrame, dict]:
    df = pd.read_parquet(PROCESSED / f"{S.SRESUMO}.parquet")
    fator, mes_para = fator_cpi(de=SNAPSHOT_2019[:7])
    e19 = df[S.COL_SNAPSHOT] == ROTULO_2019
    df[COL_PRECO_REAL] = df[S.COL_PRECO].where(~e19, df[S.COL_PRECO] * fator)
    df[ESTRATO] = np.where(df[S.COL_MIN30], "30+ noites", "< 30 noites")
    return df, {"fator": round(float(fator), 6), "de": SNAPSHOT_2019[:7], "para": mes_para}


def _mediana_ic(x: np.ndarray, n_boot: int = 1000, semente: int = SEMENTE) -> tuple:
    """Mediana e IC 95% por bootstrap percentil."""
    x = np.asarray(x, dtype=float)
    if len(x) < 10:
        return (float(np.median(x)) if len(x) else None, None, None)
    rng = np.random.default_rng(semente)
    # em lotes de 100 reamostragens: 1000 x 25 mil de uma vez seriam ~200 MB
    boot = np.concatenate([np.median(rng.choice(x, size=(100, len(x)), replace=True), axis=1)
                           for _ in range(n_boot // 100)])
    return float(np.median(x)), float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))


def kpis(df: pd.DataFrame) -> dict:
    """Indicadores de cada snapshot, sobre a base (nao so os anuncios com preco)."""
    saida = {}
    for snap, g in df.groupby(S.COL_SNAPSHOT):
        p = g.loc[g[S.COL_PRECO_VALIDO], COL_PRECO_REAL]
        por_host = g.groupby(S.COL_HOST_ID).size().sort_values(ascending=False)
        top = por_host.head(max(1, int(len(por_host) * 0.01)))
        saida[snap] = {
            "anuncios": int(len(g)),
            "anfitrioes": int(g[S.COL_HOST_ID].nunique()),
            "anuncios_com_preco": int(g[S.COL_PRECO_VALIDO].sum()),
            "pct_inteiro": float((g[S.COL_ROOM_TYPE] == S.ROOM_TYPES[0]).mean()),
            "pct_min30": float(g[S.COL_MIN30].mean()),
            "pct_host_multi": float(g[S.COL_HOST_MULTI].mean()),
            # concentracao: fatia dos anuncios nas maos do 1% de anfitrioes com mais anuncios
            "pct_anuncios_top1pct_hosts": float(top.sum() / len(g)),
            "pct_disponibilidade_zero": float((g[S.COL_DISPONIBILIDADE_365] == 0).mean()),
            "preco_mediano_real": float(p.median()),
            "preco_mediano_nominal": float(g.loc[g[S.COL_PRECO_VALIDO], S.COL_PRECO].median()),
            # invariante 8: o preco agregado so e publicado ao lado do estratificado
            "preco_mediano_real_curta": float(
                g.loc[g[S.COL_PRECO_VALIDO] & ~g[S.COL_MIN30], COL_PRECO_REAL].median()),
            "preco_mediano_real_longa": float(
                g.loc[g[S.COL_PRECO_VALIDO] & g[S.COL_MIN30], COL_PRECO_REAL].median()),
        }
    return saida


def preco_por_estrato(df: pd.DataFrame) -> list[dict]:
    """Mediana real com IC 95% por snapshot x minimo de noites x tipo de quarto."""
    base = df[df[S.COL_PRECO_VALIDO]]
    linhas = []
    for (estrato, tipo), g in base.groupby([ESTRATO, S.COL_ROOM_TYPE]):
        linha = {"estrato": estrato, "tipo": tipo}
        for snap in (ROTULO_2019, ROTULO_ATUAL):
            x = g.loc[g[S.COL_SNAPSHOT] == snap, COL_PRECO_REAL].to_numpy()
            med, lo, hi = _mediana_ic(x)
            linha[snap] = {"n": int(len(x)), "mediana": med, "ic95": [lo, hi]}
        a, b = linha[ROTULO_2019]["mediana"], linha[ROTULO_ATUAL]["mediana"]
        linha["variacao_real_pct"] = (100 * (b / a - 1)) if a and b else None
        linhas.append(linha)
    return linhas


def decomposicao(df: pd.DataFrame) -> dict:
    """Shift-share da variacao da media do log do preco real entre snapshots.

    Media do log = log da media geometrica, o que torna a decomposicao exata:

        delta = sum_e (w26_e - w19_e) * mu19_e      <- composicao (mix de estratos)
              + sum_e  w26_e * (mu26_e - mu19_e)    <- dentro do estrato (preco)

    Estrato = minimo de noites x tipo de quarto. Estrato sem anuncio em algum dos
    snapshots nao entra (e reportado a parte).
    """
    base = df[df[S.COL_PRECO_VALIDO]].copy()
    base["lp"] = np.log(base[COL_PRECO_REAL])
    base["e"] = base[ESTRATO] + " | " + base[S.COL_ROOM_TYPE].astype(str)
    t = base.groupby(["e", S.COL_SNAPSHOT])["lp"].agg(["mean", "size"]).unstack(S.COL_SNAPSHOT)
    completos = t.dropna()
    w19 = completos[("size", ROTULO_2019)] / completos[("size", ROTULO_2019)].sum()
    w26 = completos[("size", ROTULO_ATUAL)] / completos[("size", ROTULO_ATUAL)].sum()
    mu19, mu26 = completos[("mean", ROTULO_2019)], completos[("mean", ROTULO_ATUAL)]
    comp = float(((w26 - w19) * mu19).sum())
    dentro = float((w26 * (mu26 - mu19)).sum())
    total = comp + dentro
    return {
        "delta_log_total": total,
        "variacao_geometrica_pct": 100 * (np.exp(total) - 1),
        "composicao_log": comp,
        "dentro_do_estrato_log": dentro,
        "fracao_composicao": comp / total if total else None,
        "estratos": {e: {"peso_2019": float(w19[e]), "peso_2026": float(w26[e]),
                         "var_real_pct": float(100 * (np.exp(mu26[e] - mu19[e]) - 1))}
                     for e in completos.index},
        "estratos_fora": sorted(set(t.index) - set(completos.index)),
    }


def por_grupo(df: pd.DataFrame, coluna: str, minimo: int = 0) -> dict:
    """Contagem, variacao e preco real mediano por distrito/bairro e snapshot."""
    saida = {}
    for nome, g in df.groupby(coluna):
        n19 = int((g[S.COL_SNAPSHOT] == ROTULO_2019).sum())
        n26 = int((g[S.COL_SNAPSHOT] == ROTULO_ATUAL).sum())
        if max(n19, n26) < minimo:
            continue
        p = g[g[S.COL_PRECO_VALIDO]].groupby(S.COL_SNAPSHOT)[COL_PRECO_REAL].median()
        m30 = g.groupby(S.COL_SNAPSHOT)[S.COL_MIN30].mean()
        saida[str(nome)] = {
            "n_2019": n19, "n_2026": n26,
            "var_n_pct": 100 * (n26 / n19 - 1) if n19 else None,
            "preco_real_2019": float(p.get(ROTULO_2019, np.nan)),
            "preco_2026": float(p.get(ROTULO_ATUAL, np.nan)),
            "pct_min30_2019": float(m30.get(ROTULO_2019, np.nan)),
            "pct_min30_2026": float(m30.get(ROTULO_ATUAL, np.nan)),
        }
    return saida


def por_celula_r8(df: pd.DataFrame) -> pd.DataFrame:
    """Metricas por celula H3 r8 para o mapa — mediana so com anuncios suficientes."""
    linhas = []
    for h, g in df.groupby(S.COL_H3_R8):
        a = g[g[S.COL_SNAPSHOT] == ROTULO_2019]
        b = g[g[S.COL_SNAPSHOT] == ROTULO_ATUAL]
        pa = a.loc[a[S.COL_PRECO_VALIDO], COL_PRECO_REAL]
        pb = b.loc[b[S.COL_PRECO_VALIDO], COL_PRECO_REAL]
        linhas.append({
            S.COL_H3_R8: h,
            "n_2019": len(a), "n_2026": len(b),
            "var_n_pct": 100 * (len(b) / len(a) - 1) if len(a) >= MIN_ANUNCIOS_CELULA else np.nan,
            "preco_real_2019": pa.median() if len(pa) >= MIN_ANUNCIOS_CELULA else np.nan,
            "preco_2026": pb.median() if len(pb) >= MIN_ANUNCIOS_CELULA else np.nan,
            "pct_min30_2019": a[S.COL_MIN30].mean() if len(a) >= MIN_ANUNCIOS_CELULA else np.nan,
            "pct_min30_2026": b[S.COL_MIN30].mean() if len(b) >= MIN_ANUNCIOS_CELULA else np.nan,
        })
    r8 = pd.DataFrame(linhas)
    r8["var_preco_real_pct"] = 100 * (r8["preco_2026"] / r8["preco_real_2019"] - 1)
    return r8


def concentracao(df: pd.DataFrame) -> dict:
    """Quanto do mercado e profissional: faixas de anfitriao por numero de anuncios."""
    faixas = [0, 1, 2, 5, 10, 50, np.inf]
    rotulos = ["1", "2", "3–5", "6–10", "11–50", "51+"]
    saida = {}
    for snap, g in df.groupby(S.COL_SNAPSHOT):
        por_host = g.groupby(S.COL_HOST_ID).size()
        faixa = pd.cut(por_host, faixas, labels=rotulos)
        anuncios = por_host.groupby(faixa, observed=False).sum()
        saida[snap] = {
            "anfitrioes_por_faixa": por_host.groupby(faixa, observed=False).size().astype(int).to_dict(),
            "pct_anuncios_por_faixa": (anuncios / anuncios.sum()).round(4).to_dict(),
        }
    return saida


def main() -> None:
    df, cpi = carregar()
    r8 = por_celula_r8(df)
    res = {
        "cpi": cpi,
        "kpis": kpis(df),
        "preco_por_estrato": preco_por_estrato(df),
        "decomposicao": decomposicao(df),
        "por_distrito": por_grupo(df, S.COL_DISTRITO),
        "por_bairro": por_grupo(df, S.COL_BAIRRO, minimo=30),
        "concentracao": concentracao(df),
        "celulas_r8": {
            "n": int(len(r8)),
            "com_preco_nos_dois": int(r8[["preco_real_2019", "preco_2026"]].notna().all(axis=1).sum()),
        },
    }
    r8.to_parquet(SAIDA_R8, index=False)
    SAIDA.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    k19, k26 = res["kpis"][ROTULO_2019], res["kpis"][ROTULO_ATUAL]
    print(f"CPI {cpi['de']} -> {cpi['para']}: x{cpi['fator']:.4f}")
    print(f"anuncios {k19['anuncios']:,} -> {k26['anuncios']:,} | min30 "
          f"{k19['pct_min30']:.1%} -> {k26['pct_min30']:.1%}")
    d = res["decomposicao"]
    print(f"var. geometrica real {d['variacao_geometrica_pct']:+.1f}% "
          f"(composicao {d['composicao_log']:+.3f} | dentro {d['dentro_do_estrato_log']:+.3f} log)")
    print(f"gravado {SAIDA.name} e {SAIDA_R8.name}")


if __name__ == "__main__":
    main()
