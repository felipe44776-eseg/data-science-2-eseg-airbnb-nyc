"""E4 — Estacoes do metro (MTA Subway Stations, data.ny.gov `39hk-dx4f`).

Pergunta de negocio: quanto vale estar perto do metro? Em NYC o metro e o
principal meio de deslocamento do hospede; distancia a estacao e o candidato
obvio a explicar preco dentro de um mesmo bairro.

Uma linha por estacao-plataforma (Times Sq tem varias). Por isso as features
contam COMPLEXOS distintos (`complex_id`) e LINHAS distintas (`daytime_routes`),
nao linhas da tabela — contar registro inflaria os grandes entroncamentos.

Inclui a Staten Island Railway (divisao SIR): e operada pela MTA e e o "metro"
de Staten Island.

Anacronismo declarado: a tabela e a de 2026, aplicada tambem a 2019. A leva mais
recente de estacoes novas que conhecemos e a da Second Avenue Subway (2017), entao
o efeito esperado nas distancias e nulo ou desprezivel — mas a tabela nao traz
data de inauguracao para provar. Reformas de acessibilidade (coluna `ada`)
mudaram no periodo e nao entram nas features.
"""

from __future__ import annotations

import io

import pandas as pd

from airbnb import config
from airbnb.external._http import artefato, obter

DOMINIO = "data.ny.gov"
DATASET = "39hk-dx4f"
URL = f"https://{DOMINIO}/resource/{DATASET}.csv"
COLUNAS = ["gtfs_stop_id", "station_id", "complex_id", "division", "line", "stop_name",
           "borough", "daytime_routes", "structure", "gtfs_latitude", "gtfs_longitude"]

PASTA = config.EXTERNAL / "mta"
ARQUIVO = PASTA / "estacoes_metro.csv"

META = {
    "titulo": "MTA Subway Stations",
    "orgao": "Metropolitan Transportation Authority (via Open NY, data.ny.gov)",
    "licenca": "Open NY Terms of Use; atribuicao a MTA (mta.info/open-data)",
    "atribuicao": "Dados de estacoes: Metropolitan Transportation Authority (MTA), via data.ny.gov.",
}


def coletar(forcar: bool = False) -> dict:
    PASTA.mkdir(parents=True, exist_ok=True)
    params = {"$select": ",".join(COLUNAS), "$order": "station_id", "$limit": 5000}
    if ARQUIVO.exists() and not forcar:
        art = artefato(ARQUIVO, url=URL, parametros=params, nota="ja existia — nao rebaixado")
    else:
        r = obter(URL, params=params, timeout=90)
        ARQUIVO.write_bytes(r.content)
        art = artefato(ARQUIVO, url=URL, parametros=params)
    df = carregar()
    art["registros"] = int(len(df))
    return {**META, "estado": "ok", "artefatos": [art],
            "resumo": {"estacoes": int(len(df)), "complexos": int(df["complex_id"].nunique()),
                       "linhas": sorted(linhas_de(df["daytime_routes"]))}}


def linhas_de(rotas: pd.Series) -> set[str]:
    """'N W' -> {'N', 'W'}; conjunto de todas as linhas de uma serie de estacoes."""
    return {x for r in rotas.dropna() for x in str(r).split()}


def parse(texto: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(texto), dtype={"gtfs_stop_id": str, "daytime_routes": str})
    df = df.rename(columns={"gtfs_latitude": "lat", "gtfs_longitude": "lon"})
    return df.dropna(subset=["lat", "lon"])


def carregar() -> pd.DataFrame | None:
    if not ARQUIVO.exists():
        return None
    return parse(ARQUIVO.read_text(encoding="utf-8"))
