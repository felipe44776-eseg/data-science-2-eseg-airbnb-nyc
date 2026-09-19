"""E3 — Queixas criminais do NYPD, 12 meses antes de cada snapshot, por delegacia.

Pergunta de negocio: a percepcao de seguranca do entorno pesa no preco e na
permanencia do anuncio? Crime registrado e o proxy disponivel.

Fontes (NYC Open Data):
  * `qgea-i56i` NYPD Complaint Data Historic — 2006 ate o fim do ano anterior a
    publicacao (em 2026-09: rpt_dt ate 2025-12-31);
  * `5uac-w243` NYPD Complaint Data Current (Year To Date) — ano corrente, por
    trimestre fechado (em 2026-09: rpt_dt ate 2026-06-30).
Janela 2019 (2018-07-08..2019-07-07) sai toda do Historic; a atual
(2025-06-14..2026-06-13) junta Historic (ate 2025-12-31) e Current (2026).
O corte e por `rpt_dt` (data do registro), que e como os dois datasets se
particionam — filtrar pela data do fato criaria buraco ou dupla contagem na
emenda.

Agregacao NO SERVIDOR por delegacia (`addr_pct_cd`) x natureza (`law_cat_cd`):
poucas centenas de linhas por janela. A celula herda a densidade (queixas/km2)
da delegacia que contem o seu centroide. Isso e mais grosso que o anel r9 —
77/78 poligonos para a cidade inteira — e esta declarado em FEATURES.

A 116a delegacia foi criada em dez/2023 a partir da 105a (sudeste do Queens).
Em 2019 as queixas daquela area eram da 105a; por isso, na safra 2019, a 116a e
tratada como parte da 105a (area somada) — dividir pela area atual da 105a
inflaria a densidade dela e zeraria a da 116a.

Limites: crime registrado nao e crime ocorrido (subnotificacao varia por bairro
e por tipo); queixa sem delegacia valida fica fora e e contada no manifesto.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from airbnb import config
from airbnb.external._http import artefato, obter, relativo
from airbnb.external.janelas import JANELAS
from airbnb.external.socrata import contar_agrupado

DOMINIO = "data.cityofnewyork.us"
HISTORIC = "qgea-i56i"
CURRENT = "5uac-w243"
PRECINTOS = "y76i-bdw7"
URL_PRECINTOS = f"https://{DOMINIO}/resource/{PRECINTOS}.geojson"

#: ultimo dia coberto pelo Historic na data da coleta (conferido: max(rpt_dt))
FIM_HISTORIC = "2025-12-31"

PASTA = config.EXTERNAL / "nypd"
ARQ_PRECINTOS = PASTA / "delegacias.geojson"
ARQ_CONTAGENS = PASTA / "queixas_por_delegacia.csv"

#: delegacia criada depois de 2019 -> delegacia de que foi desmembrada
DESMEMBRADAS_2019 = {116: 105}

META = {
    "titulo": "NYPD Complaint Data Historic + Current (YTD); Police Precincts",
    "orgao": "New York City Police Department (via NYC Open Data); limites: NYC Dept. of City Planning",
    "licenca": "NYC Open Data Terms of Use (uso livre, sem garantia)",
    "atribuicao": "Queixas criminais: NYPD, via NYC Open Data. Limites de delegacias: NYC DCP.",
}


def precinto_na_safra(p, safra: str):
    """Delegacia sob a divisao vigente na safra (2019: 116 -> 105)."""
    if pd.isna(p):
        return p
    p = int(p)
    return DESMEMBRADAS_2019.get(p, p) if safra == "2019" else p


def trechos(safra: str) -> list[tuple[str, str, str]]:
    """(dataset, inicio, fim) que compoem a janela da safra."""
    ini, fim = JANELAS[safra]
    if fim <= FIM_HISTORIC:
        return [(HISTORIC, ini, fim)]
    if ini > FIM_HISTORIC:
        return [(CURRENT, ini, fim)]
    dia_seguinte = (pd.Timestamp(FIM_HISTORIC) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return [(HISTORIC, ini, FIM_HISTORIC), (CURRENT, dia_seguinte, fim)]


def coletar(forcar: bool = False) -> dict:
    PASTA.mkdir(parents=True, exist_ok=True)
    artefatos = []
    if ARQ_PRECINTOS.exists() and not forcar:
        artefatos.append(artefato(ARQ_PRECINTOS, url=URL_PRECINTOS, nota="ja existia"))
    else:
        r = obter(URL_PRECINTOS, params={"$limit": 1000}, timeout=90)
        ARQ_PRECINTOS.write_bytes(r.content)
        artefatos.append(artefato(ARQ_PRECINTOS, url=URL_PRECINTOS))

    consultas = []
    nota = {}
    if ARQ_CONTAGENS.exists() and not forcar:
        tab = pd.read_csv(ARQ_CONTAGENS, dtype={"addr_pct_cd": str, "law_cat_cd": str})
        nota = {"nota": "ja existia — consultas nao refeitas"}
    else:
        blocos = []
        for safra in JANELAS:
            for ds, ini, fim in trechos(safra):
                print(f"    NYPD {safra}: {ds} {ini}..{fim}", flush=True)
                df, meta = contar_agrupado(DOMINIO, ds, campo_data="rpt_dt", ini=ini, fim=fim,
                                           grupo=["addr_pct_cd", "law_cat_cd"])
                blocos.append(df.assign(safra=safra, dataset=ds))
                consultas.append({"safra": safra, "dataset": ds, "inicio": ini, "fim": fim,
                                  **meta})
        tab = pd.concat(blocos, ignore_index=True)
        tab.to_csv(ARQ_CONTAGENS, index=False)
    artefatos.append(artefato(ARQ_CONTAGENS, url=f"https://{DOMINIO}/resource/",
                              consultas=consultas, **nota))

    dens = densidades(tab, carregar_precintos())
    resumo = {}
    for safra in JANELAS:
        t = tab[tab["safra"] == safra]
        sem = t["addr_pct_cd"].isna() | ~t["addr_pct_cd"].astype(str).str.fullmatch(r"\d+")
        d = dens[dens["safra"] == safra]
        resumo[safra] = {
            "janela": list(JANELAS[safra]),
            "queixas": int(t["n"].sum()),
            "por_natureza": t.groupby("law_cat_cd")["n"].sum().astype(int).to_dict(),
            "sem_delegacia_valida": int(t.loc[sem, "n"].sum()),
            "delegacias": int(d["precinto"].nunique()),
            "total_km2_mediana": round(float(d["total_km2"].median()), 1),
        }
    return {**META, "estado": "ok", "artefatos": artefatos, "resumo": resumo,
            "saida": relativo(ARQ_CONTAGENS)}


def carregar_precintos() -> gpd.GeoDataFrame | None:
    if not ARQ_PRECINTOS.exists():
        return None
    g = gpd.read_file(ARQ_PRECINTOS)
    g["precinto"] = pd.to_numeric(g["precinct"]).astype(int)
    g["area_km2"] = g.to_crs(config.CRS_METRICO).area / 1e6
    return g[["precinto", "area_km2", "geometry"]]


def densidades(tab: pd.DataFrame, precintos: gpd.GeoDataFrame) -> pd.DataFrame:
    """(safra, precinto) -> graves_km2, total_km2, com a divisao vigente em cada safra."""
    t = tab[tab["addr_pct_cd"].astype(str).str.fullmatch(r"\d+")].copy()
    t["precinto"] = t["addr_pct_cd"].astype(int)
    linhas = []
    for safra in JANELAS:
        na_safra = {p: precinto_na_safra(p, safra)
                    for p in set(precintos["precinto"]) | set(t["precinto"])}
        area = precintos.assign(p=precintos["precinto"].map(na_safra))
        area = area.groupby("p")["area_km2"].sum()
        ts = t[t["safra"] == safra].copy()
        ts["precinto"] = ts["precinto"].map(na_safra)
        graves = ts[ts["law_cat_cd"] == "FELONY"].groupby("precinto")["n"].sum()
        total = ts.groupby("precinto")["n"].sum()
        for p, a in area.items():
            linhas.append({"safra": safra, "precinto": int(p), "area_km2": a,
                           "graves": int(graves.get(p, 0)), "total": int(total.get(p, 0))})
    d = pd.DataFrame(linhas)
    d["graves_km2"] = d["graves"] / d["area_km2"]
    d["total_km2"] = d["total"] / d["area_km2"]
    return d


def carregar() -> tuple[gpd.GeoDataFrame, pd.DataFrame] | None:
    """(poligonos das delegacias, densidades por safra e delegacia) ou None."""
    p = carregar_precintos()
    if p is None or not ARQ_CONTAGENS.exists():
        return None
    tab = pd.read_csv(ARQ_CONTAGENS, dtype={"addr_pct_cd": str, "law_cat_cd": str})
    return p, densidades(tab, p)
