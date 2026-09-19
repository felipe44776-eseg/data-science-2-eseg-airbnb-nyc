"""E10 — Local Law 18 de 2022: registros de aluguel de curta temporada (OSE).

Pergunta: a Prefeitura publica dado aberto sobre os registros exigidos pela
LL18? Resposta verificada em 2026-09-18:

* NAO ha dataset no NYC Open Data (busca no catalogo por "short-term rental",
  "Office of Special Enforcement", "Local Law 18" nao retorna nada da OSE);
* SIM ha os relatorios anuais que a propria LL18 obriga a OSE a publicar, em
  XLSX, na pagina "Data & Reports" do Office of Special Enforcement
  (nyc.gov/site/specialenforcement/about/data-reports.page), um por ano fiscal
  (FY23 a FY26; o ano fiscal vai de 1/jul a 30/jun). A Figura 1 de cada um da o
  numero de registros ATIVOS por distrito do Conselho Municipal (51 distritos) —
  agregavel no espaco.

Linha do tempo (fonte: secao "History" do relatorio FY26):
  2022-01-09  LL18 adotada;
  2023-03-06  OSE passa a aceitar pedidos de registro;
  2023-09-05  plataformas passam a ser obrigadas a verificar o registro antes
              de processar a reserva (config.LL18_VIGENCIA).
O snapshot de 2019 e anterior a tudo isso; o atual (2026-06-14) cai no FY26.

Como vira dado no projeto:
  * `registros_ll18_por_distrito.csv`: (ano fiscal, distrito, ativos no fim do
    ano fiscal, ativos em algum momento do ano) — serie para a linha do tempo;
  * coluna `ll18_registros_km2_atual` nas celulas: registros ativos em
    2026-06-30 do distrito do Conselho que contem o centroide, por km2 de terra
    do distrito. So existe para a safra atual (a lei nao existia em 2019) — e
    contexto e mapa, nao feature de modelo.

Tambem publicados pela OSE e NAO processados aqui (ficam listados no manifesto):
os relatorios anuais de fiscalizacao da Local Law 87 (2017-2025), com queixas e
inspecoes de "illegal hotel" por distrito — o candidato natural para medir a
pressao de fiscalizacao ANTES da LL18.
"""

from __future__ import annotations

import re

import geopandas as gpd
import pandas as pd

from airbnb import config
from airbnb.external._http import artefato, baixar_arquivo, obter, relativo
from airbnb.external._xlsx import ler_abas

BASE = "https://www.nyc.gov/assets/specialenforcement/downloads/excel/"
PAGINA = "https://www.nyc.gov/site/specialenforcement/about/data-reports.page"
RELATORIOS = {
    "FY23": "Short-Term-Rental-Registration-Report-FY23.xlsx",
    "FY24": "Short_Term_Rental_Registration_Report_FY24.xlsx",
    "FY25": "Short_Term_Rental_Registration_Report_FY25.xlsx",
    "FY26": "LL18_Short_Term_Rental_Registration_Report_FY26.xlsx",
}
#: relatorios de fiscalizacao (LL87) — so registrados, nao processados
RELATORIOS_LL87 = {
    "2018": "2018_LL87_report.xlsx", "2019": "2019_ll87_report.xlsx",
    "2024": "2024_LL87_OSE_Annual_Report.xlsx", "2025": "2025_LL87_2025_Annual_Report.xlsx",
}
FY_DO_SNAPSHOT_ATUAL = "FY26"
N_DISTRITOS = 51

DOMINIO = "data.cityofnewyork.us"
DISTRITOS = "872g-cjhh"
URL_DISTRITOS = f"https://{DOMINIO}/resource/{DISTRITOS}.geojson"

PASTA = config.EXTERNAL / "ll18"
ARQ_DISTRITOS = PASTA / "distritos_conselho.geojson"
SAIDA = PASTA / "registros_ll18_por_distrito.csv"

LINHA_DO_TEMPO = [
    ("2022-01-09", "Local Law 18 de 2022 adotada (Short-Term Rental Registration Law)"),
    ("2023-03-06", "OSE comeca a aceitar pedidos de registro"),
    (config.LL18_VIGENCIA, "plataformas obrigadas a verificar o registro antes da reserva"),
]

META = {
    "titulo": "Relatorios anuais da LL18 (registros de curta temporada) e distritos do Conselho",
    "orgao": "NYC Mayor's Office of Special Enforcement (OSE); limites: NYC Dept. of City Planning",
    "licenca": "publicacao oficial da Prefeitura de NYC (Termos de Uso do nyc.gov); "
               "limites via NYC Open Data Terms of Use",
    "atribuicao": "Registros de aluguel de curta temporada: NYC Office of Special Enforcement, "
                  "relatorios anuais da Local Law 18. Distritos: NYC DCP, via NYC Open Data.",
}


def _inteiro(x) -> int | None:
    try:
        return int(float(str(x).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def tabela_ativos(abas: dict[str, list[list[str]]]) -> pd.DataFrame:
    """Figura 1: (distrito, ativos_fim, ativos_periodo) a partir das abas do XLSX.

    Procura a linha de cabecalho que comeca com "Council district" e cita
    "active"; le as linhas seguintes cujo primeiro valor e um distrito 1..51.
    """
    for linhas in abas.values():
        for i, lin in enumerate(linhas):
            if (len(lin) >= 2 and re.match(r"council district", str(lin[0]), re.I)
                    and re.search(r"active", " ".join(map(str, lin[1:])), re.I)):
                out = []
                for prox in linhas[i + 1:]:
                    d = _inteiro(prox[0]) if prox else None
                    if d is None or not 1 <= d <= N_DISTRITOS or len(prox) < 2:
                        if out:
                            break
                        continue
                    out.append({"distrito": d, "ativos_fim": _inteiro(prox[1]),
                                "ativos_periodo": _inteiro(prox[2]) if len(prox) > 2 else None})
                if out:
                    return pd.DataFrame(out)
    return pd.DataFrame(columns=["distrito", "ativos_fim", "ativos_periodo"])


def coletar(forcar: bool = False) -> dict:
    PASTA.mkdir(parents=True, exist_ok=True)
    artefatos, blocos, formatos = [], [], {}
    for fy, nome in RELATORIOS.items():
        destino = PASTA / nome
        if destino.exists() and not forcar:
            artefatos.append(artefato(destino, url=BASE + nome, nota="ja existia"))
        else:
            artefatos.append(baixar_arquivo(BASE + nome, destino, timeout=60, tentativas=3))
        t = tabela_ativos(ler_abas(destino.read_bytes()))
        formatos[fy] = "ok" if len(t) else "tabela por distrito nao encontrada"
        if len(t):
            blocos.append(t.assign(ano_fiscal=fy))
    for ano, nome in RELATORIOS_LL87.items():
        destino = PASTA / nome
        try:
            if not destino.exists() or forcar:
                artefatos.append(baixar_arquivo(BASE + nome, destino, timeout=60, tentativas=2))
            else:
                artefatos.append(artefato(destino, url=BASE + nome, nota="ja existia"))
        except Exception as e:  # noqa: BLE001 — complementar; registra e segue
            formatos[f"LL87_{ano}"] = f"falhou: {type(e).__name__}"

    if ARQ_DISTRITOS.exists() and not forcar:
        artefatos.append(artefato(ARQ_DISTRITOS, url=URL_DISTRITOS, nota="ja existia"))
    else:
        r = obter(URL_DISTRITOS, params={"$limit": 100}, timeout=90)
        ARQ_DISTRITOS.write_bytes(r.content)
        artefatos.append(artefato(ARQ_DISTRITOS, url=URL_DISTRITOS))

    tab = pd.concat(blocos, ignore_index=True) if blocos else pd.DataFrame()
    tab.to_csv(SAIDA, index=False)
    artefatos.append(artefato(SAIDA, derivado_de="relatorios LL18 (Figura 1)"))
    # min_count=1: relatorio sem a coluna (FY23, FY24 so tem "ativos no fim") da
    # nulo, nao zero — zero afirmaria que nao houve registro ativo no periodo
    totais = {}
    if len(tab):
        soma = tab.groupby("ano_fiscal")[["ativos_fim", "ativos_periodo"]].sum(min_count=1)
        totais = {fy: {k: (int(v) if pd.notna(v) else None) for k, v in lin.items()}
                  for fy, lin in soma.to_dict("index").items()}
    return {**META, "estado": "ok", "artefatos": artefatos,
            "resumo": {"pagina_oficial": PAGINA, "dataset_no_nyc_open_data": False,
                       "formato_por_relatorio": formatos, "totais_por_ano_fiscal": totais,
                       "linha_do_tempo": LINHA_DO_TEMPO},
            "saida": relativo(SAIDA)}


def carregar_distritos() -> gpd.GeoDataFrame | None:
    if not ARQ_DISTRITOS.exists():
        return None
    g = gpd.read_file(ARQ_DISTRITOS)
    col = next(c for c in g.columns if c.lower() in ("coundist", "council_district", "district"))
    g["distrito_conselho"] = pd.to_numeric(g[col]).astype(int)
    g["area_km2"] = g.to_crs(config.CRS_METRICO).area / 1e6
    return g[["distrito_conselho", "area_km2", "geometry"]]


def carregar() -> tuple[gpd.GeoDataFrame, pd.DataFrame] | None:
    """(distritos, registros por distrito no FY do snapshot atual) ou None."""
    g = carregar_distritos()
    if g is None or not SAIDA.exists():
        return None
    tab = pd.read_csv(SAIDA)
    if tab.empty:
        return None
    return g, tab[tab["ano_fiscal"] == FY_DO_SNAPSHOT_ATUAL]
