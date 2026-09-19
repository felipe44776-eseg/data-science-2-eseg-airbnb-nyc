"""Figuras da documentacao, geradas dos resultados — nunca desenhadas a mao.

Regras de desenho (validadas com o validador de paleta; ver docs/09):
  - cor categorica em ordem fixa: distritos com a paleta da v0 do grupo;
    2019 x 2026 sempre azul x vermelho;
  - sequencial = um matiz (azul) claro -> escuro; divergente = azul <-> vermelho
    com cinza neutro no zero;
  - um eixo so, marcas finas, rotulo direto no lugar de legenda quando cabe,
    grade recessiva, texto sempre na cor da tinta (nunca na cor da serie);
  - fundo papel (#FBF6EC) proprio: a figura le igual no tema claro e no escuro
    da documentacao.
"""

from __future__ import annotations

import json

import h3
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402

from airbnb.config import DISTRITOS, DOCS, PROCESSED  # noqa: E402
from airbnb.produto import rotulos  # noqa: E402

DESTINO = DOCS / "assets" / "figuras"

PAPEL, TINTA, TINTA_SUAVE, TINTA_FRACA = "#FBF6EC", "#221E18", "#6E6656", "#A79E8A"
GRADE = "#E7DFCF"
COR_DISTRITO = dict(zip(DISTRITOS, ("#E14F3D", "#128F7C", "#C98A1B", "#5468D9", "#A24C97"),
                        strict=True))
COR_2019, COR_2026 = "#5468D9", "#E14F3D"
AZUL, VERMELHO, NEUTRO = "#2a78d6", "#e34948", "#f0efec"
DIVERGENTE = LinearSegmentedColormap.from_list(
    "divergente", ["#104281", "#3987e5", NEUTRO, "#e66767", "#a52a2a"])


def tema() -> None:
    plt.rcParams.update({
        "figure.facecolor": PAPEL, "axes.facecolor": PAPEL, "savefig.facecolor": PAPEL,
        "text.color": TINTA, "axes.labelcolor": TINTA_SUAVE, "xtick.color": TINTA_SUAVE,
        "ytick.color": TINTA_SUAVE, "axes.edgecolor": GRADE, "grid.color": GRADE,
        "grid.linewidth": 0.8, "axes.grid": True, "axes.grid.axis": "x",
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "font.size": 10.5, "axes.titlesize": 12, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "axes.titlepad": 12, "svg.fonttype": "none",
        "svg.hashsalt": "airbnb-nyc",  # ids estaveis: o SVG nao muda se o dado nao mudou
    })


def _ler(nome: str) -> dict | None:
    p = PROCESSED / nome
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _salvar(fig, nome: str) -> str:
    DESTINO.mkdir(parents=True, exist_ok=True)
    caminho = DESTINO / nome
    meta = {"Date": None} if nome.endswith(".svg") else {}
    fig.savefig(caminho, bbox_inches="tight", dpi=160, metadata=meta)
    plt.close(fig)
    return caminho.name


def _pct_br(v: float, casas: int = 0) -> str:
    return f"{v:.{casas}f}%".replace(".", ",")


# --- preco ---------------------------------------------------------------------------


def escada(p: dict) -> str:
    ordem = ["B0", "B1", "M1", "M2", "M3", "M4_sem_coordenadas", "M4", "M5"]
    rot = {"B0": "B0 mediana global", "B1": "B1 bairro × tipo (v0)", "M1": "M1 linear hedônico",
           "M2": "M2 só o imóvel", "M3": "M3 + coordenadas", "M4_sem_coordenadas":
           "M4 sem coordenadas", "M4": "M4 + fontes externas", "M5": "M5 produto (site)"}
    ks = [k for k in ordem if k in p["metricas"]][::-1]
    fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(ks) + 1.2))
    for i, k in enumerate(ks):
        m = p["metricas"][k]
        folds = [100 * f for f in m.get("mdape_folds", [])]
        cor = VERMELHO if k == "M5" else AZUL if k.startswith("M") else TINTA_FRACA
        ax.hlines(i, min(folds), max(folds), color=cor, lw=2, alpha=0.35)
        ax.plot(100 * m["mdape"], i, "o", ms=8, color=cor, mec=PAPEL, mew=2)
        ax.text(max(folds) + 0.8, i, _pct_br(100 * m["mdape"], 1), va="center", fontsize=9.5)
    ax.set_yticks(range(len(ks)), [rot[k] for k in ks])
    ax.set_xlabel("erro percentual mediano (MdAPE) — menor é melhor")
    ax.set_xlim(0, None)
    ax.set_title("Cada degrau da escada, sob validação cruzada espacial", pad=24)
    ax.text(0, 1.015, "ponto = todos os folds · traço = do melhor ao pior fold", fontsize=8.5,
            color=TINTA_SUAVE, transform=ax.transAxes)
    return _salvar(fig, "escada.svg")


def ablacao(p: dict) -> str:
    itens = list(p["ablacao"].items())[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 0.5 * len(itens) + 1.2))
    for i, (_fonte, a) in enumerate(itens):
        cor = VERMELHO if a["folds_que_pioram"] >= 4 else TINTA_FRACA
        ax.barh(i, a["delta_mdape_pp"], color=cor, height=0.55)
        ax.plot(a["delta_mdape_pp_folds"], [i] * len(a["delta_mdape_pp_folds"]), "|",
                color=TINTA, ms=10, mew=1.2)
        ax.text(max(a["delta_mdape_pp"], max(a["delta_mdape_pp_folds"])) + 0.03, i,
                f"{a['folds_que_pioram']}/5 folds pioram", va="center", fontsize=8.5,
                color=TINTA_SUAVE)
    ax.axvline(0, color=TINTA_SUAVE, lw=1)
    ax.set_yticks(range(len(itens)), [f for f, _ in itens])
    ax.set_xlabel("quanto o MdAPE piora ao retirar a fonte (pontos percentuais)")
    ax.set_title("O que cada fonte externa agrega ao modelo")
    return _salvar(fig, "ablacao.svg")


def shap_grupos(p: dict) -> str:
    fr = p["shap_m4"]["fracao_por_grupo"]
    itens = list(fr.items())[::-1]
    fig, ax = plt.subplots(figsize=(7.2, 0.42 * len(itens) + 1))
    for i, (g, v) in enumerate(itens):
        ax.barh(i, 100 * v, color=AZUL if g != "anúncio" else TINTA_FRACA, height=0.6)
        ax.text(100 * v + 0.5, i, _pct_br(100 * v), va="center", fontsize=9.5)
    ax.set_yticks(range(len(itens)), [g for g, _ in itens])
    ax.set_xlabel("fração da contribuição média absoluta (SHAP) no modelo M4")
    ax.set_title("Quanto do preço cada grupo de informação explica")
    return _salvar(fig, "shap_grupos.svg")


#: rotulo legivel e escala do eixo x das features de localizacao nas figuras
ROTULO_FEATURE: dict[str, tuple[str, float]] = {
    "zori": ("aluguel de longo prazo do CEP (US$/mês)", 1),
    "dist_marco_km": ("distância ao marco turístico (km)", 1),
    "dist_centro_km": ("distância a Times Square (km)", 1),
    "dist_aeroporto_km": ("distância ao aeroporto (km)", 1),
    "acs_aluguel_mediano": ("aluguel mediano do setor censitário (US$/mês)", 1),
    "acs_valor_imovel": ("valor mediano do imóvel (US$ mil)", 1e-3),
    "acs_renda_mediana": ("renda domiciliar mediana (US$ mil)", 1e-3),
    "acs_pop_densidade": ("habitantes por km²", 1),
    "metro_dist_m": ("distância ao metrô (m)", 1),
    "crime_graves_km2": ("crimes graves por km² (12 meses)", 1),
    "poi_restaurantes_k1": ("restaurantes no entorno (~500 m)", 1),
    "poi_hoteis_k1": ("hotéis no entorno (~500 m)", 1),
    "lat": ("latitude (sul → norte)", 1),
    "lon": ("longitude (oeste → leste)", 1),
}


def dependencia(p: dict) -> str:
    from matplotlib.ticker import MaxNLocator

    dep = p["shap_m4"]["dependencia"]
    n = len(dep)
    col = 3
    lin = int(np.ceil(n / col))
    fig, axs = plt.subplots(lin, col, figsize=(9.5, 2.8 * lin), squeeze=False)
    for ax, (f, d) in zip(axs.flat, dep.items(), strict=False):
        rotulo, escala = ROTULO_FEATURE.get(f, (f, 1))
        efeito = 100 * (np.exp(np.array(d["shap"])) - 1)
        ax.axhline(0, color=TINTA_FRACA, lw=0.8)
        ax.plot(np.array(d["x"]) * escala, efeito, "-o", color=AZUL, lw=2, ms=4)
        ax.set_title(rotulo, fontsize=9.5)
        ax.grid(axis="y")
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.set_ylabel("efeito no preço (%)", fontsize=8.5)
    for ax in list(axs.flat)[n:]:
        ax.axis("off")
    fig.suptitle("Como as principais variáveis de localização movem o preço "
                 "(efeito SHAP médio por faixa, modelo M4)",
                 x=0.01, ha="left", fontweight="bold", fontsize=11.5)
    fig.tight_layout()
    return _salvar(fig, "dependencia.svg")


# --- comparativo -------------------------------------------------------------------


def estratos(c: dict) -> str:
    linhas = [e for e in c["preco_por_estrato"]
              if e["2019"]["n"] >= 30 and e["2026"]["n"] >= 30][::-1]
    fig, ax = plt.subplots(figsize=(7.4, 0.55 * len(linhas) + 1.4))
    for i, e in enumerate(linhas):
        for snap, cor, dy in (("2019", COR_2019, 0.12), ("2026", COR_2026, -0.12)):
            x = e[snap]
            lo, hi = x["ic95"]
            if lo is not None:
                ax.hlines(i + dy, lo, hi, color=cor, lw=2, alpha=0.5)
            ax.plot(x["mediana"], i + dy, "o", color=cor, ms=7, mec=PAPEL, mew=1.5)
    ax.set_yticks(range(len(linhas)), [f"{rotulos.tipo(e['tipo'])} · {e['estrato']}"
                                       for e in linhas])
    ax.set_xlabel(f"preço mediano por noite, em US$ de {c['cpi']['para']} (IC 95%)")
    ax.set_title("Preço real por estrato: 2019 × 2026", pad=26)
    ax.plot([], [], "o", color=COR_2019, label="2019 (corrigido pelo CPI-U NY)")
    ax.plot([], [], "o", color=COR_2026, label="2026")
    # legenda acima da area de dados: nenhum intervalo fica coberto
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, fontsize=9,
              borderaxespad=0.2, handletextpad=0.3)
    return _salvar(fig, "estratos.svg")


def min30_distritos(c: dict) -> str:
    d = c["por_distrito"]
    nomes = [n for n in DISTRITOS if n in d][::-1]
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    for i, n in enumerate(nomes):
        a, b = 100 * d[n]["pct_min30_2019"], 100 * d[n]["pct_min30_2026"]
        ax.hlines(i, a, b, color=TINTA_FRACA, lw=1.5)
        ax.plot(a, i, "o", color=COR_2019, ms=8, mec=PAPEL, mew=1.5)
        ax.plot(b, i, "o", color=COR_2026, ms=8, mec=PAPEL, mew=1.5)
        ax.text(b + 1.5, i, _pct_br(b), va="center", fontsize=9)
        ax.text(a - 1.5, i, _pct_br(a), va="center", ha="right", fontsize=9)
    ax.set_yticks(range(len(nomes)), nomes)
    ax.set_xlim(-8, 108)
    ax.set_xlabel("anúncios que exigem mínimo de 30 noites (%)")
    ax.set_title("Local Law 18: de estadia curta a aluguel mensal")
    ax.plot([], [], "o", color=COR_2019, label="2019")
    ax.plot([], [], "o", color=COR_2026, label="2026")
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    return _salvar(fig, "min30_distritos.svg")


# --- sobrevivencia e deriva ------------------------------------------------------------


def sobrevivencia(s: dict) -> str:
    recortes = [("faixa_host", "anúncios do anfitrião em 2019"),
                ("recencia", "última avaliação antes de jul/2019")]
    fig, axs = plt.subplots(1, 2, figsize=(9, 3.2), sharex=True)
    for ax, (chave, titulo) in zip(axs, recortes, strict=True):
        itens = list(s["taxas"][chave].items())[::-1]
        for i, (_g, v) in enumerate(itens):
            ax.barh(i, 100 * v["taxa"], color=AZUL, height=0.6)
            ax.text(100 * v["taxa"] + 0.8, i, _pct_br(100 * v["taxa"]), va="center", fontsize=9)
        ax.set_yticks(range(len(itens)), [g for g, _ in itens])
        ax.set_title(titulo, fontsize=10.5)
    axs[0].set_xlabel("ainda no ar em 2026 (%)")
    axs[1].set_xlabel("ainda no ar em 2026 (%)")
    fig.suptitle("Quem sobreviveu de 2019 a 2026", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    return _salvar(fig, "sobrevivencia.svg")


def calibracao(s: dict) -> str:
    cal = s["lightgbm"]["calibracao"]
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.plot([0, 1], [0, 1], color=TINTA_FRACA, lw=1)
    ax.plot([c["previsto"] for c in cal], [c["observado"] for c in cal], "-o", color=AZUL,
            lw=2, ms=5)
    ax.set_xlabel("probabilidade prevista (decis)")
    ax.set_ylabel("fração observada que sobreviveu")
    ax.grid(axis="both")
    ax.set_title("Calibração do modelo de sobrevivência")
    return _salvar(fig, "calibracao_sobrevivencia.svg")


def deriva(d: dict) -> str:
    itens = [("2019 → 2019", "modelo_2019_cv_espacial_em_2019", COR_2019),
             ("2026 → 2026", "modelo_2026_cv_espacial_em_2026", COR_2026),
             ("2019 → 2026", "modelo_2019_aplicado_a_2026", TINTA_SUAVE),
             ("2026 → 2019", "modelo_2026_aplicado_a_2019", TINTA_FRACA)][::-1]
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    for i, (_r, k, cor) in enumerate(itens):
        v = 100 * d[k]["mdape"]
        ax.barh(i, v, color=cor, height=0.6)
        ax.text(v + 0.5, i, _pct_br(v, 1), va="center", fontsize=9.5)
    ax.set_yticks(range(len(itens)), [r for r, _, _ in itens])
    ax.set_xlabel("MdAPE (treino → teste), mesmas features comuns aos dois snapshots")
    ax.set_title("O mercado de 2019 ainda explica o de hoje?")
    return _salvar(fig, "deriva.svg")


# --- mapa ------------------------------------------------------------------------------


def mapa_premio() -> str | None:
    """Premio de localizacao modelado por celula r9 — o mesmo calculo do simulador.

    Em r9 (aresta ~174 m) os rios e a orla aparecem; o mapa r8 do site agrega para
    ter anuncios suficientes por celula, mas o premio modelado existe em toda r9.
    """
    arq = PROCESSED / "premio_r9.parquet"
    if not arq.exists():
        return None
    import geopandas as gpd
    import pandas as pd

    from airbnb.config import RAW_INSIDE

    d = pd.read_parquet(arq)
    polis = [[(lo, la) for la, lo in h3.cell_to_boundary(c)] for c in d.iloc[:, 0]]
    # escala assimetrica: o premio vai de ~-15% a +400% — simetrica em +-60 saturaria
    # Manhattan inteira; o zero continua no cinza neutro
    vmin, vmax = -20, 150
    vals = np.clip(d["premio_modelo_pct"].to_numpy(), vmin, vmax)
    fig, ax = plt.subplots(figsize=(7.5, 7.8))
    pc = PolyCollection(polis, array=vals, cmap=DIVERGENTE,
                        norm=TwoSlopeNorm(vmin=vmin, vcenter=0, vmax=vmax), edgecolor="none")
    ax.add_collection(pc)
    distritos = gpd.read_file(RAW_INSIDE / "neighbourhoods.geojson").dissolve(
        "neighbourhood_group")
    distritos.boundary.plot(ax=ax, color=TINTA, linewidth=0.6)
    for nome, geo in distritos.geometry.items():
        p = geo.representative_point()
        ax.text(p.x, p.y, nome, fontsize=8.5, color=TINTA, ha="center", va="center",
                fontweight="bold", alpha=0.85)
    ax.autoscale_view()
    ax.set_aspect(1 / np.cos(np.radians(40.7)))
    ax.axis("off")
    cb = fig.colorbar(pc, ax=ax, shrink=0.5, pad=0.01)
    cb.set_label(f"prêmio de localização (%) — escala de {vmin}% a +{vmax}%")
    cb.outline.set_visible(False)
    ax.set_title("Quanto o mesmo apartamento valeria em cada lugar")
    ax.text(0, 1.0, "apartamento inteiro, 2 hóspedes, 1 quarto, 30+ noites · modelo do "
            "simulador · célula H3 r9", transform=ax.transAxes, fontsize=8.5,
            color=TINTA_SUAVE)
    return _salvar(fig, "mapa_premio.png")


def main() -> None:
    tema()
    feitas = []
    p, c = _ler("_preco.json"), _ler("_comparativo.json")
    s, d = _ler("_sobrevivencia.json"), _ler("_deriva.json")
    if p:
        feitas += [escada(p), ablacao(p), shap_grupos(p), dependencia(p)]
    if c:
        feitas += [estratos(c), min30_distritos(c)]
    if s:
        feitas += [sobrevivencia(s), calibracao(s)]
    if d:
        feitas.append(deriva(d))
    m = mapa_premio()
    if m:
        feitas.append(m)
    print(f"{len(feitas)} figuras em {DESTINO.relative_to(DOCS.parent)}: {', '.join(feitas)}")


if __name__ == "__main__":
    main()
