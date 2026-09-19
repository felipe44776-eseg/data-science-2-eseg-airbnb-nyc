"""Testes de localizacao: I de Moran global, LISA e comparacao entre distritos.

Funcoes genericas sobre celulas H3 — sem nome de coluna do Airbnb aqui. Quem
aplica ao dado e `eda/espacial.py`.

Vizinhanca: duas celulas sao vizinhas se uma esta no anel k=1 da outra (os seis
hexagonos adjacentes). E a contiguidade "rainha" natural do H3 — sem a ambiguidade
de quinas que a grade quadrada tem. Celula sem nenhum vizinho no conjunto (ilha)
e removida antes do teste: o I de Moran de uma ilha nao e definido, e deixar a
ilha com defasagem zero puxaria a estatistica para zero.
"""

from __future__ import annotations

import h3
import numpy as np
import pandas as pd
from esda.moran import Moran, Moran_Local
from libpysal.weights import W
from scipy import stats

from airbnb.config import SEMENTE

#: Rotulos do quadrante do LISA (convencao do esda: 1=HH, 2=LH, 3=LL, 4=HL).
QUADRANTE = {1: "Alto-Alto", 2: "Baixo-Alto", 3: "Baixo-Baixo", 4: "Alto-Baixo"}
NAO_SIGNIFICATIVO = "não significativo"


def pesos_h3(celulas: list[str]) -> tuple[W, list[str]]:
    """Pesos de contiguidade H3 (padronizados por linha), sem ilhas.

    Devolve os pesos e a lista de celulas mantidas, na ordem dos pesos.
    """
    presentes = set(celulas)
    viz = {c: [v for v in h3.grid_ring(c, 1) if v in presentes] for c in celulas}
    mantidas = [c for c in celulas if viz[c]]
    # remover ilhas pode criar novas ilhas (vizinho unico era ilha): repete ate estabilizar
    while True:
        conj = set(mantidas)
        viz = {c: [v for v in viz[c] if v in conj] for c in mantidas}
        novas = [c for c in mantidas if viz[c]]
        if len(novas) == len(mantidas):
            break
        mantidas = novas
    idx = {c: i for i, c in enumerate(mantidas)}
    w = W({idx[c]: [idx[v] for v in viz[c]] for c in mantidas}, silence_warnings=True)
    w.transform = "r"
    return w, mantidas


def moran_global(valores: pd.Series, permutacoes: int = 999, semente: int = SEMENTE) -> dict:
    """I de Moran de uma variavel indexada por celula H3, com teste de permutacao."""
    valores = valores.dropna()
    w, mantidas = pesos_h3(list(valores.index))
    y = valores.loc[mantidas].to_numpy(dtype=float)
    np.random.seed(semente)  # o esda usa o gerador global do numpy nas permutacoes
    m = Moran(y, w, permutations=permutacoes)
    return {
        "n_celulas": int(len(y)),
        "ilhas_removidas": int(len(valores) - len(mantidas)),
        "I": float(m.I),
        "I_esperado": float(m.EI),
        "z_permutacao": float(m.z_sim),
        # o pseudo p-valor do esda e "dobrado": unilateral na direcao observada.
        # Sob a hipotese nula ele vive em (0; 0,5] — sem dobrar, o falso positivo
        # a 5% seria ~10%. Publicamos o bilateral.
        "p_pseudo": float(m.p_sim),
        "p_bilateral": float(min(1.0, 2 * m.p_sim)),
        "permutacoes": permutacoes,
    }


def lisa(valores: pd.Series, alfa: float = 0.05, permutacoes: int = 999,
         semente: int = SEMENTE) -> pd.DataFrame:
    """LISA por celula, com significancia corrigida por FDR (Benjamini-Hochberg).

    Sem correcao, com milhares de celulas, 5% delas sairiam "significativas" por
    acaso. A FDR controla a fracao de falsos positivos entre os clusters apontados.
    """
    valores = valores.dropna()
    w, mantidas = pesos_h3(list(valores.index))
    y = valores.loc[mantidas].to_numpy(dtype=float)
    ml = Moran_Local(y, w, permutations=permutacoes, seed=semente)
    p = np.minimum(1.0, 2 * ml.p_sim)  # bilateral, pelo mesmo motivo do global
    signif = _fdr_bh(p, alfa)
    rotulo = np.where(signif, pd.Series(ml.q).map(QUADRANTE).to_numpy(), NAO_SIGNIFICATIVO)
    return pd.DataFrame({"I_local": ml.Is, "p": p, "significativo_fdr": signif,
                         "cluster": rotulo}, index=pd.Index(mantidas, name="h3"))


def _fdr_bh(p: np.ndarray, alfa: float) -> np.ndarray:
    """Mascara de rejeicao de Benjamini-Hochberg."""
    p = np.asarray(p, dtype=float)
    n = len(p)
    ordem = np.argsort(p)
    limite = alfa * np.arange(1, n + 1) / n
    abaixo = p[ordem] <= limite
    rejeita = np.zeros(n, dtype=bool)
    if abaixo.any():
        k = np.max(np.flatnonzero(abaixo))
        rejeita[ordem[: k + 1]] = True
    return rejeita


# --- comparacao entre grupos --------------------------------------------------


def kruskal_com_efeito(valores: pd.Series, grupos: pd.Series) -> dict:
    """Kruskal-Wallis + epsilon-quadrado (tamanho de efeito para postos).

    p-valor com n de dezenas de milhares e sempre minusculo; o que informa e o
    tamanho do efeito. epsilon2 = H (n + 1) / (n^2 - 1).
    """
    df = pd.DataFrame({"v": valores, "g": grupos}).dropna()
    amostras = [s.to_numpy() for _, s in df.groupby("g")["v"]]
    h, p = stats.kruskal(*amostras)
    n = len(df)
    return {"H": float(h), "p": float(p), "n": int(n), "k": len(amostras),
            "epsilon2": float(h * (n + 1) / (n**2 - 1))}


def pares_mann_whitney(valores: pd.Series, grupos: pd.Series) -> list[dict]:
    """Comparacoes par a par com correcao de Holm e correlacao rank-biserial."""
    df = pd.DataFrame({"v": valores, "g": grupos}).dropna()
    nomes = sorted(df["g"].unique())
    saida = []
    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            xa = df.loc[df.g == a, "v"].to_numpy()
            xb = df.loc[df.g == b, "v"].to_numpy()
            u, p = stats.mannwhitneyu(xa, xb, alternative="two-sided")
            saida.append({"a": a, "b": b, "U": float(u), "p": float(p),
                          # r > 0: valores de `a` tendem a ser maiores que os de `b`
                          "rank_biserial": float(2 * u / (len(xa) * len(xb)) - 1),
                          "mediana_a": float(np.median(xa)), "mediana_b": float(np.median(xb))})
    # Holm: ordena p, multiplica pelo numero de hipoteses restantes, impoe monotonia
    ordem = np.argsort([s["p"] for s in saida])
    m = len(saida)
    acumulado = 0.0
    for pos, j in enumerate(ordem):
        acumulado = max(acumulado, min(1.0, (m - pos) * saida[j]["p"]))
        saida[j]["p_holm"] = acumulado
    return saida


def eta2(valores: pd.Series, grupos: pd.Series) -> float:
    """Fracao da variancia explicada pelas medias dos grupos (SS entre / SS total)."""
    df = pd.DataFrame({"v": valores, "g": grupos}).dropna()
    total = ((df.v - df.v.mean()) ** 2).sum()
    medias = df.groupby("g")["v"].transform("mean")
    entre = ((medias - df.v.mean()) ** 2).sum()
    return float(entre / total) if total > 0 else float("nan")
