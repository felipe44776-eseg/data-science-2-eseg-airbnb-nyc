"""Exporta os dados do site publico (site/data/) a partir dos resultados do pipeline.

Contrato: docs/09-implantacao.md. O site so le JSON/GeoJSON daqui — nenhum
numero e calculado a mao no navegador alem de avaliar o modelo exportado.

Invariante 9: nada pessoal sai daqui. Os anuncios vao sem id, sem titulo, sem
anfitriao, com a coordenada (ja deslocada pelo Airbnb) arredondada a 4 casas.
Invariante 10: o modelo exportado e conferido contra o LightGBM em Python
(`verificar_export`) e os casos de paridade sao gravados para o Node conferir o
MESMO avaliador que a pagina usa.
"""

from __future__ import annotations

import json
from datetime import date

import geopandas as gpd
import h3
import numpy as np
import pandas as pd

from airbnb import schema as S
from airbnb.config import (
    COBERTURA_ALVO,
    DISTRITOS,
    PROCESSED,
    RAW_INSIDE,
    SITE_DADOS,
    SNAPSHOT_2019,
    SNAPSHOT_ATUAL,
)
from airbnb.external import metro
from airbnb.models import especificacao as E
from airbnb.models.ocupacao import ATIVO, PARAMS_NOITES, TETO_NOITES
from airbnb.models.preco import PARAMS_PRODUTO
from airbnb.models.validacao import treinar_final
from airbnb.produto import autoria, rotulos
from airbnb.produto.modelo_js import exportar_modelo, gerar_casos_paridade, verificar_export

CASAS_COORD = 4


def _ler(nome: str) -> dict:
    return json.loads((PROCESSED / nome).read_text(encoding="utf-8"))


def _escrever(obj, nome: str) -> None:
    """JSON estrito e compacto: NaN vira null (o JSON.parse do navegador rejeita NaN)."""
    def limpar(v):
        if isinstance(v, float) and not np.isfinite(v):
            return None
        if isinstance(v, dict):
            return {k: limpar(x) for k, x in v.items()}
        if isinstance(v, list | tuple):
            return [limpar(x) for x in v]
        if isinstance(v, np.generic):
            return limpar(v.item())
        return v
    texto = json.dumps(limpar(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    (SITE_DADOS / nome).write_text(texto, encoding="utf-8")
    print(f"  {nome:<34} {len(texto.encode('utf-8')) / 1024:8.1f} KB")


def _r(v, casas: int = 1):
    return None if v is None or not np.isfinite(v) else round(float(v), casas)


# --- entradas do simulador -----------------------------------------------------


def entradas_usuario() -> list[dict]:
    """O formulario do simulador — o site constroi os campos a partir disto."""
    return [
        {"chave": E.TIPO_QUARTO_COD, "rotulo": "Tipo de acomodação", "tipo": "categoria",
         "opcoes": [{"valor": i, "rotulo": rotulos.tipo(t)} for i, t in enumerate(S.ROOM_TYPES)],
         "padrao": 0},
        {"chave": "accommodates", "rotulo": "Hóspedes", "tipo": "inteiro", "min": 1, "max": 16,
         "passo": 1, "padrao": 2},
        {"chave": "bedrooms", "rotulo": "Quartos", "tipo": "inteiro", "min": 0, "max": 8,
         "passo": 1, "padrao": 1, "ajuda": "0 = estúdio"},
        {"chave": "beds", "rotulo": "Camas", "tipo": "inteiro", "min": 1, "max": 12, "passo": 1,
         "padrao": 1},
        {"chave": S.COL_BANHEIROS, "rotulo": "Banheiros", "tipo": "decimal", "min": 0, "max": 6,
         "passo": 0.5, "padrao": 1},
        {"chave": S.COL_BANHEIRO_COMPARTILHADO, "rotulo": "Banheiro compartilhado",
         "tipo": "booleano", "padrao": 0},
        {"chave": S.COL_MIN30, "rotulo": "Mínimo de 30 noites", "tipo": "booleano", "padrao": 1,
         "ajuda": "Desde a Local Law 18 (set/2023), estadia menor que 30 noites exige registro "
                  "na Prefeitura — 8 em cada 10 anúncios hoje pedem 30+ noites."},
        {"chave": S.COL_HOST_SUPERHOST, "rotulo": "Superhost", "tipo": "booleano", "padrao": 0},
        {"chave": "review_scores_rating", "rotulo": "Nota média (0 a 5)", "tipo": "decimal",
         "min": 0, "max": 5, "passo": 0.1, "padrao": None,
         "ajuda": "Deixe em branco para um anúncio novo, ainda sem avaliação."},
    ]


# --- modelos -----------------------------------------------------------------------


def exportar_modelos(d26: pd.DataFrame, res_preco: dict, res_ocup: dict) -> dict:
    cols = E.produto()
    comum = {"entradas_usuario": entradas_usuario(),
             "features_local": E.features_local_produto(), "features_ponto": [],
             "rotulos": {f: rotulos.FEATURE_PT.get(f, f) for f in cols}}

    base = d26[d26[E.PRECO_VALIDO]]
    y = np.log(base[E.PRECO].to_numpy(dtype=float))
    booster = treinar_final(base[cols], y, res_preco["M5_n_arvores_final"], params=PARAMS_PRODUTO)
    conf = res_preco["conformal_produto"]
    grupos = {str(S.ROOM_TYPES.index(k)): {"q_inf": v["q_inf"], "q_sup": v["q_sup"]}
              for k, v in conf["mondrian"]["por_grupo"].items()}
    m5 = res_preco["metricas"]["M5"]
    modelo = exportar_modelo(
        booster, SITE_DADOS / "modelo_preco.json", features=cols, transformacao="exp",
        extras={**comum,
                "alvo": "preço por noite (US$), cotação do snapshot " + SNAPSHOT_ATUAL,
                "intervalo": {"nivel": COBERTURA_ALVO, "q_inf": conf["global"]["q_inf"],
                              "q_sup": conf["global"]["q_sup"]},
                "intervalo_por_grupo": {"chave": E.TIPO_QUARTO_COD, "grupos": grupos},
                "metricas": {"mdape": m5["mdape"], "mae_usd": m5["mae_usd"],
                             "r2_log": m5["r2_log"],
                             "cobertura_honesta": conf["mondrian"]["cobertura_honesta"],
                             "validacao": "CV espacial por bloco H3 r6 (5 folds)"}})
    ver = verificar_export(booster, modelo, base[cols])
    if not ver["aprovado"]:
        raise SystemExit(f"export do modelo de preco diverge do LightGBM: {ver}")
    gerar_casos_paridade(booster, base[cols], SITE_DADOS / "_casos_paridade_preco.json",
                         modelo=modelo)

    ativos = base[base[ATIVO] == 1] if ATIVO in base else \
        base[base[S.COL_N_AVALIACOES_LTM] > 0]
    yo = np.log(ativos[E.OCUPACAO].to_numpy(dtype=float))
    b_oc = treinar_final(ativos[cols], yo, res_ocup["noites_se_ativo"]["n_arvores_final"],
                         params=PARAMS_NOITES)
    mo = exportar_modelo(
        b_oc, SITE_DADOS / "modelo_ocupacao.json", features=cols, transformacao="exp",
        extras={**comum, "alvo": "noites ocupadas por ano, se o anúncio estiver ativo",
                "teto": TETO_NOITES,
                "metricas": {k: res_ocup["noites_se_ativo"]["modelo"][k]
                             for k in ("mae_noites", "mdae_noites", "spearman")}})
    ver_o = verificar_export(b_oc, mo, ativos[cols])
    if not ver_o["aprovado"]:
        raise SystemExit(f"export do modelo de ocupacao diverge do LightGBM: {ver_o}")
    gerar_casos_paridade(b_oc, ativos[cols], SITE_DADOS / "_casos_paridade_ocupacao.json",
                         modelo=mo)
    return {"preco": booster, "verificacao_preco": ver, "verificacao_ocupacao": ver_o}


# --- celulas ------------------------------------------------------------------------


def celulas_r9(celulas: pd.DataFrame, booster) -> tuple[dict, pd.Series]:
    """Features de localizacao por r9 (ordem do modelo) + premio de localizacao modelado.

    Premio = previsao para um imovel de referencia (o mais comum de 2026: apartamento
    inteiro, 2 hospedes, 1 quarto, 1 cama, 1 banheiro, 30+ noites) nesta celula,
    dividida pela mediana dessa previsao entre as celulas com anuncio. A celula de
    referencia do simulador e a que fica mais perto dessa mediana.
    """
    feats = E.features_da_celula(celulas, "atual")
    local = E.features_local_produto()
    tab = feats.reindex(columns=local)
    tab[E.DISTRITO_COD] = pd.Categorical(
        celulas.set_index(S.COL_H3_R9).loc[tab.index, E.DISTRITO_CELULA],
        categories=list(DISTRITOS)).codes
    ref = {E.TIPO_QUARTO_COD: 0, "accommodates": 2, "bedrooms": 1, "beds": 1,
           S.COL_BANHEIROS: 1.0, S.COL_BANHEIRO_COMPARTILHADO: 0, S.COL_MIN30: 1,
           S.COL_HOST_SUPERHOST: 0, "review_scores_rating": np.nan}
    X = pd.DataFrame({**{k: np.full(len(tab), v, dtype=float) for k, v in ref.items()},
                      **{c: tab[c].to_numpy(dtype=float) for c in local}}, index=tab.index)
    pred = pd.Series(np.exp(booster.predict(X[E.produto()])), index=tab.index)
    return tab, pred


def main() -> None:
    SITE_DADOS.mkdir(parents=True, exist_ok=True)
    comp, preco = _ler("_comparativo.json"), _ler("_preco.json")
    ocup, sobr, esp = _ler("_ocupacao.json"), _ler("_sobrevivencia.json"), _ler("_espacial.json")
    deriva = _ler("_deriva.json")
    d26 = pd.read_parquet(PROCESSED / "modelagem_2026.parquet")
    d26[ATIVO] = (d26[S.COL_N_AVALIACOES_LTM] > 0).astype(float)
    celulas = pd.read_parquet(PROCESSED / "celulas_r9.parquet")

    print("exportando site/data/:")
    modelos = exportar_modelos(d26, preco, ocup)

    # --- celulas r9 (simulador) e premio modelado
    tab9, pred_ref = celulas_r9(celulas, modelos["preco"])
    com_anuncio = set(d26[E.CELULA].dropna())
    mediana = float(pred_ref[pred_ref.index.isin(com_anuncio)].median())
    referencia = (pred_ref[pred_ref.index.isin(com_anuncio)] - mediana).abs().idxmin()
    _escrever({"colunas": list(tab9.columns),
               "celulas": {h: [_r(v, 5) for v in linha] for h, linha in
                           zip(tab9.index, tab9.to_numpy(dtype=float), strict=True)},
               "referencia": referencia,
               "preco_referencia_mediana": _r(mediana, 2)}, "celulas_r9.json")
    # o mesmo premio, por r9, para a figura da documentacao (mais fina que o mapa r8)
    pd.DataFrame({S.COL_H3_R9: pred_ref.index,
                  "premio_modelo_pct": 100 * (pred_ref.to_numpy() / mediana - 1)}).to_parquet(
        PROCESSED / "premio_r9.parquet", index=False)

    # --- celulas r8 (mapa): comparativo + sobrevivencia + espacial + deriva + externas
    r8 = pd.read_parquet(PROCESSED / "comparativo_r8.parquet").set_index(S.COL_H3_R8)
    for nome in ("sobrevivencia_r8", "espacial_r8", "deriva_r8"):
        extra = pd.read_parquet(PROCESSED / f"{nome}.parquet").set_index(S.COL_H3_R8)
        r8 = r8.join(extra.drop(columns=[c for c in extra.columns if c in r8.columns]), how="outer")
    premio = np.log(pred_ref / mediana).groupby(lambda h: h3.cell_to_parent(h, 8)).mean()
    r8["premio_modelo_pct"] = 100 * (np.exp(premio) - 1)
    ativos = d26[(d26[ATIVO] == 1) & d26[E.PRECO_VALIDO]]
    g = ativos.groupby(S.COL_H3_R8)
    r8["ocupacao_mediana"] = g[E.OCUPACAO].median().where(g.size() >= 5)
    r8["receita_mediana"] = g[S.COL_RECEITA_L365D].median().where(g.size() >= 5)
    externas_r8 = tab9.groupby(lambda h: h3.cell_to_parent(h, 8)).mean()
    for chave, col in METRICAS_EXTERNAS.items():
        if col in externas_r8:
            r8[chave] = externas_r8[col]
    if E.LL18_CELULA in celulas:
        r8["ll18_registros_km2"] = celulas.groupby(S.COL_H3_R8)[E.LL18_CELULA].mean()
    # Airbnb x aluguel: receita mediana de apartamentos inteiros ativos / (ZORI x 12)
    inteiros = ativos[ativos[E.TIPO_QUARTO_COD] == 0]
    gi = inteiros.groupby(S.COL_H3_R8)
    receita_inteiro = gi[S.COL_RECEITA_L365D].median().where(gi.size() >= 5)
    r8["airbnb_vs_aluguel_pct"] = 100 * (receita_inteiro / (12 * externas_r8[E.ZORI]) - 1)
    geo = celulas.groupby(S.COL_H3_R8)[[E.BAIRRO_CELULA, E.DISTRITO_CELULA]].agg(
        lambda s: s.mode().iat[0] if len(s.mode()) else None)
    r8 = r8.join(geo.set_axis(["bairro", "distrito"], axis=1), how="left")
    r8 = r8[r8.index.isin(externas_r8.index) | r8["n_2026"].fillna(0).gt(0)]
    chaves = [m["chave"] for m in metricas_celula()]
    colunas = ["h3", "bairro", "distrito", *chaves]
    linhas = []
    for h, row in r8.iterrows():
        linha = [h, row.get("bairro"), row.get("distrito")]
        for k in chaves:
            v = row.get(k)
            linha.append(v if isinstance(v, str) else _r(v, 2) if v is not None else None)
        linhas.append(linha)
    _escrever({"colunas": colunas, "linhas": linhas}, "celulas_r8.json")

    # --- anuncios (pontos): sem id, sem titulo, sem anfitriao (invariante 9)
    oof = pd.read_parquet(PROCESSED / "preco_oof.parquet")[[E.ID, "oof_M5"]]
    pts = d26.merge(oof, on=E.ID, how="left")
    _escrever({
        "colunas": ["lat", "lon", "tipo", "preco", "previsto", "bairro"],
        "tipos": list(S.ROOM_TYPES),
        "linhas": [[_r(a, CASAS_COORD), _r(b, CASAS_COORD), int(t),
                    _r(p, 2) if ok else None, _r(np.exp(o), 2) if np.isfinite(o) else None, nb]
                   for a, b, t, p, ok, o, nb in zip(
                       pts[S.COL_LAT], pts[S.COL_LON], pts[E.TIPO_QUARTO_COD], pts[E.PRECO],
                       pts[E.PRECO_VALIDO], pts["oof_M5"].fillna(np.nan), pts[E.BAIRRO],
                       strict=True)],
    }, "anuncios_2026.json")

    # --- geometrias
    bairros = gpd.read_file(RAW_INSIDE / "neighbourhoods.geojson")
    bairros["geometry"] = bairros.geometry.simplify(0.0003, preserve_topology=True)
    bairros = bairros.rename(columns={"neighbourhood": "bairro",
                                      "neighbourhood_group": "distrito"})[
        ["bairro", "distrito", "geometry"]]
    (SITE_DADOS / "bairros.geojson").write_text(
        bairros.to_json(drop_id=True, to_wgs84=True).replace(
            ", ", ","), encoding="utf-8")
    print(f"  {'bairros.geojson':<34} {(SITE_DADOS / 'bairros.geojson').stat().st_size / 1024:8.1f} KB")
    # um ponto por complexo de estacao (Times Sq-42 St tem 4 plataformas, 1 lugar)
    est = metro.carregar()
    complexos = est.groupby("complex_id").agg(
        nome=("stop_name", "first"), lat=("lat", "mean"), lon=("lon", "mean"),
        linhas=("daytime_routes", lambda s: " ".join(sorted(metro.linhas_de(s)))))
    (SITE_DADOS / "metro.geojson").write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {"nome": r.nome, "linhas": r.linhas},
                      "geometry": {"type": "Point", "coordinates": [_r(r.lon, 5), _r(r.lat, 5)]}}
                     for r in complexos.itertuples(index=False)]},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  {'metro.geojson':<34} {len(complexos):>5} complexos")

    # --- resumo
    k = comp["kpis"]
    b1, m5 = preco["metricas"]["B1"], preco["metricas"]["M5"]
    _escrever({
        "gerado_em": date.today().isoformat(),
        "snapshots": {"2019": SNAPSHOT_2019, "2026": SNAPSHOT_ATUAL},
        "equipe": autoria.equipe_json(),
        "credito": autoria.CREDITO,
        "repositorio": autoria.REPOSITORIO,
        "kpis": {s: {**{c: k[s][c] for c in ("anuncios", "preco_mediano_real", "pct_min30",
                                            "pct_inteiro", "pct_host_multi")},
                     "precos_por_estadia": {"curta": k[s]["preco_mediano_real_curta"],
                                            "longa": k[s]["preco_mediano_real_longa"]}}
                 for s in k},
        "sobrevivencia": {"n": int(sum(v["n"] * v["taxa"] for v in
                                       sobr["taxas"][E.DISTRITO].values())),
                          "pct": sobr["lightgbm"]["prevalencia"],
                          "auc": sobr["lightgbm"]["auc"]},
        "modelo_preco": {"mae_usd": m5["mae_usd"], "mdape": m5["mdape"], "r2_log": m5["r2_log"],
                         "cobertura_80": preco["conformal_produto"]["mondrian"]["cobertura_honesta"],
                         "melhora_vs_baseline_pct": 100 * (1 - m5["mae_usd"] / b1["mae_usd"])},
        "cpi": comp["cpi"],
        "moran_premio_local": esp["moran"]["premio_local_2026"]["I"],
        "deriva_mdape_pp": deriva["deriva_mdape_pp"],
        "metricas_celula": metricas_celula(),
        "atribuicoes": ATRIBUICOES,
    }, "resumo.json")


#: metrica do mapa -> feature de celula r9 (media das r9 da r8)
METRICAS_EXTERNAS = {
    "renda_mediana": "acs_renda_mediana",
    "crimes_graves_km2": "crime_graves_km2",
    "metro_dist_m": "metro_dist_m",
}


def metricas_celula() -> list[dict]:
    """O seletor de metrica do mapa e construido a partir desta lista."""
    return [
        {"chave": "n_2026", "rotulo": "Anúncios em 2026", "tipo": "sequencial",
         "unidade": "anúncios", "descricao": "Quantos anúncios há em cada hexágono.",
         "como": "Contagem dos anúncios do Inside Airbnb de 2026-06-14 por célula H3 r8 (~0,7 km²)."},
        {"chave": "var_n_pct", "rotulo": "Variação de anúncios 2019 → 2026", "tipo": "divergente",
         "unidade": "%", "descricao": "Quanto o número de anúncios mudou desde 2019.",
         "como": "(anúncios 2026 ÷ anúncios 2019 − 1). Só células com 5+ anúncios em 2019."},
        {"chave": "preco_2026", "rotulo": "Diária mediana, sem desconto (2026)",
         "tipo": "sequencial", "unidade": "US$",
         "descricao": "Metade dos anúncios cobra menos, metade mais.",
         "como": "Mediana da diária anunciada SEM desconto (preco_cheio): a mesma definição do "
                 "preço de 2019, para que as duas safras sejam comparáveis. A cotação que o "
                 "hóspede paga em 2026 vem com desconto mensal — 4,4% na mediana da estadia "
                 "de 30+ noites. Só células com 5+ anúncios com preço."},
        {"chave": "var_preco_real_pct", "rotulo": "Variação da diária mediana (real)",
         "tipo": "divergente", "unidade": "%",
         "descricao": "Diária de 2026 contra a de 2019, corrigida pela inflação de NYC e na mesma "
                      "definição (sem desconto).",
         "como": "Mediana 2026 ÷ (mediana 2019 × CPI-U NY) − 1. Corrige inflação e desconto, mas "
                 "ainda mistura composição (muito mais anúncios de 30+ noites hoje) — ver a "
                 "valorização ajustada."},
        {"chave": "valorizacao_ajustada_pct",
         "rotulo": "Valorização ajustada, estadia de 30+ noites",
         "tipo": "divergente", "unidade": "%",
         "descricao": "Quanto a área cobra acima do que o mercado de 2019 previa para os mesmos "
                      "anúncios — só no regime de estadia longa, que é 82% do mercado atual.",
         "como": "Média de log(preço 2026) − log(previsão do modelo treinado em 2019, em dólar "
                 "constante), calculada DENTRO do estrato de 30+ noites. Sem estratificar, a "
                 "métrica mediria onde a estadia curta sobreviveu (correlação de 0,47 com a "
                 "fração de curta na célula) em vez de valorização; estratificada, essa "
                 "correlação cai para −0,02."},
        {"chave": "pct_min30_2026", "rotulo": "Anúncios com mínimo de 30 noites (2026)",
         "tipo": "sequencial", "unidade": "fração",
         "descricao": "Efeito da Local Law 18: estadia curta passou a exigir registro.",
         "como": "Fração dos anúncios da célula com minimum_nights ≥ 30."},
        {"chave": "sobrevivencia", "rotulo": "Anúncios de 2019 ainda no ar", "tipo": "sequencial",
         "unidade": "fração", "descricao": "Dos anúncios de 2019 nesta área, quantos existem em 2026.",
         "como": "Mesmo id de anúncio no snapshot atual. Só células com 5+ anúncios em 2019."},
        {"chave": "premio_modelo_pct", "rotulo": "Prêmio de localização (modelo)",
         "tipo": "divergente", "unidade": "%",
         "descricao": "Quanto o mesmo apartamento valeria aqui, contra a mediana da cidade.",
         "como": "Previsão do modelo para um apartamento inteiro de referência (2 hóspedes, 1 quarto, "
                 "30+ noites) nesta área ÷ mediana dessa previsão na cidade − 1."},
        {"chave": "lisa_premio", "rotulo": "Aglomerados de preço (LISA)", "tipo": "categorica",
         "unidade": "", "descricao": "Onde anúncios caros (ou baratos) se concentram, além do acaso.",
         "como": "Moran local sobre o prêmio de localização observado (resíduo de um modelo que só "
                 "vê o imóvel), 999 permutações, correção FDR a 5%.",
         "categorias": ["Alto-Alto", "Baixo-Baixo", "Alto-Baixo", "Baixo-Alto", "não significativo"]},
        {"chave": "receita_mediana", "rotulo": "Receita anual mediana (anúncios ativos)",
         "tipo": "sequencial", "unidade": "US$",
         "descricao": "Faturamento estimado de quem teve hóspedes no último ano.",
         "como": "estimated_revenue_l365d do Inside Airbnb (preço × noites estimadas), mediana dos "
                 "anúncios com avaliação nos últimos 12 meses."},
        {"chave": "airbnb_vs_aluguel_pct", "rotulo": "Airbnb × aluguel de longo prazo",
         "tipo": "divergente", "unidade": "%",
         "descricao": "Quanto um apartamento inteiro ativo fatura no Airbnb contra um ano de "
                      "aluguel tradicional na mesma área.",
         "como": "Receita anual mediana (estimated_revenue_l365d) dos apartamentos inteiros com "
                 "hóspede no ano ÷ (Zillow ZORI do CEP × 12) − 1. Receita bruta: sem taxas, "
                 "limpeza nem vacância. Só células com 5+ anúncios e ZORI disponível."},
        {"chave": "renda_mediana", "rotulo": "Renda domiciliar mediana (Census)",
         "tipo": "sequencial", "unidade": "US$",
         "descricao": "Renda do entorno, pelo American Community Survey.",
         "como": "ACS 5 anos, setor censitário do centro de cada célula, média na área."},
        {"chave": "crimes_graves_km2", "rotulo": "Crimes graves registrados por km²",
         "tipo": "sequencial", "unidade": "por km²",
         "descricao": "Queixas de crimes graves (felony) ao NYPD nos 12 meses antes do snapshot.",
         "como": "NYPD Complaint Data, suavizado no anel de células vizinhas. Crime registrado não é "
                 "crime ocorrido: depende de denúncia e policiamento."},
        {"chave": "metro_dist_m", "rotulo": "Distância ao metrô", "tipo": "sequencial",
         "unidade": "m", "descricao": "Da célula até a estação de metrô mais próxima.",
         "como": "Distância em linha reta (UTM 18N) do centroide à estação da MTA mais próxima."},
        {"chave": "ll18_registros_km2", "rotulo": "Registros de curta temporada (Local Law 18)",
         "tipo": "sequencial", "unidade": "por km²",
         "descricao": "Anfitriões registrados na Prefeitura para estadias de menos de 30 noites.",
         "como": "Registros ativos no relatório anual FY26 da Office of Special Enforcement, por "
                 "distrito do Conselho Municipal, divididos pela área de terra do distrito."},
    ]


ATRIBUICOES = [
    {"fonte": "Inside Airbnb", "texto": "Dados de anúncios © Inside Airbnb, CC BY 4.0",
     "url": "https://insideairbnb.com/"},
    {"fonte": "Kaggle", "texto": "New York City Airbnb Open Data (dgomonov), CC0",
     "url": "https://www.kaggle.com/datasets/dgomonov/new-york-city-airbnb-open-data"},
    {"fonte": "OpenStreetMap", "texto": "© colaboradores do OpenStreetMap, ODbL",
     "url": "https://www.openstreetmap.org/copyright"},
    {"fonte": "US Census Bureau", "texto": "American Community Survey 5 anos",
     "url": "https://www.census.gov/programs-surveys/acs"},
    {"fonte": "NYC Open Data", "texto": "NYPD Complaint Data e 311 Service Requests",
     "url": "https://opendata.cityofnewyork.us/"},
    {"fonte": "MTA", "texto": "MTA Subway Stations (data.ny.gov)",
     "url": "https://data.ny.gov/"},
    {"fonte": "Zillow", "texto": "Zillow Observed Rent Index (ZORI)",
     "url": "https://www.zillow.com/research/data/"},
    {"fonte": "BLS / FRED", "texto": "CPI-U New York-Newark-Jersey City (CUURS12ASA0)",
     "url": "https://www.bls.gov/cpi/"},
    {"fonte": "NYC OSE", "texto": "Relatórios anuais da Local Law 18 (Office of Special "
     "Enforcement); distritos do Conselho: NYC DCP",
     "url": "https://www.nyc.gov/site/specialenforcement/"},
    {"fonte": "OpenFreeMap", "texto": "Mapa-base OpenFreeMap © OpenMapTiles, dados OSM",
     "url": "https://openfreemap.org/"},
]


if __name__ == "__main__":
    main()
