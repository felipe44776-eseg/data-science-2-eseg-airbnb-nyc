"""Produto — exporta um LightGBM para rodar no navegador, com paridade verificada.

Por que o modelo roda no navegador
----------------------------------
O site e estatico (GitHub Pages): nao ha servidor para chamar `booster.predict`.
Um GBDT e uma soma de arvores; percorrer uma arvore e uma sequencia de
comparacoes `x[f] <= limiar`. Isso se reimplementa em JavaScript e da o MESMO
numero do LightGBM — nao uma aproximacao — desde que a semantica de valor
ausente e de split categorico seja reproduzida a risca. Quem garante isso e
`tests/paridade_js.mjs` (invariante 10), com os casos gerados aqui.

Semantica reproduzida (LightGBM 4.x, `include/LightGBM/tree.h`)
---------------------------------------------------------------
0. Montagem da linha: |x| <= 1e-35f (`kZeroThreshold`) vira 0.0 — o LightGBM
   descarta esses "zeros" ao montar a linha densa de predicao.
1. Split numerico (`decision_type` "<="), conforme o `missing_type` do no:
     "None"  NaN vira 0.0 e compara normalmente;
     "Zero"  NaN vira 0.0; zero segue `default_left`; o resto compara;
     "NaN"   NaN segue `default_left`; zero compara normalmente.
2. Split categorico (`decision_type` "==", limiar "a||b||c"): NaN ou negativo
   vai para a direita; senao trunca para inteiro e vai para a esquerda se a
   categoria esta no conjunto.
3. Escore bruto = soma das folhas, arvore a arvore, na ordem, + `init_score`.
4. Predicao = transformacao(escore bruto): "identidade", "exp", "expm1" ou
   "sigmoide" (esta com a escala `sigmoid:k` do objetivo `binary`).

Formato do JSON ("lightgbm-js/1")
---------------------------------
    {
      "formato": "lightgbm-js/1", "lightgbm": "4.7.0", "objetivo": "regression",
      "features": [nomes, na ordem do modelo],
      "transformacao": "expm1", "sigmoide": 1.0 (so em "sigmoide"),
      "init_score": 0.0, "n_arvores": 300,
      "codigos": {"ausente": ["None", "Zero", "NaN"], "decisao": ["<=", "=="]},
      "arvores": [{
        "feature": [...],          indice da feature de cada no interno
        "limiar": [...],           numero ("<=") ou texto "a||b||c" ("==")
        "esquerda": [...],         filho: >= 0 no interno; < 0 folha ~filho
        "direita": [...],
        "padrao_esquerda": [...],  0/1 — default_left
        "ausente": [...],          0 None · 1 Zero · 2 NaN — missing_type
        "decisao": [...],          0 "<=" · 1 "==" — decision_type
        "folhas": [...]            leaf_value, na ordem do indice da folha
      }, ...],
      ...extras (entradas_usuario, features_local, intervalo, ...) no topo
    }

Os indices de no e de folha sao os internos do LightGBM (`split_index`,
`leaf_index`): o JSON e a mesma estrutura de arrays da `Tree` em C++. Numeros
saem com `repr` (ida e volta exata de float64) — sem arredondar nada.

Extras que o simulador do site le (todos opcionais, validados aqui):
    entradas_usuario     campos do formulario [{chave, rotulo, tipo, padrao, ...}]
    features_local       features que vem da celula r9 (colunas de celulas_r9.json)
    features_ponto       features que recebem o centro da celula r9 ([] ou ausente)
    features_fixas       {feature: valor|null} fixos no simulador
    intervalo            {nivel, q_inf, q_sup} — residuos na escala do escore bruto
    intervalo_por_grupo  {chave, grupos: {"0": {q_inf, q_sup}, ...}} — usado no
                         lugar do global quando o valor da chave tem grupo
    chave_tipo           entrada categorica cujos codigos indexam anuncios_2026 "tipos"
    teto                 limite superior da previsao (ex.: 255 noites/ano)
Toda feature do modelo tem de ter origem (entrada, local, ponto ou fixa).

Uso (na exportacao do site):
    modelo = exportar_modelo(booster, SITE_DADOS / "modelo_preco.json",
                             features=FEATURES, transformacao="expm1",
                             extras={"entradas_usuario": [...], ...})
    gerar_casos_paridade(booster, X_teste, SITE_DADOS / "_casos_paridade_preco.json",
                         modelo=modelo)
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

FORMATO = "lightgbm-js/1"
FORMATO_CASOS = "lightgbm-js-casos/1"

TRANSFORMACOES = ("identidade", "exp", "expm1", "sigmoide")

#: `kZeroThreshold` do LightGBM e um float32 (1e-35f), comparado em double.
LIMIAR_ZERO = float(np.float32(1e-35))

AUSENTE = ("None", "Zero", "NaN")  # MissingType do LightGBM, na ordem do enum
DECISAO = ("<=", "==")

#: Tolerancia da paridade no escore bruto. A soma e das MESMAS folhas na MESMA
#: ordem, em IEEE 754 double: o esperado e erro zero; 1e-9 so absorve ruido.
TOLERANCIA_BRUTO = 1e-9

#: Conversao que o proprio LightGBM aplica em `predict()` por objetivo (primeiro
#: token de `dump_model()["objective"]`). Fora desta lista: nao suportado.
_NATIVA = {
    "regression": "identidade",
    "regression_l1": "identidade",
    "huber": "identidade",
    "fair": "identidade",
    "quantile": "identidade",
    "mape": "identidade",
    "poisson": "exp",
    "gamma": "exp",
    "tweedie": "exp",
    "binary": "sigmoide",
    "cross_entropy": "sigmoide",
}

#: Transformacao declarada que e coerente com cada conversao nativa. Regressao
#: comum aceita "exp"/"expm1" porque o alvo pode ter sido treinado em log/log1p;
#: poisson/tweedie/gamma ja devolvem exp(bruto) — declarar "expm1" ali seria erro.
_COMPATIVEIS = {
    "identidade": ("identidade", "exp", "expm1"),
    "exp": ("exp",),
    "sigmoide": ("sigmoide",),
}

#: Chaves que o exportador escreve; `extras` nao pode sobrescreve-las.
_RESERVADAS = frozenset({
    "formato", "gerado_por", "lightgbm", "objetivo", "features", "transformacao",
    "sigmoide", "init_score", "n_arvores", "codigos", "arvores",
})

_TIPOS_ENTRADA = ("inteiro", "decimal", "booleano", "categoria")


# --------------------------------------------------------------------------
# exportacao
# --------------------------------------------------------------------------

def _objetivo(dump: dict) -> tuple[str, str, float]:
    """(texto do objetivo, conversao nativa, escala da sigmoide)."""
    texto = str(dump.get("objective", "")).strip()
    tokens = texto.split()
    nome = tokens[0] if tokens else ""
    if nome not in _NATIVA:
        raise NotImplementedError(
            f"objetivo {texto!r} nao suportado pelo avaliador JS "
            f"(suportados: {', '.join(sorted(_NATIVA))})")
    if "sqrt" in tokens[1:]:
        raise NotImplementedError("regression com reg_sqrt=True nao e suportado")
    escala = 1.0
    for t in tokens[1:]:
        if t.startswith("sigmoid:"):
            escala = float(t.split(":", 1)[1])
    return texto, _NATIVA[nome], escala


def _conferir_features(booster, features: Sequence[str]) -> list[str]:
    """A ordem declarada tem de ser a do modelo — trocar duas colunas nao da erro,
    da previsao errada. Nome automatico (`Column_i`, treino sem nomes) aceita os
    nomes do chamador, desde que a quantidade bata."""
    features = [str(f) for f in features]
    nomes = list(booster.feature_name())
    if len(features) != len(nomes):
        raise ValueError(f"features: {len(features)} nomes para um modelo com {len(nomes)}")
    automaticos = all(n == f"Column_{i}" for i, n in enumerate(nomes))
    if not automaticos and features != nomes:
        dif = [(i, a, b) for i, (a, b) in enumerate(zip(features, nomes, strict=True)) if a != b]
        raise ValueError(f"features fora da ordem do modelo (posicao, declarado, modelo): {dif[:5]}")
    if len(set(features)) != len(features):
        raise ValueError("features com nome repetido")
    return features


def _arvore(info: dict) -> dict:
    """Uma arvore do `dump_model()` em arrays paralelos, com os indices do C++."""
    n_folhas = int(info["num_leaves"])
    raiz = info["tree_structure"]
    if n_folhas == 1:
        # arvore degenerada: o dump traz so {"leaf_value": v}
        return {"feature": [], "limiar": [], "esquerda": [], "direita": [],
                "padrao_esquerda": [], "ausente": [], "decisao": [],
                "folhas": [float(raiz["leaf_value"])]}

    n_nos = n_folhas - 1
    arv: dict[str, list] = {k: [None] * n_nos for k in (
        "feature", "limiar", "esquerda", "direita", "padrao_esquerda", "ausente", "decisao")}
    folhas: list[float | None] = [None] * n_folhas

    def filho(no: dict) -> int:
        if "split_index" in no:
            return int(no["split_index"])
        if "leaf_coeff" in no:
            raise NotImplementedError("linear_tree=True nao e suportado pelo avaliador JS")
        i = int(no["leaf_index"])
        folhas[i] = float(no["leaf_value"])
        return ~i  # convencao do LightGBM: folha i vira -(i+1)

    pilha = [raiz]  # so nos internos entram na pilha; folhas sao gravadas por filho()
    while pilha:
        no = pilha.pop()
        i = int(no["split_index"])
        arv["feature"][i] = int(no["split_feature"])
        arv["padrao_esquerda"][i] = 1 if no["default_left"] else 0
        arv["ausente"][i] = AUSENTE.index(no["missing_type"])
        arv["decisao"][i] = DECISAO.index(no["decision_type"])
        if no["decision_type"] == "==":
            cats = sorted({int(c) for c in str(no["threshold"]).split("||") if c != ""})
            arv["limiar"][i] = "||".join(str(c) for c in cats)
        else:
            arv["limiar"][i] = float(no["threshold"])
        arv["esquerda"][i] = filho(no["left_child"])
        arv["direita"][i] = filho(no["right_child"])
        for lado in ("left_child", "right_child"):
            if "split_index" in no[lado]:
                pilha.append(no[lado])

    faltando = [k for k, v in arv.items() if any(x is None for x in v)]
    if faltando or any(v is None for v in folhas):
        raise ValueError(f"arvore {info.get('tree_index')}: indices incompletos no dump ({faltando})")
    arv["folhas"] = folhas
    return arv


def _validar_extras(extras: Mapping[str, Any], features: list[str]) -> None:
    """Confere o contrato do simulador: cada feature tem de ter origem conhecida."""
    colisao = _RESERVADAS & set(extras)
    if colisao:
        raise ValueError(f"extras nao pode sobrescrever {sorted(colisao)}")

    conhecidas = set(features)
    entradas = extras.get("entradas_usuario", [])
    for e in entradas:
        for k in ("chave", "rotulo", "tipo", "padrao"):
            if k not in e:
                raise ValueError(f"entrada_usuario sem {k!r}: {e}")
        if e["tipo"] not in _TIPOS_ENTRADA:
            raise ValueError(f"entrada {e['chave']!r}: tipo {e['tipo']!r} fora de {_TIPOS_ENTRADA}")
        if e["tipo"] == "categoria" and not e.get("opcoes"):
            raise ValueError(f"entrada {e['chave']!r}: categoria sem 'opcoes'")
        if e["chave"] not in conhecidas:
            raise ValueError(f"entrada {e['chave']!r} nao e feature do modelo")

    ponto = extras.get("features_ponto") or []  # [] ou ausente: localizacao toda da celula
    ponto_nomes = list(ponto) if not isinstance(ponto, Mapping) else list(ponto.keys())
    local = list(extras.get("features_local") or [])
    fixas = dict(extras.get("features_fixas") or {})
    for nome in [*local, *ponto_nomes, *fixas]:
        if nome not in conhecidas:
            raise ValueError(f"{nome!r} declarada em extras nao e feature do modelo")

    if entradas or local or ponto_nomes or fixas:
        origem = {e["chave"] for e in entradas} | set(local) | set(ponto_nomes) | set(fixas)
        sem_origem = [f for f in features if f not in origem]
        if sem_origem:
            raise ValueError(
                "features sem origem no simulador (declare em entradas_usuario, "
                f"features_local, features_ponto ou features_fixas): {sem_origem}")

    intervalo = extras.get("intervalo")
    if intervalo is not None:
        for k in ("nivel", "q_inf", "q_sup"):
            if k not in intervalo:
                raise ValueError(f"intervalo sem {k!r}")
        _conferir_par(intervalo, "intervalo")

    # intervalo conformal por grupo (ex.: tipo de acomodacao): o global cobre 80% no
    # total, mas nao em cada grupo. Chave do grupo = String(Number(valor)) no JS.
    por_grupo = extras.get("intervalo_por_grupo")
    if por_grupo is not None:
        if por_grupo.get("chave") not in conhecidas:
            raise ValueError(f"intervalo_por_grupo: chave {por_grupo.get('chave')!r} nao e feature")
        grupos = por_grupo.get("grupos") or {}
        if not grupos:
            raise ValueError("intervalo_por_grupo sem grupos")
        for g, par in grupos.items():
            if not _grupo_canonico(g):
                raise ValueError(f"intervalo_por_grupo: grupo {g!r} tem de ser inteiro em texto ('0', '1'...)")
            _conferir_par(par, f"intervalo_por_grupo[{g}]")

    chave_tipo = extras.get("chave_tipo")
    if chave_tipo is not None:
        tipos = {e["chave"]: e["tipo"] for e in entradas}
        if tipos.get(chave_tipo) != "categoria":
            raise ValueError(f"chave_tipo {chave_tipo!r} tem de ser uma entrada do tipo 'categoria'")

    teto = extras.get("teto")
    if teto is not None and not (isinstance(teto, int | float) and math.isfinite(teto) and teto > 0):
        raise ValueError(f"teto invalido: {teto!r}")


def _conferir_par(par: Mapping[str, Any], nome: str) -> None:
    for k in ("q_inf", "q_sup"):
        v = par.get(k)
        if not isinstance(v, int | float) or not math.isfinite(v):
            raise ValueError(f"{nome}: {k} ausente ou nao finito")
    if not par["q_inf"] <= par["q_sup"]:
        raise ValueError(f"{nome}: q_inf > q_sup")


def _grupo_canonico(g: Any) -> bool:
    """'0', '1', '-2' — o texto que `String(Number(v))` produz para um codigo inteiro."""
    try:
        return str(int(str(g))) == str(g)
    except ValueError:
        return False


def _escrever(obj: dict, caminho: Path) -> None:
    """JSON estrito (sem NaN/Infinity, que o `JSON.parse` do navegador rejeita)."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
        encoding="utf-8")


def exportar_modelo(booster, caminho: str | Path, *, features: Sequence[str],
                    transformacao: str, extras: Mapping[str, Any] | None = None,
                    init_score: float = 0.0) -> dict:
    """Converte um `lightgbm.Booster` no JSON que `site/assets/modelo.js` avalia.

    `transformacao` e o que leva o escore bruto a unidade publicada: "expm1" para
    regressor treinado em log1p(preco), "exp" para poisson/tweedie/gamma (ou alvo
    em log), "sigmoide" para binario, "identidade" para o resto. E conferida contra
    o objetivo do modelo. `init_score` so e necessario se o treino usou
    `Dataset(init_score=...)` constante — o `boost_from_average` ja esta na
    primeira arvore. `extras` e mesclado no topo (entradas_usuario, features_local,
    features_ponto, features_fixas, intervalo, metricas...).

    Devolve o dicionario gravado (ja passado pelo texto JSON, como o navegador o ve).
    """
    if transformacao not in TRANSFORMACOES:
        raise ValueError(f"transformacao {transformacao!r} fora de {TRANSFORMACOES}")
    dump = booster.dump_model()
    if int(dump.get("num_tree_per_iteration", 1)) != 1 or int(dump.get("num_class", 1)) != 1:
        raise NotImplementedError("modelo multiclasse nao e suportado pelo avaliador JS")
    if dump.get("average_output"):
        raise NotImplementedError("boosting='rf' (average_output) nao e suportado pelo avaliador JS")
    objetivo, nativa, escala = _objetivo(dump)
    if transformacao not in _COMPATIVEIS[nativa]:
        raise ValueError(
            f"transformacao {transformacao!r} incoerente com o objetivo {objetivo!r} "
            f"(o LightGBM ja aplica {nativa!r}; aceitas: {_COMPATIVEIS[nativa]})")
    features = _conferir_features(booster, features)
    if not math.isfinite(init_score):
        raise ValueError("init_score nao finito")

    modelo: dict[str, Any] = {
        "formato": FORMATO,
        "gerado_por": "airbnb.produto.modelo_js.exportar_modelo",
        "lightgbm": _versao_lightgbm(),
        "objetivo": objetivo,
        "features": features,
        "transformacao": transformacao,
    }
    if transformacao == "sigmoide":
        modelo["sigmoide"] = escala
    modelo["init_score"] = float(init_score)
    arvores = [_arvore(t) for t in dump["tree_info"]]
    modelo["n_arvores"] = len(arvores)
    modelo["codigos"] = {"ausente": list(AUSENTE), "decisao": list(DECISAO)}
    modelo["arvores"] = arvores
    if extras:
        _validar_extras(extras, features)
        modelo.update(extras)

    _escrever(modelo, Path(caminho))
    # ida e volta pelo TEXTO: e exatamente o que o navegador recebe
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def _versao_lightgbm() -> str:
    import lightgbm

    return str(lightgbm.__version__)


# --------------------------------------------------------------------------
# referencia em Python (mesma logica do JavaScript, so com o JSON)
# --------------------------------------------------------------------------

def _preparar(modelo: dict) -> list[tuple[dict, list[frozenset[int] | None]]]:
    return [(a, [frozenset(int(c) for c in str(lim).split("||") if c != "") if d == 1 else None
                 for lim, d in zip(a["limiar"], a["decisao"], strict=True)])
            for a in modelo["arvores"]]


def _folha(arv: dict, cats: list, x: list[float]) -> int:
    if not arv["feature"]:
        return 0
    no = 0
    while no >= 0:
        v = x[arv["feature"][no]]
        if arv["decisao"][no] == 1:
            if math.isnan(v) or math.trunc(v) < 0:
                no = arv["direita"][no]
            else:
                no = arv["esquerda"][no] if math.trunc(v) in cats[no] else arv["direita"][no]
            continue
        m = arv["ausente"][no]
        if math.isnan(v) and m != 2:
            v = 0.0
        if (m == 1 and -LIMIAR_ZERO <= v <= LIMIAR_ZERO) or (m == 2 and math.isnan(v)):
            no = arv["esquerda"][no] if arv["padrao_esquerda"][no] else arv["direita"][no]
        else:
            no = arv["esquerda"][no] if v <= arv["limiar"][no] else arv["direita"][no]
    return ~no


def _linha(modelo: dict, x) -> list[float]:
    feats = modelo["features"]
    if isinstance(x, Mapping):
        desconhecidas = set(x) - set(feats)
        if desconhecidas:
            raise KeyError(f"chaves que nao sao features: {sorted(desconhecidas)}")
        valores = [x.get(f) for f in feats]
    else:
        valores = list(x)
        if len(valores) != len(feats):
            raise ValueError(f"esperava {len(feats)} valores, recebeu {len(valores)}")
    linha = []
    for v in valores:
        v = math.nan if v is None else float(v)
        linha.append(0.0 if abs(v) <= LIMIAR_ZERO else v)  # NaN falha a comparacao e fica
    return linha


def prever_bruto_json(modelo: dict, x, _cache: dict | None = None) -> float:
    """Escore bruto calculado SO com o JSON — a mesma logica de `modelo.js`."""
    prep = _cache["prep"] if _cache and "prep" in _cache else _preparar(modelo)
    if _cache is not None:
        _cache["prep"] = prep
    linha = _linha(modelo, x)
    s = 0.0
    for arv, cats in prep:
        s += arv["folhas"][_folha(arv, cats, linha)]
    return s + modelo.get("init_score", 0.0)


def transformar(modelo: dict, bruto: float) -> float:
    """Leva o escore bruto a unidade publicada (mesma funcao do JavaScript)."""
    t = modelo["transformacao"]
    if t == "identidade":
        return bruto
    if t == "exp":
        return math.exp(bruto)
    if t == "expm1":
        return math.expm1(bruto)
    if t == "sigmoide":
        return 1.0 / (1.0 + math.exp(-modelo.get("sigmoide", 1.0) * bruto))
    raise ValueError(f"transformacao desconhecida: {t!r}")


def prever_json(modelo: dict, x) -> float:
    return transformar(modelo, prever_bruto_json(modelo, x))


# --------------------------------------------------------------------------
# entrada como o LightGBM a ve
# --------------------------------------------------------------------------

def matriz_lightgbm(booster, X) -> np.ndarray:
    """Matriz float64 com os valores que o LightGBM usa ao prever `X`.

    DataFrame com coluna `category` e remapeado para as categorias do TREINO
    (`booster.pandas_categorical`), como faz `lightgbm.basic._data_from_pandas`:
    o codigo que o navegador recebe tem de ser o codigo que a arvore conhece.
    Categoria ausente ou desconhecida vira NaN.
    """
    if isinstance(X, pd.DataFrame):
        df = X.copy(deep=False)
        cat_cols = [c for c, dt in zip(df.columns, df.dtypes, strict=True)
                    if isinstance(dt, pd.CategoricalDtype)]
        categorias = booster.pandas_categorical or []
        if cat_cols and len(cat_cols) != len(categorias):
            raise ValueError("colunas categoricas de X nao batem com as do treino")
        for col, cats in zip(cat_cols, categorias, strict=False):
            serie = df[col]
            if list(serie.cat.categories) != list(cats):
                serie = serie.cat.set_categories(cats)
            codigos = serie.cat.codes.to_numpy(dtype="float64")
            codigos[codigos == -1] = np.nan
            df[col] = codigos
        m = df.to_numpy(dtype="float64", na_value=np.nan)
    else:
        m = np.array(X, dtype="float64")
    if m.ndim != 2:
        raise ValueError("X tem de ser bidimensional")
    if np.isinf(m).any():
        raise ValueError("X contem +-inf: JSON nao representa infinito")
    return m


def _prever_lightgbm(booster, modelo: dict, m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(escore bruto, predicao na unidade publicada), calculados pelo LightGBM."""
    _, nativa, escala = _objetivo({"objective": modelo["objetivo"]})
    init = float(modelo.get("init_score", 0.0))
    bruto = booster.predict(m, raw_score=True) + init
    t = modelo["transformacao"]
    if nativa == "identidade":
        base = booster.predict(m) + init  # identidade: o LightGBM devolve o bruto
        pred = {"identidade": base, "exp": np.exp(base), "expm1": np.expm1(base)}[t]
    elif init == 0.0:
        pred = booster.predict(m)  # conversao do proprio LightGBM (exp ou sigmoide)
    elif nativa == "exp":
        pred = np.exp(bruto)
    else:
        pred = 1.0 / (1.0 + np.exp(-escala * bruto))
    return np.asarray(bruto, dtype="float64"), np.asarray(pred, dtype="float64")


def _carregar(modelo: dict | str | Path) -> dict:
    if isinstance(modelo, Mapping):
        return dict(modelo)
    return json.loads(Path(modelo).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# casos de paridade (lidos por tests/paridade_js.mjs)
# --------------------------------------------------------------------------

def _casos_extremos(m: np.ndarray, categoricas: set[int], rng: np.random.Generator) -> np.ndarray:
    """Linhas que exercitam as bordas da semantica, uma a uma."""
    n_f = m.shape[1]
    base = m[rng.integers(len(m))].copy()
    linhas = [np.full(n_f, np.nan), np.zeros(n_f)]
    minusculos = np.where(np.arange(n_f) % 2 == 0, 1e-40, -1e-40)  # |x| <= 1e-35f vira zero
    linhas.append(minusculos)
    linhas.append(np.full(n_f, 1e30))
    linhas.append(np.full(n_f, -1e30))
    for j in sorted(categoricas):
        for v in (-1.0, -3.0, 2.7, 1e6):  # negativo -> direita; fracao trunca; desconhecida
            r = base.copy()
            r[j] = v
            linhas.append(r)
    return np.vstack(linhas)


def gerar_casos_paridade(booster, X, caminho: str | Path, *, modelo: dict | str | Path,
                         n: int = 500, semente: int = 42) -> dict:
    """Grava entradas e saidas do PROPRIO LightGBM para o teste em Node conferir.

    `modelo` e o JSON exportado (dict devolvido por `exportar_modelo` ou caminho):
    dele vem a ordem das features, a transformacao e o init_score — uma fonte so.

    Sorteia linhas de `X` e forca, de proposito, NaN e zero em parte delas (sao os
    caminhos que mais quebram sem ninguem ver), mais linhas extremas: tudo NaN,
    tudo zero, |x| < 1e-35, +-1e30 e, nas categoricas, codigo negativo,
    fracionario e desconhecido. NaN sai como `null`.
    """
    mod = _carregar(modelo)
    features = _conferir_features(booster, mod["features"])
    m = matriz_lightgbm(booster, X)
    if m.shape[1] != len(features):
        raise ValueError(f"X tem {m.shape[1]} colunas; o modelo, {len(features)}")
    rng = np.random.default_rng(semente)
    categoricas = {f for a in mod["arvores"]
                   for f, d in zip(a["feature"], a["decisao"], strict=True) if d == 1}

    extremos = _casos_extremos(m, categoricas, rng)
    n_base = max(n - len(extremos), 1)
    idx = rng.choice(len(m), size=min(n_base, len(m)), replace=False)
    amostra = m[idx].copy()
    n_f = amostra.shape[1]
    for valor, fracao in ((np.nan, 0.15), (0.0, 0.15)):
        linhas = rng.choice(len(amostra), size=max(int(len(amostra) * fracao), 1), replace=False)
        for i in linhas:
            cols = rng.choice(n_f, size=int(rng.integers(1, min(3, n_f) + 1)), replace=False)
            amostra[i, cols] = valor
    entradas = np.vstack([amostra, extremos])

    bruto, pred = _prever_lightgbm(booster, mod, entradas)
    casos = [{"x": [None if math.isnan(v) else float(v) for v in linha],
              "bruto": float(b), "pred": float(p)}
             for linha, b, p in zip(entradas, bruto, pred, strict=True)]
    resumo = {
        "n": len(casos),
        "com_nan": int(np.isnan(entradas).any(axis=1).sum()),
        "com_zero": int((entradas == 0.0).any(axis=1).sum()),
    }
    _escrever({
        "formato": FORMATO_CASOS,
        "gerado_por": "airbnb.produto.modelo_js.gerar_casos_paridade",
        "lightgbm": _versao_lightgbm(),
        "features": features,
        "transformacao": mod["transformacao"],
        "tolerancia_bruto": TOLERANCIA_BRUTO,
        "resumo": resumo,
        "casos": casos,
    }, Path(caminho))
    return resumo


def verificar_export(booster, modelo: dict | str | Path, X, *, n: int = 1000,
                     semente: int = 42) -> dict:
    """O JSON exportado reproduz o LightGBM? Referencia em Python, sem Node.

    Mesmo papel de `verificar_paridade` do projeto anterior: se falhar, o export
    esta errado — antes de o JavaScript entrar na conta.
    """
    mod = _carregar(modelo)
    m = matriz_lightgbm(booster, X)
    rng = np.random.default_rng(semente)
    m = m[rng.choice(len(m), size=min(n, len(m)), replace=False)]
    bruto, _ = _prever_lightgbm(booster, mod, m)
    cache: dict = {}
    ref = np.array([prever_bruto_json(mod, linha.tolist(), cache) for linha in m])
    dif = np.abs(ref - bruto)
    erro = float(dif.max()) if len(dif) else 0.0
    return {"n": int(len(m)), "erro_max": erro, "aprovado": bool(erro <= TOLERANCIA_BRUTO)}
