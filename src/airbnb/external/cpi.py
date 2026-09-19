"""E7 — CPI-U New York-Newark-Jersey City (BLS, serie CUURS12ASA0): o deflator.

Por que este indice e nao o nacional: o invariante 8 exige comparar o preco de
2019 com o atual em dolar constante, e o custo de vida em NYC subiu num ritmo
proprio. A serie metropolitana e mensal (NY e uma das tres areas que o BLS publica
todo mes), sem ajuste sazonal — o que queremos, porque comparamos dois meses
especificos (os dos snapshots), nao tendencias.

Fonte primaria: CSV do FRED (St. Louis Fed), que republica a serie do BLS sem
chave. Atencao ao codigo: o BLS renomeou a area de A101 para S12A na revisao
geografica de 2018, mas o FRED manteve o identificador antigo — no FRED a serie
e `CUURA101SA0` (`fredgraph.csv?id=CUURS12ASA0` responde 404). Os valores sao os
mesmos: 2019-07 = 278,817 nos dois. Reserva e conferencia: API publica v2 do BLS
(sem chave, limite diario baixo), que usa o codigo novo.

Saida: `data/processed/cpi_ny.parquet` com colunas `mes` ("AAAA-MM") e `indice`
(base 1982-84 = 100). Outros modulos leem por `fator_cpi()` — ninguem refaz a conta.

Uso:
    python -m airbnb.external.cpi            # baixa (se faltar) e imprime o fator
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd

from airbnb import config
from airbnb.external._http import artefato, baixar_arquivo, obter

SERIE = "CUURS12ASA0"
#: mesma serie no FRED, com o codigo de area anterior a 2018 (ver docstring)
SERIE_FRED = "CUURA101SA0"
URL_FRED = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={SERIE_FRED}"
URL_BLS = f"https://api.bls.gov/publicAPI/v2/timeseries/data/{SERIE}"

PASTA = config.EXTERNAL / "cpi"
BRUTO = PASTA / f"{SERIE_FRED}_fred.csv"
BRUTO_BLS = PASTA / f"{SERIE}_bls.json"
SAIDA = config.PROCESSED / "cpi_ny.parquet"

#: mes do snapshot atual — alvo padrao do fator (invariante 8)
MES_ATUAL = config.SNAPSHOT_ATUAL[:7]
MES_2019 = config.SNAPSHOT_2019[:7]

META = {
    "titulo": "CPI-U, All items, New York-Newark-Jersey City (NSA, mensal)",
    "orgao": "U.S. Bureau of Labor Statistics (via FRED, Federal Reserve Bank of St. Louis)",
    "licenca": "dominio publico (obra do governo federal dos EUA); FRED pede citacao da fonte",
    "atribuicao": ("U.S. Bureau of Labor Statistics, Consumer Price Index for All Urban "
                   "Consumers: All Items in New York-Newark-Jersey City, NY-NJ-PA "
                   f"[{SERIE}], via FRED, Federal Reserve Bank of St. Louis."),
}


def parse_fred(texto: str) -> pd.DataFrame:
    """CSV do FRED -> (mes, indice). Valor ausente vem como '.' ou vazio e e descartado.

    O mes ausente e real, nao erro de parse: em out/2025 o BLS nao coletou precos
    (paralisacao do governo federal) — a serie simplesmente nao tem esse mes.
    """
    df = pd.read_csv(io.StringIO(texto))
    col_data = df.columns[0]
    col_val = df.columns[1]
    df = df.rename(columns={col_data: "data", col_val: "indice"})
    df["indice"] = pd.to_numeric(df["indice"], errors="coerce")
    df = df.dropna(subset=["indice"])
    df["mes"] = pd.to_datetime(df["data"]).dt.strftime("%Y-%m")
    return df[["mes", "indice"]].sort_values("mes").reset_index(drop=True)


def parse_bls(dados: dict) -> pd.DataFrame:
    """Resposta JSON da API do BLS -> (mes, indice). M13 (media anual) e descartado."""
    linhas = []
    for serie in dados.get("Results", {}).get("series", []):
        for d in serie.get("data", []):
            per = d.get("period", "")
            if not per.startswith("M") or per == "M13":
                continue
            try:
                v = float(d["value"])
            except (KeyError, ValueError):
                continue
            linhas.append({"mes": f"{d['year']}-{per[1:]}", "indice": v})
    return pd.DataFrame(linhas).sort_values("mes").reset_index(drop=True)


def _baixar_bls() -> pd.DataFrame | None:
    """Serie pela API do BLS (codigo novo). None se o servico nao responder."""
    try:
        r = obter(URL_BLS, params={"startyear": "2017", "endyear": MES_ATUAL[:4]},
                  timeout=60, tentativas=2)
        dados = json.loads(r.content)
        if dados.get("status") != "REQUEST_SUCCEEDED":
            print(f"    BLS: {dados.get('status')} {dados.get('message')}")
            return None
        BRUTO_BLS.write_bytes(r.content)
        return parse_bls(dados)
    except Exception as e:  # noqa: BLE001 — conferencia e opcional; a falha e registrada
        print(f"    BLS indisponivel ({type(e).__name__})")
        return None


def conferir(fred: pd.DataFrame, bls: pd.DataFrame) -> dict:
    """Compara as duas publicacoes nos meses em comum (devem ser identicas)."""
    m = fred.merge(bls, on="mes", suffixes=("_fred", "_bls"))
    dif = (m["indice_fred"] - m["indice_bls"]).abs()
    return {"meses_em_comum": int(len(m)), "maior_diferenca": float(dif.max()) if len(m) else None,
            "identicas": bool(len(m) and dif.max() < 1e-6)}


def coletar(forcar: bool = False) -> dict:
    """Baixa a serie (FRED; BLS se o FRED falhar) e grava `cpi_ny.parquet`."""
    PASTA.mkdir(parents=True, exist_ok=True)
    artefatos = []
    via = "FRED"
    conferencia: dict = {}
    # BLS primeiro: e a origem. O FRED e reserva (em 2026-09 ele segurava a conexao
    # de clientes que nao sao navegador ate estourar o timeout).
    if BRUTO_BLS.exists() and not forcar:
        artefatos.append(artefato(BRUTO_BLS, url=URL_BLS, nota="ja existia — nao rebaixado"))
        df, via = parse_bls(json.loads(BRUTO_BLS.read_bytes())), "BLS"
    elif BRUTO.exists() and not forcar:
        artefatos.append(artefato(BRUTO, url=URL_FRED, nota="ja existia — nao rebaixado"))
        df, via = parse_fred(BRUTO.read_text(encoding="utf-8")), "FRED"
    else:
        df = _baixar_bls()
        if df is not None:
            via = "BLS"
            artefatos.append(artefato(BRUTO_BLS, url=URL_BLS,
                                      parametros={"startyear": "2017",
                                                  "endyear": MES_ATUAL[:4]}))
        else:
            print("    tentando o FRED")
            artefatos.append(baixar_arquivo(URL_FRED, BRUTO, timeout=60, tentativas=3))
            df = parse_fred(BRUTO.read_text(encoding="utf-8"))
    if BRUTO.exists() and BRUTO_BLS.exists():
        conferencia = conferir(parse_fred(BRUTO.read_text(encoding="utf-8")),
                               parse_bls(json.loads(BRUTO_BLS.read_bytes())))
        if via == "BLS":
            artefatos.append(artefato(BRUTO, url=URL_FRED,
                                      nota="so conferencia: mesma serie publicada pelo FRED"))

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SAIDA, index=False)
    fator, mes_para = fator_cpi(MES_2019, None, df)
    faltantes = meses_faltantes(df, "2017-01", df["mes"].max())
    resumo = {
        "via": via, "serie_bls": SERIE, "serie_fred": SERIE_FRED,
        "conferencia_fred_x_bls": conferencia or "nao feita nesta execucao",
        "meses": int(len(df)), "primeiro": df["mes"].min(),
        "ultimo": df["mes"].max(), "meses_faltantes_desde_2017": faltantes,
        "fator_2019_para_atual": round(fator, 6), "mes_de": MES_2019, "mes_para": mes_para,
        "indice_de": float(_indexar(df).loc[MES_2019]),
        "indice_para": float(_indexar(df).loc[mes_para]),
        "saida": "data/processed/cpi_ny.parquet",
    }
    return {**META, "estado": "ok", "artefatos": artefatos, "resumo": resumo}


def meses_faltantes(df: pd.DataFrame, de: str, ate: str) -> list[str]:
    """Meses sem valor no intervalo — para declarar, nao para interpolar."""
    todos = pd.period_range(de, ate, freq="M").strftime("%Y-%m")
    return sorted(set(todos) - set(df["mes"]))


# --------------------------------------------------------------------------
# API usada pelos outros modulos
# --------------------------------------------------------------------------

def ler_cpi(caminho: Path = SAIDA) -> pd.DataFrame:
    """Serie (mes, indice). Falha alto se o deflator nao foi gerado."""
    if not caminho.exists():
        raise FileNotFoundError(
            f"{caminho} ausente — rode `python -m airbnb.external.coletar --apenas cpi`")
    return pd.read_parquet(caminho)


def _indexar(serie: pd.DataFrame) -> pd.Series:
    return serie.set_index("mes")["indice"].astype(float).sort_index()


def _nivel(s: pd.Series, periodo: str) -> float:
    """Indice de um mes ('AAAA-MM') ou media anual ('AAAA', exige os 12 meses).

    A media anual serve para converter valores do ACS, que o Census publica "em
    dolares de AAAA" (nivel medio de precos daquele ano), nao de um mes.
    """
    if len(periodo) == 4:
        meses = s[s.index.str.startswith(periodo + "-")]
        if len(meses) != 12:
            raise ValueError(f"media anual de {periodo} exige 12 meses; ha {len(meses)}")
        return float(meses.mean())
    if periodo not in s.index:
        raise KeyError(f"CPI sem valor para {periodo} (ultimo disponivel: {s.index.max()})")
    return float(s.loc[periodo])


def fator_cpi(de: str = MES_2019, para: str | None = None,
              serie: pd.DataFrame | None = None) -> tuple[float, str]:
    """Fator que leva dolares de `de` para dolares de `para`: valor_para = valor_de * fator.

    `para=None` usa o mes do snapshot atual (2026-06); se esse mes ainda nao foi
    publicado, cai no mes mais recente da serie — e devolve QUAL mes usou, para que
    quem chama possa declarar. Periodo com 4 digitos ('2019') = media anual.
    """
    s = _indexar(serie if serie is not None else ler_cpi())
    padrao = MES_ATUAL if MES_ATUAL in s.index else str(s.index.max())
    mes_para = padrao if para is None else para
    return _nivel(s, mes_para) / _nivel(s, de), mes_para


def main() -> None:
    r = coletar()
    print(json.dumps(r["resumo"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
