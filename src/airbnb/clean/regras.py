"""Regras de quarentena e a cascata de exclusoes (invariante 2).

Duas naturezas de exclusao, e a diferenca importa:

* escopo **base** — a linha sai de TUDO (id duplicado, coordenada fora de NYC,
  bairro desconhecido...). E dado que nao descreve um anuncio valido.
* escopo **preco** — a linha FICA na base (conta anuncio, ocupacao, mapa), mas
  sai das analises de preco (`preco_valido = False`): preco ausente, zero,
  fora do suporte, ou cotacao que o Inside Airbnb dividiu errado.

Cascata: as regras rodam na ordem abaixo e cada linha e atribuida a PRIMEIRA
regra em que cai — por isso a soma das exclusoes fecha com o total. Cada regra
tambem reporta quantas linhas casam com ela independentemente das anteriores
(`casam`), para que uma regra nao pareca inutil so porque outra pegou antes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from airbnb import config
from airbnb.clean.derivadas import NOITES_COTACAO_MAX, PRECO_PISO, PRECO_TETO
from airbnb.schema import (
    COL_ID,
    COL_LAT,
    COL_LON,
    COL_MIN_NOITES,
    COL_PRECO,
    COL_PRECO_COTACAO_NOITES,
    COL_ROOM_TYPE,
    ROOM_TYPES,
)

BASE = "base"
PRECO = "preco"

#: Colunas de distrito/bairro mudam de nome entre os snapshots (o detalhado de
#: 2026 so tem a versao _cleansed preenchida). As regras enxergam por esta chave.
COLUNAS_LOCAL = {
    config.ROTULO_2019: {"distrito": "neighbourhood_group", "bairro": "neighbourhood"},
    config.ROTULO_ATUAL: {"distrito": "neighbourhood_group_cleansed", "bairro": "neighbourhood_cleansed"},
}

#: Colunas que carregam o id (nao entram na comparacao de duplicata perfeita).
_COLUNAS_DE_ID = {COL_ID, "listing_url"}


@dataclass(frozen=True)
class Contexto:
    """O que as regras precisam saber alem da propria linha."""

    snapshot: str
    bairros_validos: frozenset[str]


@dataclass(frozen=True)
class Regra:
    codigo: str
    nome: str
    escopo: str
    motivo: str
    funcao: Callable[[pd.DataFrame, Contexto], pd.Series]
    snapshots: tuple[str, ...] = (config.ROTULO_2019, config.ROTULO_ATUAL)


def _fora_bbox(df: pd.DataFrame, ctx: Contexto) -> pd.Series:
    lon_min, lat_min, lon_max, lat_max = config.NYC_BBOX
    lat, lon = df[COL_LAT], df[COL_LON]
    dentro = lat.between(lat_min, lat_max) & lon.between(lon_min, lon_max)
    return ~dentro.fillna(False).astype(bool)


def _distrito(df: pd.DataFrame, ctx: Contexto) -> pd.Series:
    return ~df[COLUNAS_LOCAL[ctx.snapshot]["distrito"]].isin(config.DISTRITOS)


def _bairro(df: pd.DataFrame, ctx: Contexto) -> pd.Series:
    return ~df[COLUNAS_LOCAL[ctx.snapshot]["bairro"]].isin(ctx.bairros_validos)


def _duplicata_perfeita(df: pd.DataFrame, ctx: Contexto) -> pd.Series:
    cols = [c for c in df.columns if c not in _COLUNAS_DE_ID]
    return df.duplicated(subset=cols, keep="first")


REGRAS: list[Regra] = [
    Regra("B01", "id_duplicado", BASE,
          "id repetido no arquivo (mantida a primeira ocorrência)",
          lambda df, ctx: df[COL_ID].duplicated(keep="first")),
    Regra("B02", "duplicata_perfeita", BASE,
          "linha idêntica a outra em todas as colunas exceto o id (anúncio publicado em dobro)",
          _duplicata_perfeita),
    Regra("B03", "coordenada_fora_nyc", BASE,
          "latitude/longitude nula ou fora do envelope dos 5 distritos (config.NYC_BBOX)",
          _fora_bbox),
    Regra("B04", "distrito_invalido", BASE,
          "distrito fora dos 5 de Nova York", _distrito),
    Regra("B05", "bairro_desconhecido", BASE,
          "bairro ausente da lista de bairros do Inside Airbnb (neighbourhoods.csv)", _bairro),
    Regra("B06", "room_type_invalido", BASE,
          f"room_type fora de {list(ROOM_TYPES)}",
          lambda df, ctx: ~df[COL_ROOM_TYPE].isin(ROOM_TYPES)),
    Regra("B07", "minimo_noites_invalido", BASE,
          "minimum_nights nulo ou < 1: sem ele não há como situar o anúncio antes/depois da LL18",
          lambda df, ctx: ~(df[COL_MIN_NOITES] >= 1).fillna(False).astype(bool)),
    Regra("P01", "preco_ausente", PRECO,
          "preço nulo (2026: sem cotação — calendário sem data livre ou anúncio indisponível)",
          lambda df, ctx: df[COL_PRECO].isna()),
    Regra("P02", "preco_zero", PRECO,
          "preço igual a zero",
          lambda df, ctx: df[COL_PRECO].eq(0).fillna(False).astype(bool)),
    Regra("P03", "cotacao_acima_31_noites", PRECO,
          f"cotação de mais de {NOITES_COTACAO_MAX} noites: o total é mensal e o Inside Airbnb o "
          "dividiu por N noites — preço por noite subestimado (~N/30 vezes)",
          lambda df, ctx: (df[COL_PRECO_COTACAO_NOITES] > NOITES_COTACAO_MAX).fillna(False).astype(bool),
          snapshots=(config.ROTULO_ATUAL,)),
    Regra("P04", "preco_abaixo_piso", PRECO,
          f"0 < preço < US$ {PRECO_PISO:,.0f} por noite (em 2019 não existe preço positivo abaixo de 10)",
          lambda df, ctx: ((df[COL_PRECO] > 0) & (df[COL_PRECO] < PRECO_PISO)).fillna(False).astype(bool)),
    Regra("P05", "preco_acima_teto", PRECO,
          f"preço > US$ {PRECO_TETO:,.0f} por noite (máximo observado em 2019: fora do suporte de comparação)",
          lambda df, ctx: (df[COL_PRECO] > PRECO_TETO).fillna(False).astype(bool)),
]


def aplicar(df: pd.DataFrame, ctx: Contexto) -> tuple[pd.Series, pd.Series, pd.DataFrame, list[dict]]:
    """Roda a cascata. Devolve (fora_base, fora_preco, quarentena, relatorio por regra).

    `fora_preco` so marca linhas que continuam na base — linha que ja saiu da
    base nao e "excluida do preco", e excluida de tudo.
    """
    fora_base = pd.Series(False, index=df.index)
    fora_preco = pd.Series(False, index=df.index)
    blocos: list[pd.DataFrame] = []
    relatorio: list[dict] = []
    for r in REGRAS:
        if ctx.snapshot not in r.snapshots:
            continue
        casa = r.funcao(df, ctx).fillna(False).astype(bool)
        if r.escopo == BASE:
            novas = casa & ~fora_base
            fora_base |= novas
        else:
            novas = casa & ~fora_base & ~fora_preco
            fora_preco |= novas
        relatorio.append({"codigo": r.codigo, "regra": r.nome, "escopo": r.escopo,
                          "casam": int(casa.sum()), "cascata": int(novas.sum())})
        if novas.any():
            blocos.append(pd.DataFrame({
                "snapshot": ctx.snapshot,
                "id": df.loc[novas, COL_ID].astype("int64").to_numpy(),
                "regra": r.codigo,
                "motivo": r.motivo,
                "escopo": r.escopo,
            }))
    quarentena = pd.concat(blocos, ignore_index=True) if blocos else vazia()
    return fora_base, fora_preco, quarentena, relatorio


def vazia() -> pd.DataFrame:
    """Quarentena sem linhas, com o schema certo (parquet vazio ainda e contrato)."""
    return pd.DataFrame({"snapshot": pd.Series(dtype="str"), "id": pd.Series(dtype="int64"),
                         "regra": pd.Series(dtype="str"), "motivo": pd.Series(dtype="str"),
                         "escopo": pd.Series(dtype="str")})
