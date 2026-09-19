"""Colunas derivadas da limpeza — funcoes puras sobre Series.

Cada funcao recebe coluna(s) de origem e devolve a derivada, sem ler arquivo
nem depender de estado: e o que permite testa-las com frames sinteticos
(tests/test_limpeza.py) sem o dado real. Nomes das colunas moram em
`schema.py`; aqui mora a REGRA.

Constantes do modelo de ocupacao do Inside Airbnb ("San Francisco Model",
https://insideairbnb.com/data-assumptions/, consultado em 2026-09-18): taxa de
avaliacao 50%, estadia media por cidade (3 noites onde nao ha dado publico),
minimo de noites quando maior que a estadia media, teto de 70%. O valor de NYC
(6,4 noites) nao esta na pagina: foi obtido reproduzindo o
`estimated_occupancy_l365d` do snapshot de 2026 — a formula com 6,4 acerta
99,99% dos anuncios (docs/02 §6).
"""

from __future__ import annotations

import json
import re

import h3
import numpy as np
import pandas as pd

from airbnb import config
from airbnb.schema import AMENIDADES, LICENCA_STATUS, TIPOS_IMOVEL

# --- modelo de ocupacao (declarado aqui; candidato a config.py) -------------------------

TAXA_AVALIACAO = 0.50
ESTADIA_MEDIA_NYC = 6.4
ESTADIA_MEDIA_PADRAO = 3.0  # default da pagina do Inside Airbnb — usado so na sensibilidade
TETO_OCUPACAO = 0.70
#: Sem avaliacao nos ultimos 365 dias o modelo zera: e o que o Inside Airbnb faz
#: ao usar avaliacoes dos ultimos 12 meses. `reviews_per_month` e media da vida
#: inteira do anuncio — sem esta janela, anuncio parado desde 2016 teria ocupacao.
JANELA_ATIVIDADE_DIAS = 365
DIAS_POR_MES = 365.25 / 12

# --- limiares de preco (justificativa com dado em docs/04 §3) ----------------------------

#: Em 2019 nao ha preco entre US$ 1 e US$ 9: o menor preco positivo e 10.
PRECO_PISO = 10.0
#: Em 2019 o maximo observado e exatamente US$ 10.000 (3 anuncios): acima disso
#: nao ha suporte de comparacao com 2019.
PRECO_TETO = 10_000.0
#: Cotacao de ate 31 noites e total do periodo; acima disso o Inside Airbnb recebe
#: um total MENSAL e divide por N noites — preco por noite subestimado ~N/30.
NOITES_COTACAO_MAX = 31


# --- preco ------------------------------------------------------------------------------


def parse_preco(s: pd.Series) -> pd.Series:
    """'$1,234.00' -> 1234.0. Numero passa direto; texto invalido vira NaN.

    Coerce em vez de erro: o que nao for preco vira nulo e cai na regra de
    quarentena `preco_ausente` — contado, nao escondido.
    """
    if pd.api.types.is_numeric_dtype(s.dtype):
        return s.astype("float64")
    txt = s.astype("string").str.replace(r"[\s$,]", "", regex=True)
    return pd.to_numeric(txt, errors="coerce").astype("float64")


def _itens_cotacao(bruto: object) -> tuple[float, float]:
    """(preco cheio do periodo, soma dos descontos) de um `price_quote_raw`.

    Preco cheio = total cotado + |itens negativos| (desconto mensal/semanal,
    "Airbnb monthly stay savings", oferta especial). Nas cotacoes >= 28 noites
    isso e exatamente o item "Average monthly price". JSON malformado, sem
    `total_price` ou sem cotacao -> (NaN, NaN).
    """
    if not isinstance(bruto, str):
        return np.nan, np.nan
    try:
        q = json.loads(bruto)["quote"]
        total = q.get("total_price")
        if total is None:
            return np.nan, np.nan
        total = float(total)
        desconto = 0.0
        for it in q.get("raw_price_line_items") or []:
            if it.get("item_type") == "discounted_subtotal":
                continue
            valor = float(it.get("amount"))
            if valor < 0:
                desconto += -valor
        return total + desconto, desconto
    except (ValueError, TypeError, KeyError, AttributeError):
        return np.nan, np.nan


def cotacao(raw: pd.Series, checkin: pd.Series, checkout: pd.Series) -> pd.DataFrame:
    """Noites da cotacao, diaria cheia (sem desconto) e fracao de desconto.

    `preco_cheio` divide pelas mesmas N noites que o `price` publicado — logo
    herda o mesmo defeito nas cotacoes > 31 noites (tratadas na quarentena).
    """
    noites = (pd.to_datetime(checkout) - pd.to_datetime(checkin)).dt.days
    pares = raw.map(_itens_cotacao)
    cheio_periodo = pares.map(lambda t: t[0]).astype("float64")
    desconto = pares.map(lambda t: t[1]).astype("float64")
    n = noites.astype("float64").where(noites > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        preco_cheio = cheio_periodo / n
        pct = (desconto / cheio_periodo).where(cheio_periodo > 0)
    return pd.DataFrame({
        "preco_cotacao_noites": noites.astype("Int64"),
        "preco_cheio": preco_cheio.astype("float64"),
        "desconto_pct": pct.astype("float64"),
    }, index=raw.index)


# --- banheiros ------------------------------------------------------------------------------


def banheiros(bathrooms: pd.Series, texto: pd.Series) -> pd.DataFrame:
    """Numero de banheiros e se e compartilhado.

    `bathrooms` (numero extraido pelo Inside Airbnb) vale quando existe; o texto
    completa os 33% em que ele e nulo. "Half-bath" nao tem numero: e meio banheiro.
    Compartilhado = "shared" no texto; sem texto, nulo (nao sabemos).
    """
    t = texto.astype("string").str.strip().str.lower()
    num = pd.to_numeric(t.str.extract(r"(\d+(?:\.\d+)?)", expand=False), errors="coerce")
    meio = t.str.contains("half", na=False).astype(bool)
    num = num.astype("float64").where(~(meio & num.isna()), 0.5)
    n = pd.to_numeric(bathrooms, errors="coerce").astype("float64")
    return pd.DataFrame({
        "banheiros": n.where(n.notna(), num),
        "banheiro_compartilhado": t.str.contains("shared").astype("boolean"),
    }, index=texto.index)


# --- amenidades -----------------------------------------------------------------------------


def _lista(bruto: object) -> list[str] | None:
    if not isinstance(bruto, str):
        return None
    try:
        v = json.loads(bruto)
    except ValueError:
        return None
    return [str(x) for x in v] if isinstance(v, list) else None


def amenidades(s: pd.Series) -> tuple[pd.DataFrame, int]:
    """`n_amenidades` + uma coluna bool por flag de `schema.AMENIDADES`.

    A regex roda uma vez por NOME distinto (6 mil), nao por item de cada
    anuncio (860 mil): o resultado e o mesmo e custa 1% do tempo. Devolve tambem
    quantas listas nao eram JSON valido (contam como vazias e vao para o relatorio).
    """
    listas = s.map(_lista)
    invalidas = int(listas.isna().sum())
    listas = listas.map(lambda v: v if v is not None else [])
    padroes = {k: re.compile(p, re.IGNORECASE) for k, (p, _) in AMENIDADES.items()}
    nomes = set().union(*listas) if len(listas) else set()
    casa = {nome: [k for k, p in padroes.items() if p.search(nome)] for nome in nomes}
    marcas = {k: np.zeros(len(s), dtype=bool) for k in padroes}
    for i, itens in enumerate(listas):
        for item in itens:
            for k in casa[item]:
                marcas[k][i] = True
    out = pd.DataFrame({"n_amenidades": listas.map(len).astype("int64"), **marcas}, index=s.index)
    return out, invalidas


# --- licenca, tipo de imovel, anfitriao --------------------------------------------------------


def licenca_status(s: pd.Series) -> pd.Series:
    """registrada (OSE-STRREG..., sem caixa) · isenta (Exempt) · ausente · outra."""
    t = s.astype("string").str.strip()
    out = pd.Series("outra", index=s.index, dtype="object")
    out[t.isna() | t.eq("").fillna(False)] = "ausente"
    out[t.str.upper().str.startswith("OSE-STRREG").fillna(False).astype(bool)] = "registrada"
    out[t.str.lower().eq("exempt").fillna(False).astype(bool)] = "isenta"
    return pd.Series(pd.Categorical(out, categories=LICENCA_STATUS), index=s.index)


_HOTEL = re.compile(r"hotel|hostel|resort|bed and breakfast|\bdorm\b|kezhan|^room in", re.I)
_ATIPICO = re.compile(
    r"\b(boat|houseboat|camper|rv|tent|tower|floor|barn|dome|cave|castle|train|earthen|"
    r"religious|ranch|treehouse|yurt|lighthouse|windmill|bus|island)\b", re.I)
_APTO = re.compile(r"rental unit|condo|loft|serviced apartment|\bplace\b", re.I)
_POR_ROOM_TYPE = {
    "Entire home/apt": "apartamento_inteiro",
    "Private room": "quarto_em_casa",
    "Shared room": "quarto_compartilhado",
    "Hotel room": "hotel_pousada",
}


def _grupo(prop: object, room: object) -> str:
    p = str(prop).strip() if isinstance(prop, str) else ""
    pl = p.lower()
    if pl.startswith("shared room"):
        return "quarto_compartilhado"
    if _HOTEL.search(p):
        return "hotel_pousada"
    if _ATIPICO.search(p):
        return "atipico"
    if pl.startswith("private room"):
        return "quarto_em_apartamento" if _APTO.search(p) else "quarto_em_casa"
    if pl.startswith("entire"):
        return "apartamento_inteiro" if _APTO.search(p) else "casa_inteira"
    if pl in ("tiny home", "casa particular"):
        return "casa_inteira"
    return _POR_ROOM_TYPE.get(room, "atipico")


def tipo_imovel_grupo(prop: pd.Series, room_type: pd.Series) -> pd.Series:
    """69 `property_type` em 7 grupos. Ordem das regras importa: "Private room
    in houseboat" e atipico antes de ser quarto; "Room in hotel" e hotel antes
    de tudo. Valor nao previsto cai pelo `room_type`, nunca fica sem grupo."""
    g = [_grupo(p, r) for p, r in zip(prop, room_type, strict=True)]
    return pd.Series(pd.Categorical(g, categories=TIPOS_IMOVEL), index=prop.index)


def host_anos(anos: pd.Series, meses: pd.Series) -> pd.Series:
    """Anos como anfitriao. `host_since` veio 100% nulo em 2026; o Inside Airbnb
    passou a publicar o tempo ja decomposto em anos + meses (0–11)."""
    return (anos.astype("float64") + meses.astype("float64") / 12).astype("float64")


def booleano_tf(s: pd.Series) -> pd.Series:
    """'t'/'f' da origem -> boolean anulavel. Outro valor vira nulo."""
    return s.map({"t": True, "f": False}).astype("boolean")


# --- espaco, tempo e ocupacao ------------------------------------------------------------------


def celula_h3(lat: pd.Series, lon: pd.Series, resolucao: int) -> pd.Series:
    """Celula H3 de cada ponto. Coordenada invalida ja saiu na quarentena."""
    return pd.Series(
        [h3.latlng_to_cell(a, o, resolucao) for a, o in zip(lat, lon, strict=True)],
        index=lat.index, dtype="str")


def dias_desde(data: pd.Series, referencia: pd.Series | pd.Timestamp) -> pd.Series:
    """Dias inteiros entre `data` e a referencia (nulo onde `data` e nula)."""
    return (pd.to_datetime(referencia) - pd.to_datetime(data)).dt.days.astype("Int64")


def ocupacao_modelo(reviews_per_month: pd.Series, minimum_nights: pd.Series,
                    dias_sem_avaliacao: pd.Series, estadia_media: float = ESTADIA_MEDIA_NYC,
                    janela: int | None = JANELA_ATIVIDADE_DIAS) -> pd.Series:
    """Fracao do ano ocupada pelo modelo de avaliacoes do Inside Airbnb.

    reservas/mes = avaliacoes/mes / 0,5; noites por reserva = max(estadia media,
    minimo de noites); ocupacao = reservas/mes x 12 x noites / 365, teto 0,70.
    Anuncio sem avaliacao na janela (ou sem nenhuma) = 0. `janela=None`
    desliga o corte — so para a analise de sensibilidade.
    """
    rpm = reviews_per_month.astype("float64").fillna(0.0)
    noites = np.maximum(estadia_media, minimum_nights.astype("float64"))
    occ = (rpm / TAXA_AVALIACAO * 12 * noites / 365).clip(upper=TETO_OCUPACAO)
    if janela is not None:
        ativo = (dias_sem_avaliacao <= janela).fillna(False).astype(bool)
        occ = occ.where(ativo, 0.0)
    return occ.astype("float64")


def snapshot_2019_ts() -> pd.Timestamp:
    """Data do scrape de 2019 como Timestamp (referencia dos 'dias desde')."""
    return pd.Timestamp(config.SNAPSHOT_2019)
