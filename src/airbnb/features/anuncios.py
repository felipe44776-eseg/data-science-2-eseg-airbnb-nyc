"""Tabelas de modelagem: cada anuncio recebe as features da sua celula H3 r9.

Contrato (ADR 0001): a localizacao de um anuncio, para qualquer modelo, e a
celula r9 em que ele cai — as mesmas features que o simulador do site busca para
um clique. Treino e produto leem a mesma tabela de celulas; nao ha como divergir.

Anuncio cuja r9 nao esta coberta (a coordenada deslocada caiu na agua, num
parque de borda ou fora do poligono do bairro) herda a celula coberta mais
proxima, ate o anel k=3 (~0,5 km). Alem disso fica sem features de localizacao
e e contado — nunca descartado em silencio (invariante 2).

Safra: o snapshot de 2019 recebe as features externas de 2019 (ACS 2015–2019,
crimes de jul/2018–jul/2019...); o atual recebe as atuais. Features sem safra
(metro, POIs, marcos) sao as mesmas nos dois — anacronismo declarado em docs/03.
"""

from __future__ import annotations

import json

import h3
import pandas as pd

from airbnb import schema as S
from airbnb.config import DISTRITOS, PROCESSED, ROTULO_2019, ROTULO_ATUAL, SNAPSHOT_2019
from airbnb.external.cpi import fator_cpi
from airbnb.models import especificacao as E

SAIDA_JSON = PROCESSED / "_features.json"
ANEL_MAXIMO = 3


def realocar(celulas_brutas: pd.Series, cobertas: set[str]) -> tuple[pd.Series, dict]:
    """Celula coberta de cada anuncio: a propria, ou a coberta mais proxima ate k=3."""
    destino: dict[str, str | None] = {}
    por_anel = {k: 0 for k in range(ANEL_MAXIMO + 1)}
    for c in pd.unique(celulas_brutas):
        if c in cobertas:
            destino[c] = c
            continue
        destino[c] = None
        origem = h3.cell_to_latlng(c)
        for k in range(1, ANEL_MAXIMO + 1):
            candidatas = [v for v in h3.grid_ring(c, k) if v in cobertas]
            if candidatas:
                destino[c] = min(candidatas, key=lambda v: h3.great_circle_distance(
                    origem, h3.cell_to_latlng(v), unit="m"))
                break
    serie = celulas_brutas.map(destino)
    for bruta, final in zip(celulas_brutas, serie, strict=True):
        # pandas 3 devolve NaN (nao None) para o destino ausente no .map
        if pd.isna(final):
            continue
        por_anel[0 if bruta == final else h3.grid_distance(bruta, final)] += 1
    return serie, {
        "na_propria_celula": por_anel[0],
        "realocados_por_anel": {str(k): v for k, v in por_anel.items() if k > 0},
        "sem_celula_coberta": int(serie.isna().sum()),
    }


def _codificar(df: pd.DataFrame, distrito_da_celula: pd.Series) -> pd.DataFrame:
    """Categorias viram inteiros estaveis — o site envia exatamente estes codigos.

    O distrito que entra no modelo e o da CELULA, nao o declarado no anuncio: e o
    unico que o simulador conhece para um clique (ADR 0001). Os dois so diferem
    na borda entre distritos, onde o deslocamento de privacidade cruza a divisa.
    """
    for cod, (coluna, dominio) in E.CODIGOS.items():
        if coluna in df:
            df[cod] = pd.Categorical(df[coluna], categories=list(dominio)).codes.astype("int16")
    df[E.DISTRITO_COD] = pd.Categorical(
        df[E.CELULA].map(distrito_da_celula), categories=list(DISTRITOS)).codes.astype("int16")
    return df


#: Flags de controle (filtro, alvo) continuam booleanas; so FEATURE vira numero.
FLAGS = frozenset({E.PRECO_VALIDO, E.SOBREVIVEU})


def _booleanos_como_numero(df: pd.DataFrame) -> pd.DataFrame:
    """LightGBM e o avaliador JS recebem numero: bool -> 0/1, ausente -> NaN."""
    for c in df.columns:
        if c not in FLAGS and str(df[c].dtype) in ("bool", "boolean"):
            df[c] = df[c].astype("Float64").astype(float)
    return df


def montar(snapshot: str, celulas: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    nome = S.S2019 if snapshot == ROTULO_2019 else S.S2026
    df = pd.read_parquet(PROCESSED / f"{nome}.parquet")
    if snapshot == ROTULO_ATUAL:
        # os dois snapshots com o mesmo nome de coluna de bairro/distrito (o do resumo)
        df = df.rename(columns={S.COL_BAIRRO_2026: S.COL_BAIRRO,
                                S.COL_DISTRITO_2026: S.COL_DISTRITO})

    safra = "2019" if snapshot == ROTULO_2019 else "atual"
    feats = E.features_da_celula(celulas, safra)  # indice h3_r9, nomes neutros
    df[E.CELULA], alocacao = realocar(df[S.COL_H3_R9], set(feats.index))
    df = df.join(feats, on=E.CELULA)

    if snapshot == ROTULO_2019:
        fator, mes = fator_cpi(de=SNAPSHOT_2019[:7])
        df[E.PRECO_REAL] = df[S.COL_PRECO] * fator
        alocacao["cpi"] = {"fator": float(fator), "para": mes}
    else:
        df[E.PRECO_REAL] = df[S.COL_PRECO]

    df = _booleanos_como_numero(
        _codificar(df, celulas.set_index(S.COL_H3_R9)[E.DISTRITO_CELULA]))
    alocacao["n"] = int(len(df))
    alocacao["n_preco_valido"] = int(df[S.COL_PRECO_VALIDO].sum())
    return df, alocacao


def main() -> None:
    celulas = pd.read_parquet(PROCESSED / "celulas_r9.parquet")
    resumo = {"features_externas": E.externas(), "grupos_externos": E.grupos_externos(),
              "produto": E.produto()}
    for snap in (ROTULO_2019, ROTULO_ATUAL):
        df, info = montar(snap, celulas)
        destino = PROCESSED / f"modelagem_{snap}.parquet"
        df.to_parquet(destino, index=False)
        cobertura = df[E.externas()].notna().mean().round(4).to_dict()
        info["cobertura_features_externas"] = cobertura
        resumo[snap] = info
        print(f"{snap}: {len(df):,} anuncios | na propria celula {info['na_propria_celula']:,} | "
              f"realocados {info['realocados_por_anel']} | sem celula {info['sem_celula_coberta']}")
        faltando = [f for f in E.produto() if f not in df.columns]
        if snap == ROTULO_ATUAL and faltando:
            raise SystemExit(f"features do produto ausentes na tabela de modelagem: {faltando}")
    SAIDA_JSON.write_text(json.dumps(resumo, ensure_ascii=False, indent=2, default=float),
                          encoding="utf-8")
    print(f"gravado {SAIDA_JSON.name}")


if __name__ == "__main__":
    main()
