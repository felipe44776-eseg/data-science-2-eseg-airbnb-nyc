"""E6 — Zillow Observed Rent Index (ZORI) por ZIP.

Pergunta de negocio: o anuncio de curta temporada acompanha o aluguel de longo
prazo do entorno? E onde o aluguel mais subiu entre 2019 e 2026, a oferta de
Airbnb encolheu mais (a conversao para aluguel tradicional ficou mais atraente)?

ZORI "smoothed, all homes plus multifamily" (`Zip_zori_uc_sfrcondomfr_sm_month.csv`):
indice de aluguel repetido (mesma unidade ao longo do tempo), ponderado pelo
estoque de imoveis de aluguel, calculado como a media dos alugueis ANUNCIADOS
entre os percentis 35 e 65 da regiao e suavizado — em dolares nominais do mes.
Nao e aluguel pago (o ACS B25064 mede isso, com defasagem).

Valores usados: 2019-07 (mes do snapshot de 2019) e 2026-06 (mes do snapshot
atual) — se 2026-06 nao estiver publicado, o mes mais proximo, registrado no
manifesto.

Limite: o ZORI so existe para ZIP com volume de anuncio suficiente; Staten
Island e partes do Bronx/Queens ficam sem valor. A celula herda o ZORI do seu
MODZCTA (ver `modzcta.py`): o do proprio codigo ou, na falta, a media dos ZCTAs
membros que tenham valor.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from airbnb import config
from airbnb.external._http import artefato, baixar_arquivo, relativo

BASE = "https://files.zillowstatic.com/research/public_csvs/zori/"
ARQ_REMOTO = "Zip_zori_uc_sfrcondomfr_sm_month.csv"
URL = BASE + ARQ_REMOTO

PASTA = config.EXTERNAL / "zillow"
BRUTO = PASTA / ARQ_REMOTO
SAIDA = PASTA / "zori_nyc.csv"

MES_2019 = config.SNAPSHOT_2019[:7]
MES_ATUAL = config.SNAPSHOT_ATUAL[:7]
CONDADOS_NYC = {"New York County", "Kings County", "Queens County", "Bronx County",
                "Richmond County"}

META = {
    "titulo": "Zillow Observed Rent Index (ZORI), ZIP, suavizado, todas as tipologias",
    "orgao": "Zillow Research (Zillow Group)",
    "licenca": ("uso publico gratuito com atribuicao clara ao Zillow, conforme os Termos de "
                "Uso da pagina Zillow Research Data"),
    "atribuicao": "Dados de aluguel: Zillow Observed Rent Index (ZORI), Zillow Research.",
}


def coluna_do_mes(colunas: list[str], mes: str) -> str | None:
    """Coluna de data ('AAAA-MM-DD') do mes pedido; se ausente, a do mes mais proximo."""
    datas = [c for c in colunas if len(c) == 10 and c[4] == "-" and c[7] == "-"]
    exata = [c for c in datas if c.startswith(mes)]
    if exata:
        return exata[0]
    if not datas:
        return None
    alvo = pd.Timestamp(mes + "-01")
    return min(datas, key=lambda c: abs(pd.Timestamp(c) - alvo))


def filtrar_nyc(bruto: pd.DataFrame) -> pd.DataFrame:
    """Linhas dos 5 condados de NYC -> (zip, zori_2019, zori_atual, mes_atual)."""
    ny = bruto[(bruto["State"] == "NY") & bruto["CountyName"].isin(CONDADOS_NYC)].copy()
    c19 = coluna_do_mes(list(bruto.columns), MES_2019)
    cat = coluna_do_mes(list(bruto.columns), MES_ATUAL)
    return pd.DataFrame({
        "zip": ny["RegionName"].astype(str).str.zfill(5),
        "condado": ny["CountyName"],
        "zori_2019": pd.to_numeric(ny[c19], errors="coerce") if c19 else np.nan,
        "zori_atual": pd.to_numeric(ny[cat], errors="coerce") if cat else np.nan,
        "mes_2019": (c19 or "")[:7], "mes_atual": (cat or "")[:7],
    }).reset_index(drop=True)


def coletar(forcar: bool = False) -> dict:
    PASTA.mkdir(parents=True, exist_ok=True)
    if BRUTO.exists() and not forcar:
        art = artefato(BRUTO, url=URL, nota="ja existia — nao rebaixado")
    else:
        art = baixar_arquivo(URL, BRUTO, timeout=90)
    bruto = pd.read_csv(BRUTO, dtype={"RegionName": str})
    z = filtrar_nyc(bruto)
    z.to_csv(SAIDA, index=False)
    datas = [c for c in bruto.columns if len(c) == 10 and c[4] == "-"]
    return {**META, "estado": "ok", "artefatos": [art, artefato(SAIDA, derivado_de=art["arquivo"])],
            "resumo": {"zips_nyc": int(len(z)),
                       "com_2019": int(z["zori_2019"].notna().sum()),
                       "com_atual": int(z["zori_atual"].notna().sum()),
                       "mes_2019": z["mes_2019"].iloc[0] if len(z) else None,
                       "mes_atual": z["mes_atual"].iloc[0] if len(z) else None,
                       "serie": [min(datas)[:7], max(datas)[:7]] if datas else None},
            "saida": relativo(SAIDA)}


def carregar() -> pd.DataFrame | None:
    if not SAIDA.exists():
        return None
    return pd.read_csv(SAIDA, dtype={"zip": str})


def por_modzcta(zori: pd.DataFrame, mz) -> pd.DataFrame:
    """ZORI por MODZCTA: o do proprio codigo; na falta, media dos ZCTAs membros."""
    z = zori.set_index("zip")
    linhas = []
    for codigo, membros in zip(mz["zip"], mz["zctas"], strict=True):
        cand = [codigo] if codigo in z.index else [m for m in membros if m in z.index]
        v19 = z.loc[cand, "zori_2019"].mean() if cand else np.nan
        vat = z.loc[cand, "zori_atual"].mean() if cand else np.nan
        linhas.append({"zip": codigo, "zori_2019": v19, "zori_atual": vat,
                       "origem": "proprio" if cand == [codigo] else
                       ("membros" if cand else "sem valor")})
    return pd.DataFrame(linhas)
