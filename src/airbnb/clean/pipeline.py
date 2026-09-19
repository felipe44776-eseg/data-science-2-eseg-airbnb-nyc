"""Limpeza: bronze (CSV bruto) -> silver (parquet tipado e validado), dois snapshots.

Principio (invariante 2): **nenhuma linha some sem registro**. Toda exclusao
vai para `quarentena.parquet` com regra, motivo e escopo; toda regra emite
contagem em `_qualidade.json`. Excluir da analise de preco (`preco_valido`)
e diferente de excluir da base.

Saidas em data/processed/:

  anuncios_2019.parquet    Kaggle limpo e tipado, sem host_name
  anuncios_2026.parquet    detalhado limpo e tipado + derivadas, sem colunas pessoais/texto livre
                           (fica `name`, para analise; `pessoal=True` no schema impede publicar)
  anuncios_resumo.parquet  os dois snapshots empilhados nas colunas comuns + `snapshot`
  quarentena.parquet       (snapshot, id, regra, motivo, escopo)
  _qualidade.json          regras x snapshot, cascata, nulos antes/depois, hash das entradas e saidas

Por que 2026 vem do DETALHADO e nao do resumo (`visualisations/listings.csv`):
o detalhado tem 90 colunas (preco com centavos, cotacao, amenidades, licenca,
ocupacao estimada) e cobre 30.259 dos 30.555 ids do resumo com valores
identicos nas colunas comuns. Os 296 que so o resumo tem sao todos sem
anfitriao (host_id nulo), `Private room`, minimo de 1 noite e sem licenca —
inventario de hotel distribuido sem perfil (docs/04 §1).

A limpeza e deterministica e idempotente: mesma entrada, mesmo parquet (o
hash do conteudo de cada saida vai para `_qualidade.json`).

Uso:
    python -m airbnb.clean.pipeline                  # limpa e roda eda.qualidade no fim
    python -m airbnb.clean.pipeline --sem-qualidade  # so a limpeza
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from airbnb import config, schema
from airbnb.clean import derivadas as dv
from airbnb.clean import regras
from airbnb.schema import (
    COL_ANUNCIOS_HOST,
    COL_AVALIACOES_MES,
    COL_BAIRRO,
    COL_BAIRRO_2026,
    COL_DIAS_ULTIMA_AVALIACAO,
    COL_DISTRITO,
    COL_DISTRITO_2026,
    COL_HOST_MULTI,
    COL_ID,
    COL_LAT,
    COL_LON,
    COL_MIN30,
    COL_MIN_NOITES,
    COL_OCUPACAO_MODELO,
    COL_PRECO,
    COL_PRECO_VALIDO,
    COL_PRESENTE_2026,
    COL_SNAPSHOT,
    COL_ULTIMA_AVALIACAO,
    COLUNAS_H3,
    S2019,
    S2026,
    SRESUMO,
)

# --- caminhos (candidatos a config.py; declarados aqui por escopo) ----------------------------

SAIDA_2019 = config.PROCESSED / "anuncios_2019.parquet"
SAIDA_2026 = config.PROCESSED / "anuncios_2026.parquet"
SAIDA_RESUMO = config.PROCESSED / "anuncios_resumo.parquet"
SAIDA_QUARENTENA = config.PROCESSED / "quarentena.parquet"
SAIDA_QUALIDADE = config.PROCESSED / "_qualidade.json"

ARQ_DETALHADO = config.RAW_INSIDE / "listings.csv.gz"
ARQ_RESUMO_2026 = config.RAW_INSIDE / "listings_resumo.csv"
ARQ_BAIRROS = config.RAW_INSIDE / "neighbourhoods.csv"

_DATAS_2026 = ["last_scraped", "calendar_last_scraped", "first_review", "last_review",
               "price_quote_checkin_date", "price_quote_checkout_date"]
_TF_2026 = ["host_is_superhost", "host_has_profile_pic", "host_identity_verified", "has_availability"]


# --- leitura ---------------------------------------------------------------------------------


def ler_kaggle(caminho: Path = config.RAW_KAGGLE) -> pd.DataFrame:
    return pd.read_csv(caminho)


def ler_detalhado(caminho: Path = ARQ_DETALHADO) -> pd.DataFrame:
    return pd.read_csv(caminho, low_memory=False)


def ler_resumo_2026(caminho: Path = ARQ_RESUMO_2026) -> pd.DataFrame:
    return pd.read_csv(caminho)


def bairros_validos(caminho: Path = ARQ_BAIRROS) -> frozenset[str]:
    return frozenset(pd.read_csv(caminho)["neighbourhood"].astype(str))


# --- tipagem -----------------------------------------------------------------------------------


def _tipar(df: pd.DataFrame, saida: str) -> pd.DataFrame:
    """Converte cada coluna para o dtype do contrato, sem remendo silencioso.

    Categoria com valor fora do dominio e bool com nulo sao ERRO aqui: o
    `pd.Categorical` transformaria o valor estranho em NaN e o `astype(bool)`
    transformaria NaN em True — dois jeitos de sumir com dado sem aviso.
    """
    out: dict[str, pd.Series] = {}
    for col, dt in schema.tipos(saida).items():
        s = df[col]
        if dt == "category":
            dom = list(schema.ESQUEMA[col].dominio)
            fora = set(s.dropna().astype(str)) - set(dom)
            if fora:
                raise ValueError(f"{saida}.{col}: valores fora do dominio {sorted(fora)[:5]}")
            out[col] = pd.Series(pd.Categorical(s.astype("object"), categories=dom), index=df.index)
        elif dt == "bool":
            if s.isna().any():
                raise ValueError(f"{saida}.{col}: bool com {int(s.isna().sum())} nulos")
            out[col] = s.astype(bool)
        elif dt == "str":
            out[col] = s.astype("str")
        elif dt.startswith("datetime64"):
            out[col] = pd.to_datetime(s).astype(dt)
        else:
            out[col] = s.astype(dt)
    return pd.DataFrame(out, index=df.index).reset_index(drop=True)


def _nulos(df: pd.DataFrame) -> dict[str, int]:
    n = df.isna().sum()
    return {c: int(v) for c, v in n.items()}


def hash_conteudo(df: pd.DataFrame) -> str:
    """Hash do CONTEUDO (valores + nomes + dtypes), independente de como o parquet
    foi escrito. E o que prova idempotencia: duas execucoes, mesmo hash."""
    h = hashlib.sha256()
    h.update("|".join(f"{c}:{df[c].dtype}" for c in df.columns).encode())
    h.update(pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes())
    return h.hexdigest()


# --- derivadas comuns aos dois snapshots -------------------------------------------------------


def _comuns(df: pd.DataFrame, preco_valido: pd.Series, snapshot: str,
            referencia: pd.Series | pd.Timestamp) -> pd.DataFrame:
    df = df.copy()
    df[COL_SNAPSHOT] = snapshot
    df[COL_PRECO_VALIDO] = preco_valido.to_numpy()
    df[COL_MIN30] = df[COL_MIN_NOITES] >= config.NOITES_CURTA_TEMPORADA
    df[COL_HOST_MULTI] = df[COL_ANUNCIOS_HOST] > 1
    for col, res in COLUNAS_H3.items():
        df[col] = dv.celula_h3(df[COL_LAT], df[COL_LON], res)
    df[COL_DIAS_ULTIMA_AVALIACAO] = dv.dias_desde(df[COL_ULTIMA_AVALIACAO], referencia)
    df[COL_OCUPACAO_MODELO] = dv.ocupacao_modelo(
        df[COL_AVALIACOES_MES], df[COL_MIN_NOITES], df[COL_DIAS_ULTIMA_AVALIACAO])
    return df


def _cascata(entrada: int, rel: list[dict], silver: pd.DataFrame) -> dict:
    passos, restam = [], entrada
    for r in rel:
        if r["escopo"] == regras.BASE:
            restam -= r["cascata"]
            passos.append({"regra": r["codigo"], "nome": r["regra"], "sai_da_base": r["cascata"],
                           "restam": restam})
    base = restam
    for r in rel:
        if r["escopo"] == regras.PRECO:
            restam -= r["cascata"]
            passos.append({"regra": r["codigo"], "nome": r["regra"], "sai_do_preco": r["cascata"],
                           "restam_com_preco_valido": restam})
    assert base == len(silver), "cascata nao fecha com a silver"
    assert restam == int(silver[COL_PRECO_VALIDO].sum()), "cascata de preco nao fecha"
    return {"entrada": entrada, "passos": passos, "base_final": base,
            "preco_valido": restam, "fora_do_preco": base - restam}


# --- 2019 ----------------------------------------------------------------------------------------


def limpar_2019(bruto: pd.DataFrame, bairros: frozenset[str],
                ids_2026: set[int] | frozenset[int] = frozenset()) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Kaggle -> silver 2019. Devolve (silver, quarentena, relatorio)."""
    df = bruto.copy()
    df[COL_PRECO] = dv.parse_preco(df["price"])
    df = df.drop(columns=["price"])
    df[COL_ULTIMA_AVALIACAO] = pd.to_datetime(df[COL_ULTIMA_AVALIACAO], errors="coerce")

    ctx = regras.Contexto(config.ROTULO_2019, bairros)
    fora_base, fora_preco, quarentena, rel = regras.aplicar(df, ctx)
    df = df.loc[~fora_base]
    df = _comuns(df, ~fora_preco.loc[df.index], config.ROTULO_2019, dv.snapshot_2019_ts())
    df[COL_PRESENTE_2026] = df[COL_ID].isin(ids_2026)

    silver = _tipar(df, S2019)
    relatorio = {"regras": rel, "cascata": _cascata(len(bruto), rel, silver)}
    return silver, quarentena, relatorio


# --- 2026 ----------------------------------------------------------------------------------------


def limpar_2026(bruto: pd.DataFrame, bairros: frozenset[str]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Detalhado do Inside Airbnb -> silver 2026. Devolve (silver, quarentena, relatorio)."""
    df = bruto.copy()
    df[COL_PRECO] = dv.parse_preco(df["price"])
    for c in _DATAS_2026:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df = df.join(dv.cotacao(df["price_quote_raw"], df["price_quote_checkin_date"],
                            df["price_quote_checkout_date"]))

    ctx = regras.Contexto(config.ROTULO_ATUAL, bairros)
    fora_base, fora_preco, quarentena, rel = regras.aplicar(df, ctx)
    df = df.loc[~fora_base].copy()

    for c in _TF_2026:
        df[c] = dv.booleano_tf(df[c])
    df = _comuns(df, ~fora_preco.loc[df.index], config.ROTULO_ATUAL, df["last_scraped"])

    df = df.join(dv.banheiros(df["bathrooms"], df["bathrooms_text"]))
    amen, invalidas = dv.amenidades(df["amenities"])
    df = df.join(amen)
    df["licenca_status"] = dv.licenca_status(df["license"])
    df["host_superhost"] = df["host_is_superhost"].fillna(False).astype(bool)
    df["host_anos"] = dv.host_anos(df["hosts_time_as_host_years"], df["hosts_time_as_host_months"])
    df["meses_desde_primeira_avaliacao"] = (
        (df["last_scraped"] - df["first_review"]).dt.days / dv.DIAS_POR_MES).astype("float64")
    df["tipo_imovel_grupo"] = dv.tipo_imovel_grupo(df["property_type"], df["room_type"])

    silver = _tipar(df, S2026)
    relatorio = {"regras": rel, "cascata": _cascata(len(bruto), rel, silver),
                 "amenities_json_invalido": invalidas}
    return silver, quarentena, relatorio


# --- resumo empilhado ------------------------------------------------------------------------------


def empilhar_resumo(s2019: pd.DataFrame, s2026: pd.DataFrame) -> pd.DataFrame:
    """Os dois snapshots nas colunas comuns. 2026 entra com o bairro/distrito
    `_cleansed` renomeado para o nome de 2019 — e a unica renomeacao de coluna
    de origem do projeto, e so nesta tabela."""
    cols = schema.colunas(SRESUMO)
    b = s2026.rename(columns={COL_BAIRRO_2026: COL_BAIRRO, COL_DISTRITO_2026: COL_DISTRITO})
    empilhado = pd.concat([s2019[cols], b[cols]], ignore_index=True)
    return _tipar(empilhado, SRESUMO)


# --- relatorios auxiliares ---------------------------------------------------------------------------


def comparar_resumo_detalhado(resumo: pd.DataFrame, detalhado: pd.DataFrame) -> dict:
    """Por que o detalhado e nao o resumo: o que cada um tem que o outro nao tem."""
    so_resumo = resumo[~resumo[COL_ID].isin(detalhado[COL_ID])]
    comum = detalhado[[COL_ID, "price"]].merge(resumo[[COL_ID, "price"]], on=COL_ID,
                                               suffixes=("_det", "_res"))
    p_det = dv.parse_preco(comum["price_det"])
    p_res = comum["price_res"].astype("float64")
    dif = (p_det - p_res).abs()
    iguais = {}
    m = detalhado.merge(resumo, on=COL_ID, suffixes=("_d", "_r"))
    pares = {"latitude": "latitude", "longitude": "longitude", "room_type": "room_type",
             "minimum_nights": "minimum_nights", "number_of_reviews": "number_of_reviews",
             "last_review": "last_review", "reviews_per_month": "reviews_per_month",
             "calculated_host_listings_count": "calculated_host_listings_count",
             "availability_365": "availability_365", "number_of_reviews_ltm": "number_of_reviews_ltm",
             "license": "license"}
    for a, b in pares.items():
        x, y = m[f"{a}_d"], m[f"{b}_r"]
        eq = (x.astype(str) == y.astype(str)) | (x.isna() & y.isna())
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
            eq = np.isclose(x.astype(float), y.astype(float)) | (x.isna() & y.isna())
        iguais[a] = round(float(np.mean(eq)), 6)
    iguais["neighbourhood"] = round(float((m["neighbourhood_cleansed"] == m["neighbourhood_r"]).mean()), 6)
    iguais["neighbourhood_group"] = round(float(
        (m["neighbourhood_group_cleansed"] == m["neighbourhood_group"]).mean()), 6)
    nomes = so_resumo["name"].astype("string")
    return {
        "linhas_resumo": len(resumo),
        "linhas_detalhado": len(detalhado),
        "ids_so_no_resumo": len(so_resumo),
        "ids_so_no_detalhado": int((~detalhado[COL_ID].isin(resumo[COL_ID])).sum()),
        "so_resumo_host_id_nulo": int(so_resumo["host_id"].isna().sum()),
        "so_resumo_room_type": so_resumo["room_type"].value_counts().to_dict(),
        "so_resumo_minimum_nights": so_resumo["minimum_nights"].value_counts().to_dict(),
        "so_resumo_license_nula": int(so_resumo["license"].isna().sum()),
        "so_resumo_nome_de_hotel": int(nomes.str.contains(
            r"(?i)hotel|\binn\b|suite|hostel|\bpod\b|room|king|queen", na=False).sum()),
        "so_resumo_distrito": so_resumo["neighbourhood_group"].value_counts().to_dict(),
        "so_resumo_preco_mediano": float(so_resumo["price"].median()),
        "fracao_colunas_comuns_identicas": iguais,
        "preco_resumo_e_arredondamento_do_detalhado": {
            "linhas_com_preco": int(dif.notna().sum()),
            "max_diferenca_abs": float(dif.max()),
            "diferenca_ate_1_dolar": int((dif <= 1).sum()),
        },
    }


def _amenidades_relatorio(s: pd.DataFrame) -> dict:
    """Prevalencia de cada flag e razao de precos medianos com/sem, por estrato de
    minimo de noites (o `price` de 2026 nao e a mesma grandeza nos dois estratos)."""
    out = {}
    ok = s[s[COL_PRECO_VALIDO]]
    for flag in schema.COLS_AMENIDADES:
        linha = {"prevalencia": round(float(s[flag].mean()), 4)}
        for rot, estrato in (("min_lt30", ok[~ok[COL_MIN30]]), ("min30", ok[ok[COL_MIN30]])):
            com = estrato.loc[estrato[flag], COL_PRECO].median()
            sem = estrato.loc[~estrato[flag], COL_PRECO].median()
            linha[f"preco_mediano_com_{rot}"] = None if pd.isna(com) else round(float(com), 2)
            linha[f"preco_mediano_sem_{rot}"] = None if pd.isna(sem) else round(float(sem), 2)
            linha[f"razao_{rot}"] = None if pd.isna(com) or pd.isna(sem) or sem == 0 else round(float(com / sem), 3)
        out[flag] = linha
    return out


def _banheiros_relatorio(bruto: pd.DataFrame) -> dict:
    b = dv.banheiros(bruto["bathrooms"], bruto["bathrooms_text"])
    texto = dv.banheiros(pd.Series(np.nan, index=bruto.index), bruto["bathrooms_text"])["banheiros"]
    ambos = bruto["bathrooms"].notna() & texto.notna()
    return {
        "bathrooms_nulo": int(bruto["bathrooms"].isna().sum()),
        "bathrooms_text_nulo": int(bruto["bathrooms_text"].isna().sum()),
        "completados_pelo_texto": int((bruto["bathrooms"].isna() & texto.notna()).sum()),
        "banheiros_nulo_final": int(b["banheiros"].isna().sum()),
        "numero_e_texto_concordam": round(float(
            np.isclose(bruto.loc[ambos, "bathrooms"], texto[ambos]).mean()), 6) if ambos.any() else None,
        "linhas_com_os_dois": int(ambos.sum()),
    }


def _manifesto_entradas() -> dict:
    caminho = config.RAW / "_manifesto.json"
    if not caminho.exists():
        return {}
    arqs = json.loads(caminho.read_text(encoding="utf-8")).get("arquivos", {})
    return {k: {"arquivo": v["arquivo"], "sha256": v["sha256"]} for k, v in arqs.items()
            if v.get("usada_no_pipeline", True)}


# --- orquestracao ---------------------------------------------------------------------------------


def executar(rodar_qualidade: bool = True) -> dict:
    """Le o bronze, limpa os dois snapshots, valida contra o schema e grava tudo."""
    print("  lendo fontes…", flush=True)
    bairros = bairros_validos()
    kaggle = ler_kaggle()
    detalhado = ler_detalhado()
    resumo26 = ler_resumo_2026()
    ids_2026 = set(detalhado[COL_ID]) | set(resumo26[COL_ID])

    print("  limpando 2019…", flush=True)
    s19, q19, r19 = limpar_2019(kaggle, bairros, ids_2026)
    print("  limpando 2026…", flush=True)
    s26, q26, r26 = limpar_2026(detalhado, bairros)
    res = empilhar_resumo(s19, s26)
    quarentena = pd.concat([q19, q26], ignore_index=True) if len(q19) or len(q26) else regras.vazia()
    quarentena = quarentena.astype({"snapshot": "str", "id": "int64", "regra": "str",
                                    "motivo": "str", "escopo": "str"})

    erros = schema.validar(s19, S2019) + schema.validar(s26, S2026) + schema.validar(res, SRESUMO)
    if erros:
        for e in erros:
            print(f"  CONTRATO VIOLADO: {e}", file=sys.stderr)
        raise SystemExit("  a silver viola schema.py — nada foi gravado")

    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    saidas = {SAIDA_2019: s19, SAIDA_2026: s26, SAIDA_RESUMO: res, SAIDA_QUARENTENA: quarentena}
    for caminho, df in saidas.items():
        df.to_parquet(caminho, index=False, compression="zstd")

    regras_tab = []
    for r in regras.REGRAS:
        linha = {"codigo": r.codigo, "regra": r.nome, "escopo": r.escopo, "motivo": r.motivo}
        for rot, rel in ((config.ROTULO_2019, r19), (config.ROTULO_ATUAL, r26)):
            achado = next((x for x in rel["regras"] if x["codigo"] == r.codigo), None)
            linha[rot] = None if achado is None else {"casam": achado["casam"], "cascata": achado["cascata"]}
        regras_tab.append(linha)

    qualidade = {
        "descricao": ("Relatório da limpeza (clean/pipeline.py). Regras de quarentena por snapshot, "
                      "cascata de exclusões, nulos antes/depois. Números conferidos: a cascata fecha "
                      "com as linhas da silver (assert no código)."),
        "entradas": _manifesto_entradas(),
        "linhas_entrada": {config.ROTULO_2019: len(kaggle), config.ROTULO_ATUAL: len(detalhado)},
        "regras": regras_tab,
        "cascata": {config.ROTULO_2019: r19["cascata"], config.ROTULO_ATUAL: r26["cascata"]},
        "quarentena_por_escopo": quarentena.groupby(["snapshot", "escopo"]).size()
                                          .rename("linhas").reset_index().to_dict("records"),
        "nulos": {
            config.ROTULO_2019: {"antes": _nulos(kaggle), "depois": _nulos(s19)},
            config.ROTULO_ATUAL: {"antes": _nulos(detalhado), "depois": _nulos(s26)},
        },
        "limiares_preco": {"piso_usd": dv.PRECO_PISO, "teto_usd": dv.PRECO_TETO,
                           "noites_cotacao_max": dv.NOITES_COTACAO_MAX},
        "modelo_ocupacao": {"taxa_avaliacao": dv.TAXA_AVALIACAO, "estadia_media_nyc": dv.ESTADIA_MEDIA_NYC,
                            "teto": dv.TETO_OCUPACAO, "janela_atividade_dias": dv.JANELA_ATIVIDADE_DIAS,
                            "fonte": "https://insideairbnb.com/data-assumptions/ (consultado em 2026-09-18)"},
        "resumo_vs_detalhado_2026": comparar_resumo_detalhado(resumo26, detalhado),
        "amenities_json_invalido": r26["amenities_json_invalido"],
        "amenidades": _amenidades_relatorio(s26),
        "banheiros": _banheiros_relatorio(detalhado),
        "saidas": {c.name: {"linhas": len(df), "colunas": df.shape[1], "hash_conteudo": hash_conteudo(df)}
                   for c, df in saidas.items()},
    }
    SAIDA_QUALIDADE.write_text(json.dumps(qualidade, ensure_ascii=False, indent=2, default=str) + "\n",
                               encoding="utf-8")

    for c, info in qualidade["saidas"].items():
        print(f"  {c:28} {info['linhas']:>7,} x {info['colunas']:<3} "
              f"hash {info['hash_conteudo'][:12]}".replace(",", "."))
    print(f"  {SAIDA_QUALIDADE.name}")

    if rodar_qualidade:
        from airbnb.eda import qualidade as eda_qualidade

        eda_qualidade.executar()
    return qualidade


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sem-qualidade", action="store_true", help="nao roda eda.qualidade no fim")
    args = ap.parse_args(argv)
    executar(rodar_qualidade=not args.sem_qualidade)


if __name__ == "__main__":
    main()
