"""E1 — American Community Survey, estimativas de 5 anos, por tract de NYC.

Pergunta de negocio: o anuncio caro esta onde o morador e rico, ou onde o
aluguel de longo prazo e caro? E onde ha muito imovel vago/de temporada? Renda,
aluguel, valor do imovel, posse (alugado x proprio) e vacancia do tract.

Safras (cada uma com os tracts da propria decada, ver `tracts.py`):
  * 2019  -> ACS 2015-2019 (tracts 2010), dolares de 2019;
  * atual -> ACS 2020-2024 (tracts 2020), dolares de 2024 — a mais recente
             publicada (a 2021-2025 sai em dez/2026).

Como os dados chegam — e por que nao pela API:
  a API `api.census.gov` passou a exigir chave em TODA requisicao (em
  2026-09-18 respondia a pagina "Missing Key"; o briefing previa uso sem chave).
  A alternativa oficial sem chave e o ACS Summary File no formato por tabela
  (www2.census.gov/programs-surveys/acs/summary_file/): um arquivo por tabela,
  com estimativa e margem de erro de TODAS as geografias do pais. Para 2018-2020
  o Census publica esse formato na pasta `prototype/` (pagina oficial do Summary
  File: "2018-2020: Select the Prototype folder").
  Cada arquivo tem 15-27 MB, mas e ORDENADO por GEO_ID e o servidor aceita
  `Range`: uma busca binaria por bytes acha o bloco "1400000US36..." (tracts de
  NY) e baixa ~100-300 KB em vez do arquivo inteiro.

Codigos-sentinela: o Census grava -666666666 (estimativa impossivel),
-999999999, -888888888, -222222222, -333333333, -555555555 em vez de valor.
Todas as variaveis daqui sao nao-negativas, entao qualquer negativo -> NaN.
Mediana com teto (250.001 renda, 2.000.001 valor do imovel, 3.501 aluguel) e
censura, nao valor: contada no manifesto.
"""

from __future__ import annotations

import io
import time

import numpy as np
import pandas as pd

from airbnb import config
from airbnb.external._http import artefato, obter, relativo, sha256_bytes

URLS = {
    "2019": "https://www2.census.gov/programs-surveys/acs/summary_file/2019/prototype/"
            "5YRData/acsdt5y2019-{tabela}.dat",
    "atual": "https://www2.census.gov/programs-surveys/acs/summary_file/2024/"
             "table-based-SF/data/5YRData/acsdt5y2024-{tabela}.dat",
}
PERIODO = {"2019": "2015-2019", "atual": "2020-2024"}

#: tabela -> {coluna no Summary File: nome no projeto}. Coluna do SF `B19013_E001`
#: e a variavel da API `B19013_001E`.
TABELAS: dict[str, dict[str, str]] = {
    "b01003": {"B01003_E001": "populacao"},
    "b19013": {"B19013_E001": "renda_mediana", "B19013_M001": "renda_mediana_moe"},
    "b25064": {"B25064_E001": "aluguel_mediano", "B25064_M001": "aluguel_mediano_moe"},
    "b25077": {"B25077_E001": "valor_imovel", "B25077_M001": "valor_imovel_moe"},
    "b25003": {"B25003_E001": "ocupados", "B25003_E003": "alugados"},
    "b25002": {"B25002_E001": "unidades", "B25002_E003": "vagos"},
}

#: prefixo do GEO_ID de tract no estado 36 e o limite superior (primeiro de 37)
PREFIXO = f"1400000US{config.ESTADO_FIPS}"
LIMITE = f"1400000US{int(config.ESTADO_FIPS) + 1:02d}"
JANELA_BUSCA = 256 * 1024
TETOS = {"renda_mediana": 250_001, "valor_imovel": 2_000_001, "aluguel_mediano": 3_501}

PASTA = config.EXTERNAL / "acs"

META = {
    "titulo": "American Community Survey 5-year — Summary File por tabela (tracts de NYC)",
    "orgao": "U.S. Census Bureau",
    "licenca": "dominio publico (obra do governo federal dos EUA)",
    "atribuicao": ("Fonte: U.S. Census Bureau, American Community Survey 5-year estimates "
                   "(2015-2019 e 2020-2024). Este produto usa dados do Census Bureau, mas nao "
                   "e endossado nem certificado por ele."),
}


def arquivo(safra: str):
    return PASTA / f"acs5_{PERIODO[safra]}_tracts_nyc.csv"


# --------------------------------------------------------------------------
# leitura por faixa de bytes
# --------------------------------------------------------------------------

def _faixa(url: str, ini: int, fim: int) -> bytes:
    r = obter(url, headers={"Range": f"bytes={ini}-{fim}"}, timeout=60, tentativas=4)
    if r.status_code != 206:
        raise RuntimeError(f"servidor ignorou Range em {url} (HTTP {r.status_code})")
    return r.content


def _geo_apos(url: str, pos: int, tam: int) -> str:
    """GEO_ID da primeira linha COMPLETA que comeca depois do byte `pos`."""
    b = _faixa(url, pos, min(pos + 8191, tam - 1))
    i = b.find(b"\n")
    if i < 0 or i + 1 >= len(b):
        return "￿"  # fim do arquivo: maior que qualquer chave
    return b[i + 1:].split(b"|", 1)[0].decode()


def _busca(url: str, tam: int, chave: str) -> tuple[int, int]:
    """(lo, hi): toda linha com GEO_ID >= chave comeca depois de lo; a primeira
    delas comeca ate hi + 1 linha. Invariante: geo_apos(lo) < chave <= geo_apos(hi)."""
    lo, hi = 0, tam
    while hi - lo > JANELA_BUSCA:
        meio = (lo + hi) // 2
        if _geo_apos(url, meio, tam) < chave:
            lo = meio
        else:
            hi = meio
        time.sleep(0.1)
    return lo, hi


def extrair_bloco(texto: str, prefixo: str) -> list[str]:
    """Linhas completas cujo GEO_ID comeca com `prefixo` (descarta as pontas partidas)."""
    linhas = texto.split("\n")
    return [x for x in linhas[1:-1] if x.startswith(prefixo)]


def baixar_tabela(url: str) -> tuple[str, list[str]]:
    """(cabecalho, linhas dos tracts de NY) de um arquivo do Summary File."""
    cab = _faixa(url, 0, 4095).split(b"\n", 1)[0].decode().strip()
    tam = int(obter(url, metodo="HEAD", timeout=60).headers["Content-Length"])
    ini, _ = _busca(url, tam, PREFIXO)
    _, fim = _busca(url, tam, LIMITE)
    texto = _faixa(url, ini, min(fim + 8192, tam - 1)).decode()
    linhas = extrair_bloco(texto, PREFIXO)
    geos = [x.split("|", 1)[0] for x in linhas]
    if geos != sorted(geos) or len(set(geos)) != len(geos):
        raise RuntimeError(f"bloco extraido fora de ordem ou com repeticao: {url}")
    return cab, linhas


def parse_tabela(cab: str, linhas: list[str], colunas: dict[str, str]) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO("\n".join([cab, *linhas])), sep="|", dtype=str)
    out = pd.DataFrame({"geoid": df["GEO_ID"].str.replace("1400000US", "", regex=False)})
    for orig, nome in colunas.items():
        out[nome] = limpar_sentinelas(df[orig])
    return out


def limpar_sentinelas(s: pd.Series) -> pd.Series:
    """Numerico; codigos-sentinela (negativos) e vazio -> NaN."""
    v = pd.to_numeric(s, errors="coerce").astype(float)
    return v.where(v >= 0)


def coletar(forcar: bool = False) -> dict:
    PASTA.mkdir(parents=True, exist_ok=True)
    condados = set(config.CONDADO_FIPS.values())
    artefatos, resumo = [], {}
    for safra, modelo in URLS.items():
        destino = arquivo(safra)
        if destino.exists() and not forcar:
            artefatos.append(artefato(destino, url=modelo, nota="ja existia — nao rebaixado"))
        else:
            tabela_final, fontes = None, []
            for tabela, colunas in TABELAS.items():
                url = modelo.format(tabela=tabela)
                cab, linhas = baixar_tabela(url)
                t = parse_tabela(cab, linhas, colunas)
                t = t[t["geoid"].str[2:5].isin(condados)]
                fontes.append({"url": url, "linhas_ny": len(linhas),
                               "linhas_nyc": int(len(t)),
                               "sha256_bloco": sha256_bytes("\n".join(linhas).encode())})
                print(f"    ACS {safra} {tabela}: {len(t)} tracts de NYC", flush=True)
                tabela_final = t if tabela_final is None else tabela_final.merge(
                    t, on="geoid", how="outer")
            tabela_final.sort_values("geoid").to_csv(destino, index=False)
            artefatos.append(artefato(destino, url=modelo, tabelas=fontes,
                                      metodo="HTTP Range + busca binaria por GEO_ID"))
        d = carregar(safra)
        resumo[safra] = {
            "periodo": PERIODO[safra], "tracts": int(len(d)),
            "nulos_pct": {c: round(float(d[c].isna().mean() * 100), 1) for c in d.columns},
            "no_teto": {k: int((d[k] >= v).sum()) for k, v in TETOS.items()},
            "renda_cv_mediana": round(float(np.nanmedian(
                d["renda_mediana_moe"] / 1.645 / d["renda_mediana"])), 3),
        }
    return {**META, "estado": "ok", "artefatos": artefatos, "resumo": resumo,
            "saida": [relativo(arquivo(s)) for s in URLS]}


def carregar(safra: str) -> pd.DataFrame | None:
    """Tabela da safra indexada por GEOID de 11 digitos, ou None se nao coletada."""
    p = arquivo(safra)
    if not p.exists():
        return None
    return pd.read_csv(p, dtype={"geoid": str}).set_index("geoid")
