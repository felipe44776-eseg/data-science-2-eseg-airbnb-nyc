"""Especificacao das features de modelagem — fonte unica dos conjuntos de colunas.

`schema.py` manda nas colunas da silver; este modulo manda em QUAIS delas entram
em cada modelo, em que grupo, e com que nome codificado. Mudar um conjunto aqui
muda todos os modelos, a ablacao, o SHAP por grupo e a exportacao do site ao
mesmo tempo — e e esse o ponto.

Grupos (a ablacao e o SHAP somam por grupo):
  anuncio   — o imovel e as regras do anuncio (estrutura, comodidades, anfitriao)
  local     — coordenadas do centroide da celula r9 e distrito
  externas  — uma entrada por fonte externa (ACS, NYPD, 311, MTA, OSM, Zillow, marcos)
"""

from __future__ import annotations

from functools import cache

from airbnb import schema as S
from airbnb.config import SNAPSHOT_ATUAL
from airbnb.features import celulas as C

# --- identificacao e alvo ----------------------------------------------------

ID = S.COL_ID
SNAPSHOT = S.COL_SNAPSHOT
PRECO = S.COL_PRECO
PRECO_VALIDO = S.COL_PRECO_VALIDO
PRECO_REAL = "preco_real"
TIPO_QUARTO = S.COL_ROOM_TYPE
DISTRITO = S.COL_DISTRITO  # na tabela de modelagem os dois snapshots usam o nome do resumo
BAIRRO = S.COL_BAIRRO
MIN30 = S.COL_MIN30
BLOCO_CV = S.COL_H3_R6
CELULA = "h3_r9_modelo"  # a r9 coberta que o anuncio herda (ADR 0001; pode diferir da r9 bruta)
#: colunas de distrito e bairro da TABELA DE CELULAS (features/celulas.py)
DISTRITO_CELULA = "distrito"
BAIRRO_CELULA = "bairro"
#: registros ativos da Local Law 18 por km2 (OSE, FY26) — contexto do mapa, NAO feature:
#: so existe na safra atual e seria informacao do futuro para qualquer modelo de 2019
LL18_CELULA = "ll18_registros_km2_atual"
#: aluguel de longo prazo (Zillow ZORI, US$/mes) — nome neutro em features/celulas.py
ZORI = "zori"
#: toda feature monetaria (renda, aluguel, valor do imovel, ZORI) entra em dolar deste mes,
#: nas duas safras — o modelo de 2019 le 2026 na mesma unidade (invariante 8)
DOLAR_REFERENCIA = SNAPSHOT_ATUAL[:7]
SOBREVIVEU = S.COL_PRESENTE_2026
OCUPACAO = S.COL_OCUPACAO_L365D

# --- codificacoes (inteiros estaveis: o site envia o mesmo codigo) -------------

TIPO_QUARTO_COD = "room_type_cod"
DISTRITO_COD = "distrito_cod"
TIPO_IMOVEL_COD = "tipo_imovel_cod"
LICENCA_COD = "licenca_cod"
LAT = "lat"  # centroide da celula r9, nao a coordenada deslocada do anuncio
LON = "lon"

CODIGOS = {
    TIPO_QUARTO_COD: (S.COL_ROOM_TYPE, S.ROOM_TYPES),
    TIPO_IMOVEL_COD: (S.COL_TIPO_IMOVEL_GRUPO, S.TIPOS_IMOVEL),
    LICENCA_COD: (S.COL_LICENCA_STATUS, S.LICENCA_STATUS),
}

# --- grupos de features ----------------------------------------------------------

ESTRUTURA = [TIPO_QUARTO_COD, TIPO_IMOVEL_COD, "accommodates", "bedrooms", "beds",
             S.COL_BANHEIROS, S.COL_BANHEIRO_COMPARTILHADO]
COMODIDADES = [S.COL_N_AMENIDADES, *S.COLS_AMENIDADES]
REGRAS = [S.COL_MIN_NOITES, S.COL_MIN30, LICENCA_COD]
# taxas de resposta e de aceitacao vieram 100% vazias no snapshot 2026 (schema.py)
ANFITRIAO = [S.COL_HOST_SUPERHOST, S.COL_HOST_ANOS, S.COL_ANUNCIOS_HOST]
AVALIACOES = ["review_scores_rating", "review_scores_cleanliness", "review_scores_location",
              S.COL_N_AVALIACOES, S.COL_MESES_PRIMEIRA_AVALIACAO]

ANUNCIO = ESTRUTURA + COMODIDADES + REGRAS + ANFITRIAO + AVALIACOES
LOCAL_BASE = [LAT, LON, DISTRITO_COD]

#: Regressao linear (M1): estas entram como one-hot, o resto como numero.
CATEGORICAS_LINEAR = [TIPO_QUARTO_COD, TIPO_IMOVEL_COD, LICENCA_COD, DISTRITO_COD]

#: O que o usuario informa no simulador. Tudo o mais que o modelo do produto usa
#: vem da celula (localizacao) — nada e inventado no navegador.
ENTRADAS_PRODUTO = [TIPO_QUARTO_COD, "accommodates", "bedrooms", "beds", S.COL_BANHEIROS,
                    S.COL_BANHEIRO_COMPARTILHADO, S.COL_MIN30, S.COL_HOST_SUPERHOST,
                    "review_scores_rating"]

#: Features comuns aos dois snapshots (o Kaggle so tem 16 colunas): validacao
#: temporal e sobrevivencia usam so estas, mais a localizacao.
COMUNS_2019_2026 = [TIPO_QUARTO_COD, S.COL_MIN_NOITES, S.COL_MIN30, S.COL_N_AVALIACOES,
                    S.COL_AVALIACOES_MES, S.COL_ANUNCIOS_HOST, S.COL_DISPONIBILIDADE_365]


@cache
def externas() -> list[str]:
    """Features externas por celula, com nome neutro de safra (ver features/celulas.py)."""
    return [f for f in C.FEATURES_LOCAL_NEUTRAS if f not in (LAT, LON, DISTRITO_COD)]


def features_da_celula(celulas, safra: str):
    """Features de localizacao da safra, nomes neutros, monetarias em DOLAR_REFERENCIA."""
    return C.features_da_safra(celulas, safra, dolar=DOLAR_REFERENCIA)


@cache
def grupos_externos() -> dict[str, list[str]]:
    """Features externas agrupadas por fonte — a unidade da ablacao."""
    grupos: dict[str, list[str]] = {}
    for f in externas():
        grupos.setdefault(C.fonte_da_feature(f), []).append(f)
    return grupos


def produto() -> list[str]:
    """Features do modelo do simulador, na ordem exportada para o site."""
    return ENTRADAS_PRODUTO + LOCAL_BASE + externas()


def features_local_produto() -> list[str]:
    """As que o site busca em celulas_r9.json (tudo que nao e entrada do usuario)."""
    return LOCAL_BASE + externas()


def grupo_de_cada_feature(cols: list[str]) -> dict[str, str]:
    """Rotulo de grupo de cada feature, para somar SHAP por grupo.

    O que nao e coordenada nem fonte externa e atributo do anuncio — inclusive as
    derivadas que so um modelo usa (ex.: dias desde a ultima avaliacao, na
    sobrevivencia).
    """
    mapa = {c: "coordenadas" for c in LOCAL_BASE}
    for fonte, fs in grupos_externos().items():
        mapa.update({f: fonte for f in fs})
    return {c: mapa.get(c, "anúncio") for c in cols}

