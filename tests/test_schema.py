"""Testes do contrato de dados (schema.py) e da ingestao (ingest/baixar.py).

O teste mais importante do arquivo e `test_nenhuma_coluna_pessoal_em_saida_alguma`:
e a trava do invariante 9 na origem — se alguem acrescentar `host_name` a um
parquet da silver, isto quebra antes de o dado chegar ao site.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from airbnb import config, schema
from airbnb.ingest import baixar
from airbnb.schema import (
    AMENIDADES,
    DETALHADO_2026,
    ESQUEMA,
    KAGGLE_2019,
    PROIBIDAS_NA_SILVER,
    RESUMO_2026,
    SAIDAS,
)

DTYPES_ACEITOS = {"int64", "Int64", "float64", "bool", "boolean", "str", "category", "datetime64[ns]"}


# --- coerencia do contrato ---------------------------------------------------------------


def test_todo_dtype_e_conhecido_e_categoria_tem_dominio():
    for nome, c in ESQUEMA.items():
        assert c.dtype in DTYPES_ACEITOS, nome
        if c.dtype == "category":
            assert c.dominio, f"{nome}: categoria sem dominio"
        if c.minimo is not None and c.maximo is not None:
            assert c.minimo <= c.maximo, nome


def test_toda_coluna_da_silver_esta_em_alguma_saida_e_tem_descricao():
    for nome, c in ESQUEMA.items():
        assert c.saidas and set(c.saidas) <= set(SAIDAS), nome
        assert len(c.descricao) > 10 and c.origem, nome


def test_derivada_e_snake_case_ascii():
    """Invariante 1: derivada e pt-BR snake_case (sem acento no identificador)."""
    for nome, c in ESQUEMA.items():
        if c.origem.startswith("derivada"):
            assert re.fullmatch(r"[a-z0-9_]+", nome), nome


def test_coluna_de_origem_mantem_o_nome_da_origem():
    """Coluna que nao e derivada tem de existir com o MESMO nome em algum arquivo bruto."""
    nomes_brutos = {b.nome for b in schema.BRUTAS.values()}
    for nome, c in ESQUEMA.items():
        if not c.origem.startswith("derivada") and nome != schema.COL_PRECO:
            assert nome in nomes_brutos, nome


def test_constantes_col_apontam_para_colunas_do_contrato():
    for attr in dir(schema):
        if attr.startswith("COL_") and isinstance(getattr(schema, attr), str):
            assert getattr(schema, attr) in ESQUEMA, attr


def test_nenhuma_coluna_pessoal_em_saida_alguma():
    for saida in SAIDAS:
        assert not PROIBIDAS_NA_SILVER & set(schema.colunas(saida)), saida
    for proibida in ("host_name", "host_about", "host_picture_url", "listing_url", "description"):
        assert proibida in PROIBIDAS_NA_SILVER


def test_ids_e_titulo_sao_marcados_pessoais():
    """Ficam na silver (a analise precisa), mas nunca sao publicados."""
    for nome in (schema.COL_ID, schema.COL_HOST_ID, schema.COL_NOME):
        assert ESQUEMA[nome].pessoal, nome


def test_brutas_cobrem_os_tres_arquivos():
    assert len(schema.brutas(KAGGLE_2019)) == 16
    assert len(schema.brutas(RESUMO_2026)) == 19
    assert len(schema.brutas(DETALHADO_2026)) == 90
    for b in schema.BRUTAS.values():
        assert b.tratamento in {"mantida", "renomeada", "derivada", "descartada", "referencia"}
        if b.tratamento == "descartada":
            assert b.motivo, f"{b.arquivo}.{b.nome}: descarte sem motivo"


def test_resumo_so_tem_colunas_comuns():
    assert set(schema.colunas(schema.SRESUMO)) <= set(schema.colunas(schema.S2019))


# --- validar ---------------------------------------------------------------------------------


def _frame_resumo_valido(n: int = 3) -> pd.DataFrame:
    dados = {
        "snapshot": pd.Categorical(["2019"] * n, categories=schema.SNAPSHOTS),
        "id": pd.Series(range(1, n + 1), dtype="int64"),
        "host_id": pd.Series([7] * n, dtype="int64"),
        "neighbourhood_group": pd.Categorical(["Manhattan"] * n, categories=config.DISTRITOS),
        "neighbourhood": pd.Series(["Harlem"] * n, dtype="str"),
        "latitude": [40.81] * n, "longitude": [-73.94] * n,
        "room_type": pd.Categorical(["Private room"] * n, categories=schema.ROOM_TYPES),
        "preco": [100.0] * n,
        "minimum_nights": pd.Series([2] * n, dtype="int64"),
        "number_of_reviews": pd.Series([1] * n, dtype="int64"),
        "last_review": pd.to_datetime(["2019-06-01"] * n).astype("datetime64[ns]"),
        "reviews_per_month": [0.5] * n,
        "calculated_host_listings_count": pd.Series([1] * n, dtype="int64"),
        "availability_365": pd.Series([100] * n, dtype="int64"),
        "preco_valido": [True] * n, "min30": [False] * n, "host_multi": [False] * n,
        "h3_r9": pd.Series(["89"] * n, dtype="str"), "h3_r8": pd.Series(["88"] * n, dtype="str"),
        "h3_r6": pd.Series(["86"] * n, dtype="str"),
        "ocupacao_modelo": [0.1] * n,
        "dias_desde_ultima_avaliacao": pd.Series([37] * n, dtype="Int64"),
    }
    return pd.DataFrame(dados)[schema.colunas(schema.SRESUMO)]


def test_validar_aceita_frame_conforme():
    assert schema.validar(_frame_resumo_valido(), schema.SRESUMO) == []


def test_validar_pega_coluna_faltando_dtype_dominio_nulo_e_pessoal():
    df = _frame_resumo_valido()
    assert any("faltam" in e for e in schema.validar(df.drop(columns=["preco"]), schema.SRESUMO))

    ruim = df.copy()
    ruim["minimum_nights"] = ruim["minimum_nights"].astype("float64")
    assert any("dtype" in e for e in schema.validar(ruim, schema.SRESUMO))

    ruim = df.copy()
    ruim["availability_365"] = pd.Series([400, 1, 2], dtype="int64")
    assert any("> 365" in e for e in schema.validar(ruim, schema.SRESUMO))

    ruim = df.copy()
    ruim["latitude"] = [40.81, None, 40.8]
    assert any("nulos" in e for e in schema.validar(ruim, schema.SRESUMO))

    ruim = df.copy()
    ruim["host_name"] = "Ana"
    assert any("pessoal" in e for e in schema.validar(ruim, schema.SRESUMO))


# --- amenidades: a regex tem de separar o que a grafia do Airbnb mistura -----------------------


@pytest.mark.parametrize(("item", "flag", "esperado"), [
    ("Wifi", "amen_wifi", True),
    ("Fast wifi – 304 Mbps", "amen_wifi", True),
    ("Kitchen", "amen_cozinha", True),
    ("Kitchenette", "amen_cozinha", True),
    ("KitchenAid refrigerator", "amen_cozinha", False),
    ("Outdoor kitchen", "amen_cozinha", False),
    ("Window AC unit", "amen_ar_condicionado", True),
    ("Hair conditioner", "amen_ar_condicionado", False),
    ("Free washer – In unit", "amen_lavadora", True),
    ("Dishwasher", "amen_lavadora", False),
    ("Dishwasher", "amen_lava_loucas", True),
    ("Paid dryer – In building", "amen_secadora", True),
    ("Hair dryer", "amen_secadora", False),
    ("Shared gym in building", "amen_academia", True),
    ("Shared gym nearby", "amen_academia", False),
    ("Free parking on premises", "amen_estacionamento", True),
    ("Free street parking", "amen_estacionamento", False),
    ("Shared outdoor pool - available seasonally", "amen_piscina", True),
    ("Pool table", "amen_piscina", False),
    ("Pool view", "amen_piscina", False),
    ("Building staff", "amen_porteiro", True),
    ("Portable heater", "amen_aquecimento", True),
    ("Movie theater", "amen_aquecimento", False),
    ("55 inch HDTV with Fire TV", "amen_tv", True),
    ("Private patio or balcony", "amen_varanda_patio", True),
])
def test_regex_de_amenidade(item, flag, esperado):
    padrao = re.compile(AMENIDADES[flag][0], re.IGNORECASE)
    assert bool(padrao.search(item)) is esperado


# --- dicionario gerado ------------------------------------------------------------------------------


def test_dicionario_em_docs_esta_sincronizado_com_o_schema():
    """docs/dicionario-dados.md e SAIDA do schema; editado a mao, diverge."""
    arq = config.DOCS / "dicionario-dados.md"
    if not arq.exists():
        pytest.skip("dicionario ainda nao gerado (python -m airbnb.schema --escrever)")
    assert arq.read_text(encoding="utf-8") == schema.dicionario_markdown(), \
        "rode: python -m airbnb.schema --escrever"


# --- ingestao: conferir o hash, nao so registrar --------------------------------------------------


def _fonte(tmp_path: Path) -> baixar.Fonte:
    return baixar.Fonte("teste", tmp_path / "arquivo.csv", "https://exemplo.invalid/a.csv",
                        "CC0", "arquivo de teste")


def test_conferir_detecta_arquivo_trocado(tmp_path):
    f = _fonte(tmp_path)
    assert baixar.conferir(f.destino, None)["estado"] == "ausente"
    f.destino.write_bytes(b"conteudo original")
    assert baixar.conferir(f.destino, None)["estado"] == "sem-referencia"
    reg = baixar.registro(f, f.destino, "2026-09-18")
    assert len(reg["sha256"]) == 64 and reg["bytes"] == 17
    assert baixar.conferir(f.destino, reg)["estado"] == "ok"
    f.destino.write_bytes(b"conteudo TROCADO!")  # mesmo tamanho, outro conteudo
    assert baixar.conferir(f.destino, reg)["estado"] == "hash-errado"
    f.destino.write_bytes(b"truncado")
    assert baixar.conferir(f.destino, reg)["estado"] == "tamanho-errado"


def test_processar_aborta_se_a_fonte_mudou_e_nao_reescreve_o_manifesto(tmp_path):
    """Registrar sem comparar prova nada: a fonte trocada tem de FALHAR alto."""
    f = _fonte(tmp_path)
    f.destino.write_bytes(b"versao 1")
    man = {"arquivos": {}}
    _, ok = baixar.processar(f, man, verificar=False, forcar=False, aceitar_nova=False, kaggle=None)
    assert ok and man["arquivos"]["teste"]["bytes"] == 8
    registrado = dict(man["arquivos"]["teste"])

    f.destino.write_bytes(b"versao 2")
    linha, ok = baixar.processar(f, man, verificar=True, forcar=False, aceitar_nova=False, kaggle=None)
    assert not ok and "A FONTE MUDOU" in linha
    assert man["arquivos"]["teste"] == registrado, "manifesto nao pode ser sobrescrito"

    _, ok = baixar.processar(f, man, verificar=False, forcar=False, aceitar_nova=True, kaggle=None)
    assert ok and man["arquivos"]["teste"]["sha256"] != registrado["sha256"]


def test_manifesto_ilegivel_e_erro_nao_ausencia(tmp_path):
    arq = tmp_path / "_manifesto.json"
    arq.write_text("{ nao e json", encoding="utf-8")
    with pytest.raises(SystemExit, match="ilegivel"):
        baixar.ler_manifesto(arq)


def test_kaggle_sem_arquivo_nem_credencial_explica_onde_baixar(tmp_path, monkeypatch):
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)
    monkeypatch.setattr(baixar.Path, "home", lambda: tmp_path)
    with pytest.raises(SystemExit, match="kaggle.com/datasets"):
        baixar.obter_kaggle(tmp_path / "AB_NYC_2019.csv", None)


def test_kaggle_aceita_pasta_e_zip(tmp_path):
    import zipfile

    pasta = tmp_path / "AB_NYC_2019.csv"  # a copia do usuario e uma PASTA com esse nome
    pasta.mkdir()
    (pasta / "AB_NYC_2019.csv").write_text("id\n1\n", encoding="utf-8")
    destino = tmp_path / "raw" / "AB_NYC_2019.csv"
    baixar.obter_kaggle(destino, pasta)
    assert destino.read_text(encoding="utf-8") == "id\n1\n"

    zp = tmp_path / "archive.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("AB_NYC_2019.csv", "id\n2\n")
    destino.unlink()
    baixar.obter_kaggle(destino, zp)
    assert destino.read_text(encoding="utf-8") == "id\n2\n"


# --- dado real ----------------------------------------------------------------------------------------


@pytest.mark.dados
def test_cabecalho_real_bate_com_as_colunas_brutas_do_schema():
    for arquivo, rel in schema.ARQUIVOS_ORIGEM.items():
        caminho = config.RAIZ / rel
        if not caminho.exists():
            pytest.skip(f"{rel} ausente")
        cab = list(pd.read_csv(caminho, nrows=0).columns)
        assert cab == [b.nome for b in schema.brutas(arquivo)], arquivo


@pytest.mark.dados
def test_manifesto_do_repositorio_registra_todas_as_fontes():
    caminho = baixar.MANIFESTO
    if not caminho.exists():
        pytest.skip("ingestao nao executada")
    arqs = json.loads(caminho.read_text(encoding="utf-8"))["arquivos"]
    assert {f.chave for f in baixar.FONTES} == set(arqs)
    for chave, info in arqs.items():
        assert len(info["sha256"]) == 64 and info["bytes"] > 0, chave
        assert info["licenca"] and info["acesso"] and info["url"].startswith("https://"), chave
