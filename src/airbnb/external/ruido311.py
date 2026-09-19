"""E5 — Chamados de barulho ao 311, 12 meses antes de cada snapshot, por ZIP.

Pergunta de negocio: vida noturna atrai hospede e irrita vizinho. Barulho
registrado no 311 mede as duas coisas ao mesmo tempo — onde ha bar, e onde ha
morador disposto a reclamar (inclusive DO Airbnb vizinho).

Dois datasets, porque o 311 foi dividido em 2020:
  * `76ig-c548` 311 Service Requests from 2010 to 2019 -> janela 2019;
  * `erm2-nwe9` 311 Service Requests from 2020 to Present -> janela atual.

Filtro: `complaint_type like 'Noise%'` — pega "Noise - Residential", "Noise -
Street/Sidewalk", "Noise - Commercial", "Noise - Vehicle", "Noise - Helicopter",
"Noise - Park", "Noise - House of Worship" e o "Noise" do DEP (obra, alarme).

Escolha de granularidade (documentada, conforme o briefing): por ZIP, agregado
NO SERVIDOR (`$group=incident_zip`). O volume por linha (~700-900 mil chamados
por janela) tornava a coleta por ponto lenta e pesada para a API; por ZIP sao
~200 linhas. O ZIP e traduzido para o MODZCTA (via a lista de ZCTAs de cada
MODZCTA) e dividido pela area do MODZCTA -> chamados/km2. A celula herda o valor
do seu MODZCTA. ZIP que nao pertence a nenhum MODZCTA (caixa postal, ZIP de um
predio, erro de digitacao) fica fora e e contado no manifesto.

Limite declarado: chamado mede disposicao a reclamar tanto quanto barulho; bairro
que reclama pouco nao e necessariamente silencioso.
"""

from __future__ import annotations

import pandas as pd

from airbnb import config
from airbnb.external import modzcta
from airbnb.external._http import artefato, relativo
from airbnb.external.janelas import JANELAS
from airbnb.external.socrata import contar_agrupado

DOMINIO = "data.cityofnewyork.us"
DATASETS = {"2019": "76ig-c548", "atual": "erm2-nwe9"}
FILTRO = "complaint_type like 'Noise%'"

PASTA = config.EXTERNAL / "nyc311"
ARQUIVO = PASTA / "barulho_por_zip.csv"

META = {
    "titulo": "311 Service Requests (2010-2019 e 2020-presente), complaint_type 'Noise%'",
    "orgao": "NYC 311 / Office of Technology and Innovation (via NYC Open Data)",
    "licenca": "NYC Open Data Terms of Use (uso livre, sem garantia)",
    "atribuicao": "Chamados de barulho: NYC 311, via NYC Open Data.",
}


def coletar(forcar: bool = False) -> dict:
    PASTA.mkdir(parents=True, exist_ok=True)
    consultas = []
    nota = {}
    if ARQUIVO.exists() and not forcar:
        tab = pd.read_csv(ARQUIVO, dtype={"incident_zip": str})
        nota = {"nota": "ja existia — consultas nao refeitas"}
    else:
        blocos = []
        for safra, (ini, fim) in JANELAS.items():
            ds = DATASETS[safra]
            print(f"    311 {safra}: {ds} {ini}..{fim}", flush=True)
            df, meta = contar_agrupado(DOMINIO, ds, campo_data="created_date", ini=ini,
                                       fim=fim, grupo=["incident_zip"], filtro=FILTRO)
            blocos.append(df.assign(safra=safra, dataset=ds))
            consultas.append({"safra": safra, "dataset": ds, "inicio": ini, "fim": fim, **meta})
        tab = pd.concat(blocos, ignore_index=True)
        tab.to_csv(ARQUIVO, index=False)
    art = artefato(ARQUIVO, url=f"https://{DOMINIO}/resource/", consultas=consultas, **nota)

    mz = modzcta.carregar()
    resumo = {}
    if mz is not None:
        dens = por_modzcta(tab, mz)
        for safra in JANELAS:
            t = tab[tab["safra"] == safra]
            d = dens[dens["safra"] == safra]
            resumo[safra] = {
                "janela": list(JANELAS[safra]), "chamados": int(t["n"].sum()),
                "fora_de_modzcta": int(t["n"].sum() - d["n"].sum()),
                "modzcta_com_valor": int(len(d)),
                "por_km2_mediana": round(float(d["por_km2"].median()), 1),
            }
    return {**META, "estado": "ok", "artefatos": [art], "resumo": resumo,
            "saida": relativo(ARQUIVO)}


def normalizar_zip(z) -> str | None:
    """'10001-1234' / '10001.0' / ' 10001' -> '10001'; lixo -> None."""
    if pd.isna(z):
        return None
    s = str(z).strip().split("-")[0].split(".")[0]
    return s if len(s) == 5 and s.isdigit() else None


def por_modzcta(tab: pd.DataFrame, mz) -> pd.DataFrame:
    """(safra, zip do MODZCTA) -> n, por_km2."""
    mapa = modzcta.zip_para_modzcta(mz)
    area = mz.set_index("zip")["area_km2"]
    t = tab.copy()
    t["zip"] = t["incident_zip"].map(normalizar_zip).map(mapa)
    t = t.dropna(subset=["zip"])
    d = t.groupby(["safra", "zip"], as_index=False)["n"].sum()
    d["por_km2"] = d["n"] / d["zip"].map(area)
    return d


def carregar() -> pd.DataFrame | None:
    mz = modzcta.carregar()
    if mz is None or not ARQUIVO.exists():
        return None
    return por_modzcta(pd.read_csv(ARQUIVO, dtype={"incident_zip": str}), mz)
