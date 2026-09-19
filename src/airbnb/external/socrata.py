"""Consulta agregada (SoQL `$group`) em dataset Socrata — NYPD e 311.

Por que agregar no servidor: o NYPD Historic tem ~10 milhoes de linhas e o 311
dezenas de milhoes; paginar as linhas de uma janela de 12 meses (~500 mil NYPD,
~800 mil de barulho) levou minutos por pagina no teste de 2026-09-18 e travou a
coleta. Agregado por delegacia ou por ZIP, o resultado tem centenas de linhas.

Estrategia de convivencia: timeout curto (90 s) e poucas tentativas. Se a janela
inteira nao responder, ela e partida em meses e as contagens sao somadas — a
soma de meses disjuntos e exatamente a contagem da janela (os intervalos sao
fechados no dia e nao se sobrepoem).
"""

from __future__ import annotations

import io
import time

import pandas as pd

from airbnb.external._http import obter, sha256_bytes
from airbnb.external.janelas import where_soql

TIMEOUT = 90


def _consulta(url: str, params: dict) -> pd.DataFrame:
    r = obter(url, params=params, timeout=TIMEOUT, tentativas=3, espera=10)
    return pd.read_csv(io.StringIO(r.content.decode("utf-8")), dtype=str)


def meses(ini: str, fim: str) -> list[tuple[str, str]]:
    """Particiona [ini, fim] (dias inclusivos) em intervalos mensais disjuntos."""
    a, b = pd.Timestamp(ini), pd.Timestamp(fim)
    out = []
    while a <= b:
        prox = (a + pd.offsets.MonthBegin(1)).normalize()
        out.append((a.strftime("%Y-%m-%d"), min(prox - pd.Timedelta(days=1), b).strftime("%Y-%m-%d")))
        a = prox
    return out


def contar_agrupado(dominio: str, dataset: str, *, campo_data: str, ini: str, fim: str,
                    grupo: list[str], filtro: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Contagem por `grupo` no intervalo [ini, fim]; parte em meses se precisar.

    Devolve (tabela com colunas grupo + n, metadados da consulta para o manifesto).
    """
    url = f"https://{dominio}/resource/{dataset}.csv"
    sel = ", ".join(grupo) + ", count(*) AS n"

    def params(a: str, b: str) -> dict:
        w = where_soql(campo_data, a, b) + (f" AND {filtro}" if filtro else "")
        return {"$select": sel, "$where": w, "$group": ", ".join(grupo), "$limit": 50_000}

    t0 = time.time()
    try:
        df = _consulta(url, params(ini, fim))
        partes = [(ini, fim)]
    except RuntimeError:
        print(f"      {dataset}: janela inteira nao respondeu em {TIMEOUT}s — partindo em meses",
              flush=True)
        blocos = []
        partes = meses(ini, fim)
        for a, b in partes:
            blocos.append(_consulta(url, params(a, b)))
            print(f"      {dataset} {a}..{b}: {len(blocos[-1])} grupos", flush=True)
            time.sleep(1)
        df = pd.concat(blocos, ignore_index=True)
    df["n"] = pd.to_numeric(df["n"]).astype("int64")
    df = df.fillna({c: "" for c in grupo}).groupby(grupo, as_index=False)["n"].sum()
    meta = {"url": url, "parametros": params(ini, fim), "consultas": len(partes),
            "segundos": round(time.time() - t0, 1),
            "sha256_resultado": sha256_bytes(df.to_csv(index=False).encode()),
            "total": int(df["n"].sum())}
    return df, meta
