"""Tabelas de resultado da documentacao, geradas dos `_*.json` do pipeline.

As paginas de docs/ incluem `_snippets/<tabela>.md` (pymdownx.snippets) em vez
de copiar numeros a mao: rodou o pipeline de novo, rode isto, e toda tabela
publicada acompanha. O texto corrido cita poucos numeros — e cada um tem de
bater com a tabela ao lado.
"""

from __future__ import annotations

import json

from airbnb import schema as S
from airbnb.config import DOCS, PROCESSED
from airbnb.produto import rotulos

DESTINO = DOCS / "_snippets"

NOMES_MODELO = {
    "B0": "B0 · mediana global",
    "B1": "B1 · mediana por bairro × tipo (v0)",
    "M1": "M1 · regressão linear hedônica",
    "M2": "M2 · LightGBM, só o imóvel",
    "M3": "M3 · + coordenadas e distrito",
    "M4": "M4 · + fontes externas",
    "M4_sem_coordenadas": "M4 sem coordenadas (só externas)",
    "M5": "**M5 · produto (simulador)**",
}


def _ler(nome: str) -> dict | None:
    p = PROCESSED / nome
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _pct(v, casas: int = 1, sinal: bool = False) -> str:
    if v is None:
        return "—"
    s = f"{100 * v:+.{casas}f}" if sinal else f"{100 * v:.{casas}f}"
    return s.replace(".", ",") + "%"


def _num(v, casas: int = 0, prefixo: str = "") -> str:
    if v is None:
        return "—"
    s = f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return prefixo + s


def _tabela(cab: list[str], linhas: list[list[str]], alinhar: str | None = None) -> str:
    alinhar = alinhar or "l" + "r" * (len(cab) - 1)
    sep = ["---:" if a == "r" else ":---:" if a == "c" else "---" for a in alinhar]
    out = ["| " + " | ".join(cab) + " |", "| " + " | ".join(sep) + " |"]
    out += ["| " + " | ".join(linha) + " |" for linha in linhas]
    return "\n".join(out) + "\n"


# --- preco ------------------------------------------------------------------------


def escada(p: dict) -> str:
    linhas = []
    for k, nome in NOMES_MODELO.items():
        m = p["metricas"].get(k)
        if not m:
            continue
        folds = m.get("mdape_folds", [])
        faixa = f"{_pct(min(folds))} – {_pct(max(folds))}" if folds else "—"
        linhas.append([nome, _pct(m["mdape"]), _num(m["mae_usd"], 1, "US$ "),
                       _num(m["r2_log"], 3), faixa])
    return _tabela(["modelo", "MdAPE", "MAE", "R² (log)", "MdAPE entre folds"], linhas)


def ablacao(p: dict) -> str:
    linhas = [[fonte, ", ".join(f"`{f}`" for f in a["features"]),
               f"{a['delta_mdape_pp']:+.2f}".replace(".", ",") + " p.p.",
               _num(a["delta_mae_usd"], 2, "US$ "), f"{a['folds_que_pioram']}/5"]
              for fonte, a in p["ablacao"].items()]
    return _tabela(["fonte retirada", "features", "Δ MdAPE", "Δ MAE", "folds que pioram"], linhas,
                   "llrrc")


def shap_grupos(p: dict) -> str:
    fr = p["shap_m4"]["fracao_por_grupo"]
    return _tabela(["grupo de features", "fração da contribuição (SHAP)"],
                   [[g, _pct(v)] for g, v in fr.items()])


def conformal(p: dict) -> str:
    c = p["conformal_produto"]
    g = c["global"]["honesta"]["por_grupo"]
    m = c["mondrian"]["cobertura_honesta_por_grupo"]
    linhas = [[rotulos.tipo(grupo), _num(c["mondrian"]["por_grupo"][grupo]["n"]),
               _pct(g[grupo]["cobertura"]), _pct(m[grupo])] for grupo in m]
    linhas.append(["**todos**", _num(sum(v["n"] for v in c["mondrian"]["por_grupo"].values())),
                   _pct(c["global"]["honesta"]["cobertura"]),
                   _pct(c["mondrian"]["cobertura_honesta"])])
    return _tabela(["tipo de acomodação", "n", "cobertura (intervalo global)",
                    "cobertura (Mondrian por tipo)"], linhas)


RECORTES = {S.COL_ROOM_TYPE: "tipo", S.COL_DISTRITO: "distrito", S.COL_MIN30: "mínimo de noites",
            "faixa_host": "anúncios do anfitrião", "recencia": "última avaliação"}


def _grupo(recorte: str, g: str) -> str:
    if recorte == S.COL_ROOM_TYPE:
        return rotulos.tipo(g)
    if recorte == S.COL_MIN30:
        return "30+ noites" if g in ("True", "1.0", "1") else "< 30 noites"
    return g


def produto_por_estrato(p: dict) -> str:
    linhas = []
    for col, grupos in p["produto_por_estrato"].items():
        for g, m in grupos.items():
            linhas.append([RECORTES.get(col, col), _grupo(col, g), _num(m["n"]),
                           _pct(m["mdape"]), _num(m["mae_usd"], 1, "US$ ")])
    return _tabela(["recorte", "grupo", "n", "MdAPE", "MAE"], linhas, "llrrr")


# --- comparativo -------------------------------------------------------------------


def kpis(c: dict) -> str:
    k19, k26 = c["kpis"]["2019"], c["kpis"]["2026"]
    itens = [("anúncios", "anuncios", "n"), ("anfitriões", "anfitrioes", "n"),
             ("anúncios com preço", "anuncios_com_preco", "n"),
             ("apartamento/casa inteira", "pct_inteiro", "%"),
             ("mínimo ≥ 30 noites", "pct_min30", "%"),
             ("de anfitrião com 2+ anúncios", "pct_host_multi", "%"),
             ("nas mãos do 1% maiores anfitriões", "pct_anuncios_top1pct_hosts", "%"),
             ("calendário 100% fechado (availability_365 = 0)", "pct_disponibilidade_zero", "%"),
             ("preço mediano nominal", "preco_mediano_nominal", "$"),
             (f"preço mediano real (US$ de {c['cpi']['para']})", "preco_mediano_real", "$")]
    fmt = {"n": lambda v: _num(v), "%": lambda v: _pct(v), "$": lambda v: _num(v, 0, "US$ ")}
    return _tabela(["indicador", "2019", "2026"],
                   [[r, fmt[t](k19[c_]), fmt[t](k26[c_])] for r, c_, t in itens])


def estratos(c: dict) -> str:
    linhas = []
    for e in c["preco_por_estrato"]:
        a, b = e["2019"], e["2026"]

        def fmt(x):
            if x["mediana"] is None:
                return "—"
            ic = x["ic95"]
            faixa = f" ({_num(ic[0], 0)}–{_num(ic[1], 0)})" if ic[0] is not None else ""
            return _num(x["mediana"], 0, "US$ ") + faixa
        var = e["variacao_real_pct"]
        linhas.append([e["estrato"], rotulos.tipo(e["tipo"]), _num(a["n"]), fmt(a),
                       _num(b["n"]), fmt(b), "—" if var is None else f"{var:+.0f}%"])
    return _tabela(["mínimo de noites", "tipo", "n 2019", "mediana real 2019 (IC 95%)",
                    "n 2026", "mediana 2026 (IC 95%)", "variação real"], linhas, "llrrrrr")


def decomposicao(c: dict) -> str:
    d = c["decomposicao"]

    def rotulo(e: str) -> str:
        estrato, tipo = e.split(" | ")
        return f"{estrato} · {rotulos.tipo(tipo)}"
    linhas = [[rotulo(e), _pct(v["peso_2019"]), _pct(v["peso_2026"]),
               f"{v['var_real_pct']:+.0f}%"] for e, v in d["estratos"].items()]
    corpo = _tabela(["estrato (mínimo de noites · tipo)", "peso 2019", "peso 2026",
                     "variação real no estrato"], linhas)
    def br(v: float, casas: int) -> str:
        return f"{v:+.{casas}f}".replace(".", ",")
    resumo = (f"\nVariação da média geométrica real: **{br(d['variacao_geometrica_pct'], 1)}%**, "
              f"sendo {br(d['composicao_log'], 3)} (log) de **composição** e "
              f"{br(d['dentro_do_estrato_log'], 3)} (log) de **preço dentro do estrato**.\n")
    return corpo + resumo


def distritos(c: dict) -> str:
    linhas = [[nome, _num(v["n_2019"]), _num(v["n_2026"]),
               "—" if v["var_n_pct"] is None else f"{v['var_n_pct']:+.0f}%",
               _num(v["preco_real_2019"], 0, "US$ "), _num(v["preco_2026"], 0, "US$ "),
               _pct(v["pct_min30_2019"], 0), _pct(v["pct_min30_2026"], 0)]
              for nome, v in c["por_distrito"].items()]
    return _tabela(["distrito", "anúncios 2019", "anúncios 2026", "variação",
                    "preço real 2019", "preço 2026", "30+ noites 2019", "30+ noites 2026"], linhas)


# --- espacial, sobrevivencia, deriva, ocupacao -----------------------------------


def moran(e: dict) -> str:
    rot = {"preco_2026": "preço mediano 2026", "preco_real_2019": "preço mediano real 2019",
           "premio_local_2026": "prêmio de localização 2026 (resíduo do M2)"}
    def p_txt(v: dict) -> str:
        piso = 2 / (v["permutacoes"] + 1)  # nenhuma permutacao tao extrema quanto o observado
        return f"≤ {_num(piso, 3)} (piso)" if v["p_bilateral"] <= piso + 1e-12 \
            else _num(v["p_bilateral"], 3)
    linhas = [[rot[k], _num(v["n_celulas"]), _num(v["I"], 3), _num(v["z_permutacao"], 1),
               p_txt(v)] for k, v in e["moran"].items()]
    return _tabela(["variável (célula H3 r8)", "células", "I de Moran", "z (permutação)",
                    "p bilateral"], linhas)


def variancia(e: dict) -> str:
    v = e["variancia_explicada"]
    linhas = [["distrito (5 grupos)", _pct(v["distrito_eta2"])],
              ["bairro (~220 grupos)", _pct(v["bairro_eta2"])],
              ["célula H3 r8", _pct(v["celula_r8_eta2"])],
              ["o imóvel, sem localização (M2, fora do fold)", _pct(v["imovel_M2_r2_fora_do_fold"])],
              ["imóvel + localização (M4, fora do fold)",
               _pct(v["imovel_mais_local_M4_r2_fora_do_fold"])]]
    return _tabela(["o que explica o log do preço", "variância explicada"], linhas)


def sobrevivencia_or(s: dict) -> str:
    lg = s["logistica"]
    linhas = [[f"`{k}`", _num(v["or"], 2), f"{_num(v['ic95'][0], 2)} – {_num(v['ic95'][1], 2)}",
               "< 0,001" if v["p"] < 0.001 else _num(v["p"], 3)]
              for k, v in lg["razoes_de_chance"].items()]
    return _tabela(["variável (2019)", "razão de chance", "IC 95% (agrupado por anfitrião)", "p"],
                   linhas)


def sobrevivencia_taxas(s: dict) -> str:
    linhas = []
    for recorte, grupos in s["taxas"].items():
        for g, v in grupos.items():
            linhas.append([RECORTES.get(recorte, recorte), _grupo(recorte, g), _num(v["n"]),
                           _pct(v["taxa"])])
    return _tabela(["recorte", "grupo", "anúncios 2019", "ainda no ar em 2026"], linhas, "llrr")


def deriva(d: dict) -> str:
    itens = [("2019 → 2019 (CV espacial)", "modelo_2019_cv_espacial_em_2019"),
             ("2026 → 2026 (CV espacial)", "modelo_2026_cv_espacial_em_2026"),
             ("**2019 → 2026**", "modelo_2019_aplicado_a_2026"),
             ("2026 → 2019", "modelo_2026_aplicado_a_2019")]
    return _tabela(["treino → teste", "MdAPE", "MAE (US$ de 2026)", "R² (log)"],
                   [[r, _pct(d[k]["mdape"]), _num(d[k]["mae_usd"], 1, "US$ "),
                     _num(d[k]["r2_log"], 3)] for r, k in itens])


def ocupacao(o: dict) -> str:
    n = o["noites_se_ativo"]
    return _tabela(["modelo (noites/ano, só anúncios ativos)", "MAE (noites)", "erro mediano",
                    "Spearman"],
                   [["baseline: mediana bairro × tipo × 30+ noites",
                     _num(n["baseline_bairro_tipo_min30"]["mae_noites"], 1),
                     _num(n["baseline_bairro_tipo_min30"]["mdae_noites"], 1),
                     _num(n["baseline_bairro_tipo_min30"]["spearman"], 3)],
                    ["LightGBM (entradas do simulador + localização)",
                     _num(n["modelo"]["mae_noites"], 1), _num(n["modelo"]["mdae_noites"], 1),
                     _num(n["modelo"]["spearman"], 3)]])


def criterios(p: dict | None, s: dict | None) -> str:
    """Os criterios de sucesso de docs/01 contra o resultado — sem ajuste de regua."""
    linhas = []
    if p:
        c = p["criterios"]
        n_folds = len(p["metricas"]["M4"]["mdape_folds"])
        melhora = c["C4_folds_em_que_externas_melhoram"]
        linhas += [
            ["C1 · MAE ≥ 15% menor que o baseline B1",
             f"{c['C1_mae_vs_b1_pct']:.1f}% menor".replace(".", ","),
             "✅" if c["C1_mae_vs_b1_pct"] >= 15 else "❌"],
            ["C2 · MdAPE do produto ≤ 30%", _pct(c["C2_mdape_produto"]),
             "✅" if c["C2_mdape_produto"] <= 0.30 else "❌"],
            ["C3 · cobertura honesta do intervalo de 80% entre 77% e 83%",
             _pct(c["C3_cobertura_mondrian"]),
             "✅" if 0.77 <= c["C3_cobertura_mondrian"] <= 0.83 else "❌"],
            ["C4 · fontes externas melhoram de forma consistente (M4 × M3, fold a fold)",
             f"melhora em {melhora}/{n_folds} folds; Δ MdAPE "
             + f"{c['C4_delta_mdape_pp']:+.2f}".replace(".", ",") + " p.p.",
             "✅" if melhora >= n_folds - 1 and c["C4_delta_mdape_pp"] < 0 else "❌"],
        ]
    if s:
        c5 = s["criterio_C5"]
        linhas.append(["C5 · sobrevivência: AUC ≥ 0,70 e Brier abaixo do baseline",
                       f"AUC {c5['auc']:.3f}".replace(".", ","), "✅" if c5["atende"] else "❌"])
    return _tabela(["critério (registrado antes da modelagem)", "resultado", ""], linhas, "lrc")


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    fontes = {n: _ler(f"_{n}.json") for n in
              ("preco", "comparativo", "espacial", "sobrevivencia", "deriva", "ocupacao")}
    geradores = {
        "tabela_escada": ("preco", escada), "tabela_ablacao": ("preco", ablacao),
        "tabela_shap_grupos": ("preco", shap_grupos), "tabela_conformal": ("preco", conformal),
        "tabela_produto_estratos": ("preco", produto_por_estrato),
        "tabela_kpis": ("comparativo", kpis), "tabela_estratos": ("comparativo", estratos),
        "tabela_decomposicao": ("comparativo", decomposicao),
        "tabela_distritos": ("comparativo", distritos),
        "tabela_moran": ("espacial", moran), "tabela_variancia": ("espacial", variancia),
        "tabela_sobrevivencia_or": ("sobrevivencia", sobrevivencia_or),
        "tabela_sobrevivencia_taxas": ("sobrevivencia", sobrevivencia_taxas),
        "tabela_deriva": ("deriva", deriva), "tabela_ocupacao": ("ocupacao", ocupacao),
    }
    for nome, (fonte, f) in geradores.items():
        dado = fontes[fonte]
        texto = f(dado) if dado else f"*resultado ainda não gerado (`_{fonte}.json`)*\n"
        (DESTINO / f"{nome}.md").write_text(texto, encoding="utf-8")
    (DESTINO / "tabela_criterios.md").write_text(
        criterios(fontes["preco"], fontes["sobrevivencia"]), encoding="utf-8")
    print(f"{len(geradores) + 1} tabelas gravadas em {DESTINO.relative_to(DOCS.parent)}")


if __name__ == "__main__":
    main()
