"""Janelas de 12 meses antes de cada snapshot — as mesmas para NYPD e 311.

Por que 12 meses e nao o ano civil: o snapshot de 2019 e de 8 de julho; o ano
civil de 2019 incluiria meses DEPOIS do scrape (informacao do futuro para o
anuncio) e o de 2018 estaria meio ano defasado. A janela termina na vespera do
snapshot e cobre um ano inteiro — todas as estacoes, sem sazonalidade parcial.
"""

from __future__ import annotations

import pandas as pd

from airbnb import config


def janela(snapshot: str) -> tuple[str, str]:
    """(inicio, fim) inclusivos: [snapshot - 1 ano, snapshot - 1 dia]."""
    s = pd.Timestamp(snapshot)
    ini = s - pd.DateOffset(years=1)
    fim = s - pd.Timedelta(days=1)
    return ini.strftime("%Y-%m-%d"), fim.strftime("%Y-%m-%d")


#: safra -> (inicio, fim): 2019 -> 2018-07-08..2019-07-07; atual -> 2025-06-14..2026-06-13
JANELAS: dict[str, tuple[str, str]] = {
    "2019": janela(config.SNAPSHOT_2019),
    "atual": janela(config.SNAPSHOT_ATUAL),
}


def where_soql(campo: str, ini: str, fim: str) -> str:
    """Filtro SoQL inclusivo no dia inteiro de `fim` (campo e floating timestamp)."""
    return f"{campo} between '{ini}T00:00:00' and '{fim}T23:59:59'"
